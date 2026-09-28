# SGLang 0.5.19 patches

Apply them from the site-packages directory of the engine venv: `patch -p0 < file`. The diff headers use absolute scratch paths, so pass the target file explicitly if `patch` complains.

| Patch | Why | Test that shows it |
|---|---|---|
| `sglang-0.5.19-det-mamba-checkpoint.patch` | In deterministic mode, only checkpoint Gated-DeltaNet/mamba state when a prefill ends on the 64-token grid. Mid-extend checkpoints come from the lower-precision intermediate `h`, and resuming from them is not bitwise equal to recomputing. Switch: `SGLANG_DET_ALIGNED_MAMBA_CHECKPOINTS=0`. | `replaykit/pair_probe.py`: 76/84 before, 84/84 after. Engine probe: 278/300 before, 300/300 after |
| `sglang-0.5.19-fa3-truncation-align.patch` | Opt-in chunked-prefill split alignment for fa3 (`SGLANG_FA3_PREFILL_TRUNCATION_ALIGN_SIZE=64`), so long prompts split under load also resume on the grid | Drift without it: 700/720. With it: 720/720 |
| `sglang-0.5.19-mixed-logprob-batch.patch` | Fixes the crash when logprob and plain requests share a decode batch (sgl-project/sglang#34719) | Engine probe with plain background traffic |

Upstream status: not yet proposed. Planned for v0.3.
