"""Run the real configured Ollama model against isolated synthetic scenarios."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agent import run_agent
from app.config import Settings
from app.store import Store


def main():
    settings = Settings.from_env()
    if settings.mode != 'ollama':
        raise SystemExit('AGENT_MODE must be ollama for live verification')
    out = Path(__file__).resolve().parents[1] / 'docs/evidence'
    with TemporaryDirectory() as tmp:
        for name, prompt in [
            ('ollama-no-resources', '請安排下一批工作，說明目前是否能派工。'),
            ('ollama-unknown-order', '請查詢訂單 O999 的延誤風險。'),
        ]:
            store = Store(Path(tmp) / f'{name}.sqlite3')
            if name == 'ollama-no-resources':
                store.event('off-w', 'station_offline', 'wok-1')
                store.event('off-s', 'station_offline', 'soup-1')
            before = store.snapshot()
            trace = run_agent(store, settings, prompt)
            (out / f'{name}.json').write_text(
                json.dumps(trace, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({k: trace[k] for k in
                              ('status', 'tool_calls', 'duration_ms', 'answer')},
                             ensure_ascii=False), flush=True)
            expected = 'NO_FEASIBLE_TASK' if name == 'ollama-no-resources' else 'UNKNOWN_ORDER'
            errors = [s['result'].get('error', {}).get('code') for s in trace['steps']
                      if s['type'] == 'observation']
            if trace['status'] != 'tool_error' or expected not in errors or store.snapshot() != before:
                raise SystemExit(1)


if __name__ == '__main__':
    main()
