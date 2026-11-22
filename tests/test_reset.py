import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app.agent import DemoPlanner
from app.config import Settings
from app.domain import DomainError, add_order, seed_state
from app.main import create_app
from app.store import Store


def test_reset_backs_up_all_tables_and_restores_initial_state(tmp_path):
    store = Store(tmp_path/'kitchen.sqlite3')
    store.mutate(lambda s: add_order(s, 'EXTRA', [{'dish':'greens', 'quantity':1}], 10))
    proposal = store.propose(store.snapshot()['version'])
    store.confirm(proposal['proposal_id'])
    store.event('start-1', 'start', proposal['assignments'][0]['task_id'])
    store.save_trace({'id':'before-reset','created_at':'now','mode':'demo',
                      'status':'completed','user_input':'test'})
    before = store.snapshot()
    result = store.reset(before['version'])
    initial = seed_state()
    initial['version'] = before['version'] + 1
    assert store.snapshot() == initial
    assert store.traces() == []
    with sqlite3.connect(result['backup_path']) as backup:
        assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert json.loads(backup.execute('SELECT body FROM kitchen').fetchone()[0]) == before
        for table in ('proposals', 'events', 'traces'):
            assert backup.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 1
    with store.connect() as current:
        for table in ('proposals', 'events', 'traces'):
            assert current.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert Store(store.path).snapshot() == initial
    with pytest.raises(DomainError) as error:
        store.confirm(proposal['proposal_id'])
    assert error.value.code == 'UNKNOWN_PROPOSAL'
    with pytest.raises(DomainError) as error:
        store.propose(before['version'])
    assert error.value.code == 'STALE_STATE'


def test_failed_backup_does_not_reset_state(tmp_path, monkeypatch):
    store = Store(tmp_path/'kitchen.sqlite3')
    before = store.snapshot()
    original = Path.mkdir
    def fail_backups(path, *args, **kwargs):
        if path.name == 'backups':
            raise PermissionError('read only disk')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', fail_backups)
    with pytest.raises(DomainError) as error:
        store.reset(before['version'])
    assert error.value.code == 'BACKUP_FAILED'
    assert store.snapshot() == before


def test_reset_api_download_and_stale_reset(tmp_path):
    app = create_app(Settings(mode='demo', db_path=str(tmp_path/'kitchen.sqlite3')))
    with TestClient(app) as client:
        version = client.get('/api/state').json()['version']
        result = client.post('/api/simulation/reset', json={'state_version': version})
        assert result.status_code == 200
        backup = client.get(result.json()['backup_url'])
        assert backup.content.startswith(b'SQLite format 3\x00')
        assert 'attachment' in backup.headers['content-disposition']
        assert client.get('/api/backups/invalid.sqlite3').status_code == 409
        stale = client.post('/api/simulation/reset', json={'state_version': version})
        assert stale.json()['error']['code'] == 'STALE_STATE'
        assert len(list((tmp_path/'backups').glob('*.sqlite3'))) == 1
        cross_origin = client.post('/api/simulation/reset', json={'state_version': version+1},
                                   headers={'Origin':'https://example.com'})
        assert cross_origin.status_code == 403


def test_reset_rejected_while_model_is_working(tmp_path):
    entered, release = Event(), Event()
    class WaitingPlanner(DemoPlanner):
        def next(self, messages):
            entered.set()
            assert release.wait(5)
            return {'content':'查詢完成'}
    app = create_app(Settings(mode='demo', db_path=str(tmp_path/'kitchen.sqlite3')), WaitingPlanner())
    with TestClient(app) as client, ThreadPoolExecutor() as pool:
        pending = pool.submit(client.post, '/api/chat', json={'message':'查詢'})
        try:
            assert entered.wait(5)
            reset = client.post('/api/simulation/reset', json={'state_version':1})
            assert reset.json()['error']['code'] == 'SIMULATION_BUSY'
            assert not (tmp_path/'backups').exists()
        finally:
            release.set()
        assert pending.result().status_code == 200
