"""
Database connection config — saved to a JSON file in the app data directory.
"""

import json
from pathlib import Path
from app_paths import ensure_data_dirs

DEFAULT_CONFIG = {
    'host':     'localhost',
    'port':     '5432',
    'database': 'tdm_db',
    'username': 'postgres',
    'password': 'password',
}


def _config_path() -> Path:
    return ensure_data_dirs() / "config" / "db_config.json"


def load_db_config() -> dict:
    path = _config_path()
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            return {**DEFAULT_CONFIG, **saved}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_db_config(config: dict):
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding='utf-8')


def get_db_url() -> str:
    c = load_db_config()
    return (
        f"postgresql://{c['username']}:{c['password']}"
        f"@{c['host']}:{c['port']}/{c['database']}"
    )
