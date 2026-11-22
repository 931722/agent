from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from app.domain import DomainError, add_order, assert_invariants
from app.store import Store
from app.scheduler import fifo_schedule, order_risks
from app.config import Settings
from app.agent import run_agent, DemoPlanner, OllamaPlanner
from app.tools import ToolRegistry
from app.main import create_app


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / 'kitchen.sqlite3')


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(mode='demo', db_path=str(tmp_path / 'api.sqlite3'))))


def proposal(store):
    return store.propose(store.snapshot()['version'])


def test_fifo_selects_oldest_and_independent_resources(store):
    p = proposal(store)
    assert [a['order_id'] for a in p['assignments']] == ['O001', 'O002']
    assert len({a['chef_id'] for a in p['assignments']}) == 2
    assert len({a['station_id'] for a in p['assignments']}) == 2
    assert all(t['status'] not in ('RESERVED', 'RUNNING') for t in store.snapshot()['tasks'].values())


def test_dependency_cannot_start_early(store):
    with pytest.raises(DomainError, match='RESERVED'):
        store.event('e1', 'start', 'O001-1-1-plate')
    assert store.snapshot()['tasks']['O001-1-1-plate']['status'] == 'WAITING'


def test_shared_chef_cannot_double_book(store):
    def change(s):
        s['chefs']['chef-a']['skills'] = ['wok', 'soup', 'pass']
        s['chefs']['chef-b']['available'] = False
        return {}
    store.mutate(change)
    p = proposal(store)
    assert len(p['assignments']) == 1
    store.confirm(p['proposal_id'])
    assert_invariants(store.snapshot())


def test_blocked_oldest_does_not_block_other_station(store):
    store.event('off', 'station_offline', 'wok-1')
    p = proposal(store)
    assert [a['order_id'] for a in p['assignments']] == ['O002']
    assert any(b['order_id'] == 'O001' for b in p['blocked'])


def test_stale_proposal_rejected_without_mutating(store):
    p = proposal(store)
    store.event('off', 'station_offline', 'wok-1')
    with pytest.raises(DomainError) as err:
        store.confirm(p['proposal_id'])
    assert err.value.code == 'STALE_STATE'
    assert not any(t['status'] == 'RESERVED' for t in store.snapshot()['tasks'].values())


def test_confirm_is_idempotent(store):
    p = proposal(store); store.confirm(p['proposal_id'])
    version = store.snapshot()['version']
    assert store.confirm(p['proposal_id'])['already_confirmed']
    assert store.snapshot()['version'] == version


def test_two_concurrent_proposals_only_one_reserves(store):
    p1, p2 = proposal(store), proposal(store)
    def confirm(pid):
        try: return store.confirm(pid)['ok']
        except DomainError: return False
    with ThreadPoolExecutor(max_workers=2) as ex:
        outcomes = list(ex.map(confirm, [p1['proposal_id'], p2['proposal_id']]))
    assert sorted(outcomes) == [False, True]
    assert_invariants(store.snapshot())


def test_complete_unlocks_successor_and_releases_resource(store):
    p = proposal(store); store.confirm(p['proposal_id'])
    tid = 'O001-1-1-cook'
    store.event('start', 'start', tid);store.event('done', 'complete', tid)
    s = store.snapshot()
    assert s['tasks']['O001-1-1-plate']['status'] == 'READY'
    assert s['tasks'][tid]['status'] == 'DONE'
    assert any(a['chef_id'] == 'chef-a' for a in proposal(store)['assignments'])


def test_event_duplicate_does_not_reapply(store):
    p = proposal(store);store.confirm(p['proposal_id'])
    tid = 'O001-1-1-cook';store.event('start', 'start', tid)
    original = store.event('finish', 'complete', tid);duplicate = store.event('finish', 'complete', tid)
    assert duplicate['duplicate']
    assert original['state_version'] == duplicate['state_version'] == store.snapshot()['version']


def test_event_id_cannot_be_reused_for_different_payload(store):
    store.event('same', 'station_offline', 'wok-1')
    with pytest.raises(DomainError) as err:store.event('same', 'station_online', 'wok-1')
    assert err.value.code == 'EVENT_ID_CONFLICT'


def test_running_task_not_auto_completed_by_clock(store):
    p=proposal(store);store.confirm(p['proposal_id']);store.event('s', 'start', 'O001-1-1-cook')
    store.mutate(lambda s: (s.update(clock=100) or {}))
    assert store.snapshot()['tasks']['O001-1-1-cook']['status'] == 'RUNNING'
    assert not any(a['chef_id'] == 'chef-a' for a in fifo_schedule(store.snapshot())['assignments'])
    assert '確認現場' in order_risks(store.snapshot(), 'O001')['orders'][0]['status']


