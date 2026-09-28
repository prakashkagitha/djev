# Deterministic Jev

**Decisions that repeat.** An open System One server that speaks TypeSafe's Jev API (`POST /v1/systemone`: noul, choice, score). The same request bytes always get the same answer, down to the last bit, however busy the GPU is. The repo also holds a replay test kit for any Jev-compatible backend, and task suites where repeatable decisions matter.

- **Evidence and story:** results page (private artifact, share when ready): https://claude.ai/code/artifact/c31af720-f352-4016-9d34-27c4c84ff57d
- **Contract:** [`spec/determinism.md`](spec/determinism.md)
- **Roadmap:** [`docs/ROADMAP.md`](docs/ROADMAP.md)

## Headline results (one H100 NVL, 2026-09-28)

| | Hosted Jev 1.13 | Stock SGLang serving | **Deterministic Jev** |
|---|---|---|---|
| TypeSafe claim cookbook, 15 identical calls | 15 distinct answer sets; `covered` flips yes/no | 7–15 distinct | **1** |
| Guardrail suite: messages whose action changed on identical calls (of 2,236) | 44 | 16 | **0** |
| Unsafe messages that pass on some calls and are stopped on others (of 954) | 15 | 4 | **0** |
| Guardrail F1 (strict policy) | 0.749 | 0.791 | 0.791 |
| Guard call latency, 1 at a time | 144 ms | 121 ms | 122 ms |
| Held-out decision requests identical under load (720 repeats) | n/a | 12 | **720** |
| 324 decisions after restart / on a second GPU | n/a | 1 | **324 / 324** |

Caveats:
- **Different models.** Hosted Jev is a different, larger model. Deterministic Jev serves Bespoke-Nimble-9B, which misses some jailbreaks that Jev catches, TypeSafe's own `neurosemantical` example among them.
- **Throughput.** One H100 serves about 20 guard calls per second.
- **Scope of the promise.** Determinism means identical bytes give identical answers. It is not correctness, and it is not invariance to rephrasing. See the Evidence page.

## Layout
```
server/detjev/        Jev-compatible server: fingerprint header, --canonicalize, --memo (exact response memo)
patches/              SGLang 0.5.19 patches: aligned mamba checkpoints in deterministic mode,
                      fa3 prefill split alignment, mixed-logprob batch crash fix
replaykit/            backend-agnostic tests: client (same bytes every time), engine/pair probes,
                      drift under load, golden files, invariance, latency, hosted-Jev probe
tasks/
  guardrails/         FLAGSHIP: TypeSafe's guardrail battery verbatim on XSTest, ToxicChat,
                      in-the-wild jailbreaks, JailbreakBench (card.md, datasets, run, analyze)
  typesafe_consistency/  TypeSafe's two self-consistency cookbooks, 4 conditions, any backend
  nimble_holdout/     accuracy/calibration on Nimble's 324 Jev-format held-out requests
results/              raw outputs + cards (core/ = engine and API experiments, guardrails/, typesafe_consistency/)
spec/                 the determinism contract
site/                 results page (template + builders)
docs/                 roadmap, original plan, research notes (TypeSafe framing, cookbook payloads)
scripts/              launch and experiment scripts (GPU 3 by default; GPU=<n> to change)
tests/                CPU tests (pytest)
```

## Quick start
```bash
# 1. Engine: SGLang 0.5.19 + patches
uv venv .venv && VIRTUAL_ENV=.venv uv pip install --prerelease=allow sglang==0.5.19 ninja
for p in patches/*.patch; do patch -p0 -d .venv/lib/python3.12/site-packages < "$p"; done   # see patches/README

# 2. API env: openjev-sglang @7f84bedc + Bespoke Nimble (cloned next to this repo), merge the LoRA
uv venv .venv-api && VIRTUAL_ENV=.venv-api uv pip install -e ./openjev-sglang transformers==5.17.0 peft torch pandas

# 3. Serve (deterministic) and call it
SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64 scripts/serve_bg.sh detjev models/nimble-9b-merged 1 30020 \
  --json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193
scripts/api_up.sh detjev            # add --canonicalize / --memo 100000
curl -si localhost:8020/v1/systemone -H 'Content-Type: application/json' -d @openjev-sglang/examples/request.json | grep -i detjev

# 4. Run the flagship suite against any backend
python -m tasks.guardrails.datasets
python -m tasks.guardrails.run --backend local --url http://127.0.0.1:8020 --name detjev --repeats 5
python -m tasks.guardrails.run --backend hosted --repeats 10          # needs typesafe_apikey.txt
python -m tasks.guardrails.analyze detjev hosted-jev
```

## Contributing
- **Add a task:** create `tasks/<name>/` with `card.md` (why it must repeat, source, license, and which Jev cookbook it mirrors), a dataset adapter that downloads from the source, `run.py` and `analyze.py`.
- **Add a backend:** anything that serves `/v1/systemone` works with `replaykit.client.Backend`.
- **Add an engine fix:** a patch plus a probe (`replaykit/pair_probe.py` style) that fails before the fix and passes after.
- **Results PRs:** include the raw JSON and the server fingerprint.

## Credits
- [ekzhang/openjev-sglang](https://github.com/ekzhang/openjev-sglang): wire API and one-token readout.
- [Bespoke Nimble](https://github.com/bespokelabsai/nimble): model and prompt compiler.
- [SGLang](https://github.com/sgl-project/sglang): deterministic inference.
- TypeSafe: [cookbooks](https://docs.typesafe.ai/cookbooks) whose batteries and requests are reproduced here with attribution.
- Datasets: XSTest, ToxicChat, In-the-wild jailbreak prompts, JailbreakBench.

Before publishing: confirm TypeSafe's terms for publishing API measurements, and the licenses of Nimble, openjev-sglang and each dataset. The license for this repository is still to be chosen.
