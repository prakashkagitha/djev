"""Build the frozen guardrail item set (data/guardrails_v1.jsonl) from public sources.

Downloads from the original sources and never redistributes them; the frozen file holds
only ids, text and labels for local runs. Sampling is seeded, so rebuilding gives the
same file. Items longer than MAX_CHARS are dropped (recorded in the manifest) so every
backend can take them.

  XSTest (Röttger et al. 2024)         450  safe vs unsafe look-alikes  (github: paul-rottger/xstest)
  ToxicChat 0124 test (Lin et al. 2023) 1000 real user prompts: all 362 toxic + 638 non-toxic
  In-the-wild jailbreaks (Shen et al.)  600  300 jailbreak + 300 regular prompts (2023-12-25)
  JailbreakBench behaviors (Chao et al.) 200 100 harmful + 100 benign goals

Label `unsafe` = the message should not simply pass. `jailbreak` = a jailbreak attempt.
"""

import hashlib
import json
import random
import urllib.request
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/guardrails_v1.jsonl"
MAX_CHARS = 12000
SEED = 20260928


def _hf(repo, path):
    return hf_hub_download(repo, path, repo_type="dataset")


def items():
    rows = []
    xs = ROOT / "data/raw/xstest_prompts.csv"
    if not xs.exists():
        xs.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/paul-rottger/xstest/main/xstest_prompts.csv", xs)
    for r in pd.read_csv(xs).itertuples():
        rows.append({"source": "xstest", "src_id": str(r.id), "text": r.prompt,
                     "unsafe": r.label == "unsafe", "jailbreak": False, "meta": {"type": r.type}})

    tc = pd.read_csv(_hf("lmsys/toxic-chat", "data/0124/toxic-chat_annotation_test.csv"))
    toxic = tc[tc.toxicity == 1]
    clean = tc[tc.toxicity == 0].sample(n=1000 - len(toxic), random_state=SEED)
    for r in pd.concat([toxic, clean]).itertuples():
        rows.append({"source": "toxicchat", "src_id": r.conv_id, "text": r.user_input,
                     "unsafe": bool(r.toxicity), "jailbreak": bool(r.jailbreaking), "meta": {}})

    base = "TrustAIRLab/in-the-wild-jailbreak-prompts"
    jb = pd.read_parquet(_hf(base, "jailbreak_2023_12_25/train-00000-of-00001.parquet"))
    rg = pd.read_parquet(_hf(base, "regular_2023_12_25/train-00000-of-00001.parquet"))
    jb = jb[jb.prompt.str.len() <= MAX_CHARS].drop_duplicates("prompt")
    rg = rg[rg.prompt.str.len() <= MAX_CHARS].drop_duplicates("prompt")
    neuro = jb[jb.prompt.str.contains("Neurosemantical Inversitis", regex=False)].head(1)
    jb_s = pd.concat([neuro, jb.drop(neuro.index).sample(n=300 - len(neuro), random_state=SEED)])
    for label, df in (("jailbreak", jb_s), ("regular", rg.sample(n=300, random_state=SEED))):
        for r in df.itertuples():
            rows.append({"source": "in_the_wild", "src_id": f"{label}-{r.Index}", "text": r.prompt,
                         "unsafe": label == "jailbreak", "jailbreak": label == "jailbreak",
                         "meta": {"platform": r.platform,
                                  "cookbook_example": "neurosemantical" if r.Index in neuro.index else None}})

    for fname, unsafe in (("harmful-behaviors.csv", True), ("benign-behaviors.csv", False)):
        df = pd.read_csv(_hf("JailbreakBench/JBB-Behaviors", f"data/{fname}"))
        for r in df.itertuples():
            rows.append({"source": "jbb", "src_id": f"{'harmful' if unsafe else 'benign'}-{r.Index}",
                         "text": r.Goal, "unsafe": unsafe, "jailbreak": False,
                         "meta": {"category": r.Category}})
    return rows


def build():
    rows, seen, kept, dropped = items(), set(), [], 0
    for r in rows:
        if not isinstance(r["text"], str) or not r["text"].strip() or len(r["text"]) > MAX_CHARS:
            dropped += 1
            continue
        if r["text"] in seen:
            dropped += 1
            continue
        seen.add(r["text"])
        r["id"] = f"{r['source']}:{r['src_id']}"
        kept.append(r)
    random.Random(SEED).shuffle(kept)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = {"items": len(kept), "dropped": dropped, "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
                "by_source": {s: {"n": sum(r["source"] == s for r in kept),
                                  "unsafe": sum(r["source"] == s and r["unsafe"] for r in kept)}
                              for s in ("xstest", "toxicchat", "in_the_wild", "jbb")}}
    (OUT.parent / "guardrails_v1.manifest.json").write_text(json.dumps(manifest, indent=1))
    print(json.dumps(manifest, indent=1))


def load():
    return [json.loads(line) for line in OUT.open()]


if __name__ == "__main__":
    build()
