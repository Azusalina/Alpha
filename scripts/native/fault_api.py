"""Deterministic transport fixture, NEVER shipped as backend or used on a live DB."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

db = Path(sys.argv[sys.argv.index('--db') + 1])
assert db.is_absolute() and db.name == 'synthetic.sqlite3'
marker = db.parent / 'health-failed'
log = db.parent / 'fixture-methods.jsonl'
real = Path(os.environ['ALPHA_NATIVE_REAL_ROOT'])
child = subprocess.Popen([sys.executable,'-E','-s','-u','-m','core.api','--db',str(db)], cwd=real,
    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
try:
    for line in sys.stdin:
        request = json.loads(line)
        with log.open('a') as stream:
            stream.write(json.dumps({'id':request['id'],'method':request['method']})+'\n')
        if request['method'] == 'health' and not marker.exists():
            marker.write_text('synthetic')
            break
        child.stdin.write(line)
        child.stdin.flush()
        response = child.stdout.readline()
        if request['method'] == 'submit':
            mode = os.environ['ALPHA_NATIVE_FAULT']
            if mode == 'timeout':
                time.sleep(35)
            elif mode == 'invalid':
                print('invalid fixture response',flush=True)
            break  # EOF AFTER real backend commit, with no response/replay.
        print(response,end='',flush=True)
finally:
    child.stdin.close()
    child.wait(timeout=10)
