"""Create the raw and public buckets if missing (runs in the migrate step; R2 buckets are created in the dashboard)."""

from app.core.config import get_settings
from app.core.storage import S3Storage

if __name__ == "__main__":
    if get_settings().is_deployed:
        print("deployed environment: buckets are managed in Cloudflare R2; skipping")
    else:
        S3Storage().ensure_buckets()
        print("buckets ready")
