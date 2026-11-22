from .domain import DomainError


ACTIVE = {'RESERVED', 'RUNNING'}


def fifo_schedule(state):
    """One dispatch batch, not a globally optimal or full future schedule."""
    busy_stations = {t['station_id'] for t in state['tasks'].values() if t['status'] in ACTIVE}
    busy_chefs = {t['chef_id'] for t in state['tasks'].values() if t['status'] in ACTIVE}
    assigned_stations = set()
    ready = sorted((t for t in state['tasks'].values() if t['status'] == 'READY'),
                   key=lambda t: (t['ready_at'], state['orders'][t['order_id']]['accepted_at'], t['id']))
    assignments, blocked = [], []
    for task in ready:
        stations = [s for s in state['stations'].values()
                    if s['available'] and s['type'] == task['station_type'] and s['id'] not in busy_stations]
        chefs = [c for c in state['chefs'].values()
                 if c['available'] and task['station_type'] in c['skills'] and c['id'] not in busy_chefs]
        if not stations or not chefs:
            compatible = [s for s in state['stations'].values() if s['type'] == task['station_type']]
            if not stations:
                if not any(s['available'] for s in compatible):
                    reason = '相容工作站已停用；不是工序佔用，需現場確認設備恢復後再啟用'
                elif any(s['available'] and s['id'] in assigned_stations for s in compatible):
                    reason = '相容工作站已分配給本批較早工序的提案；提案尚未確認，並未實際保留資源'
                else:
                    reason = '相容工作站正被已保留或執行中的工序佔用，需等待實際完成'
            else:
                reason = '本批無可用且具備所需技能的廚師'
            blocked.append({'task_id': task['id'], 'order_id': task['order_id'], 'reason': reason})
            continue
        station = sorted(stations, key=lambda s: s['id'])[0]
        chef = sorted(chefs, key=lambda c: (len(c['skills']), c['id']))[0]
        busy_stations.add(station['id']); busy_chefs.add(chef['id'])
        assigned_stations.add(station['id'])
        assignments.append({
            'task_id': task['id'], 'order_id': task['order_id'], 'dish': task['dish'], 'step': task['step'],
            'station_id': station['id'], 'station_name': station['name'],
            'chef_id': chef['id'], 'chef_name': chef['name'], 'minutes': task['minutes'],
            'reason': f"FIFO：就緒於第 {task['ready_at']} 分鐘；前置工序已完成且工作站與廚師皆可用。",
        })
    return {'strategy': 'fifo', 'state_version': state['version'], 'clock': state['clock'],
            'assignments': assignments, 'blocked': blocked,
            'note': '僅為目前可開工的一批建議；尚未實際保留資源，需人工確認。blocked 可能是本提案已分配相同資源，不表示設備故障。確認並實際完成工序後才可回報完成釋放資源；切換設備狀態不能釋放。不是完整未來排程。'}


def order_risks(state, order_id=None):
    """Optimistic remaining critical path, never marketed as a resource-aware ETA."""
    if order_id and order_id not in state['orders']:
        raise DomainError('UNKNOWN_ORDER', '找不到指定訂單。')
    results = []
    for order in state['orders'].values():
        if order_id and order['id'] != order_id:
            continue
        memo = {}
        def remaining(tid):
            if tid in memo:
                return memo[tid]
            task = state['tasks'][tid]
            if task['status'] == 'DONE':
                value = 0
            elif task['status'] == 'RUNNING':
                value = max(0, task['minutes'] - (state['clock'] - task['started_at']))
            else:
                value = task['minutes'] + max((remaining(dep) for dep in task['dependencies']), default=0)
            memo[tid] = value
            return value
        tasks = [state['tasks'][i] for i in order['task_ids']]
        complete = all(t['status'] == 'DONE' for t in tasks)
        overrun = any(t['status'] == 'RUNNING' and state['clock'] - t['started_at'] >= t['minutes'] for t in tasks)
        minimum_finish = state['clock'] + max((remaining(t['id']) for t in tasks), default=0)
        unavailable = any(t['status'] != 'DONE' and not any(s['available'] and s['type'] == t['station_type'] for s in state['stations'].values()) for t in tasks)
        finish_at = max((t['finished_at'] for t in tasks), default=None) if complete else None
        if complete:
            status = '已逾期完成' if finish_at > order['due_at'] else '已準時完成'
        elif unavailable:
            status = '設備阻塞，完成時間無法確定'
        elif overrun:
            status = '已超過預估工時，需確認現場狀態'
        elif minimum_finish > order['due_at']:
            status = '存在逾期風險'
        else:
            status = '尚未發現必然逾期，仍可能因資源競爭延誤'
        results.append({'order_id': order['id'], 'due_at': order['due_at'], 'completed': complete,
                        'completed_at': finish_at, 'earliest_finish_lower_bound': None if complete else minimum_finish,
                        'status': status})
    return {'orders': results, 'clock': state['clock'],
            'note': '最早完成下界忽略未來資源競爭、人工確認延遲與估時誤差，不能當作 ETA 或交付保證。'}
