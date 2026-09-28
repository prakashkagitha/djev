# djev: Deterministic Jev

**Jev-compatible decisions that repeat, bit for bit.**

djev is an open, self-hosted server for TypeSafe's [Jev API](https://docs.typesafe.ai/api): `POST /v1/systemone` with `noul`, `choice` and `score` questions. The same request bytes always return the same probabilities, whatever else is running on the GPU, after a restart, and on another GPU of the same model.

<p align="center"><img src="assets/hero/djev.gif" width="900" alt="The same insurance-claim request sent 15 times: hosted Jev answers YES 6 times and NO 9 times with 15 different answer hashes; djev returns one identical answer 15 times. Below: 720/720 repeats bit-identical under load, guardrail decision changes 44 to 0, 324/324 decisions replayed after restart and on another GPU."></p>

Jev is built as a fast decision function for software: routing, triage, moderation and guardrails. Code that branches on a decision needs the same input to take the same branch. Otherwise the decision cannot be replayed when debugging, cannot be pinned in a test, cannot be re-derived for an audit, and, for a guardrail, can be beaten by sending the same message again.

## How djev works

| Layer | What we use |
|---|---|
| **API** | [openjev-sglang](https://github.com/ekzhang/openjev-sglang) (`7f84bedc`): Jev wire format. Each question is scored by a single prefill and a one-token read of the option log-probabilities, with no text generation |
| **Model** | [Bespoke-Nimble-9B](https://huggingface.co/bespokelabs/Bespoke-Nimble-9B): a LoRA trained for Jev-style decisions on [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B), merged to BF16. Qwen3.5 is a **hybrid** model: Gated DeltaNet linear-attention layers interleaved with full attention |
| **Engine** | [SGLang](https://github.com/sgl-project/sglang) 0.5.19 with `--enable-deterministic-inference`, the fa3 attention backend, prefix caching on, CUDA graphs on, plus **djev's patches** |
| **Hardware** | One NVIDIA H100 NVL (94 GB), CUDA 13 |

**Where nondeterminism comes from.** A GPU kernel's arithmetic order depends on the batch around it: how many requests share a matrix multiply, how attention splits its work, where a long prompt is cut into chunks. Floating-point addition is not associative, so the same request gets slightly different logits depending on the other traffic. Temperature 0 does not change this. Thinking Machines Lab named the missing property *batch invariance* ([Defeating Nondeterminism in LLM Inference](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/)). SGLang then shipped batch-invariant kernels behind `--enable-deterministic-inference` ([LMSYS, 2025](https://www.lmsys.org/blog/2025-09-22-sglang-deterministic/)). On dense transformers that flag is enough: Qwen3-8B returned 300/300 bit-identical repeats in our probe.

**What was still broken.** The open Jev-style models run on the hybrid Qwen3.5/3.6 family, and there the flag was not enough: 22 of 300 repeats still drifted under load. We traced the drift to prefix caching of the linear-attention state:
- Gated DeltaNet carries a recurrent state computed in 64-token chunks.
- When SGLang caches that state partway through a prompt, it copies it from the chunk kernel's intermediate buffer, which is bf16 (`kernels/ops/attention/fla/chunk_delta_h.py`). The running state is fp32.
- A request that resumes from that copy gets different numbers from one that recomputes. Whether a request resumes depends on what the cache holds at that moment, so the answer depends on traffic.

<p align="center"><img src="assets/root_cause.png" width="760" alt="Resuming from a mid-chunk bf16 checkpoint gives different bits; resuming from a 64-aligned fp32 state gives identical bits"></p>

**djev's changes.**
1. **Aligned exact checkpoints** ([patch](patches/sglang-0.5.19-det-mamba-checkpoint.patch)). In deterministic mode, recurrent-state checkpoints are saved only where a prefill ends exactly on the 64-token grid, where the state is the exact fp32 state. The engine probe goes from 278/300 to **300/300** bit-identical.
2. **Aligned prefill splits for fa3** ([patch](patches/sglang-0.5.19-fa3-truncation-align.patch), `SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64`). A long prompt split under load resumes on the grid too. Without it, 700/720; with it, **720/720**.
3. **Server design** ([`server/detjev/serve.py`](server/detjev/serve.py)):
   - **Aligned warm-up.** Multi-question requests warm the shared state to a 64-token boundary, so every question reuses an exact checkpoint.
   - **Fast path.** Single-question requests take one prefill.
   - **`--memo`.** An exact response cache, which is only sound because answers are a pure function of the request bytes.
   - **`--canonicalize`.** Sorts the keys of `state`.
   - **Fingerprint header.** Each response carries a hash of the weights, prompt code, engine version and flags, and GPU model. The [determinism contract](spec/determinism.md) is defined over this fingerprint.

A third patch fixes an unrelated crash when logprob and plain requests share a batch ([sglang#34719](https://github.com/sgl-project/sglang/issues/34719)).

**Cost.** For this workload, determinism is almost free:
- Median decision: 51 ms, against 50 ms with SGLang's default mode.
- Throughput: 45 decisions/s at 32 concurrent requests, the same in both modes.
- Exact repeats: served from the memo at 344 decisions/s.

## Next steps
1. **Upstream the fix and widen model coverage.** Propose the aligned-checkpoint patch to SGLang with a regression test. Then verify more hybrid and mixture-of-experts models, starting with Qwen3.6-35B-A3B, which fits on one H100 in FP8.
2. **Grow the guardrail suite into the reference test.** Add WildGuardTest and the output-side battery (XSTest responses), and compare against open guard models such as Llama Guard and WildGuard.
3. **Close the quality gap without losing determinism.** Make decisions stable under option order, a known weakness (9 flips in 146), by scoring symmetric permutations. Train or calibrate on the misses the suite surfaces, and run each new model through the same replay tests before release.

## Results

### TypeSafe's consistency cookbooks, identical requests
We rebuilt TypeSafe's two [self-consistency cookbooks](https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook) (a moderation post with 8 choice questions, an insurance claim with 14 yes/no questions) and scored them with their published metrics. We added one column: how many different answer sets came back when the same request bytes were sent 15 times.

| 15 identical calls | Moderation: agreement / mean prob std / distinct answers | Insurance claim: agreement / mean prob std / distinct answers |
|---|---|---|
| Hosted Jev 1.13 | 95.0% / 0.0092 / **15 of 15** | 97.1% / 0.0099 / **15 of 15** (`covered`: 6 yes, 9 no) |
| **djev** | **100% / 0.0000 / 1 of 15** | **100% / 0.0000 / 1 of 15** |

<p align="center"><img src="assets/consistency.png" width="760" alt="TypeSafe's consistency table with hosted Jev and djev rows added"></p>

### Guardrails: a decision you cannot retry past
We ran TypeSafe's [guardrail cookbook](https://docs.typesafe.ai/cookbooks/llm_guardrails) unchanged: four hazard questions, a severity score, and their pass/review/block/support routing. The data was 2,236 messages from XSTest, ToxicChat, in-the-wild jailbreak prompts and JailbreakBench, each message sent byte for byte 10 times to hosted Jev and 5 times to djev.

<p align="center"><img src="assets/guardrail.gif" width="760" alt="Hosted Jev blocks an unsafe request 7 times and passes it 3 times; djev blocks it every time"></p>

| Strict policy | Hosted Jev 1.13 | djev |
|---|---|---|
| Messages whose action changed between identical calls | 44 | **0** |
| Unsafe messages that got through on some calls only | 15 of 954 | **0** |
| Unsafe caught / safe wrongly flagged | 68.4% / 10.6% | 74.4% / 10.3% |

Load, restart and second-GPU replays, accuracy, engine probes and the full tables are in **[docs/EVIDENCE.md](docs/EVIDENCE.md)**.

## Limitations
- **Determinism is not correctness.** djev's model misses some jailbreaks that hosted Jev catches, including TypeSafe's own “Neurosemantical Inversitis” example. On Nimble's held-out set it scores 87.0%; Bespoke reports 93.2% for Jev 1.13. A repeatable miss can be tested and fixed, but it is still a miss.
- **Identical bytes, not identical meaning.** Reordering options or adding an irrelevant field can change an answer. `--canonicalize` removes the effect of key order only.
- **One fingerprint at a time.** Answers repeat for a fixed model, engine version, flags and GPU model. Agreement across GPU models or tensor-parallel sizes is not yet tested.
- **Throughput.** One H100 serves about 20 five-question guard calls per second. The median guard call takes 122 ms, against 121 ms with SGLang's default mode.

## Quick start
```bash
git clone https://github.com/prakashkagitha/djev && cd djev
# engine: SGLang 0.5.19 + patches (see patches/README.md)
uv venv .venv && VIRTUAL_ENV=.venv uv pip install --prerelease=allow sglang==0.5.19 ninja
# api: openjev-sglang@7f84bedc and Bespoke Nimble cloned next to this repo; merge the LoRA into Qwen3.5-9B
uv venv .venv-api && VIRTUAL_ENV=.venv-api uv pip install -e ./openjev-sglang transformers==5.17.0 peft torch pandas matplotlib pytest
( cd nimble && ../.venv-api/bin/python -m nimble.scoring.merge_local_adapter \
    --adapter <Bespoke-Nimble-9B snapshot> --output ../models/nimble-9b-merged --base <Qwen3.5-9B snapshot> )

# serve (GPU 3 by default; GPU=<n> to change)
SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64 scripts/serve_bg.sh djev models/nimble-9b-merged 1 30020 \
  --json-model-override-args '{"language_model_only": true}' --mamba-radix-cache-strategy extra_buffer --context-length 8193
scripts/api_up.sh djev                      # optional: --canonicalize, --memo 100000

# benchmarks (hosted runs read typesafe_apikey.txt, which is gitignored)
python -m tasks.typesafe_consistency.run --backend local --name djev
python -m tasks.guardrails.datasets && python -m tasks.guardrails.run --backend local --name djev --repeats 5
python -m tasks.guardrails.analyze djev
pytest -q tests
```

## Repository
```
server/detjev/   the Jev-compatible deterministic server       patches/   SGLang patches, each with its evidence
replaykit/       determinism tests for any /v1/systemone        tasks/     guardrails · typesafe_consistency · nimble_holdout
results/         raw outputs and result cards                   spec/      the determinism contract
docs/            EVIDENCE.md, ROADMAP.md                        site/      figure and results-page builders
```
Contributions are welcome:
- **New tasks.** Add them under `tasks/<name>/` with a card explaining why the decision must repeat.
- **New backends.** Any `/v1/systemone` server works with `replaykit`.
- **Engine fixes.** Include a probe that fails before the fix and passes after.

## Credits
- [TypeSafe](https://typesafe.ai) for Jev and the cookbooks, whose requests, guardrail battery and metrics are reproduced here with attribution.
- [ekzhang/openjev-sglang](https://github.com/ekzhang/openjev-sglang).
- [Bespoke Labs Nimble](https://github.com/bespokelabsai/nimble).
- [SGLang](https://github.com/sgl-project/sglang).
- [Thinking Machines Lab](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/).
- Datasets: XSTest, ToxicChat, In-the-wild jailbreak prompts, JailbreakBench.

djev is independent and not affiliated with TypeSafe. Hosted-Jev results were measured through the public API on 2026-09-28 with `jev-1.13.0`, and may change with later versions.

## License
[MIT](LICENSE) for djev's code, patches and results. Upstream models, datasets and TypeSafe's cookbook content remain under their own terms.
