"""Collect every result file (results/core and task results) into one compact JSON bundle for the report page."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results/core"


def load(name):
    p = R / name
    return json.loads(p.read_text()) if p.exists() else None


def engine(name):
    d = load(name)
    if d is None:
        return None
    s = d["summary"]
    return {"by_load": {k: {"identical": v["identical"], "n": v["n"], "max_abs_diff": v["max_abs_diff"]}
                        for k, v in s.items()},
            "identical": sum(v["identical"] for v in s.values()), "n": sum(v["n"] for v in s.values())}


def drift(name):
    d = load(name)
    refs = d["references"]
    rows = []
    for t in d["trials"]:
        (qid, q), = t["questions"].items()
        rows.append({"id": t["id"], "load": t["load"], "rep": t["rep"], "same": t["identical"],
                     "dp": q["abs_diff"], "p": q["p"], "ref_p": q["ref_p"], "flip": q["flip"], "type": q["type"], "ms": round(t["ms"], 1)})
    ids = list(refs)
    return {"fingerprint": d["fingerprint"], "ids": ids, "rows": rows,
            "identical": sum(r["same"] for r in rows), "n": len(rows),
            "flips": sum(r["flip"] for r in rows), "max_dp": max(r["dp"] for r in rows)}


def quality(name):
    d = load(name)
    return {"all": {k: d["all"][k] for k in ("n", "correct", "accuracy", "brier", "nll", "ece", "reliability")},
            "by_type": {t: {k: v[k] for k in ("n", "correct", "accuracy")} for t, v in d["by_type"].items()},
            "score_mae": d["score_mae"]}


def cookbook(name):
    d = load(name)
    return [{"kind": r["kind"], "condition": r["condition"], "protocol": r["protocol"],
             "mean_std": r["mean_std"], "flipping": r["flipping_questions"],
             "questions": {q: {"p": v["p"], "labels": v["labels"]} for q, v in r["questions"].items()}}
            for r in d["runs"]]


jev = json.loads((ROOT / "tasks/typesafe_consistency/requests/jev_results.json").read_text())
bundle = {
    "engine": {k: engine(f) for k, f in {
        "dense_off": "e0_qwen3_8b_nodet.json", "dense_on": "e0_qwen3_8b_det.json",
        "hybrid_off": "e0_nimble_nodet.json", "hybrid_on_stock": "e0_nimble_det.json",
        "hybrid_on_triton": "e3_nimble_det_triton.json", "hybrid_on_align64": "e3_nimble_det_fa3_align64.json",
        "hybrid_on_patched": "e3b_nimble_det_patched.json"}.items()},
    "pair_patched": load("e3b_pair_patched.json"),
    "drift": {"off": drift("e12_det_off.json"), "on": drift("e12_final_on.json")},
    "quality": {"off": quality("e5_det_off.json"), "on": quality("e5_det_on.json")},
    "latency": {k: load(f) for k, f in {"off": "e4_det_off.json", "on": "e4_det_on.json",
                                          "on_stock_cache": "e4_det_on_stock_cache.json",
                                          "off_aligned": "e4_det_off_aligned_warmup.json"}.items()},
    "cookbook": {"off": cookbook("e8_det_off.json"), "on": cookbook("e8_final_on.json"),
                 "jev_noul": jev["noul"]["jev_per_repeat_p_true"]["values"],
                 "jev_choice_top": jev["choice"]["jev_per_repeat_top_probability"]["values"]},
    "golden": {k: load(f) for k, f in {"off_restart": "e7_det_off_restart.json",
                                         "on_same": "e7_det_on_same.json",
                                         "on_restart": "e7_det_on_restart.json",
                                         "on_gpu4": "e7_det_on_gpu4.json",
                                         "final_on": "e7_final_on.json",
                                         "final_on_memo": "e7_final_on_memo.json"}.items()},
    "invariance": {"raw": load("e6_det_on.json")["summary"],
                   "canonical": load("e6_det_on_canonical.json")["summary"]},
    "fingerprint": {"off": load("fingerprint_f_off.json"), "on": load("fingerprint_f_on.json")},
}
rows = {json.loads(l)["id"]: json.loads(l) for l in open(ROOT / "nimble/data/eval.jsonl")}
bundle["examples"] = {}
for rid in bundle["drift"]["off"]["ids"]:
    q = next(iter(rows[rid]["input"]["questions"].items()))
    crit = q[1].get("criteria")
    bundle["examples"][rid] = {"qid": q[0], "type": q[1]["type"], "domain": rows[rid]["domain"],
                               "instructions": str(q[1]["instructions"])[:280],
                               "options": list(crit) if isinstance(crit, dict) else crit}

def hosted():
    d = load("e9_hosted_jev.json")
    if d is None:
        return None
    import statistics as st

    def top(a):
        if a["type"] == "noul":
            return ("yes" if a["noul"] >= 0.5 else "no"), a["noul"]
        if a["type"] == "choice":
            return a["choice"], a["probabilities"][a["choice"]]
        return max(a["probabilities"], key=a["probabilities"].get), a["score"]
    cb = {}
    for kind, modes in d["cookbook"].items():
        cb[kind] = {}
        for mode, runs in modes.items():
            qs = {}
            for q in runs[0]["answers"]:
                ds = [top(r["answers"][q]) for r in runs]
                qs[q] = {"labels": [x[0] for x in ds], "p": [x[1] for x in ds]}
            cb[kind][mode] = {"distinct": len({r["hash"] for r in runs}), "n": len(runs),
                              "mean_std": st.mean(st.pstdev(v["p"]) for v in qs.values()),
                              "flipping": [q for q, v in qs.items() if len(set(v["labels"])) > 1],
                              "questions": qs, "p50_ms": sorted(r["ms"] for r in runs)[len(runs) // 2]}
    drift = []
    for rid, v in d["drift"].items():
        (q, _), = v[0]["answers"].items()
        ds = [top(x["answers"][q]) for x in v]
        drift.append({"id": rid, "distinct": len({x["hash"] for x in v}), "flip": len({x[0] for x in ds}) > 1,
                      "spread": max(x[1] for x in ds) - min(x[1] for x in ds), "p": [x[1] for x in ds],
                      "labels": [x[0] for x in ds]})
    return {"model": d["cookbook"]["noul"]["sequential"][0]["model"], "cookbook": cb, "drift": drift}


bundle["hosted"] = hosted()
# our own model on the same cookbook requests, identical bytes, busy server (final build)

def guardrails():
    G = ROOT / "results/guardrails"
    items = {json.loads(l)["id"]: json.loads(l) for l in open(ROOT / "data/guardrails_v1.jsonl")}
    names = ["hosted-jev", "stock-nimble", "detjev"]
    cards = {n: {pol: json.loads((G / n / f"card_{pol}.json").read_text()) for pol in ("strict", "permissive")}
             for n in names}
    for n in names:
        for pol in cards[n]:
            cards[n][pol].pop("flipped_examples", None)
    lat = {n: json.loads((G / n / "latency.json").read_text()) for n in names if (G / n / "latency.json").exists()}

    def acts(n):
        d = {}
        for l in open(G / n / "calls.jsonl"):
            r = json.loads(l)
            d.setdefault(r["id"], []).append((r["rep"], r["actions"]["strict"], r["nouls"], r["severity"]))
        return {k: sorted(v) for k, v in d.items()}
    A = {n: acts(n) for n in names}
    examples = []
    for i in ["xstest:" + next(k.split(":")[1] for k, v in items.items() if v["text"].startswith("What are my ex husband")),
              next(k for k, v in items.items() if v["text"].startswith("Describe how Eric Harris")),
              next(k for k, v in items.items() if (v["meta"] or {}).get("cookbook_example") == "neurosemantical")]:
        examples.append({"id": i, "text": items[i]["text"][:300], "source": items[i]["source"], "unsafe": items[i]["unsafe"],
                         "calls": {n: [{"action": a, "nouls": nl, "severity": sv} for _, a, nl, sv in A[n][i]] for n in names}})
    return {"items": len(items), "cards": cards, "latency": lat, "examples": examples}


def consistency():
    C = ROOT / "results/typesafe_consistency"
    return {p.stem: [{k: v for k, v in c.items() if k != "questions"} | {"counts": {q: x["counts"] for q, x in c["questions"].items()}}
                     for c in json.loads(p.read_text())["conditions"]] for p in C.glob("*.json")}


bundle["guardrails"] = guardrails()
bundle["consistency"] = consistency()
out = R / "site_data.json"
out.write_text(json.dumps(bundle, separators=(",", ":")))
print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
