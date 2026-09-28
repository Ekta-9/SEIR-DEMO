"""Export the Pydantic contracts to JSON Schema files in /contracts/schemas.

Run from seir-evidence/:  python -m scripts.export_schemas
Re-run whenever a model in app/schema changes, and commit the output.
"""

import json
from pathlib import Path

from app.schema import EXPORTED_CONTRACTS, SCHEMA_VERSION

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "contracts" / "schemas"


def export(target_dir: Path = SCHEMAS_DIR) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in EXPORTED_CONTRACTS.items():
        schema = model.model_json_schema(mode="serialization")
        schema["$id"] = f"seir/{name}/{SCHEMA_VERSION}"
        path = target_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for path in export():
        print(f"wrote {path}")
