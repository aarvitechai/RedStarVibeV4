"""Hybrid search and the RAG assistant (Blueprint 9.5, 11.3; ADRs 0006-0008).

- One `search.documents` table: posts, businesses and help articles. Direct messages are never indexed.
- Keyword: tsvector + GIN. Meaning: pgvector cosine. Merged with Reciprocal Rank Fusion (k = 60).
- The permission filter is in SQL (visibility, owner, blocked authors) - the prompt is never the security boundary.
- Every vector row stores its model; only vectors of the active model are compared.
"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gateway
from app.ai.providers import get_ai, hash_embedding
from app.modules.accounts.models import User

RRF_K = 60
MIN_VECTOR_SIMILARITY = 0.25
ANSWER_THRESHOLD = 0.012  # RRF score below which the assistant says "I don't know" (~ rank 23 in one list)
Kind = Literal["post", "business", "help"]


class SearchHit(BaseModel):
    kind: str
    source_id: str
    title: str
    snippet: str
    score: float
    url: str


class AskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=500)


class Citation(BaseModel):
    n: int
    title: str
    url: str


class AnswerOut(BaseModel):
    answer: str
    citations: list[Citation]
    grounded: bool
    mode: str  # generated | extractive | unknown


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def _url(kind: str, source_id: str) -> str:
    return {"post": f"/p/{source_id}", "business": f"/business/{source_id}", "help": f"/help#{source_id}"}.get(kind, "/")


async def index_document(
    db: AsyncSession, *, kind: Kind, source_id: str, owner_id: uuid.UUID | None, visibility: str, title: str, content: str
) -> bool:
    """Upsert one document. Skips the embedding call when the content and model are unchanged (cache by hash)."""
    ai = get_ai()
    model = ai.embedding_model
    digest = hashlib.sha256(f"{title}\n{content}".encode()).hexdigest()
    existing = (
        await db.execute(
            text("SELECT content_hash, model FROM search.documents WHERE kind = :k AND source_id = :s"),
            {"k": kind, "s": source_id},
        )
    ).first()
    if existing and existing.content_hash == digest and existing.model == model.name:
        if visibility:
            await db.execute(
                text("UPDATE search.documents SET visibility = :v WHERE kind = :k AND source_id = :s"),
                {"v": visibility, "k": kind, "s": source_id},
            )
        return False
    try:
        vector = (await ai.embed([f"{title}\n{content}"[:4000]]))[0]
        model_name, model_version = model.name, model.version
    except Exception:
        vector, model_name, model_version = hash_embedding(f"{title}\n{content}"), "hash-v1", "1"  # re-embedded by backfill later
    await db.execute(
        text("""
        INSERT INTO search.documents (kind, source_id, owner_id, visibility, title, content, embedding, model, model_version, content_hash)
        VALUES (:k, :s, :o, :v, :t, :c, CAST(:e AS vector), :m, :mv, :h)
        ON CONFLICT (kind, source_id) DO UPDATE SET owner_id = EXCLUDED.owner_id, visibility = EXCLUDED.visibility,
          title = EXCLUDED.title, content = EXCLUDED.content, embedding = EXCLUDED.embedding, model = EXCLUDED.model,
          model_version = EXCLUDED.model_version, content_hash = EXCLUDED.content_hash, updated_at = now()
    """),
        {
            "k": kind,
            "s": source_id,
            "o": owner_id,
            "v": visibility,
            "t": title[:200],
            "c": content[:8000],
            "e": _vec(vector),
            "m": model_name,
            "mv": model_version,
            "h": digest,
        },
    )
    return True


async def remove_document(db: AsyncSession, kind: Kind, source_id: str) -> None:
    await db.execute(text("DELETE FROM search.documents WHERE kind = :k AND source_id = :s"), {"k": kind, "s": source_id})


_SEARCH_SQL = text("""
WITH allowed AS (
  SELECT id, kind, source_id, owner_id, title, content, tsv, embedding, model
  FROM search.documents
  WHERE (visibility = 'public' OR owner_id = :viewer)
    AND (owner_id IS NULL OR owner_id = :viewer OR NOT (owner_id = ANY(CAST(:hidden AS uuid[]))))
    AND (CAST(:kinds AS text[]) IS NULL OR kind = ANY(CAST(:kinds AS text[])))
    AND (:own_only = false OR owner_id = :viewer OR kind = 'help' OR (kind = 'business' AND visibility = 'public'))
),
kw AS (
  SELECT id, row_number() OVER (ORDER BY ts_rank(tsv, q) DESC) AS r
  FROM allowed, to_tsquery('simple', :tsq) AS q
  WHERE tsv @@ q
  LIMIT 50
),
vec AS (
  SELECT id, row_number() OVER (ORDER BY embedding <=> CAST(:v AS vector)) AS r
  FROM allowed
  WHERE model = :model AND 1 - (embedding <=> CAST(:v AS vector)) > :min_sim
  ORDER BY embedding <=> CAST(:v AS vector)
  LIMIT 50
)
SELECT a.kind, a.source_id, a.title, a.content,
       COALESCE(1.0 / (:rrf + kw.r), 0) + COALESCE(1.0 / (:rrf + vec.r), 0) AS score
