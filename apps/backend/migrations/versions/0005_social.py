"""Social: profiles, follows, blocks, mutes; posts, hashtags, likes, saves, comments; stories; chat; reports.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SQL = """
CREATE SCHEMA IF NOT EXISTS social;
CREATE SCHEMA IF NOT EXISTS posts;
CREATE SCHEMA IF NOT EXISTS stories;
CREATE SCHEMA IF NOT EXISTS chat;
CREATE SCHEMA IF NOT EXISTS moderation;

CREATE TABLE social.profiles (
  user_id uuid PRIMARY KEY, bio varchar(300), avatar_asset_id uuid, website varchar(200),
  is_private boolean NOT NULL DEFAULT false, updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE social.follows (
  follower_id uuid NOT NULL, followee_id uuid NOT NULL,
  status varchar(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active','pending')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (follower_id, followee_id), CHECK (follower_id <> followee_id)
);
CREATE INDEX ix_follows_followee ON social.follows (followee_id, status);
CREATE TABLE social.blocks (
  blocker_id uuid NOT NULL, blocked_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (blocker_id, blocked_id)
);
CREATE INDEX ix_blocks_blocked ON social.blocks (blocked_id);
CREATE TABLE social.mutes (
  muter_id uuid NOT NULL, muted_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (muter_id, muted_id)
);

CREATE TABLE posts.posts (
  id uuid PRIMARY KEY, author_id uuid NOT NULL,
  kind varchar(10) NOT NULL DEFAULT 'post' CHECK (kind IN ('post','reel')),
  caption text CHECK (char_length(caption) <= 2200),
  visibility varchar(12) NOT NULL DEFAULT 'public' CHECK (visibility IN ('public','followers')),
  media jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar(12) NOT NULL DEFAULT 'published' CHECK (status IN ('published','removed')),
  like_count int NOT NULL DEFAULT 0 CHECK (like_count >= 0),
  comment_count int NOT NULL DEFAULT 0 CHECK (comment_count >= 0),
  created_at timestamptz NOT NULL DEFAULT now(), deleted_at timestamptz
);
CREATE INDEX ix_posts_author ON posts.posts (author_id, created_at DESC, id DESC) WHERE deleted_at IS NULL;
CREATE INDEX ix_posts_reels ON posts.posts (created_at DESC, id DESC) WHERE kind = 'reel' AND deleted_at IS NULL;
CREATE TABLE posts.post_hashtags (
  tag varchar(60) NOT NULL, post_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tag, post_id)
);
CREATE TABLE posts.likes (
  user_id uuid NOT NULL, post_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, post_id)
);
CREATE INDEX ix_likes_post ON posts.likes (post_id);
CREATE TABLE posts.saves (
  user_id uuid NOT NULL, post_id uuid NOT NULL, collection varchar(40) NOT NULL DEFAULT 'Saved',
  created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (user_id, post_id)
);
CREATE TABLE posts.comments (
  id uuid PRIMARY KEY, post_id uuid NOT NULL, author_id uuid NOT NULL, parent_id uuid,
  body varchar(1000) NOT NULL, status varchar(12) NOT NULL DEFAULT 'published',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_comments_post ON posts.comments (post_id, created_at);

CREATE TABLE stories.stories (
  id uuid PRIMARY KEY, author_id uuid NOT NULL, asset_id uuid NOT NULL,
  audience varchar(12) NOT NULL DEFAULT 'followers',
  created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL
);
CREATE INDEX ix_stories_author_live ON stories.stories (author_id, expires_at);
CREATE TABLE stories.views (
  story_id uuid NOT NULL, viewer_id uuid NOT NULL, viewed_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (story_id, viewer_id)
);
CREATE TABLE stories.highlights (
  id uuid PRIMARY KEY, owner_id uuid NOT NULL, title varchar(40) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE stories.highlight_items (highlight_id uuid NOT NULL, story_id uuid NOT NULL, PRIMARY KEY (highlight_id, story_id));

CREATE TABLE chat.conversations (
  id uuid PRIMARY KEY, kind varchar(8) NOT NULL CHECK (kind IN ('direct','group')), title varchar(80),
  direct_key varchar(80) UNIQUE, created_by uuid NOT NULL, last_seq bigint NOT NULL DEFAULT 0,
  last_message_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE chat.members (
  conversation_id uuid NOT NULL, user_id uuid NOT NULL, role varchar(8) NOT NULL DEFAULT 'member',
  last_read_seq bigint NOT NULL DEFAULT 0, left_at timestamptz, PRIMARY KEY (conversation_id, user_id)
);
CREATE INDEX ix_members_user ON chat.members (user_id) WHERE left_at IS NULL;
-- Messages: monthly partitioning is added when the table reaches the operational threshold (Blueprint 8.2).
CREATE TABLE chat.messages (
  id uuid PRIMARY KEY, conversation_id uuid NOT NULL, seq bigint NOT NULL, sender_id uuid NOT NULL,
  body varchar(4000), asset_id uuid, client_id varchar(64), created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ux_messages_seq UNIQUE (conversation_id, seq)
);
CREATE UNIQUE INDEX ux_messages_client ON chat.messages (conversation_id, sender_id, client_id) WHERE client_id IS NOT NULL;

CREATE TABLE moderation.reports (
  id uuid PRIMARY KEY, reporter_id uuid NOT NULL, target_type varchar(12) NOT NULL, target_id uuid NOT NULL,
  reason varchar(20) NOT NULL, details varchar(1000),
  status varchar(12) NOT NULL DEFAULT 'open' CHECK (status IN ('open','actioned','dismissed')),
  reviewer_id uuid, resolution varchar(20), created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz
);
CREATE INDEX ix_reports_queue ON moderation.reports (status, created_at);
"""


def upgrade() -> None:
    for stmt in [s.strip() for s in SQL.split(";") if s.strip()]:
        op.execute(stmt)


def downgrade() -> None:
    for schema in ("moderation", "chat", "stories", "posts", "social"):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
