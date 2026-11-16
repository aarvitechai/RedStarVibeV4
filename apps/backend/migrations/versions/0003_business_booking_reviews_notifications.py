"""Business pages, services, hours, resources; bookings with a no-double-booking constraint; reviews; notifications.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = (
    "electrician",
    "plumber",
    "welder",
    "driver",
    "carpenter",
    "painter",
    "beauty",
    "tailor",
    "tutor",
    "home_food",
    "bakery",
    "shop",
    "photographer",
    "event",
    "other",
)


def upgrade() -> None:
    cats = ", ".join(f"'{c}'" for c in CATEGORIES)
    op.execute("CREATE SCHEMA IF NOT EXISTS business")
    op.execute("CREATE SCHEMA IF NOT EXISTS booking")
    op.execute("CREATE SCHEMA IF NOT EXISTS reviews")

    op.execute(f"""
    CREATE TABLE business.businesses (
      id                 uuid PRIMARY KEY,
      owner_id           uuid NOT NULL,
      slug               citext NOT NULL UNIQUE,
      name               varchar(120) NOT NULL,
      category           varchar(40) NOT NULL CHECK (category IN ({cats})),
      tagline            varchar(160),
      description        text,
      phone_enc          bytea,
      area               varchar(120),
      city               varchar(80),
      lat                double precision CHECK (lat BETWEEN -90 AND 90),
      lng                double precision CHECK (lng BETWEEN -180 AND 180),
      location           geography(Point, 4326) GENERATED ALWAYS AS (
                           CASE WHEN lat IS NOT NULL AND lng IS NOT NULL
                                THEN ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography END) STORED,
      service_radius_km  int NOT NULL DEFAULT 10 CHECK (service_radius_km BETWEEN 1 AND 200),
      timezone           varchar(40) NOT NULL DEFAULT 'Asia/Kolkata',
      status             varchar(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'hidden', 'suspended')),
      created_at         timestamptz NOT NULL DEFAULT now(),
      updated_at         timestamptz NOT NULL DEFAULT now(),
      CHECK ((lat IS NULL) = (lng IS NULL))
    )""")
    op.execute("CREATE INDEX ix_businesses_owner ON business.businesses (owner_id)")
    op.execute("CREATE INDEX ix_businesses_location ON business.businesses USING gist (location)")
    op.execute("CREATE INDEX ix_businesses_category ON business.businesses (category) WHERE status = 'active'")

    op.execute("""
    CREATE TABLE business.services (
      id            uuid PRIMARY KEY,
      business_id   uuid NOT NULL,
      name          varchar(120) NOT NULL,
      description   varchar(500),
      price_paise   int NOT NULL CHECK (price_paise >= 0),
      duration_min  int NOT NULL CHECK (duration_min BETWEEN 5 AND 720),
      buffer_min    int NOT NULL DEFAULT 0 CHECK (buffer_min BETWEEN 0 AND 240),
      active        boolean NOT NULL DEFAULT true,
      created_at    timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_services_business ON business.services (business_id)")

    op.execute("""
    CREATE TABLE business.hours (
      business_id  uuid NOT NULL,
      weekday      smallint NOT NULL CHECK (weekday BETWEEN 0 AND 6),
      opens        time NOT NULL,
      closes       time NOT NULL,
      PRIMARY KEY (business_id, weekday, opens),
      CHECK (opens < closes)
    )""")

    op.execute("""
    CREATE TABLE business.resources (
      id           uuid PRIMARY KEY,
      business_id  uuid NOT NULL,
      name         varchar(80) NOT NULL,
      active       boolean NOT NULL DEFAULT true,
      created_at   timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_resources_business ON business.resources (business_id)")

    # Blueprint 8.3: the database itself makes double booking impossible, even under races.
    op.execute("""
    CREATE TABLE booking.bookings (
      id               uuid PRIMARY KEY,
      business_id      uuid NOT NULL,
      resource_id      uuid NOT NULL,
      service_id       uuid NOT NULL,
      customer_id      uuid NOT NULL,
      slot             tstzrange NOT NULL,
      starts_at        timestamptz NOT NULL,
      ends_at          timestamptz NOT NULL,
      status           varchar(20) NOT NULL CHECK (status IN ('pending','confirmed','done','cancelled','expired')),
      service_name     varchar(120) NOT NULL,
      price_paise      int NOT NULL CHECK (price_paise >= 0),
      advance_paise    int NOT NULL DEFAULT 0 CHECK (advance_paise >= 0),
      customer_note    varchar(500),
      idempotency_key  varchar(80) NOT NULL,
      reminded_at      timestamptz,
      created_at       timestamptz NOT NULL DEFAULT now(),
      updated_at       timestamptz NOT NULL DEFAULT now(),
      CHECK (lower(slot) = starts_at AND upper(slot) >= ends_at AND ends_at > starts_at),
      EXCLUDE USING gist (resource_id WITH =, slot WITH &&) WHERE (status IN ('pending', 'confirmed'))
    )""")
    op.execute("CREATE INDEX ix_bookings_business_start ON booking.bookings (business_id, starts_at)")
    op.execute("CREATE INDEX ix_bookings_customer_start ON booking.bookings (customer_id, starts_at DESC, id DESC)")
    op.execute("CREATE UNIQUE INDEX ux_bookings_idempotency ON booking.bookings (customer_id, idempotency_key)")
    op.execute(
        "CREATE INDEX ix_bookings_reminder ON booking.bookings (starts_at) WHERE status = 'confirmed' AND reminded_at IS NULL"
    )
    op.execute("CREATE INDEX ix_bookings_pending ON booking.bookings (starts_at) WHERE status = 'pending'")

    op.execute("""
    CREATE TABLE booking.status_history (
      id           bigserial PRIMARY KEY,
      booking_id   uuid NOT NULL,
      from_status  varchar(20),
      to_status    varchar(20) NOT NULL,
      actor_id     uuid,
      created_at   timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_status_history_booking ON booking.status_history (booking_id)")

    op.execute("""
    CREATE TABLE reviews.reviews (
      id             uuid PRIMARY KEY,
      booking_id     uuid NOT NULL UNIQUE,
      business_id    uuid NOT NULL,
      customer_id    uuid NOT NULL,
      customer_name  varchar(80) NOT NULL,
      rating         smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
      body           varchar(1000),
      reply_body     varchar(1000),
      replied_at     timestamptz,
      status         varchar(20) NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'hidden')),
      created_at     timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_reviews_business ON reviews.reviews (business_id, created_at DESC, id DESC)")

    op.execute("""
    CREATE TABLE notify.notifications (
      id          uuid PRIMARY KEY,
      user_id     uuid NOT NULL,
      type        varchar(60) NOT NULL,
      title       varchar(160) NOT NULL,
      body        varchar(500),
      link        varchar(300),
      dedupe_key  varchar(160) NOT NULL UNIQUE,
      read_at     timestamptz,
      created_at  timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_notifications_user ON notify.notifications (user_id, created_at DESC, id DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notify.notifications")
    op.execute("DROP SCHEMA IF EXISTS reviews CASCADE")
    op.execute("DROP SCHEMA IF EXISTS booking CASCADE")
    op.execute("DROP SCHEMA IF EXISTS business CASCADE")
