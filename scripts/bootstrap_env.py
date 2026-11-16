"""First run: write .env from .env.example with fresh random secrets.

    python scripts/bootstrap_env.py          # refuses to overwrite an existing .env
    python scripts/bootstrap_env.py --force  # regenerate (destroys access to existing local DB volume)
"""

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="overwrite an existing .env")
    args = parser.parse_args()

    if TARGET.exists() and not args.force:
        print(".env already exists; use --force to regenerate it.")
        return 0

    db_password = secrets.token_urlsafe(24)
    values = {
        "RSV_SECRET_KEY": secrets.token_urlsafe(48),
        "RSV_FIELD_ENCRYPTION_KEY": secrets.token_urlsafe(48),
        "POSTGRES_PASSWORD": db_password,
        "RSV_DATABASE_URL": f"postgresql+asyncpg://rsv:{db_password}@db:5432/rsv",
    }

    out: list[str] = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip()
        if key in values and not line.lstrip().startswith("#"):
            out.append(f"{key}={values[key]}")
        else:
            out.append(line)

    TARGET.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)} with fresh secrets. Never commit it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
