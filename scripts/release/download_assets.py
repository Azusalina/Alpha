"""Explicit network step: pinned runtime, notices and hashed Linux wheels."""
import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path
from build_runtime import LOCK, LICENSES, digest


def download(url, target, expected):
    urllib.request.urlretrieve(url, target)
    if digest(target) != expected:
        raise ValueError(f"checksum mismatch: {target.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute() or args.output.exists():
        raise SystemExit("output must be a new absolute directory")
    args.output.mkdir()
    download(LOCK["url"], args.output / "python.tar.gz", LOCK["sha256"])
    notices = args.output / "licenses"
    notices.mkdir()
    for name, checksum in LICENSES["files"].items():
        download(LICENSES["base_url"] + name, notices / name, checksum)
    subprocess.run([sys.executable, "-m", "pip", "download", "--no-cache-dir",
        "--only-binary=:all:", "--require-hashes", "--python-version", "313",
        "--implementation", "cp", "--abi", "cp313", "--abi", "abi3",
        "--platform", "manylinux_2_34_x86_64", "--platform", "manylinux2014_x86_64",
        "--dest", str(args.output / "wheels"), "-r",
        str(Path(__file__).with_name("security-requirements.txt"))], check=True)
