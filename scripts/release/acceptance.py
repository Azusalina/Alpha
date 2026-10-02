"""Relocated real backend, empty PATH, explicit fresh temporary DB only."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from package import verify


def acceptance(resources, security=False):
    manifest = verify(resources)
    with tempfile.TemporaryDirectory(prefix="alpha-release-acceptance-") as tmp:
        tmp = Path(tmp)
        relocated = tmp / "relocated/brain-runtime"
        shutil.copytree(resources, relocated, symlinks=True)
        python = relocated / "python/bin/python3"
        db = tmp / "synthetic.sqlite3"
        env = {"PATH": "", "TMPDIR": str(tmp), "ALPHA_BRAIN_DB": str(db), "ALPHA_BRAIN_TRACE": "0",
               "XDG_DATA_HOME": str(tmp / "xdg-data"), "XDG_CONFIG_HOME": str(tmp / "xdg-config"),
               "XDG_CACHE_HOME": str(tmp / "xdg-cache")}
        if "HOME" in os.environ:
            env["HOME"] = os.environ["HOME"]
        script = "import sys,sqlite3,ssl,jieba; print(sys.version); print(jieba.__file__)"
        if security:
            script += "; import nacl.secret,nacl.bindings,_cffi_backend; b=nacl.secret.SecretBox(bytes(32)); assert b.decrypt(b.encrypt(b'synthetic'))==b'synthetic'; print(nacl.__version__)"
        # Backend cwd preserves fixed -E -s semantics. Jieba is the sibling clone.
        subprocess.run([str(python), "-E", "-s", "-c", "import sys; sys.path.insert(0,'../ext-refs/jieba'); " + script],
                       cwd=relocated / "back-end-core", env=env, check=True)
        seq = 0
        def start():
            return subprocess.Popen([str(python), "-E", "-s", "-u", "-m", "core.api", "--db", str(db)],
                cwd=relocated / "back-end-core", env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True)
        child = start()
        def call(method, **params):
            nonlocal seq
            seq += 1
            req = {"schema_version": 1, "id": str(seq), "method": method, "params": params}
            child.stdin.write(json.dumps(req) + "\n")
            child.stdin.flush()
            response = json.loads(child.stdout.readline())
            assert response["id"] == str(seq), response
            assert response["ok"], response
            return response["result"]
        def stop():
            child.stdin.close()
            child.wait(timeout=10)
            assert child.returncode == 0
        try:
            health = call("health")
            assert health["schema_version"] == 1 and health["contract_revision"] == 2, health
            assert len(health["methods"]) == 30, health
            for i in range(137):
                call("submit", partition="rational", kind="philosophy", text=f"合成 {i}。我重视自由。", immediate=True)
            page = call("input_page", limit=50)
            ids = [r["source_id"] for r in page["items"]]
            counts = [len(ids)]
            while page["next_cursor"]:
                page = call("input_page", limit=50, cursor=page["next_cursor"])
                ids += [r["source_id"] for r in page["items"]]
                counts.append(len(ids))
            assert counts == [50, 100, 137] and len(set(ids)) == 137
            source = ids[0]
            call("review", source_id=source, agree=True)
            assert call("state", partition="rational")["value.autonomy"]["observed"]
            call("revoke", source_id=source)
            assert not call("state", partition="rational")["value.autonomy"]["observed"]
            call("input_edit", source_id=source, text="合成修改。我重视成长。", immediate=True)
            call("review", source_id=source, agree=True)
            stop()
            child = start()
            assert call("input_get", source_id=source)["text"] == "合成修改。我重视成长。"
            assert call("state", partition="rational")["value.growth"]["observed"]
            call("input_delete", source_id=source)
            assert not call("state", partition="rational")["value.growth"]["observed"]
            if security:
                stop()
                setup = ("from core.access import setup_access,AccessSession; "
                         "from core.backup import create_backup,restore_backup; "
                         "from pathlib import Path; import os; "
                         "db=Path(os.environ['ALPHA_BRAIN_DB']); "
                         "setup_access(db,'synthetic-passphrase'); "
                         "s=AccessSession(db); assert s.status()['locked']; "
                         "s.unlock('synthetic-passphrase'); "
                         "create_backup(db,db.parent/'synthetic.backup','backup-passphrase',session=s); "
                         "restore_backup(db.parent/'synthetic.backup',db.parent/'restored.sqlite3','backup-passphrase','restored-passphrase')")
                subprocess.run([str(python), "-E", "-s", "-c", setup], cwd=relocated / "back-end-core", env=env, check=True)
                child = start()
                assert call("access_status")["locked"]
                # One deliberate sensitive read while locked; never retry writes.
                seq += 1
                child.stdin.write(json.dumps({"schema_version":1,"id":str(seq),"method":"state","params":{}})+"\n")
                child.stdin.flush()
                assert json.loads(child.stdout.readline())["error"]["code"] == "LOCKED"
                assert not call("unlock", password="synthetic-passphrase")["locked"]
                call("state", partition="rational")
                assert call("lock")["locked"]
            print(json.dumps({"passed": True, "paging": counts, "restart": True, "security": security,
                              "methods": health["methods"], "manifest": manifest["backend_files"]}, sort_keys=True))
        finally:
            if child.poll() is None:
                stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", required=True, type=Path)
    parser.add_argument("--security", action="store_true")
    args = parser.parse_args()
    acceptance(args.resources, args.security)
