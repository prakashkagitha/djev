"""Deterministic Jev: Nimble's trained prompt + openjev-sglang's Jev wire API,
connected to an already-running SGLang backend, with a determinism fingerprint.

Every response carries `x-detjev-fingerprint`: a hash of everything that can
change the bits of an answer (weights, prompt compiler, SGLang build and flags,
GPU SKU, probability temperature). The contract is: same fingerprint + same
request body -> bitwise-identical `answers`.

Usage:
  NIMBLE_MODEL_PATH=models/nimble-9b-merged python -m detjev.serve \
      --backend http://127.0.0.1:30020 --port 8020 [--canonicalize]
"""

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path

import httpx
import orjson
import uvicorn
from openjev.backend import Generation, SGLangClient
from openjev.config import Settings
from openjev.prompts import PreparedRequest
from openjev.runtime import wait_ready
from openjev.service import EvaluationService
from starlette.types import ASGIApp, Receive, Scope, Send
from transformers import AutoTokenizer

from nimble.scoring.calibration import served_temperature
from nimble.serving.compiler import NimbleCompiler
from nimble.serving.server import MODEL, make_app

# Server flags that can change numerics. Anything else (ports, log level) is excluded.
NUMERIC_FLAGS = (
    "version", "model_path", "dtype", "tp_size", "quantization", "kv_cache_dtype",
    "attention_backend", "prefill_attention_backend", "decode_attention_backend",
    "linear_attn_backend", "linear_attn_prefill_backend", "sampling_backend",
    "enable_deterministic_inference", "disable_radix_cache", "chunked_prefill_size",
    "mamba_radix_cache_strategy", "cuda_graph_backend_prefill", "disable_cuda_graph",
    "json_model_override_args", "context_length",
)


def canonical_state(value):
    """Canonical JSON form: sorted object keys, so key order in `state` cannot change bits."""
    if isinstance(value, str):
        return value
    return json.loads(json.dumps(value, sort_keys=True, ensure_ascii=False))


async def build_fingerprint(client: httpx.AsyncClient, model_path: Path, temperature: float,
                            canonicalize: bool) -> dict:
    info = (await client.get("/get_server_info")).json()
    flags = {k: info.get(k) for k in NUMERIC_FLAGS if k in info}
    ready = model_path / "READY.json"
    weights = json.loads(ready.read_text()).get("weight_sha256") if ready.exists() else None
    import nimble.scoring.parallel_schema as ps
    import nimble.serving.compiler as comp
    compiler = hashlib.sha256(Path(ps.__file__).read_bytes() + Path(comp.__file__).read_bytes()).hexdigest()
    gpu = os.popen("nvidia-smi --query-gpu=name --format=csv,noheader -i "
                   + os.environ.get("CUDA_VISIBLE_DEVICES", "0").split(",")[0]).read().strip()
    parts = {"weights": weights or str(model_path), "compiler_sha256": compiler,
             "serve_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "sglang": flags,
             "gpu": gpu, "temperature": temperature, "canonicalize": canonicalize,
             "align_warmup": os.environ.get("DETJEV_ALIGN_WARMUP", "1"),
             "fa3_align": os.environ.get("SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE")}
    digest = hashlib.sha256(orjson.dumps(parts, option=orjson.OPT_SORT_KEYS)).hexdigest()[:16]
    return {"fingerprint": digest, "parts": parts}


class ResponseMemo:
    """Exact memo of /v1/systemone responses keyed by the request bytes.

    Only sound because answers are a pure function of (request bytes, fingerprint);
    on a non-deterministic server this would silently freeze one noisy sample."""

    def __init__(self, app: ASGIApp, capacity: int):
        from collections import OrderedDict
        self.app, self.capacity, self.store = app, capacity, OrderedDict()

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["path"] != "/v1/systemone" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            event = await receive()
            body.extend(event.get("body", b""))
            if not event.get("more_body", False):
                break
        key = hashlib.sha256(bytes(body)).digest()
        if key in self.store:
            self.store.move_to_end(key)
            status, headers, payload = self.store[key]
            await send({"type": "http.response.start", "status": status,
                        "headers": headers + [(b"x-detjev-memo", b"hit")]})
            return await send({"type": "http.response.body", "body": payload})
        delivered, captured = False, {"body": bytearray()}

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def capture(message):
            if message["type"] == "http.response.start":
                captured["status"], captured["headers"] = message["status"], list(message.get("headers", []))
            else:
                captured["body"].extend(message.get("body", b""))
                if not message.get("more_body", False) and captured.get("status") == 200:
                    self.store[key] = (200, captured["headers"], bytes(captured["body"]))
                    if len(self.store) > self.capacity:
                        self.store.popitem(last=False)
            await send(message)

        return await self.app(scope, replay, capture)


