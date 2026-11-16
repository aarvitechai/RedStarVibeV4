"""AI providers behind one interface (ADR 0009). `none` always works: hash-v1 embeddings and rule-based helpers.

AI_PROVIDER=none        no external calls; keyword search + hash-v1 vectors; suggestions are rule-based
AI_PROVIDER=cloudflare  Workers AI: bge-m3 (1024-d) embeddings, LLaVA vision captions, Whisper, m2m100 translation, small LLM
AI_PROVIDER=anthropic   Claude for text generation; embeddings stay on Workers AI if configured, else hash-v1
"""

import base64
import hashlib
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

DIMS = 1024
TOXIC_WORDS = {
    "idiot",
    "stupid",
    "kill",
    "hate you",
    "ugly",
    "loser",
    "bitch",
    "bastard",
    "chutiya",
    "kutta",
    "kamina",
    "harami",
    "gandu",
    "madarchod",
    "bhenchod",
    "saala",
}


class AIUnavailable(Exception):
    """The feature needs a model the current provider does not have; callers fall back to the non-AI path."""


@dataclass(frozen=True)
class EmbeddingModel:
    name: str
    version: str


HASH_V1 = EmbeddingModel("hash-v1", "1")
BGE_M3 = EmbeddingModel("bge-m3", "workers-ai-1")


def hash_embedding(text: str) -> list[float]:
    """Deterministic bag-of-words hashing into 1024 dims, L2-normalised. A fallback, never compared with bge-m3."""
    vec = [0.0] * DIMS
    for token in re.findall(r"[\wऀ-ॿ]+", text.lower()):
        h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
        vec[h % DIMS] += 1.0 if (h >> 32) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def rule_hashtags(text: str, limit: int = 6) -> list[str]:
    words = [w.lower() for w in re.findall(r"[A-Za-zऀ-ॿ]{4,}", text)]
    stop = {"with", "this", "that", "from", "have", "your", "will", "today", "here", "they", "their", "what", "when"}
    seen: list[str] = []
    for w in words:
        if w not in stop and w not in seen:
            seen.append(w)
    return [f"#{w}" for w in seen[:limit]]


def rule_toxicity(text: str) -> float:
    t = text.lower()
    hits = sum(1 for w in TOXIC_WORDS if w in t)
    shouting = sum(1 for c in text if c.isupper()) > 0.7 * max(1, sum(1 for c in text if c.isalpha())) and len(text) > 12
    return min(1.0, hits * 0.5 + (0.2 if shouting else 0.0) + (0.1 if "!!!" in text else 0.0))


class AIProvider(Protocol):
    name: str
    embedding_model: EmbeddingModel

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
    async def complete(self, system: str, prompt: str, max_tokens: int = 400) -> str: ...
    async def caption_image(self, image: bytes) -> str: ...
    async def transcribe(self, audio: bytes) -> str: ...
    async def translate(self, text: str, target: str) -> str: ...
    async def toxicity(self, text: str) -> float: ...


class NoneProvider:
    name = "none"
    embedding_model = HASH_V1

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [hash_embedding(t) for t in texts]

    async def complete(self, system: str, prompt: str, max_tokens: int = 400) -> str:
        raise AIUnavailable("text generation")

    async def caption_image(self, image: bytes) -> str:
        raise AIUnavailable("vision")

    async def transcribe(self, audio: bytes) -> str:
        raise AIUnavailable("speech")

    async def translate(self, text: str, target: str) -> str:
        raise AIUnavailable("translation")

    async def toxicity(self, text: str) -> float:
        return rule_toxicity(text)


class CloudflareProvider(NoneProvider):
    name = "cloudflare"
    embedding_model = BGE_M3

    def __init__(self, account_id: str, token: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(20.0, connect=5.0),
        )

    async def _run(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = await self._http.post(model, json=payload)
        r.raise_for_status()
        result: dict[str, Any] = r.json()["result"]
        return result

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = (await self._run("@cf/baai/bge-m3", {"text": texts}))["data"]
        return out

    async def complete(self, system: str, prompt: str, max_tokens: int = 400) -> str:
        res = await self._run(
            "@cf/meta/llama-3.1-8b-instruct",
            {"messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "max_tokens": max_tokens},
        )
        return str(res.get("response", "")).strip()

    async def caption_image(self, image: bytes) -> str:
        res = await self._run(
            "@cf/llava-hf/llava-1.5-7b-hf",
            {"image": list(image), "prompt": "Describe this photo in one short sentence.", "max_tokens": 60},
        )
        return str(res.get("description", "")).strip()

    async def transcribe(self, audio: bytes) -> str:
        res = await self._run("@cf/openai/whisper", {"audio": list(audio)})
        return str(res.get("text", "")).strip()

    async def translate(self, text: str, target: str) -> str:
        res = await self._run("@cf/meta/m2m100-1.2b", {"text": text, "target_lang": target})
        return str(res.get("translated_text", "")).strip()


class AnthropicProvider(NoneProvider):
    """Claude for text generation. Embeddings and media stay on Workers AI when configured, else hash-v1/unavailable."""

    name = "anthropic"
    MODEL = "claude-haiku-5-5"

    def __init__(self, api_key: str, fallback: NoneProvider) -> None:
        self._fallback = fallback
        self.embedding_model = fallback.embedding_model
        self._http = httpx.AsyncClient(
            base_url="https://api.anthropic.com/v1/",
            timeout=httpx.Timeout(30.0, connect=5.0),
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await self._fallback.embed(texts)

    async def complete(self, system: str, prompt: str, max_tokens: int = 400) -> str:
        r = await self._http.post(
            "messages",
            json={
                "model": self.MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()

    async def caption_image(self, image: bytes) -> str:
        r = await self._http.post(
            "messages",
            json={
                "model": self.MODEL,
                "max_tokens": 80,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/webp",
                                    "data": base64.b64encode(image).decode(),
                                },
                            },
                            {"type": "text", "text": "Describe this photo in one short sentence for a social post. No hashtags."},
                        ],
                    }
                ],
            },
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text").strip()

    async def transcribe(self, audio: bytes) -> str:
        return await self._fallback.transcribe(audio)

    async def translate(self, text: str, target: str) -> str:
        return await self.complete(
            "Translate the user's text. Reply with the translation only.", f"Target language: {target}\n\n{text}"
        )


@lru_cache(maxsize=1)
def get_ai() -> AIProvider:
    s = get_settings()
    cf: NoneProvider = (
        CloudflareProvider(s.cloudflare_account_id, s.cloudflare_ai_token)
        if s.cloudflare_account_id and s.cloudflare_ai_token
        else NoneProvider()
    )
    if s.ai_provider == "anthropic" and s.anthropic_api_key:
        return AnthropicProvider(s.anthropic_api_key, cf)
    if s.ai_provider == "cloudflare" and isinstance(cf, CloudflareProvider):
        return cf
    return NoneProvider()
