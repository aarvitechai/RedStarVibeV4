"""Events (packages, vendor network, event bookings, holds with exclusion constraint) and shop (products, orders).

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL = """
CREATE SCHEMA IF NOT EXISTS events;
CREATE SCHEMA IF NOT EXISTS shop;

CREATE TABLE events.packages (
  id uuid PRIMARY KEY, business_id uuid NOT NULL, name varchar(120) NOT NULL,
  tier varchar(10) NOT NULL DEFAULT 'custom' CHECK (tier IN ('silver','gold','platinum','custom')),
  description varchar(2000), price_paise bigint NOT NULL CHECK (price_paise >= 0),
  max_guests int NOT NULL CHECK (max_guests > 0), start_time varchar(5) NOT NULL DEFAULT '10:00',
  duration_hours int NOT NULL DEFAULT 8 CHECK (duration_hours BETWEEN 1 AND 24),
  active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_packages_business ON events.packages (business_id);
CREATE TABLE events.package_items (
  id uuid PRIMARY KEY, package_id uuid NOT NULL, label varchar(120) NOT NULL, vendor_business_id uuid
);
CREATE INDEX ix_package_items_package ON events.package_items (package_id);
CREATE TABLE events.vendor_links (
  organizer_id uuid NOT NULL, vendor_id uuid NOT NULL,
  status varchar(10) NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','accepted','declined')),
  terms varchar(500), created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (organizer_id, vendor_id), CHECK (organizer_id <> vendor_id)
);
CREATE INDEX ix_vendor_links_vendor ON events.vendor_links (vendor_id);
CREATE TABLE events.event_bookings (
  id uuid PRIMARY KEY, package_id uuid NOT NULL, organizer_id uuid NOT NULL, customer_id uuid NOT NULL,
  event_date date NOT NULL, guests int NOT NULL CHECK (guests > 0),
  status varchar(12) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','confirmed','done','cancelled','expired')),
  payment_status varchar(12) NOT NULL DEFAULT 'unpaid', price_paise bigint NOT NULL, package_name varchar(120) NOT NULL,
  note varchar(500), idempotency_key varchar(80) NOT NULL, expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_event_bookings_idem ON events.event_bookings (customer_id, idempotency_key);
CREATE INDEX ix_event_bookings_org ON events.event_bookings (organizer_id, event_date);
CREATE INDEX ix_event_bookings_pending ON events.event_bookings (expires_at) WHERE status = 'pending';
CREATE TABLE events.holds (
  id bigserial PRIMARY KEY, event_booking_id uuid NOT NULL, business_id uuid NOT NULL,
  slot tstzrange NOT NULL, active boolean NOT NULL DEFAULT true,
  EXCLUDE USING gist (business_id WITH =, slot WITH &&) WHERE (active)
);
CREATE INDEX ix_holds_booking ON events.holds (event_booking_id);

CREATE TABLE shop.products (
  id uuid PRIMARY KEY, business_id uuid NOT NULL, name varchar(120) NOT NULL, description varchar(2000), sku varchar(40),
  price_paise int NOT NULL CHECK (price_paise >= 0), stock int NOT NULL DEFAULT 0 CHECK (stock >= 0),
  media jsonb NOT NULL DEFAULT '[]'::jsonb, active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_products_business ON shop.products (business_id) WHERE active;
CREATE TABLE shop.orders (
  id uuid PRIMARY KEY, business_id uuid NOT NULL, customer_id uuid NOT NULL,
  status varchar(12) NOT NULL DEFAULT 'placed' CHECK (status IN ('placed','confirmed','ready','shipped','delivered','cancelled')),
  payment_status varchar(12) NOT NULL DEFAULT 'unpaid', total_paise bigint NOT NULL CHECK (total_paise >= 0),
  fulfilment varchar(10) NOT NULL DEFAULT 'pickup' CHECK (fulfilment IN ('pickup','delivery')),
  address_enc bytea, wanted_on date, note varchar(500), idempotency_key varchar(80) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_orders_idem ON shop.orders (customer_id, idempotency_key);
CREATE INDEX ix_orders_business ON shop.orders (business_id, created_at DESC);
CREATE INDEX ix_orders_customer ON shop.orders (customer_id, created_at DESC);
CREATE TABLE shop.order_items (
  order_id uuid NOT NULL, product_id uuid NOT NULL, name varchar(120) NOT NULL,
  unit_price_paise int NOT NULL, qty int NOT NULL CHECK (qty > 0), PRIMARY KEY (order_id, product_id)
);
CREATE TABLE shop.order_status_history (
  id bigserial PRIMARY KEY, order_id uuid NOT NULL, from_status varchar(12), to_status varchar(12) NOT NULL,
  actor_id uuid, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_order_history_order ON shop.order_status_history (order_id);
"""


def upgrade() -> None:
    for stmt in [s.strip() for s in SQL.split(";") if s.strip()]:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS shop CASCADE")
    op.execute("DROP SCHEMA IF EXISTS events CASCADE")
