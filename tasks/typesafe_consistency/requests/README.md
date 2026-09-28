# TypeSafe consistency cookbooks: reproduction material

Fetched 2026-09-28 from:
- https://docs.typesafe.ai/cookbooks/consistency_noul_cookbook.md (archived: `source/consistency_noul_cookbook.md`)
- https://docs.typesafe.ai/cookbooks/consistency_choice_cookbook.md (archived: `source/consistency_choice_cookbook.md`)

Both runs: `jev-latest` on the production API, sampled 2026-09-11. All 15 calls per cookbook returned `response.model = "jev-1.13.0"`.

## Files
- `noul_request.json`, `choice_request.json`: the POST body for `/v1/systemone`, one repeat each (sample_index 0).
- `jev_results.json`: per-repeat Jev numbers, published aggregate tables, and LLM condition aggregates, each with its source URL.
- `source/`: the page markdown, the decoded playground share payloads, and the rendered figures that the per-repeat numbers were read from.

## What is verbatim and what is reconstructed
**State and questions: verbatim, checked two ways.** `CLAIM`/`POST` and `QUESTIONS` were exec'd straight from the page's Python blocks. The wire-form questions were built the way the SDK builds them. `Noul(instructions=q)` serializes to `{"type":"noul","instructions":q}`, and `Choice(instructions, criteria)` serializes to `{"type":"choice","instructions":...,"criteria":{label: desc}}` (see `typesafe-sdk-python/src/typesafe_sdk/_core/question_types.py`). Both were then compared with the page's playground share link, decoded with lz-string (`source/*_playground_share_decoded.json`). State and questions match exactly, including key order. Floats serialize as `500.0` and so on.

**Body envelope: reconstructed from the SDK source.** `prepare_system_one` builds `{"state", "model", "questions"}` in that key order, and the request files keep it. The endpoint is `POST https://api.typesafe.ai` + `SYSTEM_ONE_PATH`. No `extra_body` or extra headers are used.

**uid: format is verbatim, the token value is illustrative.** The uid is the first key of `state`, a sibling of the payload key.
- Noul: `state={"uid": f"{sample_index}:{token_hex(4)}", "claim": CLAIM}`. Example: `"0:a1b2c3d4"`. sample_index runs 0..14, and `token_hex(4)` is 8 random lowercase hex chars.
- Choice: `state={"uid": f"{RUBRIC_HASH}:{sample_index}:{token_hex(4)}", "post": POST}`, where `RUBRIC_HASH = sha256(json.dumps([POST, QUESTIONS], sort_keys=True, default=str))[:12]` = `fa84120d8444`, computed locally from the verbatim code. The noul hash is `4097f7732246`, but it is not placed in the noul uid.
- The actual random tokens used in the published run are **not recoverable**. They lived only in the unpublished `json_cache.json`. The 15 calls were sequential, not concurrent.
- The playground link omits the uid, so its state is `{"claim": ...}` or `{"post": ...}` only.

**Per-repeat Jev numbers: transcribed from PNG figures.** They are 2-decimal cell labels, read at 2x zoom. Checks against the page text:
- Noul: the mean population std over questions of the transcribed values = 0.01022. The page says 0.0102. The covered range 0.43–0.53 and exclusion range 0.53–0.62 also match.
- Choice: the transcribed values reproduce policy-agree 99.2% and uncertain 25.8%.

## Missing / not public
- No notebook source, `json_cache.json`, or data in the GitHub org. `typesafe-ai` has 9 repos: skills (only a SKILL.md), sdk-python/js, system-one-adapter-python, the github.io stub, and forks. There is no `cookbooks` repo, and guessed cache URLs on docs and mintcdn return 404. `cooksafe` on PyPI is only the JsonCache/playground-link utility.
- Noul: only the 2-decimal P(true) per repeat. No full precision, and no per-repeat tokens or latency.
- Choice: only the **top-label probability** per repeat. Full per-label distributions are not published. For `primary_risk` (Harassment 11 / Violence 4) and `link_handling` (RmLink 8 / Brigade 7) the counts are published, but not which repeat got which label.
- LLM per-repeat values exist only as cell text in `source/*_fig1_all_conditions_heatmap.png` and were not transcribed. The published per-condition aggregates are in `jev_results.json`. The noul page gives no numeric LLM std table.
