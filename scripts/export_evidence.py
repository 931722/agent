"""Generate reproducible demo/failure evidence, without claiming a live model run."""
import json
from tempfile import TemporaryDirectory
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.agent import run_agent
from app.domain import DomainError
from app.store import Store
from app.tools import TOOLS

out=Path(__file__).resolve().parents[1]/'docs'/'evidence';out.mkdir(parents=True,exist_ok=True)
def save(name,obj):
    (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
with TemporaryDirectory() as tmp:
    store=Store(Path(tmp)/'normal.sqlite3')
    save('demo-success.json',run_agent(store,Settings(mode='demo'),'安排下一批工作'))
    blocked=Store(Path(tmp)/'blocked.sqlite3')
    blocked.event('off-w','station_offline','wok-1');blocked.event('off-s','station_offline','soup-1')
    save('demo-no-resources.json',run_agent(blocked,Settings(mode='demo'),'安排下一批工作'))
    stale=Store(Path(tmp)/'stale.sqlite3')
    p=stale.propose(stale.snapshot()['version']);stale.event('off-w','station_offline','wok-1')
    try:stale.confirm(p['proposal_id'])
    except DomainError as e:save('stale-proposal.json',{'type':'direct-tool-test','scenario':'提案後設備狀態改變','proposal':p,'observed':e.as_dict(),'state_after':stale.snapshot()})
    # This is an intentionally unavailable LOCAL endpoint, not an injected fake response.
    unavailable=Store(Path(tmp)/'unavailable.sqlite3')
    trace=run_agent(unavailable,Settings(mode='ollama',base_url='http://127.0.0.1:1',timeout=1),'安排下一批工作')
    save('ollama-unavailable.json',{'purpose':'故意對未啟動服務的本機端點實測連線失敗；不代表成功呼叫模型','trace':trace})
save('tool-schemas.json',TOOLS)
print(out)
