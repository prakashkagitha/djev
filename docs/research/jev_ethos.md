# Deterministic Jev: situating it in TypeSafe's framing

Sources were read 2026-09-28. Quotes are verbatim. **[inferred]** marks our own reading, not a TypeSafe statement.
Short URLs used below: **B** = typesafe.ai/blog/introducing-system-one-models-and-jev · **S1** = docs.typesafe.ai/concepts/system-one · **NC** = docs.typesafe.ai/cookbooks/consistency_noul_cookbook · **CC** = …/consistency_choice_cookbook · **M** = docs.typesafe.ai/models · **J** = docs.typesafe.ai/model-jaggedness/jev-1.13 · **E** = evals.typesafe.ai

## 1. Jev's thesis, in their words

- **System One vs System Two.** The name comes from Kahneman: "System 1 thinking is fast and intuitive. System 2 is slower and more deliberate. Here, the emphasis is on fast, focused judgments." (S1). Jev "does the best on System One tasks. It may struggle with tasks that require additional levels of indirection." (J)
- **Decisions as typed functions.** "Think of Jev as a frontier-intelligence function call: unstructured state in, typed probabilistic decisions out." (B). It has three primitives: Choice, Score, and Noul (P(true)). "Every *question* is evaluated in parallel and in isolation against the same *state* in one go." (docs.typesafe.ai/introduction)
- **Machine-to-machine framing.** Their target is "AI with software-like properties such as structure, reliability, observability, testability, speed, consistency, and low cost." (docs.typesafe.ai/introduction/machine-learning-primer)
- **Why probabilities and calibration.** "If a model can do a task 95% of the time but doesn't say when it's in the 5%, it can't automate that task." (B). The model is trained with RLCD, which optimises for "answers with epistemically honest probabilities on System One tasks." (B). They add a caveat: calibration "does not guarantee that an individual answer is correct." (S1)
- **Never hallucinates, schema by construction.** "Possible outputs and structure are defined in advance. The model never makes type errors." (B) On the 0% figure: "Our number is not empirical. Schema matching is guaranteed" (B)
- **Cost and latency.** "Input tokens: $0.042 / MTok ($42 per billion tokens). Output tokens: FREE (too cheap to meter)." (B) "End-to-end response time is 70ms-500ms" versus "3 to 329 seconds" for frontier models (B). The homepage figures of 193.6x faster and 444.6x cheaper come from the workflow evals, which TypeSafe itself calls "on the higher end of real world gains" (B). Rate limits are 250k tok/s and 1,200 req/min, with 64k context (M).
- **Target use cases.** "AI-Powered Workflows / smart if-statements", "Map-reducing over big data", "Real-time applications", and "Verify everything. Score, judge, verify, guardrail, and detect jailbreaks" (B). The use-case map (docs.typesafe.ai/concepts/use-case-map) lists classification, detection (spam, fraud, jailbreaks), scoring, routing ("Tool use, escalation, model routing, support queues"), search, ranking, verification, ML feature extraction and structured data extraction.
- **Consistency is part of the pitch.** "More consistent: returns similar answers for similar inputs." (B) "System One is designed to return stable answers across repeated evaluations." (docs.typesafe.ai/concepts/how-to-build-with-system-one)
- **Workflow evals (E).** Reference is GPT-6 Astra plus Claude Fable 5.1 at high thinking. Jev scores 67.8% at $0.0004 and 0.4 s per case; opus 5 scores 73.1% at $0.1761 and 37.8 s.

## 2. What TypeSafe says about consistency and determinism

TypeSafe never claims determinism. Its two cookbooks each take one borderline case and repeat the call 15 times per condition. Both used `jev-latest`, which resolved to `jev-1.13.0` on all 15 calls. They were "sampled on 2026-09-11". Each call also carries **a fresh `uid` field**, and the cookbooks say this "cannot separate sensitivity to the irrelevant field from variation that would occur on identical requests." (NC, CC) **[inferred]** So their numbers put an upper bound on identical-request noise plus sensitivity to that nuisance field. The public API also exposes no temperature or seed control (docs.typesafe.ai/api).

