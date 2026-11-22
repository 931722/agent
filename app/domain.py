from copy import deepcopy
from datetime import datetime, timezone


class DomainError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message

    def as_dict(self):
        return {'ok': False, 'error': {'code': self.code, 'message': self.message}}


MENU = {
    'fried_rice': {'name': '蛋炒飯', 'station_type': 'wok', 'minutes': 4},
    'kung_pao': {'name': '宮保雞丁', 'station_type': 'wok', 'minutes': 7},
    'greens': {'name': '炒青菜', 'station_type': 'wok', 'minutes': 3},
    'egg_soup': {'name': '蛋花湯', 'station_type': 'soup', 'minutes': 3},
    'tofu_soup': {'name': '豆腐湯', 'station_type': 'soup', 'minutes': 5},
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def refresh_ready(state):
    for task in state['tasks'].values():
        if task['status'] == 'WAITING' and all(state['tasks'][p]['status'] == 'DONE' for p in task['dependencies']):
            task['status'], task['ready_at'] = 'READY', state['clock']


def add_order(state, order_id, items, due_in):
    if order_id in state['orders']:
        raise DomainError('DUPLICATE_ORDER', '訂單編號已存在。')
    if not items or len(items) > 10:
        raise DomainError('INVALID_ORDER', '每張單需有 1 至 10 個品項。')
    if not isinstance(due_in, int) or isinstance(due_in, bool) or due_in < 1 or due_in > 240:
        raise DomainError('INVALID_DEADLINE', '承諾時間需為目前模擬時間之後 1 至 240 分鐘。')
    # Validate every item before any mutation.
    for item in items:
        if item['dish'] not in MENU:
            raise DomainError('UNKNOWN_DISH', '菜單中沒有此品項。')
        qty = item['quantity']
        if not isinstance(qty, int) or isinstance(qty, bool) or not 1 <= qty <= 10:
            raise DomainError('INVALID_QUANTITY', '每品項數量需為 1 至 10。')
    task_ids = []
    for i, item in enumerate(items, 1):
        recipe = MENU[item['dish']]
        for qty in range(1, item['quantity'] + 1):
            cook_id = f'{order_id}-{i}-{qty}-cook'
            for step, station_type, minutes, deps in [
                ('cook', recipe['station_type'], recipe['minutes'], []),
                ('plate', 'pass', 1, [cook_id]),
            ]:
                tid = f'{order_id}-{i}-{qty}-{step}'
                task_ids.append(tid)
                state['tasks'][tid] = {
                    'id': tid, 'order_id': order_id, 'dish': recipe['name'], 'step': step,
                    'station_type': station_type, 'minutes': minutes, 'dependencies': deps,
                    'status': 'WAITING', 'ready_at': None, 'station_id': None,
                    'chef_id': None, 'reserved_at': None, 'started_at': None, 'finished_at': None,
                }
    state['orders'][order_id] = {
        'id': order_id, 'items': deepcopy(items), 'accepted_at': state['clock'],
        'due_at': state['clock'] + due_in, 'task_ids': task_ids,
    }
    refresh_ready(state)
    return {'order_id': order_id, 'tasks_created': len(task_ids)}


def seed_state():
    state = {
        'clock': 0, 'version': 1, 'simulation': True,
        'stations': {
            'wok-1': {'id': 'wok-1', 'name': '炒台一', 'type': 'wok', 'available': True},
            'soup-1': {'id': 'soup-1', 'name': '湯台一', 'type': 'soup', 'available': True},
            'pass-1': {'id': 'pass-1', 'name': '出餐台', 'type': 'pass', 'available': True},
        },
        'chefs': {
            'chef-a': {'id': 'chef-a', 'name': '阿明', 'skills': ['wok', 'pass'], 'available': True},
            'chef-b': {'id': 'chef-b', 'name': '小陳', 'skills': ['soup', 'pass'], 'available': True},
        },
        'orders': {}, 'tasks': {},
    }
    add_order(state, 'O001', [{'dish': 'fried_rice', 'quantity': 1}], 12)
    state['clock'] = 1
    add_order(state, 'O002', [{'dish': 'egg_soup', 'quantity': 1}], 8)
    state['clock'] = 2
    add_order(state, 'O003', [{'dish': 'kung_pao', 'quantity': 1}, {'dish': 'greens', 'quantity': 1}], 14)
    return state


def assert_invariants(state):
    stations, chefs = set(), set()
    for task in state['tasks'].values():
        if task['status'] not in ('RESERVED', 'RUNNING', 'DONE'):
            continue
        if not all(state['tasks'][dep]['status'] == 'DONE' for dep in task['dependencies']):
            raise DomainError('DEPENDENCY_VIOLATION', '前置工序尚未完成。')
        if task['status'] == 'DONE':
            continue
        station = state['stations'].get(task['station_id'])
        chef = state['chefs'].get(task['chef_id'])
        if not station or not chef or station['type'] != task['station_type'] or task['station_type'] not in chef['skills']:
            raise DomainError('RESOURCE_MISMATCH', '工作站或廚師技能不符合。')
        if station['id'] in stations or chef['id'] in chefs:
            raise DomainError('RESOURCE_CONFLICT', '同一資源被重複指派。')
        stations.add(station['id']); chefs.add(chef['id'])