def test_station_fault_during_active_work_requires_review(store):
    p=proposal(store);store.confirm(p['proposal_id'])
    with pytest.raises(DomainError) as e:store.event('off','station_offline','wok-1')
    assert e.value.code == 'ACTIVE_WORK_REQUIRES_REVIEW'
    assert store.snapshot()['stations']['wok-1']['available']


def test_no_feasible_tasks_is_explicit(store):
    store.event('a','station_offline','wok-1');store.event('b','station_offline','soup-1')
    result=proposal(store)
    assert not result['ok'] and result['error']['code'] == 'NO_FEASIBLE_TASK'
    assert result['blocked']


def test_state_survives_restart(store):
    store.event('off','station_offline','wok-1')
    restored=Store(store.path)
    assert restored.snapshot()==store.snapshot()


def test_invalid_order_rolls_back_all_changes(store):
    before=store.snapshot()
    with pytest.raises(DomainError):
        store.mutate(lambda s:add_order(s,'BAD',[{'dish':'fried_rice','quantity':1},{'dish':'unknown','quantity':1}],15))
    assert store.snapshot()==before


def test_model_cannot_call_write_tool(store):
    result=ToolRegistry(store).call('confirm_assignment', {'proposal_id':'x'})
    assert result['error']['code']=='UNKNOWN_TOOL'
    assert store.snapshot()['version']==1


@pytest.mark.parametrize('args',[{}, {'state_version':'1'}, {'state_version':True}, {'state_version':1,'strategy':'random'}, {'state_version':1,'extra':'x'}, None])
def test_tool_argument_validation(store,args):
    result=ToolRegistry(store).call('propose_schedule',args)
    assert result['error']['code']=='INVALID_ARGUMENTS'


def test_demo_trace_executes_real_python_tools(store):
    t=run_agent(store,Settings(mode='demo'),'安排下一批工作')
    assert t['mode']=='demo' and t['tool_calls']==2 and t['status']=='completed'
    assert [s['name'] for s in t['steps'] if s['type']=='tool_call']==['get_kitchen_state','propose_schedule']
    assert len(t['proposals'][0]['assignments'])==2
    assert store.traces(t['id'])==t


def test_ollama_failure_does_not_fallback(store):
    class Down:
        def next(self, messages):raise DomainError('MODEL_UNAVAILABLE','模型未啟動')
    t=run_agent(store,Settings(mode='ollama'),'安排下一批工作',Down())
    assert t['status']=='failed' and t['mode']=='ollama' and t['tool_calls']==0 and not t['proposals']


def test_tool_loop_limit(store):
    class Loop:
        def next(self, messages):return DemoPlanner.call('get_kitchen_state',{})
    t=run_agent(store,Settings(mode='demo',max_calls=2),'狀態',Loop())
    assert t['error']['code']=='TOOL_LIMIT' and t['tool_calls']==2


def test_tool_failure_cannot_be_presented_as_confirmation(store):
    class IncorrectSummary:
        def next(self, messages):
            if messages[-1]['role'] != 'tool':
                return DemoPlanner.call('get_order_risks', {'order_id': 'O999'})
            return {'content': '已安排 O999，請確認派工。'}
    trace = run_agent(store, Settings(mode='ollama'), '查詢 O999', IncorrectSummary())
    assert trace['status'] == 'tool_error'
    assert trace['answer_source'] == 'tool_error_guard'
    assert '請確認派工' not in trace['answer']
    assert '請核對訂單編號' in trace['answer']
    assert trace['model_answer'] == '已安排 O999，請確認派工。'


def test_agent_rejects_malformed_tool_call(store):
    class Bad:
        def next(self,messages):return {'tool_calls':[{'function':{'name':42}}]}
    t=run_agent(store,Settings(mode='demo'),'狀態',Bad())
    assert t['error']['code']=='MODEL_BAD_RESPONSE'


def test_hidden_model_reasoning_is_not_saved(store):
    class Hidden:
        def next(self,messages):return {'content':'請提供訂單編號。','thinking':'private hidden content'}
    t=run_agent(store,Settings(mode='ollama'),'某張單如何',Hidden())
    assert 'private hidden content' not in str(t)
    assert t['status']=='no_tool_response'


