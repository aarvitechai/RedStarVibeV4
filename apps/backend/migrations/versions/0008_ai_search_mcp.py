"""AI call log, hybrid search documents (tsvector + pgvector 1024-d HNSW), MCP tokens and drafts.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL = """
CREATE SCHEMA IF NOT EXISTS ai;
CREATE SCHEMA IF NOT EXISTS search;
CREATE SCHEMA IF NOT EXISTS mcp;

CREATE TABLE ai.ai_calls (
  id bigserial PRIMARY KEY, user_hash varchar(16) NOT NULL, feature varchar(40) NOT NULL, provider varchar(16) NOT NULL,
  prompt_version varchar(40), latency_ms int NOT NULL, outcome varchar(16) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_ai_calls_day ON ai.ai_calls (created_at, feature);

CREATE TABLE search.documents (
  id bigserial PRIMARY KEY,
  kind varchar(12) NOT NULL CHECK (kind IN ('post','business','help')),
  source_id varchar(80) NOT NULL, owner_id uuid,
  visibility varchar(12) NOT NULL CHECK (visibility IN ('public','followers','private')),
  title varchar(200) NOT NULL, content text NOT NULL,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, ''))) STORED,
  embedding vector(1024) NOT NULL, model varchar(40) NOT NULL, model_version varchar(40) NOT NULL,
  content_hash varchar(64) NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (kind, source_id)
);
CREATE INDEX ix_documents_tsv ON search.documents USING gin (tsv);
CREATE INDEX ix_documents_embedding ON search.documents USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ix_documents_owner ON search.documents (owner_id);

CREATE TABLE mcp.tokens (
  id uuid PRIMARY KEY, user_id uuid NOT NULL, token_hash varchar(64) NOT NULL UNIQUE, scopes varchar(20)[] NOT NULL,
  label varchar(60) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL, revoked_at timestamptz
);
CREATE INDEX ix_mcp_tokens_user ON mcp.tokens (user_id);
CREATE TABLE mcp.drafts (
  id uuid PRIMARY KEY, user_id uuid NOT NULL, caption varchar(2200) NOT NULL, source varchar(20) NOT NULL DEFAULT 'mcp',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_mcp_drafts_user ON mcp.drafts (user_id, created_at DESC)
"""


def upgrade() -> None:
    for stmt in [s.strip() for s in SQL.split(";") if s.strip()]:
        op.execute(stmt)


def downgrade() -> None:
    for schema in ("mcp", "search", "ai"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
