"""Build only explicit runtime resources; output must be a NEW absolute directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

REPO = Path(__file__).resolve().parents[2]
LOCK = json.loads(Path(__file__).with_name("runtime.lock.json").read_text())
LICENSES = json.loads(Path(__file__).with_name("licenses.lock.json").read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if rel == "manifest.json" or path.is_dir():
            continue
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"escaping symlink: {rel}")
            result[rel] = {"link": os.readlink(path)}
        else:
            result[rel] = {"sha256": digest(path), "mode": path.stat().st_mode & 0o777}
    return result


def copy_files(source, target, names):
    for name in names:
        path = source / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"invalid source: {path}")
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        dest.chmod(0o644)


def backend_names(source):
    # Explicit directories/extensions, never recursive repository copy. Includes
    # newly added security modules without including DBs, docs or raw materials.
    names = []
    for package in ("core", "model", "translator"):
        for path in sorted((source / package).rglob("*.py")):
            if "__pycache__" not in path.parts and not path.name.startswith("test_"):
                names.append(path.relative_to(source).as_posix())
    return names + ["model/baseline.json"]


def build(output, archive=None, requirements=None, wheelhouse=None):
    if not output.is_absolute() or output.exists():
        raise ValueError("output must be a new absolute directory")
    jieba = REPO / "ext-refs/jieba"
    commit = subprocess.check_output(["git", "-C", str(jieba), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(jieba), "status", "--porcelain"], text=True)
    if commit != LOCK["jieba_commit"] or dirty:
        raise ValueError("jieba checkout must be clean and pinned")
    with tempfile.TemporaryDirectory(prefix="alpha-runtime-build-") as work:
        work = Path(work)
        asset = Path(archive) if archive else work / "python.tar.gz"
        if not archive:
            urllib.request.urlretrieve(LOCK["url"], asset)
        if digest(asset) != LOCK["sha256"]:
            raise ValueError("CPython official asset checksum mismatch")
        stage = work / "stage"
        stage.mkdir()
        with tarfile.open(asset) as tar:
            # Python's data filter rejects absolute/traversal links and devices.
            tar.extractall(stage, filter="data")
        runtime = stage / "python"
        python = runtime / "bin/python3"
        version = subprocess.check_output([str(python), "-I", "-c", "import platform; print(platform.python_version())"], text=True).strip()
        if version != LOCK["python_version"]:
            raise ValueError("unexpected Python version")
        site = runtime / "lib" / ("python" + ".".join(version.split(".")[:2])) / "site-packages"
        if requirements:
            if not wheelhouse:
                raise ValueError("hashed requirements require an offline wheelhouse")
            subprocess.run([str(python), "-I", "-m", "pip", "install", "--no-index", "--no-compile", "--only-binary=:all:",
                            "--require-hashes", "--find-links", str(Path(wheelhouse).resolve()),
                            "--target", str(site), "-r", str(Path(requirements).resolve())], check=True)
            # No executable .pth hooks or editable paths in the shipped runtime.
            for pth in site.glob("*.pth"):
                raise ValueError(f"dependency .pth hook requires review: {pth.name}")
        resources = work / "resources"
        resources.mkdir()
        shutil.move(runtime, resources / "python")
        backend = REPO / "back-end-core"
        names = backend_names(backend)
        before = {name: digest(backend / name) for name in names}
        copy_files(backend, resources / "back-end-core", names)
        if before != {name: digest(backend / name) for name in backend_names(backend)}:
            raise ValueError("backend changed during capture; refresh runtime")
        tracked = subprocess.check_output(["git", "-C", str(jieba), "ls-files", "jieba", "LICENSE"], text=True).splitlines()
        allowed = [name for name in tracked if name == "LICENSE" or
                   ("lac_small" not in name.split("/") and Path(name).suffix in (".py", ".p", ".txt"))]
        copy_files(jieba, resources / "ext-refs/jieba", allowed)
        notices = resources / "licenses/python-build-standalone"
        notices.mkdir(parents=True)
        for name, expected in LICENSES["files"].items():
            data = urllib.request.urlopen(LICENSES["base_url"] + name, timeout=30).read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f"license checksum mismatch: {name}")
            (notices / name).write_bytes(data)
        # Keep upstream runtime licenses, including compiled dependency notices.
        if not list((resources / "python").rglob("*LICENSE*")):
            raise ValueError("standalone asset lacks license notices")
        distributions = subprocess.check_output([str(resources / "python/bin/python3"), "-I", "-c",
            "import importlib.metadata,json; print(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions()}))"],text=True)
        manifest = {"schema_version": 1, "lock": LOCK, "license_lock": LICENSES, "backend_files": before,
                    "distributions": json.loads(distributions),
                    "requirements_sha256": digest(Path(requirements)) if requirements else None,
                    "files": inventory(resources)}
        (resources / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(resources, output, symlinks=True)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    args = parser.parse_args()
    result = build(args.output, args.archive, args.requirements, args.wheelhouse)
    print(json.dumps({"output": str(args.output), "files": len(result["files"]), "lock": LOCK}))
