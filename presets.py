import json
import os
from pathlib import Path

# User-saved presets go here
USER_DIR = Path(os.environ.get('APPDATA', '.')) / 'ZeroTrace' / 'presets'
# Built-in presets shipped with the app
BUNDLED_DIR = Path(__file__).parent / 'data'


def _ensure_user_dir():
    USER_DIR.mkdir(parents=True, exist_ok=True)


def list_presets() -> list[str]:
    _ensure_user_dir()
    names: list[str] = []

    if BUNDLED_DIR.exists():
        for f in sorted(BUNDLED_DIR.glob('*.json')):
            names.append(f.stem)

    for f in sorted(USER_DIR.glob('*.json')):
        if f.stem not in names:
            names.append(f.stem)

    return names or ['Default']


def load_preset(name: str) -> dict | None:
    for path in [USER_DIR / f'{name}.json', BUNDLED_DIR / f'{name}.json']:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    return None


def save_preset(name: str, data: dict) -> None:
    _ensure_user_dir()
    with open(USER_DIR / f'{name}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def delete_preset(name: str) -> bool:
    """Only user-saved presets can be deleted."""
    path = USER_DIR / f'{name}.json'
    if path.exists():
        path.unlink()
        return True
    return False


def is_bundled(name: str) -> bool:
    return (BUNDLED_DIR / f'{name}.json').exists()
