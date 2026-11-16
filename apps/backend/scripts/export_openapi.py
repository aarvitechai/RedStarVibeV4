"""Print the OpenAPI schema as stable JSON (used by `make types` and the CI staleness check)."""

import json
import os
import sys

os.environ.setdefault("RSV_ENV", "test")

from app.main import create_app  # noqa: E402


def main() -> None:
    schema = create_app().openapi()
    sys.stdout.write(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
