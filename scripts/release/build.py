"""Production build with an explicit Tauri resource map, then portable archive."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
from build_runtime import build, REPO
from package import package


def config(resources, frontend=None):
    # DIRECTORY map (trailing slash), never glob flattening: preserves layout.
    result = {"bundle": {"active": False, "resources": {str(resources) + "/": "brain-runtime/"}}}
    if frontend:
        result["build"] = {"frontendDist": str(frontend), "beforeBuildCommand": ""}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--wheelhouse", required=True, type=Path)
    parser.add_argument("--requirements", type=Path, default=Path(__file__).with_name("security-requirements.txt"))
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--licenses", required=True, type=Path)
    args = parser.parse_args()
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise SystemExit("only native Linux x86_64 is supported")
    if not args.output.is_absolute() or args.output.exists() or args.output.with_suffix(".tar.gz").exists():
        raise SystemExit("output and archive must be new absolute paths")
    with tempfile.TemporaryDirectory(prefix="alpha-release-") as tmp:
        tmp = Path(tmp)
        resources = tmp / "resources"
        build(resources, args.archive, args.requirements, args.wheelhouse, args.licenses)
        cfg = tmp / "tauri.release.json"
        cfg.write_text(json.dumps(config(resources)))
        subprocess.run([str(REPO / "node_modules/.bin/tauri"), "build", "--no-bundle", "--config", str(cfg)],
                       cwd=REPO, env=dict(os.environ, CARGO_NET_OFFLINE="true"), check=True)
        package(REPO / "src-tauri/target/release/alpha", resources, args.output)
