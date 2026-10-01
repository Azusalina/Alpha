"""Native release WebKitGTK acceptance. No WebDriver; private Xvfb + ctypes XTest."""
import argparse
import ctypes
import ctypes.util
import functools
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'release'))
from build_runtime import REPO
from build import config
from package import package, verify


class Receiver(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.send_header('Access-Control-Allow-Methods','POST, OPTIONS')
        self.end_headers()

    def do_POST(self):
        self.server.result = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.server.ready.set()

    def log_message(self,*args):
        pass


def xtest(display_name):
    x = ctypes.CDLL(ctypes.util.find_library('X11'))
    t = ctypes.CDLL(ctypes.util.find_library('Xtst'))
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XFlush.argtypes = [ctypes.c_void_p]
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    t.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
    t.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
    d = x.XOpenDisplay(display_name.encode())
    if not d:
        raise RuntimeError('Xvfb display unavailable')
    try:
        t.XTestFakeMotionEvent(d,-1,100,100,0)
        t.XTestFakeButtonEvent(d,1,1,0)
        t.XTestFakeButtonEvent(d,1,0,0)
        x.XFlush(d)
    finally:
        x.XCloseDisplay(d)


def main(resources, output, cases):
    verify(resources)
    if output.exists() or not output.is_absolute():
        raise ValueError('output must be a new absolute directory')
    output.mkdir()
    server = ThreadingHTTPServer(('127.0.0.1',0),Receiver)
    server.ready = threading.Event()
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    xvfb = None
    app = None
    try:
        with tempfile.TemporaryDirectory(prefix='alpha-native-') as tmp:
            tmp = Path(tmp)
            # displayfd avoids colliding with an existing X server.
            readfd, writefd = os.pipe()
            xvfb = subprocess.Popen(['/usr/bin/Xvfb','-displayfd',str(writefd),'-screen','0','1800x1100x24','-nolisten','tcp'],pass_fds=(writefd,),stderr=subprocess.DEVNULL)
            os.close(writefd)
            with os.fdopen(readfd) as stream:
                display = ':' + stream.readline().strip()
            frontend = tmp / 'frontend'
            env = dict(os.environ,VITE_ALPHA_DIAGNOSTICS='1')
            subprocess.run([str(REPO / 'node_modules/.bin/vite'),'build','--outDir',str(frontend)],cwd=REPO,env=env,check=True)
            # One binary per case: compile-time embedded instrumentation, no
            # HTTP dev server or development-source dependency at runtime.
            original = (frontend / 'index.html').read_text()
            results = []
            realdb = tmp / 'real/synthetic.sqlite3'
            realdb.parent.mkdir()
            testing_runtime = tmp / 'testing-runtime'
            shutil.copytree(resources,testing_runtime,symlinks=True)
            python = testing_runtime / 'python/bin/python3'
            seed = subprocess.Popen([str(python),'-E','-s','-u','-m','core.api','--db',str(realdb)],
                cwd=testing_runtime / 'back-end-core',stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,
                env=dict(os.environ,ALPHA_BRAIN_DB=str(realdb),ALPHA_BRAIN_TRACE='0'))
            for i in range(137):
                seed.stdin.write(json.dumps({'schema_version':1,'id':str(i),'method':'submit','params':{
                    'partition':'rational','kind':'philosophy','text':f'合成分页 {i}。我重视自由。','immediate':True}})+'\n')
                seed.stdin.flush()
                assert json.loads(seed.stdout.readline())['ok']
            seed.stdin.close()
            seed.wait(timeout=10)
            for case in cases:
                server.ready.clear()
                js = f'const ALPHA_NATIVE_URL={json.dumps(url)}, ALPHA_NATIVE_CASE={json.dumps(case)};\n' + Path(__file__).with_name('acceptance.js').read_text()
                (frontend / 'index.html').write_text(original.replace('</body>','<script>'+js+'</script></body>'))
                cfg = config(resources,frontend)
                compile_env = dict(os.environ,TAURI_CONFIG=json.dumps(cfg))
                subprocess.run(['cargo','build','--release','--features','tauri/custom-protocol','--manifest-path',str(REPO / 'src-tauri/Cargo.toml')],
                    cwd=REPO,env=compile_env,check=True)
                portable = tmp / ('portable-'+case)
                package(REPO / 'src-tauri/target/release/alpha',resources,portable,create_archive=False)
                db = realdb
                launch_env = {k:v for k,v in os.environ.items() if not k.startswith(('ALPHA_BRAIN_','PYTHON'))}
                launch_env.update(DISPLAY=display,GDK_BACKEND='x11',LIBGL_ALWAYS_SOFTWARE='1',PATH='',HOME=str(tmp),
                    XDG_DATA_HOME=str(tmp / 'xdg'),TMPDIR=str(tmp),ALPHA_BRAIN_TRACE='0')
                if case.startswith('fault-'):
                    fixture = tmp / case
                    (fixture / 'core').mkdir(parents=True)
                    (fixture / 'core/__init__.py').write_text('')
                    shutil.copyfile(Path(__file__).with_name('fault_api.py'),fixture / 'core/api.py')
                    db = fixture / 'synthetic.sqlite3'
                    launch_env.update(ALPHA_BRAIN_PYTHON=str(python),ALPHA_BRAIN_ROOT=str(fixture),
                        ALPHA_NATIVE_REAL_ROOT=str(testing_runtime / 'back-end-core'),ALPHA_NATIVE_FAULT=case.removeprefix('fault-'))
                launch_env['ALPHA_BRAIN_DB'] = str(db)
                with (output / (case+'.stderr')).open('w') as log:
                    app = subprocess.Popen([str(portable / 'bin/alpha')],cwd=tmp,env=launch_env,stderr=log,stdout=log)
                    time.sleep(2)
                    xtest(display)
                    deadline = time.monotonic()+180
                    while not server.ready.wait(1):
                        if app.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError(f'{case}: native process ended or report timed out; see {log.name}')
                    result = server.result
                    if case.startswith('fault-'):
                        methods = [json.loads(line)['method'] for line in (db.parent / 'fixture-methods.jsonl').read_text().splitlines()]
                        result['fixture_methods'] = methods
                        result['no_write_autoretry'] = methods.count('submit') == 1
                        result['passed'] = result['passed'] and result['no_write_autoretry']
                    result['binary_sha256'] = json.loads((portable / 'release.json').read_text())['binary_sha256']
                    (output / (case+'.json')).write_text(json.dumps(result,indent=2)+'\n')
                    results.append(result)
                    app.terminate()
                    app.wait(timeout=15)
                    app = None
                    if not result['passed']:
                        raise RuntimeError(json.dumps(result))
            (output / 'summary.json').write_text(json.dumps(results,indent=2)+'\n')
    finally:
        if app and app.poll() is None:
            app.terminate()
            app.wait(timeout=15)
        if xvfb:
            xvfb.terminate()
            xvfb.wait(timeout=10)
        server.shutdown()
    print(json.dumps({'passed':True,'output':str(output),'cases':cases}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',nargs='+',default=['real','persistence','fault-eof','fault-invalid','fault-timeout'])
    args = parser.parse_args()
    main(args.resources.resolve(),args.output,args.cases)
