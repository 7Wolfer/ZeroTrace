"""
ZeroTrace — entry point
Auto-installs deps, requests UAC elevation, then launches the UI.
"""

import sys
import subprocess
import ctypes
import os


def _ensure_deps():
    for pkg in ('customtkinter', 'cryptography'):
        try:
            __import__(pkg)
        except ImportError:
            print(f'Installing {pkg}...')
            subprocess.check_call(
                [sys.executable, '-m', 'pip', 'install', '--quiet', pkg]
            )


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _pythonw() -> str:
    """Return path to pythonw.exe (no console window), fallback to python.exe."""
    exe = sys.executable
    candidate = exe.replace('python.exe', 'pythonw.exe')
    return candidate if os.path.exists(candidate) else exe


def _relaunch_as_admin():
    """Re-launch this script elevated, using pythonw so no console window appears."""
    script = os.path.abspath(sys.argv[0])
    params = ' '.join(f'"{a}"' for a in sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, 'runas', _pythonw(), f'"{script}" {params}', None, 1
    )
    return ret > 32


if __name__ == '__main__':
    _ensure_deps()

    if not _is_admin():
        # Try to elevate; if the user cancels UAC the app still opens (without admin).
        # Fast Flags works without admin; Asset Blocker will show a clear error.
        _relaunch_as_admin()
        sys.exit(0)

    from ui import ZeroTraceApp
    app = ZeroTraceApp()
    app.mainloop()
