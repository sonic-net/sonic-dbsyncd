"""Reject DEB outputs in a declared build or test action graph before execution."""

import json
from pathlib import Path
import sys


graph = json.loads(Path(sys.argv[1]).read_text())
fragments = {item["id"]: item for item in graph.get("pathFragments", [])}


def artifact_path(fragment_id):
    parts = []
    while fragment_id:
        fragment = fragments[fragment_id]
        parts.append(fragment["label"])
        fragment_id = fragment.get("parentId", 0)
    return "/".join(reversed(parts))


artifacts = {item["id"]: artifact_path(item["pathFragmentId"]) for item in graph.get("artifacts", [])}
outputs = {artifacts[output] for action in graph.get("actions", []) for output in action.get("outputIds", [])}
assert outputs, "Empty action output inventory"
for output in outputs:
    assert not output.endswith((".deb", ".udeb", ".ddeb")), output
print(json.dumps({"status": "passed", "actions": len(graph.get("actions", [])),
                  "outputs": len(outputs), "deb_outputs": 0}))
