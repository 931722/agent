import argparse
import json
from pathlib import Path
import uvicorn
from .config import Settings
from .store import Store
from .agent import run_agent


def main():
    parser = argparse.ArgumentParser(description='出餐排程 Agent 作業二')
    parser.add_argument('--mode', choices=['ollama', 'demo'], help='明確選擇真實模型或固定規則模擬')
    parser.add_argument('--db', help='SQLite 路徑')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve'); serve.add_argument('--host', default='127.0.0.1'); serve.add_argument('--port', type=int, default=8000)
    chat = sub.add_parser('chat'); chat.add_argument('message'); chat.add_argument('--output', help='JSON 執行紀錄輸出路徑')
    args = parser.parse_args()
    settings = Settings.from_env()
    from dataclasses import replace
    if args.mode: settings = replace(settings, mode=args.mode)
    if args.db: settings = replace(settings, db_path=args.db)
    if args.command == 'serve':
        from .main import create_app
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
    else:
        trace = run_agent(Store(settings.db_path), settings, args.message)
        encoded = json.dumps(trace, ensure_ascii=False, indent=2)
        if args.output:
            dest = Path(args.output); dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(encoded)
        print(encoded)
        if trace['status'] in ('failed', 'tool_error'):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
