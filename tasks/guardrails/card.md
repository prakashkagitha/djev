# Task: guardrails

**What it tests.** Screening a user message before it reaches an LLM, with TypeSafe's guardrail cookbook applied verbatim: four Noul hazards (jailbreak, harmful request, medical advice, self-harm) and one severity Score, routed by `route()` into pass, review, block or support under the cookbook's `strict` and `permissive` policies.

**Why it must repeat.**
- **Retry attack.** A guard is a security boundary. If an unsafe message passes on some calls and not others, an attacker who resends the same bytes will eventually get through. The chance of success within k tries is 1 − (1 − p)^k.
- **Incident review.** Reviewers need to replay the verdict that was actually given.
- **Regression tests.** Tests over guard decisions must not flake.

**Jev fit.** TypeSafe's use-case map lists "Verify everything. Score, judge, verify, guardrail, and detect jailbreaks." The battery, thresholds and routing come from the [Guardrails for LLMs](https://docs.typesafe.ai/cookbooks/llm_guardrails) cookbook (jev-1.12, 2026-08-15).

## Data (`data/guardrails_v1.jsonl`, built by `datasets.py`; not redistributed)
| Source | Items | Unsafe | Label used |
|---|---|---|---|
| [XSTest](https://github.com/paul-rottger/xstest) (Röttger et al., NAACL 2024) | 450 | 200 | `label == unsafe`. Its 250 safe prompts measure over-blocking |
| [ToxicChat](https://huggingface.co/datasets/lmsys/toxic-chat) 0124 test (Lin et al., 2023) | 987 | 354 | `toxicity == 1`. Includes the human-labelled jailbreaks |
| [In-the-wild jailbreak prompts](https://huggingface.co/datasets/TrustAIRLab/in-the-wild-jailbreak-prompts) (Shen et al., CCS 2024), 2023-12-25 | 599 | 300 | Jailbreak vs regular. The cookbook drew its jailbreaks from this set, and its `neurosemantical` example is included |
| [JailbreakBench behaviors](https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors) (Chao et al., 2024) | 200 | 100 | Harmful vs benign goals |

Two sources are pending Hugging Face access approval: WildGuardTest (`allenai/wildguardmix`), and XSTest responses (`allenai/xstest-response`) for the output-side battery.

## Metrics (`analyze.py`)
- **Detection.** Recall on unsafe, false-positive rate on safe, and F1. A message counts as flagged when the policy does not pass it. Reported per call (mean and range across repeats) and by majority vote.
- **Self-consistency.** The consistency cookbooks' check, run on byte-identical requests: action-flip rate, plurality agreement, mean std per hazard, and bit-identical answer rate.
- **Retry attack.** Leaky unsafe items (0 < pass rate < 1) and success@k for k = 1, 3, 10, 30.
- **Latency.** p50 and p99.

## Run
```bash
python -m tasks.guardrails.datasets                       # build the frozen item set
python -m tasks.guardrails.run --backend hosted --repeats 10
python -m tasks.guardrails.run --backend local --url http://127.0.0.1:8020 --name detjev --repeats 5
python -m tasks.guardrails.analyze hosted-jev detjev stock-nimble
```
