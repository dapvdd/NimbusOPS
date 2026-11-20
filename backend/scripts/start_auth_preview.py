"""Start only an explicitly prepared private preview; never defaults to live DB."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main() -> None:
    home = Path(os.environ['NIMBUSOPS_AUTH_PREVIEW_HOME']).resolve()
    settings = json.loads((home / 'environment.json').read_text())
    expected = f"sqlite:///{(home / 'auth.sqlite3').as_posix()}"
    if settings.get('NIMBUSOPS_DATABASE_URL') != expected:
        raise SystemExit('Refusing an unexpected preview database')
    os.environ.update(settings)
    root = Path(__file__).resolve().parents[2]
    if len(sys.argv) != 2 or sys.argv[1] not in ('api', 'ui'):
        raise SystemExit('Choose api or ui')
    if sys.argv[1] == 'api':
        import uvicorn
        port = int(os.environ.get('NIMBUSOPS_PREVIEW_API_PORT', '18420'))
        uvicorn.run('backend.app.main:app', host='127.0.0.1', port=port)
    else:
        port = os.environ.get('NIMBUSOPS_PREVIEW_UI_PORT', '18421')
        subprocess.run(['node', 'node_modules/vite/bin/vite.js', '--host', '127.0.0.1',
                        '--port', port, '--strictPort'], cwd=root / 'frontend', check=True)


if __name__ == '__main__':
    main()
