import os
from dataclasses import dataclass
from pathlib import Path


def load_env(path='.env'):
    """Minimal KEY=value loader; never executes shell code or overwrites env."""
    if Path(path).is_file():
        for raw in Path(path).read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))


@dataclass(frozen=True)
class Settings:
    mode: str = 'ollama'
    base_url: str = 'http://127.0.0.1:11434'
    model: str = 'qwen3:4b'
    timeout: float = 120
    max_calls: int = 6
    db_path: str = 'data/kitchen.sqlite3'

    @classmethod
    def from_env(cls):
        load_env()
        mode = os.getenv('AGENT_MODE', 'ollama')
        if mode not in ('ollama', 'demo'):
            raise ValueError('AGENT_MODE must be ollama or demo')
        return cls(mode, os.getenv('OLLAMA_BASE_URL', cls.base_url).rstrip('/'),
                   os.getenv('OLLAMA_MODEL', cls.model), float(os.getenv('OLLAMA_TIMEOUT', '120')),
                   max(1, min(12, int(os.getenv('MAX_TOOL_CALLS', '6')))),
                   os.getenv('DB_PATH', cls.db_path))
