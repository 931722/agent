"""Read-only environment check. Run with .venv/bin/python scripts/doctor.py."""
import json
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.config import Settings
s=Settings.from_env()
root = Path(__file__).resolve().parents[1]
def cli(name):
    installed = shutil.which(name)
    if installed:
        return [installed]
    candidates = ['.local-tools/ollama/ollama'] if name == 'ollama' else [
        '.local-tools/podman-5.6.2/podman.pkg/Payload/podman/bin/podman',
        '.local-tools/podman/package/podman.pkg/Payload/podman/bin/podman']
    if any((root / path).is_file() for path in candidates):
        return ['sh', str(root / f'scripts/{name}-local.sh')]
    return None
report={'python':sys.version.split()[0], 'mode':s.mode, 'model':s.model,
        'ollama_cli':cli('ollama'), 'podman_cli':cli('podman')}
try:
    with httpx.Client(timeout=4,trust_env=False) as c:
        r=c.get(s.base_url+'/api/tags');r.raise_for_status()
        report['ollama_models']=[m['name'] for m in r.json()['models']]
        report['selected_model_installed']=s.model in report['ollama_models']
except (httpx.HTTPError,KeyError,ValueError):
    report['ollama_status']='unavailable'
if report['podman_cli']:
    result=subprocess.run(report['podman_cli']+['info','--format','json'],capture_output=True,text=True,timeout=30)
    report['podman_ready']=result.returncode==0
else: report['podman_ready']=False
print(json.dumps(report,ensure_ascii=False,indent=2))
