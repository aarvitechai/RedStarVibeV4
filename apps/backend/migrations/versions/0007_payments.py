"""Payments: payments, webhook events (unique provider id), append-only ledger, plans (seeded), subscriptions.

Revision ID: 0007
Revises: 0006
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Blueprint 19.5. Prices are starting ideas; changing them is a data change, not a deploy.
PLANS = [
    ("free", "Free", 0, 50, ["Business page", "Posts and stories", "Basic booking", "Cards with watermark"]),
    ("creator", "Creator", 19900, 300, ["Tips (soon)", "Subscriber posts (soon)", "Advanced analytics"]),
    ("premium", "Premium", 9900, 200, ["No watermark", "Verified badge", "More templates"]),
    ("business", "Business", 39900, 500, ["SMS/WhatsApp reminders", "Advance payments", "Analytics", "No watermark"]),
]

SQL = """
CREATE SCHEMA IF NOT EXISTS payments;
CREATE TABLE payments.payments (
  id uuid PRIMARY KEY, user_id uuid NOT NULL,
  purpose varchar(16) NOT NULL CHECK (purpose IN ('order','event_booking','subscription')),
  reference_id varchar(64) NOT NULL, business_id uuid, amount_paise bigint NOT NULL CHECK (amount_paise > 0),
  status varchar(20) NOT NULL DEFAULT 'created' CHECK (status IN ('created','paid','failed','refunded','partially_refunded')),
  provider varchar(12) NOT NULL, provider_order_id varchar(64) NOT NULL UNIQUE, provider_payment_id varchar(64),
  refunded_paise bigint NOT NULL DEFAULT 0 CHECK (refunded_paise >= 0 AND refunded_paise <= amount_paise),
  idempotency_key varchar(80) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), paid_at timestamptz
);
CREATE UNIQUE INDEX ux_payments_idem ON payments.payments (user_id, idempotency_key);
CREATE INDEX ix_payments_pending ON payments.payments (created_at) WHERE status = 'created';
CREATE INDEX ix_payments_user ON payments.payments (user_id, created_at DESC);
CREATE TABLE payments.webhook_events (
  provider_event_id varchar(80) PRIMARY KEY, provider varchar(12) NOT NULL, type varchar(60) NOT NULL,
  payload jsonb NOT NULL, received_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE payments.ledger (
  id bigserial PRIMARY KEY, payment_id uuid NOT NULL,
  entry varchar(16) NOT NULL CHECK (entry IN ('charge','platform_fee','refund','payout')),
  account varchar(12) NOT NULL CHECK (account IN ('business','platform')), business_id uuid,
  amount_paise bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_ledger_business ON payments.ledger (business_id, entry);
CREATE FUNCTION payments.ledger_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'ledger is append-only'; END $$;
CREATE TRIGGER ledger_append_only BEFORE UPDATE OR DELETE ON payments.ledger
  FOR EACH STATEMENT EXECUTE FUNCTION payments.ledger_append_only();
CREATE TABLE payments.plans (
  code varchar(16) PRIMARY KEY, name varchar(40) NOT NULL, price_paise int NOT NULL CHECK (price_paise >= 0),
  ai_calls_per_day int NOT NULL, features jsonb NOT NULL DEFAULT '[]'::jsonb, active boolean NOT NULL DEFAULT true
);
CREATE TABLE payments.subscriptions (
  user_id uuid PRIMARY KEY, plan_code varchar(16) NOT NULL, status varchar(12) NOT NULL DEFAULT 'active',
  current_period_end timestamptz NOT NULL
)
"""


def upgrade() -> None:
    # Split on statement terminators outside the $$ function body.
    body, rest = SQL.split("CREATE FUNCTION", 1)
    fn, tail = rest.split("$$;", 1)
    for stmt in [s.strip() for s in body.split(";") if s.strip()]:
        op.execute(stmt)
    op.execute("CREATE FUNCTION" + fn + "$$")
    for stmt in [s.strip() for s in tail.split(";") if s.strip()]:
        op.execute(stmt)
    insert = sa.text(
        "INSERT INTO payments.plans (code, name, price_paise, ai_calls_per_day, features) "
        "VALUES (:code, :name, :price, :ai, CAST(:features AS jsonb))"
    )
    for code, name, price, ai, features in PLANS:
        op.get_bind().execute(insert, {"code": code, "name": name, "price": price, "ai": ai, "features": json.dumps(features)})


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS payments CASCADE")