FROM allowed a LEFT JOIN kw ON kw.id = a.id LEFT JOIN vec ON vec.id = a.id
WHERE kw.id IS NOT NULL OR vec.id IS NOT NULL
ORDER BY score DESC
LIMIT :limit
""")


def _tsquery(q: str, match_any: bool) -> str:
    """Sanitised tsquery: words only (no operators from user input). AND for search, OR for the assistant."""
    words = re.findall(r"[\wऀ-ॿ]+", q.lower())[:12]
    return (" | " if match_any else " & ").join(words) or "''"


async def search(
    db: AsyncSession,
    viewer: User | None,
    q: str,
    kinds: list[str] | None = None,
    limit: int = 20,
    own_only: bool = False,
    match_any: bool = False,
) -> list[SearchHit]:
    from app.modules.social import service as social

    viewer_id = viewer.id if viewer else uuid.UUID(int=0)
    hidden = [str(x) for x in (await social.hidden_ids_for(db, viewer.id) if viewer else set())]
    ai = get_ai()
    try:
        qv = (await ai.embed([q]))[0]
        model = ai.embedding_model.name
    except Exception:
        qv, model = hash_embedding(q), "hash-v1"  # keyword search keeps working when the AI provider is down
    rows = (
        await db.execute(
            _SEARCH_SQL,
            {
                "viewer": viewer_id,
                "hidden": hidden,
                "kinds": kinds,
                "tsq": _tsquery(q, match_any),
                "v": _vec(qv),
                "model": model,
                "min_sim": MIN_VECTOR_SIMILARITY,
                "rrf": RRF_K,
                "limit": limit,
                "own_only": own_only,
            },
        )
    ).all()
    return [
        SearchHit(
            kind=r.kind,
            source_id=r.source_id,
            title=r.title,
            snippet=r.content[:220],
            score=round(float(r.score), 5),
            url=_url(r.kind, r.source_id),
        )
        for r in rows
    ]


async def _business_context(db: AsyncSession, user: User, question: str) -> list[tuple[str, str, str]]:
    """Business assistant: 'What bookings do I have tomorrow?' answered from the owner's own data (tenant-scoped)."""
    q = question.lower()
    if not any(w in q for w in ("booking", "bookings", "appointment", "order", "kal", "tomorrow", "today", "aaj")):
        return []
    from app.modules.booking import service as booking
    from app.modules.business import service as business

    out = []
    for b in await business.mine(db, user):
        day = datetime.now(ZoneInfo(b.timezone)).date() + (timedelta(days=1) if ("tomorrow" in q or "kal" in q) else timedelta(0))
        rows = await booking.business_day(db, user, b.id, day)
        lines = [
            f"{r.starts_at.astimezone(ZoneInfo(b.timezone)).strftime('%I:%M %p')} {r.service_name} ({r.status})" for r in rows
        ]
        out.append((f"{b.name} bookings on {day.isoformat()}", "; ".join(lines) or "No bookings.", "/dashboard"))
    return out


async def ask(db: AsyncSession, user: User, data: AskIn) -> AnswerOut:
    from app.modules.payments import service as payments

    hits = await search(db, user, data.question, kinds=["help", "post", "business"], limit=5, own_only=True, match_any=True)
    sources = [(h.title, h.snippet, h.url) for h in hits if h.score >= ANSWER_THRESHOLD]
    sources = [*await _business_context(db, user, data.question), *sources][:6]
    if not sources:
        return AnswerOut(
            answer="I don't know. Try rephrasing, or contact support from the Help page.",
            citations=[],
            grounded=False,
            mode="unknown",
        )
    citations = [Citation(n=i + 1, title=t, url=u) for i, (t, _, u) in enumerate(sources)]
    version, system = gateway.prompt("assistant_v1")
    blocks = "\n".join(f'<source id="{i + 1}" title={json.dumps(t)}>{s}</source>' for i, (t, s, _) in enumerate(sources))
    ent = await payments.entitlements(db, user.id)

    async def generate() -> str:
        return await get_ai().complete(system, f"{blocks}\n\nQuestion: {data.question}", max_tokens=300)

    def extractive() -> str:
        _title, snippet, _ = sources[0]
        return f"{snippet} [1]"

    answer, outcome = await gateway.run(db, user.id, ent.ai_calls_per_day, "assistant", generate, extractive, version)
    grounded = answer.strip() != "I don't know."
    return AnswerOut(
        answer=answer,
        citations=citations if grounded else [],
        grounded=grounded,
        mode="generated" if outcome == "ok" else "extractive",
    )


async def index_help_docs(db: AsyncSession) -> int:
    from app.ai.help_docs import HELP_DOCS

    n = 0
    for slug, title, body in HELP_DOCS:
        n += int(
            await index_document(db, kind="help", source_id=slug, owner_id=None, visibility="public", title=title, content=body)
        )
    await db.commit()
    return n


async def reembed_stale(db: AsyncSession, batch: int = 32) -> int:
    """Backfill: re-embed rows whose model differs from the active one (model change or past provider outage)."""
    model = get_ai().embedding_model.name
    rows = (
        await db.execute(
            text("SELECT kind, source_id, owner_id, visibility, title, content FROM search.documents WHERE model <> :m LIMIT :n"),
            {"m": model, "n": batch},
        )
    ).all()
    for r in rows:
        await db.execute(
            text("UPDATE search.documents SET content_hash = '' WHERE kind = :k AND source_id = :s"),
            {"k": r.kind, "s": r.source_id},
        )
        await index_document(
            db, kind=r.kind, source_id=r.source_id, owner_id=r.owner_id, visibility=r.visibility, title=r.title, content=r.content
        )
    await db.commit()
    return len(rows)
