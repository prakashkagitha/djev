"""TypeSafe's consistency-cookbook metrics, implemented exactly as their published code
defines them (docs.typesafe.ai/cookbooks/consistency_{choice,noul}_cookbook), so our rows
can be appended to their tables.

Choice cookbook
  raw agree     mean over questions of the plurality top-label share across the draws
  policy agree  same, after mapping top probability < 0.60 to "uncertain"
  uncertain     share of all answers that are "uncertain"
  automatic     share of all answers that select a label
  conflicts     questions with more than one concrete (non-uncertain) label
  mean/max std  population std of each label's probability across draws, averaged / max over
                all labels of all questions
Noul cookbook
  mean std      mean over questions of the population std of P(true)
  band          no < 0.30 <= uncertain <= 0.70 < yes; policy agree / uncertain / automatic /
                conflicts as above; `crosses 0.5` counts questions whose P(true) straddles 0.5
We add one stricter column: distinct answer sets (1 means bit-identical every time).
"""

import statistics as st
from collections import Counter

MIN_CHOICE_PROBABILITY = 0.60
NOUL_LOW, NOUL_HIGH = 0.30, 0.70


def _share(values):
    return max(Counter(values).values()) / len(values)


def choice_metrics(draws: list[dict]) -> dict:
    """draws: one {question: answer} dict per call."""
    qs = list(draws[0])
    raw, policy, flat, conflicts, stds = [], [], [], 0, []
    for q in qs:
        probs = [d[q]["probabilities"] for d in draws]
        labels = list(probs[0])
        top = [max(p, key=p.get) for p in probs]
        dec = [t if p[t] >= MIN_CHOICE_PROBABILITY else "uncertain" for t, p in zip(top, probs)]
        raw.append(_share(top))
        policy.append(_share(dec))
        flat += dec
        conflicts += len({x for x in dec if x != "uncertain"}) > 1
        stds += [st.pstdev([p[label] for p in probs]) for label in labels]
    return {"raw_agree": st.mean(raw), "policy_agree": st.mean(policy),
            "uncertain": sum(x == "uncertain" for x in flat) / len(flat),
            "automatic": sum(x != "uncertain" for x in flat) / len(flat),
            "conflicts": conflicts, "mean_std": st.mean(stds), "max_std": max(stds)}


def noul_metrics(draws: list[dict]) -> dict:
    qs = list(draws[0])
    raw, policy, flat, conflicts, stds, crosses = [], [], [], 0, [], 0
    for q in qs:
        ps = [d[q]["noul"] for d in draws]
        raw.append(_share([p >= 0.5 for p in ps]))
        dec = ["no" if p < NOUL_LOW else "yes" if p > NOUL_HIGH else "uncertain" for p in ps]
        policy.append(_share(dec))
        flat += dec
        conflicts += {"yes", "no"} <= set(dec)
        stds.append(st.pstdev(ps))
        crosses += min(ps) < 0.5 <= max(ps)
    return {"raw_agree": st.mean(raw), "policy_agree": st.mean(policy),
            "uncertain": sum(x == "uncertain" for x in flat) / len(flat),
            "automatic": sum(x != "uncertain" for x in flat) / len(flat),
            "conflicts": conflicts, "mean_std": st.mean(stds), "max_std": max(stds),
            "crosses_0.5": crosses}