@pytest.mark.parametrize('content,answer', [
    ('<think>private hidden content</think>可公開回答', '可公開回答'),
    ('private hidden content</think>可公開回答', '可公開回答'),
    ('<think>private hidden content', '模型未提供公開回答，請改寫需求後重試。'),
])
def test_thinking_tags_in_content_are_not_persisted(store, content, answer):
    class Tagged:
        def next(self, messages):
            return {'content': content}
    trace = run_agent(store, Settings(mode='ollama'), '查詢', Tagged())
    assert trace['answer'] == answer
    assert 'private hidden content' not in str(store.traces(trace['id']))
    if '</think>' not in content:
        assert trace['status'] == 'failed'


def test_lower_bound_is_not_claimed_as_eta(store):
    results=order_risks(store.snapshot())
    assert 'ETA' in results['note'] and '不是' not in results['orders'][0]['status']
    assert results['orders'][0]['earliest_finish_lower_bound']==7
    assert all('eta' not in o for o in results['orders'])


def test_completed_order_risk_uses_actual_finish_time(store):
    for tid in ['O001-1-1-cook','O001-1-1-plate']:
        p=proposal(store);store.confirm(p['proposal_id']);store.event('s'+tid,'start',tid);store.event('f'+tid,'complete',tid)
    store.mutate(lambda s: (s.update(clock=100) or {}))
    assert order_risks(store.snapshot(),'O001')['orders'][0]['status']=='已準時完成'


def test_api_end_to_end(client):
    assert client.get('/').status_code==200
    trace=client.post('/api/chat',json={'message':'安排下一批工作'}).json()
    pid=trace['proposals'][0]['proposal_id']
    assert client.post(f'/api/proposals/{pid}/confirm').json()['ok']
    assert client.post('/api/events',json={'event_id':'s1','kind':'start','target_id':'O001-1-1-cook'}).json()['ok']
    assert client.post('/api/clock',json={'minutes':4}).json()['clock']==6
    assert client.post('/api/events',json={'event_id':'f1','kind':'complete','target_id':'O001-1-1-cook'}).json()['ok']
    assert client.get(f'/api/traces/{trace["id"]}').json()['id']==trace['id']
    assert client.get('/api/state').json()['tasks']['O001-1-1-plate']['status']=='READY'


def test_api_rejects_bad_input_and_unknown_resources(client):
    assert client.post('/api/orders',json={'id':'A','items':[{'dish':'unknown','quantity':1}],'due_in':12}).status_code==409
    assert client.post('/api/orders',json={'id':'A','items':[{'dish':'fried_rice','quantity':0}],'due_in':12}).status_code==422
    assert client.post('/api/events',json={'kind':'start','target_id':'missing'}).json()['error']['code']=='UNKNOWN_TASK'


def test_browser_cross_origin_write_rejected(client):
    r=client.post('/api/clock',json={'minutes':1},headers={'Origin':'https://evil.example'})
    assert r.status_code==403
    assert client.get('/api/state').json()['clock']==2


def test_ollama_http_uses_native_tools_and_hides_reasoning(monkeypatch):
    import httpx
    observed=[]
    real_client=httpx.Client
    def handler(request):
        import json
        body=json.loads(request.content);observed.append(body)
        assert request.url.path=='/api/chat'
        return httpx.Response(200,json={'message':{'role':'assistant','content':'請提供訂單編號。'}})
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr('app.agent.httpx.Client',lambda **kwargs:real_client(transport=transport,**kwargs))
    msg=OllamaPlanner(Settings()).next([{'role':'user','content':'訂單'}])
    assert msg['content']=='請提供訂單編號。'
    assert observed[0]['tools'][0]['function']['name']=='get_kitchen_state'
    assert observed[0]['stream'] is False and observed[0]['think'] is False


def test_ollama_missing_model_error(monkeypatch):
    import httpx
    real_client=httpx.Client
    transport=httpx.MockTransport(lambda request:httpx.Response(404,json={'error':'model not found'}))
    monkeypatch.setattr('app.agent.httpx.Client',lambda **kwargs:real_client(transport=transport,**kwargs))
    with pytest.raises(DomainError) as e:OllamaPlanner(Settings()).next([])
    assert e.value.code=='MODEL_NOT_FOUND'


def test_ollama_timeout_returns_typed_error(monkeypatch):
    import httpx
    real_client=httpx.Client
    def handler(request):raise httpx.ReadTimeout('timeout',request=request)
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr('app.agent.httpx.Client',lambda **kwargs:real_client(transport=transport,**kwargs))
    with pytest.raises(DomainError) as e:OllamaPlanner(Settings()).next([])
    assert e.value.code=='MODEL_TIMEOUT'
