# پروزه اتوماسیون بورسی
"""Read-only local readiness check; never prints private configuration values."""
from pathlib import Path
import shutil
import sys
import tomllib

ROOT = Path(__file__).resolve().parent


def load_config(path):
    with path.open('rb') as stream:
        config = tomllib.load(stream)
    server = config['server']
    if server['host'] != '127.0.0.1':
        raise ValueError('Only local loopback binding is configured for this project.')
    if type(server['port']) is not int or not 1024 <= server['port'] <= 65535:
        raise ValueError('Invalid local port.')
    resolved = {}
    for key in ('data', 'reports', 'logs', 'sessions'):
        relative = Path(config['paths'][key])
        target = (ROOT / relative).resolve()
        if relative.is_absolute() or target == ROOT or not target.is_relative_to(ROOT):
            raise ValueError(f'Path must stay inside the project: {key}')
        resolved[key] = target
    return config, resolved


def main():
    path = ROOT / 'config.local.toml'
    if not path.exists():
        path = ROOT / 'config.example.toml'
        print('INFO: using example settings; run setup-local.ps1 on each device.')
    try:
        load_config(path)
    except (KeyError, TypeError, ValueError, OSError):
        print('FAIL: invalid settings; check the example without sharing secrets.')
        return 1
    print('OK: local-only settings and project-relative paths.')
    print('OK: Git available.' if shutil.which('git') else 'MISSING: Git required for synchronization.')
    print('OK: Python 3.12.' if sys.version_info[:2] == (3, 12) else 'MISSING: use Python 3.12 on both devices.')
    print('INFO: local demo server is available; brokerage portfolio extraction is not implemented yet.')
    return 0 if shutil.which('git') and sys.version_info[:2] == (3, 12) else 1


if __name__ == '__main__':
    raise SystemExit(main())
