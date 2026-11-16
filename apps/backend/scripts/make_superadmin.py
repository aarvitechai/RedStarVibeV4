"""The only way to create a super admin (ADR 0013). Promotes an existing account and writes the audit log.

docker compose run --rm api python -m scripts.make_superadmin someone@example.com
"""

import asyncio
import sys

from app.core.database import dispose_engine, get_sessionmaker
from app.modules.accounts import repository as repo
from app.modules.audit import service as audit


async def main(email: str) -> int:
    async with get_sessionmaker()() as db:
        user = await repo.get_user_by_email(db, email.lower())
        if user is None:
            print("No account with that email. Sign up first, then run this script.")
            return 1
        await repo.set_role(db, user.id, "superadmin")
        await audit.record(
            db,
            actor_id=None,
            action="user.superadmin_granted",
            target_type="user",
            target_id=str(user.id),
            details={"via": "scripts/make_superadmin.py", "from": user.role},
        )
        await db.commit()
    await dispose_engine()
    print(f"{user.username} is now a superadmin.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m scripts.make_superadmin <email>")
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1])))
