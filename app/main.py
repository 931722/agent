from pathlib import Path
from typing import Literal
from uuid import uuid4
from threading import Lock
import re
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, ConfigDict
from .config import Settings
from .domain import DomainError, MENU, add_order
from .store import Store
from .tools import TOOLS
from .scheduler import order_risks
from .agent import run_agent


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ChatInput(Input):
    message: str = Field(min_length=1, max_length=2000)


class Item(Input):
    dish: str
    quantity: int = Field(strict=True, ge=1, le=10)


class OrderInput(Input):
    id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,24}$')
    items: list[Item] = Field(min_length=1, max_length=10)
    due_in: int = Field(strict=True, ge=1, le=240)


class ScheduleInput(Input):
    state_version: int = Field(strict=True, ge=1)


class EventInput(Input):
    event_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=80)
    kind: Literal['start', 'complete', 'station_offline', 'station_online']
    target_id: str = Field(min_length=1, max_length=80)


class ClockInput(Input):
    minutes: int = Field(strict=True, ge=1, le=60)


def create_app(settings=None, planner=None):
    settings = settings or Settings.from_env()
    store = Store(settings.db_path)
    simulation_lock = Lock()
    app = FastAPI(title='中餐館出餐排程 Agent', version='0.1.0')
    app.state.store = store
    app.state.settings = settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])

    @app.middleware('http')
    async def local_origin_only(request: Request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
                return JSONResponse({'ok': False, 'error': {'code': 'CROSS_ORIGIN', 'message': '請從本機操作介面送出操作。'}}, status_code=403)
        return await call_next(request)

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse(exc.as_dict(), status_code=409)

    @app.get('/health')
    def health():
        return {'ok': True, 'mode': settings.mode, 'model': settings.model,
                'simulation': True, 'model_connection_verified': False}

    @app.get('/api/state')
    def state():
        return {'ok': True, **store.snapshot(), 'menu': MENU, 'mode': settings.mode, 'model': settings.model}

    @app.get('/api/risks')
    def risks():
        return {'ok': True, **order_risks(store.snapshot())}

    @app.get('/api/tools')
    def tools():
        return TOOLS

    @app.post('/api/chat')
    def chat(body: ChatInput):
        if not simulation_lock.acquire(blocking=False):
            raise DomainError('SIMULATION_BUSY', '助理正在處理或模擬正在重置，請稍候再試。')
        try:
            return run_agent(store, settings, body.message, planner=planner)
        finally:
            simulation_lock.release()

    @app.post('/api/simulation/reset')
    def reset(body: ScheduleInput):
        if not simulation_lock.acquire(blocking=False):
            raise DomainError('SIMULATION_BUSY', '助理正在處理，請等待回答完成後再重置。')
        try:
            return store.reset(body.state_version)
        finally:
            simulation_lock.release()

    @app.get('/api/backups/{name}')
    def backup(name: str):
        if not re.fullmatch(r'simulation-\d{8}T\d{6}Z-[0-9a-f]{32}\.sqlite3', name):
            raise DomainError('UNKNOWN_BACKUP', '找不到備份。')
        path = Path(settings.db_path).parent / 'backups' / name
        if not path.is_file() or path.is_symlink():
            raise DomainError('UNKNOWN_BACKUP', '找不到備份。')
        return FileResponse(path, filename=name, media_type='application/octet-stream')

    @app.post('/api/schedule')
    def schedule(body: ScheduleInput):
        return store.propose(body.state_version)

    @app.post('/api/proposals/{proposal_id}/confirm')
    def confirm(proposal_id: str):
        # Human UI/API endpoint only: never exposed in the LLM tool registry.
        return store.confirm(proposal_id)

    @app.post('/api/orders')
    def order(body: OrderInput):
        def action(state):
            if len(state['tasks']) >= 1000:
                raise DomainError('DEMO_CAPACITY', '雛形資料已達上限，請匯出紀錄後使用新的資料庫。')
            return add_order(state, body.id, [item.model_dump() for item in body.items], body.due_in)
        return store.mutate(action)

    @app.post('/api/events')
    def event(body: EventInput):
        return store.event(body.event_id, body.kind, body.target_id)

    @app.post('/api/clock')
    def clock(body: ClockInput):
        def action(state):
            state['clock'] += body.minutes
            return {'clock': state['clock'], 'note': '模擬時間已推進，工序不會自動完成。'}
        return store.mutate(action)

    @app.get('/api/traces')
    def traces():
        return store.traces()

    @app.get('/api/traces/{trace_id}')
    def trace(trace_id: str):
        return store.traces(trace_id)

    static = Path(__file__).parent / 'static'
    app.mount('/static', StaticFiles(directory=static), name='static')

    @app.get('/')
    def index():
        return FileResponse(static / 'index.html')

    return app
