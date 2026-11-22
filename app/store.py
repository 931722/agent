import json
import sqlite3
import os
from datetime import datetime, timezone
from contextlib import contextmanager, closing
from pathlib import Path
from uuid import uuid4
from .domain import DomainError, seed_state, assert_invariants, refresh_ready, utc_now
from .scheduler import fifo_schedule, ACTIVE


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


class Store:
    """A single-store SQLite snapshot; BEGIN IMMEDIATE serializes state mutations."""
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS kitchen (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, body TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, body TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS traces (id TEXT PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')
            con.execute('INSERT OR IGNORE INTO kitchen VALUES(1, ?)', (dump(seed_state()),))

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=10)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def read(con):
        return json.loads(con.execute('SELECT body FROM kitchen WHERE id=1').fetchone()[0])

    @staticmethod
    def write(con, state):
        assert_invariants(state)
        con.execute('UPDATE kitchen SET body=? WHERE id=1', (dump(state),))

    def snapshot(self):
        with self.connect() as con:
            return self.read(con)

    def _backup(self):
        directory = Path(self.path).parent / 'backups'
        name = f"simulation-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex}.sqlite3"
        target = directory / name
        temporary = target.with_suffix('.partial')
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
            temporary.touch(mode=0o600, exist_ok=False)
            # Use a separate reader: backing up a connection with an active
            # write transaction can wait indefinitely. reset() holds the write
            # reservation so no other writer can change this snapshot.
            with self.connect() as source:
                with closing(sqlite3.connect(temporary)) as destination:
                    source.backup(destination)
                    if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise sqlite3.DatabaseError('Backup integrity check failed')
            with temporary.open('rb') as saved:
                os.fsync(saved.fileno())
            temporary.rename(target)
            return target
        except (OSError, sqlite3.Error):
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # Preserve the original backup error on a read-only/full disk.
            raise DomainError('BACKUP_FAILED', '備份失敗，模擬資料未重置。請檢查 Disk 空間及寫入權限。') from None

    def reset(self, state_version):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            current = self.read(con)
            if current['version'] != state_version:
                raise DomainError('STALE_STATE', '廚房狀態已改變，請更新畫面後再重置。')
            backup = self._backup()
            initial = seed_state()
            # Keep versions monotonic so a proposal based on the old version
            # cannot become valid again after a reset.
            initial['version'] = current['version'] + 1
            self.write(con, initial)
            for table in ('proposals', 'events', 'traces'):
                con.execute(f'DELETE FROM {table}')
            return {'ok': True, 'clock': initial['clock'], 'state_version': initial['version'],
                    'backup_name': backup.name, 'backup_path': str(backup),
                    'backup_url': f'/api/backups/{backup.name}',
                    'message': '已先備份資料，再恢復初始三張訂單。模擬時間回到第 2 分鐘。'}

    def mutate(self, action):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            state = self.read(con)
            result = action(state)
            state['version'] += 1
            self.write(con, state)
            return {'ok': True, 'state_version': state['version'], **result}

    def propose(self, state_version):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            state = self.read(con)
            if state_version != state['version']:
                raise DomainError('STALE_STATE', '廚房狀態已改變，請重新查詢再排程。')
            result = fifo_schedule(state)
            if not result['assignments']:
                return {'ok': False, 'error': {'code': 'NO_FEASIBLE_TASK', 'message': '目前沒有可同時取得工作站與廚師的就緒工序。'}, **result}
            result['proposal_id'] = uuid4().hex
            con.execute('INSERT INTO proposals(id,body) VALUES(?,?)', (result['proposal_id'], dump(result)))
            return {'ok': True, **result}

    def confirm(self, proposal_id):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT body,confirmed FROM proposals WHERE id=?', (proposal_id,)).fetchone()
            if not row:
                raise DomainError('UNKNOWN_PROPOSAL', '找不到排程提案。')
            proposal = json.loads(row[0])
            if row[1]:
                return {'ok': True, 'already_confirmed': True, 'proposal_id': proposal_id}
            state = self.read(con)
            if proposal['state_version'] != state['version']:
                raise DomainError('STALE_STATE', '提案已過期，請產生新提案並重新確認。')
            # Recompute rather than trusting client-submitted assignments.
            current = fifo_schedule(state)
            if current['assignments'] != proposal['assignments']:
                raise DomainError('RESOURCE_CONFLICT', '資源已變更，請重新排程。')
            for assignment in proposal['assignments']:
                task = state['tasks'][assignment['task_id']]
                task.update(status='RESERVED', station_id=assignment['station_id'], chef_id=assignment['chef_id'], reserved_at=state['clock'])
            state['version'] += 1
            self.write(con, state)
            con.execute('UPDATE proposals SET confirmed=1 WHERE id=?', (proposal_id,))
            return {'ok': True, 'proposal_id': proposal_id, 'assignments': proposal['assignments'], 'state_version': state['version']}

    def event(self, event_id, kind, target_id):
        payload = {'kind': kind, 'target_id': target_id}
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            previous = con.execute('SELECT body,result FROM events WHERE id=?', (event_id,)).fetchone()
            if previous:
                if json.loads(previous[0]) != payload:
                    raise DomainError('EVENT_ID_CONFLICT', '同一事件編號不能用於不同操作。')
                return {**json.loads(previous[1]), 'duplicate': True}
            state = self.read(con)
            if kind in ('start', 'complete'):
                task = state['tasks'].get(target_id)
                if not task:
                    raise DomainError('UNKNOWN_TASK', '找不到工序。')
                required = 'RESERVED' if kind == 'start' else 'RUNNING'
                if task['status'] != required:
                    raise DomainError('INVALID_TRANSITION', f'此操作需要 {required} 狀態，目前為 {task["status"]}。')
                if kind == 'start':
                    if not state['stations'][task['station_id']]['available']:
                        raise DomainError('STATION_UNAVAILABLE', '設備已停用，請先處理現場狀態。')
                    task.update(status='RUNNING', started_at=state['clock'])
                else:
                    task.update(status='DONE', finished_at=state['clock'])
                    refresh_ready(state)
            elif kind in ('station_offline', 'station_online'):
                station = state['stations'].get(target_id)
                if not station:
                    raise DomainError('UNKNOWN_STATION', '找不到工作站。')
                active = [t for t in state['tasks'].values() if t['station_id'] == target_id and t['status'] in ACTIVE]
                if kind == 'station_offline' and active:
                    raise DomainError('ACTIVE_WORK_REQUIRES_REVIEW', '此站有已保留或執行中的工作，雛形不自動轉移或解除保留；請先處理現場工作。')
                station['available'] = kind == 'station_online'
            else:
                raise DomainError('UNKNOWN_EVENT', '不支援此事件。')
            state['version'] += 1
            self.write(con, state)
            result = {'ok': True, 'event_id': event_id, 'state_version': state['version'], 'clock': state['clock']}
            con.execute('INSERT INTO events VALUES(?,?,?)', (event_id, dump(payload), dump(result)))
            return result

    def save_trace(self, trace):
        with self.connect() as con:
            con.execute('INSERT INTO traces VALUES(?,?,?)', (trace['id'], dump(trace), trace['created_at']))

    def traces(self, trace_id=None):
        with self.connect() as con:
            if trace_id:
                row = con.execute('SELECT body FROM traces WHERE id=?', (trace_id,)).fetchone()
                if not row:
                    raise DomainError('UNKNOWN_TRACE', '找不到執行紀錄。')
                return json.loads(row[0])
            rows = con.execute('SELECT body FROM traces ORDER BY created_at DESC LIMIT 20').fetchall()
            return [{'id': t['id'], 'mode': t['mode'], 'status': t['status'], 'user_input': t['user_input'], 'created_at': t['created_at']} for t in map(lambda r: json.loads(r[0]), rows)]
