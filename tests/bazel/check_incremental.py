"""Verify cached builds and reversible owner-source invalidation."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bazel", default="bazel")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd()
    source = root / "src/lldp_syncd/conventions.py"
    original = source.read_bytes()
    edited = original + b"\n# Bazel incremental owner-source probe.\n"
    targets = ["//:sonic_dbsyncd_wheel", "//:sonic_dbsyncd_runtime"]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    results = {}
    paths = None

    def build(name):
        nonlocal paths
        begin = time.monotonic()
        with output.with_name("incremental-" + name + ".log").open("w") as log:
            subprocess.run([args.bazel, "build", "--jobs=2", "--local_resources=cpu=2", *targets],
                           check=True, stdout=log, stderr=subprocess.STDOUT)
        elapsed = time.monotonic() - begin
        if paths is None:
            paths = {}
            for target in targets:
                files = subprocess.check_output([args.bazel, "cquery", target, "--output=files"],
                                                text=True).splitlines()
                assert len(files) == 1, (target, files)
                paths[target] = root / files[0]
        result = {"seconds": elapsed, "sha256": {
            target: hashlib.sha256(path.read_bytes()).hexdigest() for target, path in paths.items()}}
        results[name] = result
        return result["sha256"]

    try:
        baseline = build("baseline")
        assert build("noop") == baseline, "Unchanged source changed output bytes"
        assert source.read_bytes() == original, "Owner source changed concurrently"
        source.write_bytes(edited)
        changed = build("edit")
        assert all(changed[target] != baseline[target] for target in targets), results
    finally:
        current = source.read_bytes()
        assert current in (original, edited), "Refusing to overwrite a concurrent source edit"
        source.write_bytes(original)
    assert build("restore") == baseline, "Restoring owner source did not restore output bytes"
    output.write_text(json.dumps({
        "status": "passed", "source": str(source.relative_to(root)), "builds": results,
        "scope": "Warm baseline/no-op/source-edit/restore; not a cache-free rebuild",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
