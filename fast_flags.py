import os
import json
from pathlib import Path

# All known launcher paths, in priority order
_LAUNCHERS = [
    'Bloxstrap',   # Bloxstrap (custom launcher)
    'Roblox',      # Official Roblox launcher
]


def _search_versions(base: Path) -> Path | None:
    versions = base / 'Versions'
    if not versions.exists():
        return None
    candidates = [
        p for p in versions.iterdir()
        if p.is_dir() and p.name.startswith('version-')
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def find_roblox_version_path() -> Path | None:
    local = os.environ.get('LOCALAPPDATA', '')
    for launcher in _LAUNCHERS:
        result = _search_versions(Path(local) / launcher)
        if result:
            return result
    return None


def get_launcher_name() -> str:
    local = os.environ.get('LOCALAPPDATA', '')
    for launcher in _LAUNCHERS:
        if _search_versions(Path(local) / launcher):
            return launcher
    return 'Unknown'


def get_settings_path() -> Path | None:
    base = find_roblox_version_path()
    if base is None:
        return None
    return base / 'ClientSettings' / 'ClientAppSettings.json'


def roblox_found() -> bool:
    return find_roblox_version_path() is not None


def flags_active() -> bool:
    path = get_settings_path()
    return path is not None and path.exists()


def apply_flags(flags: dict) -> None:
    path = get_settings_path()
    if path is None:
        raise RuntimeError(
            'Roblox not found. Checked: '
            + ', '.join(f'%LOCALAPPDATA%\\{l}\\Versions' for l in _LAUNCHERS)
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(flags, f, indent=2)


def restore_flags() -> bool:
    path = get_settings_path()
    if path and path.exists():
        path.unlink()
        return True
    return False


def get_roblox_version_label() -> str:
    p = find_roblox_version_path()
    if p is None:
        return 'Not found'
    return f'{get_launcher_name()}  •  {p.name}'
