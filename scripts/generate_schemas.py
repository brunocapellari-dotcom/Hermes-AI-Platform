"""Generate JSON Schema 2020-12 artifacts from canonical Pydantic contracts."""

from __future__ import annotations

import json
from pathlib import Path

from contracts.manifests import AgentManifest, ToolManifest


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"


def write_schema(filename: str, model: type) -> None:
    schema = model.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$comment"] = "GENERATED from contracts/manifests.py; do not edit manually."
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    (SCHEMA_DIR / filename).write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_schema("agent_manifest.schema.json", AgentManifest)
    write_schema("tool_manifest.schema.json", ToolManifest)