class FingerprintHeader:
    def __init__(self, app: ASGIApp, fingerprint: dict):
        self.app = app
        self.fp = fingerprint

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (b"x-detjev-fingerprint", self.fp["fingerprint"].encode()))
                deterministic = self.fp["parts"]["sglang"].get("enable_deterministic_inference")
                message["headers"].append(
                    (b"x-detjev-deterministic", b"1" if deterministic else b"0"))
            await send(message)

        return await self.app(scope, receive, send_with_header)


# Hybrid (Gated DeltaNet) layers checkpoint their recurrent state on a 64-token grid.
# Warming the shared prefix to a grid boundary makes its checkpoint the exact fp32 final
# state, so every question branch resumes from it bit-for-bit (see patches/).
CHECKPOINT_GRID = 64


class DetCompiler(NimbleCompiler):
    def __init__(self, *args, canonicalize=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.canonicalize = canonicalize

    def prepare(self, request):
        if self.canonicalize:
            request = request.model_copy(update={"state": canonical_state(request.state)})
        prepared = super().prepare(request)
        if os.environ.get("DETJEV_ALIGN_WARMUP", "1") == "0":  # upstream behaviour, for baselines
            return prepared
        if len(prepared.branches) == 1:
            # Nothing to share: one prefill of prefix + question costs the same as stock
            # warm-up + branch, and skips an extra round trip.
            return PreparedRequest([], prepared.branches)
        aligned = len(prepared.prefix_ids) // CHECKPOINT_GRID * CHECKPOINT_GRID
        return PreparedRequest(prepared.prefix_ids[: max(aligned, 1)], prepared.branches)


class DetClient(SGLangClient):
    async def generate(self, input_ids, label_ids=None):
        if not input_ids:  # warm-up skipped by DetCompiler
            return Generation(logprobs=[], input_tokens=0, output_tokens=0, cached_tokens=0)
        return await super().generate(input_ids, label_ids)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="http://127.0.0.1:30020")
    ap.add_argument("--port", type=int, default=8020)
    ap.add_argument("--canonicalize", action="store_true")
    ap.add_argument("--max-concurrent-requests", type=int, default=64)
    ap.add_argument("--memo", type=int, default=0, help="exact response memo capacity (0 = off)")
    args = ap.parse_args()

    path = Path(os.environ["NIMBLE_MODEL_PATH"]).resolve()
    ready = path / "READY.json"
    temperature = served_temperature(json.loads(ready.read_text())) if ready.exists() else 1.0
    settings = Settings(model=str(path), served_model_name=MODEL, model_alias="nimble-latest",
                        backend_url=args.backend, max_input_tokens=8193,
                        max_total_input_tokens=64 * 8193,
                        max_concurrent_requests=args.max_concurrent_requests,
                        max_concurrent_branches=64, temperature=temperature)
    async with httpx.AsyncClient(base_url=args.backend, timeout=600,
                                 limits=httpx.Limits(max_connections=128)) as client:
        backend = DetClient(settings, client)
        await wait_ready(backend, None, 1200)
        fp = await build_fingerprint(client, path, temperature, args.canonicalize)
        print("fingerprint", json.dumps(fp, indent=1), flush=True)
        compiler = DetCompiler(AutoTokenizer.from_pretrained(path, local_files_only=True),
                               max_prompt_tokens=8192, canonicalize=args.canonicalize)
        app = make_app(settings, EvaluationService(settings, compiler, backend))

        @app.get("/v1/fingerprint")
        async def fingerprint():
            return fp

        asgi = FingerprintHeader(app, fp)
        if args.memo:
            asgi = ResponseMemo(asgi, args.memo)
        server = uvicorn.Server(uvicorn.Config(asgi, host="127.0.0.1",
                                               port=args.port, access_log=False))
        await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
