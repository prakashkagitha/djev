"""A System One client that sends the *same bytes* for the same request.

Works against hosted Jev (https://api.typesafe.ai) and any /v1/systemone server,
including Deterministic Jev. Serializes each request body once, so repeats are
byte-identical; retries 429/529/5xx with backoff; records latency, model and hashes.
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import orjson

HOSTED = "https://api.typesafe.ai"


def body_bytes(request: dict) -> bytes:
    return orjson.dumps(request)


def answers_hash(answers: dict) -> str:
    return hashlib.sha256(orjson.dumps(answers, option=orjson.OPT_SORT_KEYS)).hexdigest()[:16]


@dataclass
class Backend:
    name: str
    base_url: str
    api_key: str | None = None
    model: str = "jev-latest"
    concurrency: int = 16

    @classmethod
    def hosted(cls, key_file: str | Path, model: str = "jev-1.13.0", concurrency: int = 16):
        return cls("hosted-jev", HOSTED, Path(key_file).read_text().strip(), model, concurrency)

    @classmethod
    def local(cls, name: str, url: str, model: str = "nimble-latest", concurrency: int = 32):
        return cls(name, url, None, model, concurrency)


class Client:
    def __init__(self, backend: Backend, timeout: float = 120):
        self.backend = backend
        headers = {"Content-Type": "application/json"}
        if backend.api_key:
            headers["Authorization"] = f"Bearer {backend.api_key}"
        self.http = httpx.AsyncClient(base_url=backend.base_url, headers=headers, timeout=timeout,
                                      limits=httpx.Limits(max_connections=backend.concurrency + 4))
        self.sem = asyncio.Semaphore(backend.concurrency)

    async def ask(self, raw: bytes) -> dict:
        """POST pre-serialized bytes; return {answers, model, ms, hash, fingerprint}."""
        async with self.sem:
            for attempt in range(8):
                t = time.perf_counter()
                try:
                    r = await self.http.post("/v1/systemone", content=raw)
                except httpx.TransportError:
                    await asyncio.sleep(1 + attempt)
                    continue
                if r.status_code in (429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 529):
                    await asyncio.sleep(float(r.headers.get("retry-after", 1 + attempt)))
                    continue
                if r.status_code == 422:
                    return {"error": r.json(), "status": 422}
                r.raise_for_status()
                d = r.json()
                return {"answers": d["answers"], "model": d.get("model"),
                        "ms": round((time.perf_counter() - t) * 1000, 1),
                        "hash": answers_hash(d["answers"]),
                        "fingerprint": r.headers.get("x-detjev-fingerprint"),
                        "usage": d.get("usage")}
        raise RuntimeError(f"{self.backend.name}: request kept failing")

    async def close(self):
        await self.http.aclose()
