import os
import json
from pathlib import Path

# (launcher_folder, versions_subfolder)
_LAUNCHERS = [
    ('Voidstrap', 'RblxVersions'),  # Voidstrap uses RblxVersions
    ('Bloxstrap', 'Versions'),      # Bloxstrap uses Versions
    ('Roblox',    'Versions'),      # Official launcher
]


def _search_versions(base: Path, versions_dir: str) -> Path | None:
    versions = base / versions_dir
    if not versions.exists():
        return None
    candidates = [
        p for p in versions.iterdir()
        if p.is_dir() and p.name.startswith('version-')
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _detect() -> tuple[Path, str] | tuple[None, None]:
    """Returns (version_path, launcher_name) or (None, None)."""
    local = os.environ.get('LOCALAPPDATA', '')
    for launcher, versions_dir in _LAUNCHERS:
        result = _search_versions(Path(local) / launcher, versions_dir)
        if result:
            return result, launcher
    return None, None


def find_roblox_version_path() -> Path | None:
    path, _ = _detect()
    return path


def get_launcher_name() -> str:
    _, name = _detect()
    return name or 'Unknown'


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
        checked = ', '.join(f'{l}\\{v}' for l, v in _LAUNCHERS)
        raise RuntimeError(f'Roblox not found. Checked: {checked}')
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
    path, launcher = _detect()
    if path is None:
        return 'Not found'
    return f'{launcher}  •  {path.name}'