**Noul cookbook (NC).** One auto-insurance claim with 14 Noul questions, run 15 times. The comparison conditions were claude-haiku-4-5 and gpt-5.4-mini (at t=0, at the default temperature, and as t=0 yes/no), plus gpt-5.5 and claude-opus-4-8 with reasoning.
- Jev's "mean per-question probability standard deviation is `0.0102`, below all LLM probability conditions here." The LLM per-condition standard deviations are not printed.
- `covered` spans "`0.43` to `0.53`, crossing a `0.5` decision threshold". `exclusion` spans `0.53` to `0.62`. The other 13 questions stay on one side of 0.5.
- They offer an "uncertain" band from 0.30 to 0.70 and note that it "is no more deterministic for it".

**Choice cookbook (CC).** One borderline moderation post with 8 Choice questions, run 15 times, using the same models.
- "TypeSafe flips on 2 of the 8 questions": `primary_risk` came back Harassment 11 times and Violence 4 times, and `link_handling` came back RmLink 8 times and Brigade 7 times.
- Under a rule of top probability ≥0.60, otherwise "uncertain", agreement is 90.8% before and 99.2% after, and 74.2% of answers are automatic. "Haiku at temperature 0 had 100% agreement here, with no abstentions."
- "This policy does not make the model deterministic."

**Table to re-plot** (all numbers exact from the pages. "—" means the page does not report it):

| Condition | Choice mean prob std | Choice max std | Choice raw agree | Choice policy agree (≥0.60) | Choice automatic | Choice conflicts | Choice ms/call | Choice $/call | Noul ms/call | Noul $/call |
|---|---|---|---|---|---|---|---|---|---|---|
| haiku-4-5 t=0 | 0.0012 | 0.0221 | 100.0% | 100.0% | 100.0% | 0 | 3853 | 0.003498 | 1780 | 0.001798 |
| haiku-4-5 t=default | 0.0516 | 0.3150 | 87.5% | 86.7% | 98.3% | 2 | 3860 | 0.003494 | 1644 | 0.001798 |
| haiku-4-5 single-pick/yes-no t=0 | — | — | — | — | — | — | 992 | 0.001527 | 1485 | 0.001650 |
| gpt-5.4-mini t=0 | 0.0312 | 0.0905 | 99.2% | 87.5% | 87.5% | 0 | 2293 | 0.002299 | 1405 | 0.001089 |
| gpt-5.4-mini t=default | 0.0543 | 0.2303 | 90.8% | 84.2% | 77.5% | 2 | 1986 | 0.002164 | 1177 | 0.001179 |
| gpt-5.4-mini single-pick/yes-no t=0 | — | — | — | — | — | — | 826 | 0.000936 | 1113 | 0.000950 |
| gpt-5.5 reasoning | 0.0305 | 0.1047 | 90.0% | 93.3% | 69.2% | 1 | 12978 | 0.041255 | 11125 | 0.033157 |
| claude-opus-4-8 reasoning | 0.0245 | 0.0693 | 92.5% | 94.2% | 66.7% | 0 | 10376 | 0.028375 | 13886 | 0.034275 |
| **Jev (jev-1.13.0)** | **0.0098** | **0.0515** | **90.8%** | **99.2%** | **74.2%** | **0** | **114** | **0.000046** | **111** | **0.000043** |

Jev's Noul mean std is 0.0102. Costs use "historical price assumptions" (NC, CC).

One more relevant statement comes from J: "`jev-1.13` is extremely consistent, meaning you should expect quantitatively similar outputs for semantically similar inputs." The same page lists structural invariants that do not hold. For example, a Noul and its negation sum to 1.19.

## 3. Gaps a deterministic open implementation addresses

Deterministic Jev targets one property: **the same request bytes, model, and version produce bitwise-identical probabilities.** This is SGLang deterministic inference with batch-invariant kernels. The table below maps each gap to a TypeSafe use case.

