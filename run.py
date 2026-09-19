"""Start the local app. Dependencies and frontend must be installed/built first."""
import argparse
import threading
import webbrowser
import json
import urllib.request
from pathlib import Path
import uvicorn

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--open',action='store_true',help='Open the browser after starting')
    args=parser.parse_args()
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/api/bootstrap',timeout=1) as response:
            existing=json.load(response)
        if 'providers' in existing and 'directions' in existing and 'token' in existing:
            print('PaperNest is already running at http://127.0.0.1:8765')
            if args.open:webbrowser.open('http://127.0.0.1:8765')
            raise SystemExit(0)
    except (OSError,ValueError):
        pass
    if not (Path(__file__).parent/'frontend/dist/index.html').exists():
        raise SystemExit('Frontend not built. Run frontend package manager install and build first; see README.md.')
    if args.open:threading.Timer(1.5,lambda:webbrowser.open('http://127.0.0.1:8765')).start()
    uvicorn.run('backend.app:app',host='127.0.0.1',port=8765,log_level='info')
