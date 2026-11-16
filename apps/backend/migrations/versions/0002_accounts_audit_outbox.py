"""Accounts (users, sessions, login events), append-only audit log, transactional outbox.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS accounts")
    op.execute("CREATE SCHEMA IF NOT EXISTS notify")

    op.execute("""
    CREATE TABLE accounts.users (
      id                 uuid PRIMARY KEY,
      username           citext NOT NULL UNIQUE,
      email              citext NOT NULL UNIQUE,
      password_hash      text NOT NULL,
      display_name       varchar(80) NOT NULL,
      role               varchar(20) NOT NULL DEFAULT 'user'
                           CHECK (role IN ('user','business','staff','admin','superadmin')),
      status             varchar(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','deleted')),
      is_adult_confirmed boolean NOT NULL CHECK (is_adult_confirmed),
      created_at         timestamptz NOT NULL DEFAULT now(),
      updated_at         timestamptz NOT NULL DEFAULT now(),
      deleted_at         timestamptz
    )""")

    op.execute("""
    CREATE TABLE accounts.sessions (
      id          uuid PRIMARY KEY,
      user_id     uuid NOT NULL,
      family_id   uuid NOT NULL,
      token_hash  varchar(64) NOT NULL UNIQUE,
      created_at  timestamptz NOT NULL DEFAULT now(),
      expires_at  timestamptz NOT NULL,
      rotated_at  timestamptz,
      revoked_at  timestamptz,
      user_agent  varchar(300),
      ip          inet
    )""")
    op.execute("CREATE INDEX ix_sessions_user ON accounts.sessions (user_id)")
    op.execute("CREATE INDEX ix_sessions_family ON accounts.sessions (family_id)")

    op.execute("""
    CREATE TABLE accounts.login_events (
      id          bigserial PRIMARY KEY,
      user_id     uuid,
      success     boolean NOT NULL,
      reason      varchar(40),
      ip          inet,
      user_agent  varchar(300),
      created_at  timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_login_events_user ON accounts.login_events (user_id, created_at DESC)")

    op.execute("""
    CREATE TABLE accounts.audit_log (
      id           bigserial PRIMARY KEY,
      actor_id     uuid,
      action       varchar(80) NOT NULL,
      target_type  varchar(40) NOT NULL,
      target_id    varchar(80) NOT NULL,
      ip           inet,
      details      jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at   timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_audit_actor ON accounts.audit_log (actor_id, id DESC)")
    op.execute("""
    CREATE FUNCTION accounts.audit_log_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'audit_log is append-only';
    END $$""")
    op.execute("""
    CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE OR TRUNCATE ON accounts.audit_log
      FOR EACH STATEMENT EXECUTE FUNCTION accounts.audit_log_append_only()""")

    op.execute("""
    CREATE TABLE notify.outbox (
      id            bigserial PRIMARY KEY,
      event_id      uuid NOT NULL UNIQUE,
      type          text NOT NULL,
      version       smallint NOT NULL DEFAULT 1,
      payload       jsonb NOT NULL,
      created_at    timestamptz NOT NULL DEFAULT now(),
      published_at  timestamptz,
      attempts      int NOT NULL DEFAULT 0,
      last_error    text
    )""")
    op.execute("CREATE INDEX outbox_pending ON notify.outbox (id) WHERE published_at IS NULL")

    op.execute("""
    CREATE TABLE notify.processed_events (
      consumer      varchar(100) NOT NULL,
      event_id      uuid NOT NULL,
      processed_at  timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (consumer, event_id)
    )""")

    op.execute("""
    CREATE TABLE notify.dead_letter (
      id          bigserial PRIMARY KEY,
      event_id    uuid NOT NULL,
      consumer    varchar(100),
      type        text NOT NULL,
      payload     jsonb NOT NULL,
      error       text NOT NULL,
      created_at  timestamptz NOT NULL DEFAULT now()
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notify.dead_letter, notify.processed_events, notify.outbox")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update_delete ON accounts.audit_log")
    op.execute("DROP FUNCTION IF EXISTS accounts.audit_log_append_only()")
    op.execute("DROP TABLE IF EXISTS accounts.audit_log, accounts.login_events, accounts.sessions, accounts.users")
