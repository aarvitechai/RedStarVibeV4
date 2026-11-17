"""Two-factor login factors (TOTP secret encrypted at field level; last used step blocks code replay).

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE accounts.mfa_factors (
      user_id uuid PRIMARY KEY, secret_enc bytea NOT NULL, confirmed_at timestamptz, last_step bigint,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS accounts.mfa_factors")