| Gap | Why it matters for "smart if-statements" |
|---|---|
| **Replay / debuggability** | A claims-triage decision that crossed 0.5 (NC `covered`: 0.43–0.53) can be re-run and gives the *same* number. You debug the input, not the sampler. |
| **Golden / snapshot tests** | TypeSafe's own cookbooks ship a `json_cache.json` so that re-rendering "reproduces the published numbers". Determinism makes that unnecessary: a test can assert `p == 0.4731…` exactly, with no tolerance bands and no flaky tests. |
| **Audit / compliance** | For insurance, lending and moderation appeals, a regulator or appeal can re-derive the exact score from logged state and model hash. DataCamp's explainer names an audit gap for regulated scoring. |
| **Caching / memoization** | When the function is pure, `hash(state, questions, model)` is a correct cache key. Map-reduce over big data can dedupe inputs and resume jobs without drift. |
| **CI regressions** | Any change in output comes from a code, prompt or model change, never from noise. A prompt edit can be diffed exactly across a golden set. TypeSafe warns that aliases move silently (M: pin `jev-1.13.0`). |
| **A/B safety** | Differences between arms are attributable to the treatment. You don't need 15 repeats per condition to separate signal from 0.01-std jitter. |
| **Agent loops** | Skill selection, function calling, and routing inside agents get stable branching. The same trace replays down the same path, so failures are reproducible. With CC-style label flips such as 8/7 RmLink/Brigade, a replay can take a different branch. |
| **Self-hosting / privacy** | Jev is hosted-only. Its ZDR is enterprise-only (M), and rate limits "can change without notice" (M). A self-hosted server keeps PHI/PII on-prem and removes the dependency on quotas. |
| **Pricing** | Jev is already cheap at $0.042/MTok. Self-hosting trades that for fixed GPU cost. **[inferred]** This wins mainly at very high volume, in air-gapped deployments, or once cache hit rates are high. |

## 4. Future prospects and scope

- **Cross-hardware determinism:** bitwise-identical results across GPU SKUs and TP sizes, not only within one node.
- **Signed decision receipts:** each response carries `sha256(request ‖ weights ‖ kernel-config ‖ output)`, signed by the server.
- **Decision provenance logs:** append-only logs that support exact replay, for audit.
- **Deterministic fine-tuning and calibration:** reproducible RLCD-style calibration runs and temperature scaling with fixed seeds.
- **Order-invariance:** make answers invariant to state key order and question order, and to batch composition, which is already the goal.
- **Nuisance-field invariance:** test against TypeSafe's `uid` perturbation explicitly and report sensitivity separately from noise.
- **On-device / edge:** small deterministic decision models for offline guards.
- **MoE determinism:** routing that is invariant to batch composition.
- **Wire compatibility:** drop-in `POST /v1/systemone`, so users can run the same cookbook against both backends.

## 5. Honest caveats

- **Determinism is not correctness.** A deterministic wrong answer is wrong every time. It is not calibration either, and not accuracy on E's workflows.
- **It is not robustness to paraphrase.** A single changed byte, such as the `uid` field, may legitimately change the output. Determinism only holds the answer fixed for identical requests.
- **Stable is not good.** TypeSafe's own finding that Haiku at t=0 hit 100% agreement shows repeatability alone is a weak quality signal.
- **Comparisons with Jev must be fair.** Jev's measured variance *includes* the `uid` perturbation, so it is not pure identical-request noise. A hosted service may also cache, batch, or change silently behind an alias. Compare against the pinned `jev-1.13.0`, report identical-request and perturbed-request results separately, and do not claim Jev is "non-deterministic" beyond what was measured.
- **Deterministic modes cost throughput.** Batch-invariant kernels usually run slower. Measure the latency and cost overhead and publish it.
- **Model quality is separate.** An open model behind the same wire format will not match Jev's accuracy or calibration by default. Evaluate it on E-style workflows and publish the nuance, which is TypeSafe's own norm ("Disclose the nuance in your evals", B).

Third-party sources: flaviocopes.com/jev, truefoundry.com/blog/typesafe-ai-jev, datacamp.com/blog/system-one-models-jev.
