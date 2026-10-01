"""Assemble portable bin/alpha + lib/<productName>/brain-runtime; verify before shipping."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import tarfile
from build_runtime import inventory, digest, REPO


def verify(resources):
    manifest = json.loads((resources / "manifest.json").read_text())
    if inventory(resources) != manifest["files"]:
        raise ValueError("resource inventory/checksum mismatch")
    return manifest


def package(binary, resources, output, create_archive=True):
    manifest = verify(resources)
    if output.exists() or not output.is_absolute():
        raise ValueError("output must be a new absolute directory")
    (output / "bin").mkdir(parents=True)
    shutil.copy2(binary, output / "bin/alpha")
    # Tauri 2.11.5 uses PackageInfo.name (productName), case-sensitive on Linux.
    name = json.loads((REPO / "src-tauri/tauri.conf.json").read_text())["productName"]
    if not name or Path(name).name != name or name in (".", ".."):
        raise ValueError("unsafe productName")
    shutil.copytree(resources, output / "lib" / name / "brain-runtime", symlinks=True)
    (output / "release.json").write_text(json.dumps({"binary_sha256": digest(binary),
        "runtime_manifest_sha256": digest(resources / "manifest.json"),
        "target": manifest["lock"]["target"]}, sort_keys=True, indent=2) + "\n")
    if not create_archive:
        return
    archive = output.with_suffix(".tar.gz")
    if archive.exists():
        raise ValueError("archive already exists")
    # Fixed ordering/time/ownership: same binary/resources => same archive bytes.
    with archive.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as tar:
            for path in [output, *sorted(output.rglob("*"))]:
                info = tar.gettarinfo(str(path), arcname="alpha/" + path.relative_to(output).as_posix())
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                if path.is_file() and not path.is_symlink():
                    with path.open("rb") as stream:
                        tar.addfile(info, stream)
                else:
                    tar.addfile(info)
    print(json.dumps({"archive": str(archive), "sha256": digest(archive)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--resources", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    package(args.binary, args.resources, args.output)
