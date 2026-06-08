"""
ZeroTrace — entry point
Installs missing dependencies on first run, then launches the UI.
"""

import sys
import subprocess


def _ensure_deps():
    required = {
        'customtkinter': 'customtkinter',
        'cryptography': 'cryptography',
    }
    missing = []
    for import_name, pkg_name in required.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg_name)

    if missing:
        print(f'Installing missing packages: {", ".join(missing)}')
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '--quiet'] + missing
        )
        print('Done. Starting ZeroTrace...')


if __name__ == '__main__':
    _ensure_deps()
    from ui import ZeroTraceApp
    app = ZeroTraceApp()
    app.mainloop()
