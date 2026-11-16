"""Media assets, card templates + cards, referrals + Star Points ledger, albums.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEMPLATES = [
    (
        "birthday-en",
        "birthday",
        "Birthday — Confetti",
        "en",
        {
            "bg_top": "#7C3AED",
            "bg_bottom": "#DB2777",
            "accent": "#FDE68A",
            "text": "#FFFFFF",
            "emoji_line": "* * *",
            "default_title": "Happy Birthday!",
        },
    ),
    (
        "birthday-hi",
        "birthday",
        "जन्मदिन — रंगीन",
        "hi",
        {"bg_top": "#F97316", "bg_bottom": "#DB2777", "accent": "#FEF3C7", "text": "#FFFFFF", "default_title": "जन्मदिन मुबारक!"},
    ),
    (
        "wedding-en",
        "wedding",
        "Wedding — Royal",
        "en",
        {"bg_top": "#7F1D1D", "bg_bottom": "#B45309", "accent": "#FCD34D", "text": "#FFFBEB", "default_title": "Shubh Vivah"},
    ),
    (
        "diwali-hi",
        "festival",
        "दिवाली — दीये",
        "hi",
        {"bg_top": "#1E1B4B", "bg_bottom": "#B45309", "accent": "#FBBF24", "text": "#FFFBEB", "default_title": "शुभ दीपावली"},
    ),
    (
        "holi-en",
        "festival",
        "Holi — Colours",
        "en",
        {"bg_top": "#16A34A", "bg_bottom": "#DB2777", "accent": "#FEF08A", "text": "#FFFFFF", "default_title": "Happy Holi!"},
    ),
    (
        "eid-en",
        "festival",
        "Eid — Crescent",
        "en",
        {"bg_top": "#064E3B", "bg_bottom": "#0F766E", "accent": "#FDE68A", "text": "#ECFDF5", "default_title": "Eid Mubarak"},
    ),
    (
        "christmas-en",
        "festival",
        "Christmas — Pine",
        "en",
        {"bg_top": "#14532D", "bg_bottom": "#991B1B", "accent": "#FDE68A", "text": "#FFFFFF", "default_title": "Merry Christmas"},
    ),
    (
        "business-promo-en",
        "business",
        "Business — Star Red",
        "en",
        {"bg_top": "#C8102E", "bg_bottom": "#9B0C23", "accent": "#FDF2F3", "text": "#FFFFFF", "default_title": "Now open!"},
    ),
    (
        "thank-you-en",
        "general",
        "Thank you — Soft",
        "en",
        {"bg_top": "#0EA5E9", "bg_bottom": "#6366F1", "accent": "#E0F2FE", "text": "#FFFFFF", "default_title": "Thank you!"},
    ),
]


def upgrade() -> None:
    for schema in ("media", "cards", "referrals", "albums"):
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    op.execute("""
    CREATE TABLE media.assets (
      id            uuid PRIMARY KEY,
      owner_id      uuid NOT NULL,
      kind          varchar(10) NOT NULL CHECK (kind IN ('image','video','audio')),
      purpose       varchar(20) NOT NULL DEFAULT 'post',
      status        varchar(12) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','ready','failed')),
      raw_key       varchar(200) NOT NULL UNIQUE,
      content_type  varchar(60) NOT NULL,
      size_bytes    bigint NOT NULL CHECK (size_bytes > 0),
      width         int,
      height        int,
      duration_s    double precision,
      variants      jsonb NOT NULL DEFAULT '{}'::jsonb,
      error         varchar(200),
      created_at    timestamptz NOT NULL DEFAULT now(),
      processed_at  timestamptz
    )""")
    op.execute("CREATE INDEX ix_assets_owner ON media.assets (owner_id, created_at DESC)")

    op.execute("""
    CREATE TABLE cards.templates (
      id        varchar(40) PRIMARY KEY,
      occasion  varchar(30) NOT NULL,
      name      varchar(80) NOT NULL,
      locale    varchar(5) NOT NULL DEFAULT 'en',
      version   int NOT NULL DEFAULT 1,
      spec      jsonb NOT NULL,
      active    boolean NOT NULL DEFAULT true,
      premium   boolean NOT NULL DEFAULT false
    )""")
    tpl = sa.table(
        "templates",
        sa.column("id"),
        sa.column("occasion"),
        sa.column("name"),
        sa.column("locale"),
        sa.column("spec", sa.dialects.postgresql.JSONB),
        schema="cards",
    )
    op.bulk_insert(tpl, [{"id": i, "occasion": o, "name": n, "locale": loc, "spec": spec} for i, o, n, loc, spec in TEMPLATES])

    op.execute("""
    CREATE TABLE cards.cards (
      id              uuid PRIMARY KEY,
      owner_id        uuid NOT NULL,
      template_id     varchar(40) NOT NULL,
      fields          jsonb NOT NULL,
      photo_asset_id  uuid,
      input_hash      varchar(64) NOT NULL,
      render_key      varchar(200),
      status          varchar(12) NOT NULL DEFAULT 'rendering',
      share_count     int NOT NULL DEFAULT 0,
      created_at      timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_cards_owner ON cards.cards (owner_id, created_at DESC)")

    op.execute("""
    CREATE TABLE referrals.codes (
      user_id     uuid PRIMARY KEY,
      code        varchar(12) NOT NULL UNIQUE,
      created_at  timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""
    CREATE TABLE referrals.referrals (
      referee_id    uuid PRIMARY KEY,
      referrer_id   uuid NOT NULL,
      status        varchar(12) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','qualified','rejected')),
      created_at    timestamptz NOT NULL DEFAULT now(),
      qualified_at  timestamptz,
      CHECK (referee_id <> referrer_id)
    )""")
    op.execute("CREATE INDEX ix_referrals_referrer ON referrals.referrals (referrer_id)")
    op.execute("""
    CREATE TABLE referrals.points_ledger (
      id          bigserial PRIMARY KEY,
      user_id     uuid NOT NULL,
      delta       int NOT NULL,
      reason      varchar(40) NOT NULL,
      ref_id      varchar(80) NOT NULL,
      created_at  timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT ux_points_once UNIQUE (user_id, reason, ref_id)
    )""")
    op.execute("CREATE INDEX ix_points_user ON referrals.points_ledger (user_id)")
    op.execute("""
    CREATE FUNCTION referrals.ledger_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'points_ledger is append-only'; END $$""")
    op.execute("""
    CREATE TRIGGER points_ledger_append_only BEFORE UPDATE OR DELETE ON referrals.points_ledger
      FOR EACH STATEMENT EXECUTE FUNCTION referrals.ledger_append_only()""")

    op.execute("""
    CREATE TABLE albums.albums (
      id                uuid PRIMARY KEY,
      owner_id          uuid NOT NULL,
      title             varchar(100) NOT NULL,
      visibility        varchar(10) NOT NULL DEFAULT 'link' CHECK (visibility IN ('private','link')),
      share_token       varchar(32) NOT NULL UNIQUE,
      slideshow_key     varchar(200),
      slideshow_status  varchar(12) NOT NULL DEFAULT 'none',
      created_at        timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_albums_owner ON albums.albums (owner_id)")
    op.execute("""
    CREATE TABLE albums.items (
      album_id  uuid NOT NULL,
      asset_id  uuid NOT NULL,
      position  int NOT NULL,
      caption   varchar(200),
      PRIMARY KEY (album_id, asset_id)
    )""")


def downgrade() -> None:
    for schema in ("albums", "referrals", "cards", "media"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
