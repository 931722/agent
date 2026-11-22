from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .domain import DomainError
from .scheduler import order_risks


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ScheduleArgs(EmptyArgs):
    state_version: int = Field(ge=1, description='必須使用剛剛查詢得到的廚房狀態版本')
    strategy: Literal['fifo'] = 'fifo'


class RiskArgs(EmptyArgs):
    order_id: str | None = Field(default=None, min_length=1, max_length=32, description='指定訂單，例如 O001；省略則查全部')


TOOL_SPECS = [
    ('get_kitchen_state', '取得目前模擬時間、狀態版本、訂單、工序、工作站與廚師。任何排程前必須先查詢。', EmptyArgs),
    ('propose_schedule', '使用 FIFO 排程演算法產生可行派工提案，只建立建議，不直接保留資源或開工。', ScheduleArgs),
    ('get_order_risks', '查詢訂單狀態及基於剩餘工序的逾期風險。最早完成下界不是 ETA。', RiskArgs),
]
TOOLS = [{'type': 'function', 'function': {'name': n, 'description': d, 'parameters': schema.model_json_schema()}}
         for n, d, schema in TOOL_SPECS]
ARG_MODELS = {n: model for n, _, model in TOOL_SPECS}


class ToolRegistry:
    def __init__(self, store):
        self.store = store

    def call(self, name, arguments):
        try:
            if name not in ARG_MODELS:
                raise DomainError('UNKNOWN_TOOL', '此工具未註冊或不允許由 Agent 呼叫。')
            parsed = ARG_MODELS[name].model_validate(arguments)
            if name == 'get_kitchen_state':
                return {'ok': True, **self.store.snapshot()}
            if name == 'propose_schedule':
                return self.store.propose(parsed.state_version)
            return {'ok': True, **order_risks(self.store.snapshot(), parsed.order_id)}
        except ValidationError as e:
            return {'ok': False, 'error': {'code': 'INVALID_ARGUMENTS', 'message': '工具參數格式錯誤。',
                                         'fields': [str(err['loc']) for err in e.errors()]}}
        except DomainError as e:
            return e.as_dict()
