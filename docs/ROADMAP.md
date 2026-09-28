# Repository plan: Deterministic Jev

**Mission:** an open home for System One decisions that must repeat. It holds:
- a reference deterministic server;
- a backend-agnostic replay test kit;
- use-case suites with established test sets;
- a determinism spec others can implement.

## Structure
| Path | Contents |
|---|---|
| `server/` | Jev-compatible `/v1/systemone` server. Includes fingerprint header, `--canonicalize`, exact memo, and (next) signed receipts. Today: `detjev/serve.py`. |
| `patches/` | Engine patches. Each patch has a regression test (`bench/pair_probe.py` style) and its upstream status. |
| `replaykit/` | Tests that run against any backend (hosted Jev, detjev, any `/v1/systemone`, or LLMs via TypeSafe's system-one-adapter): identical-bytes replay, drift under load, golden files across restart and GPU, invariance, retry attack. Today: `bench/`. |
| `tasks/<name>/` | `card.md` (why it must repeat, source, license, Jev cookbook it mirrors), `adapter.py` (dataset → Jev requests, downloads data and never redistributes it), gold labels, metrics. |
| `results/<task>/<backend>/<fingerprint>.json` | Result cards and raw outputs. The site renders these. |
| `spec/` | Determinism contract: fingerprint fields, receipt format, canonicalization rules, compliance test. |
| `site/` | The story, evidence, how-it-works and roadmap pages. |

## Result card
Every task × backend card has the same columns:
- accuracy / F1
- Brier and ECE
- replay rate (bit-identical under load)
- decision flips on identical bytes
- retry-attack pass@k
- invariance flips (key order, option order, nuisance field)
- p50 and p99 latency
- cost per million decisions
- fingerprint

## Candidate flagship use cases
| Use case | Jev cookbook it mirrors | Why it must repeat | Established tests |
|---|---|---|---|
| Guardrails / jailbreak screening | Guardrails for LLMs | A random guard falls to retries (10% pass → 65% within 10 tries); incident replay | WildGuardTest, XSTest, JailbreakBench, HarmBench classifier set, AgentDojo |
| Grounding / citation checks | Double-checking citations; Classifying RAG passages | CI release gates must not flake | LLM-AggreFact, RAGTruth |
| LLM judges for evaluation | Score primitive; composite scoring | Regressions vs noise; leaderboard stability | RewardBench, JudgeBench, MT-Bench human judgments |
| Agent routing / tool choice | Function calling; Skill suggestion; Intent routing | Replayable agent failures; pass^k | BFCL, τ-bench, CLINC150, Banking77 |
| Rule-based regulated decisions | Consistency cookbooks (claims, moderation) | Like cases alike; audit logs | LegalBench rule tasks, HateCheck, Nimble 324 held-out |

## Phases
- **v0.1 (now):** server, patches, replay kit, cookbook replays, hosted-Jev comparison, site.
- **v0.2:** flagship suite with result cards for hosted Jev, detjev and two open LLM baselines. Fingerprint includes patched sources.
- **v0.3:** three more suites, contributor guide, CI (CPU on every PR, GPU replay by maintainers), SGLang PR.
- **v1.0:** spec plus compliance test, public result board, cross-GPU-model determinism, deterministic MoE.

## Proofs of concept
1. Retry attack.
2. Flaky snapshot-test suite (100 CI runs).
3. Audit replay after restart, on another GPU and after a month.
4. Memo economics on dedupe-heavy batch jobs.
5. Leaderboard stability with a Score judge.
6. Drop-in base-URL swap from hosted Jev.

## Before going public
- Check TypeSafe's terms for publishing API measurements and for any use of Jev outputs.
- Check licenses for Nimble weights (Bespoke), openjev-sglang (ekzhang), and each dataset.
- Credit the upstream projects.
- Keep `typesafe_apikey.txt` out of git (`.gitignore`).
