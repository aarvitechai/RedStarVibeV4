"""Print the OpenAPI schema as stable JSON (used by `make types` and the CI staleness check)."""

import json
import os
import sys

os.environ.setdefault("RSV_ENV", "test")

from app.main import create_app


def main() -> None:
    schema = create_app().openapi()
    # Bytes, UTF-8 and LF on every OS, so the CI staleness diff is stable.
    sys.stdout.buffer.write((json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
