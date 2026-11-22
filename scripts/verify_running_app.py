"""Exercise a fresh running app, including real model and human workflow.

This intentionally changes the synthetic demo state at the supplied local URL.
"""
import json
import sys
from pathlib import Path
import httpx

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8000'
out = Path(__file__).resolve().parents[1] / 'docs/evidence'
with httpx.Client(base_url=base, timeout=360, trust_env=False) as client:
    def post(path, body=None):
        r = client.post(path, json=body) if body is not None else client.post(path)
        r.raise_for_status()
        return r.json()
    health = client.get('/health').json()
    assert health['mode'] == 'ollama', health
    state = client.get('/api/state').json()
    assert state['version'] == 1, 'Use a fresh demonstration data volume'
    trace = post('/api/chat', {'message': '請安排下一批工作，說明優先原因。'})
    (out/'container-ollama-success.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2)+'\n')
    assert trace['status'] == 'completed', trace['answer']
    assert [s['name'] for s in trace['steps'] if s['type'] == 'tool_call'] == ['get_kitchen_state', 'propose_schedule']
    proposal = trace['proposals'][-1]
    assert len(proposal['assignments']) == 2
    confirmed = post(f"/api/proposals/{proposal['proposal_id']}/confirm")
    assert confirmed['ok']
    task = 'O001-1-1-cook'
    assert post('/api/events', {'event_id': 'integration-start', 'kind': 'start', 'target_id': task})['ok']
    post('/api/clock', {'minutes': 4})
    assert post('/api/events', {'event_id': 'integration-complete', 'kind': 'complete', 'target_id': task})['ok']
    final = client.get('/api/state').json()
    assert final['tasks'][task]['status'] == 'DONE'
    assert final['tasks']['O001-1-1-plate']['status'] == 'READY'
    result = {'health': health, 'trace_id': trace['id'], 'duration_ms': trace['duration_ms'],
              'confirmed': confirmed, 'state_after': final, 'workflow_passed': True}
    (out/'container-workflow.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'workflow_passed': True, 'trace_id': trace['id'], 'duration_ms': trace['duration_ms']}))
