"""Render README / social assets (1200x675) straight from result files.

  assets/same_question.gif   15 identical calls: hosted Jev flips yes/no, djev repeats
  assets/guardrail.gif       an unsafe message that hosted Jev sometimes lets through
  assets/consistency.png     TypeSafe's own consistency table, extended with our rows
  assets/scoreboard.png      headline numbers
  assets/root_cause.png      why hybrid models needed a patch

python site/make_assets.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)
W, H, DPI = 12, 6.75, 100
BG, INK, INK2, MUTED, RULE = "#f7f8fa", "#0f1722", "#445061", "#7a8594", "#dfe3e8"
JEV, DEF, DJEV = "#15936a", "#e0612f", "#2a78d6"
YES_FILL = {JEV: "#d5efe5", DJEV: "#d8e6f8", DEF: "#fbe1d6"}
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK})


def canvas():
    fig = plt.figure(figsize=(W, H), dpi=DPI, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1200)
    ax.set_ylim(675, 0)
    ax.axis("off")
    return fig, ax


def footer(ax, text):
    ax.text(40, 648, text, fontsize=10.5, color=MUTED, va="center")
    ax.text(1160, 648, "github.com/prakashkagitha/djev", fontsize=10.5, color=MUTED, ha="right", va="center")


def box(ax, x, y, w, h, edge, fill, top, bottom, alpha=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=6", lw=2,
                                edgecolor=edge, facecolor=fill, alpha=alpha))
    ax.text(x + w / 2, y + h * 0.40, top, ha="center", va="center", fontsize=13, weight="bold", color=INK, alpha=alpha)
    ax.text(x + w / 2, y + h * 0.72, bottom, ha="center", va="center", fontsize=10.5, color=INK2, alpha=alpha)


def gif(frames, path, durations):
    imgs = []
    for fig in frames:
        fig.canvas.draw()
        imgs.append(Image.frombuffer("RGBA", fig.canvas.get_width_height(), fig.canvas.buffer_rgba()).convert("RGB"))
        plt.close(fig)
    pal = [im.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for im in imgs]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=durations, loop=0, optimize=True)
    imgs[-1].save(path.with_suffix(".png"))


def same_question():
    load = lambda n: json.loads((ROOT / f"results/typesafe_consistency/{n}.json").read_text())
    pick = lambda d: next(c for c in d["conditions"] if c["kind"] == "noul" and c["protocol"] == "identical"
                          and c["mode"] == "sequential")
    jev = [x["covered"]["noul"] for x in pick(load("hosted-jev"))["draws"]]
    dj = [x["covered"]["noul"] for x in pick(load("djev"))["draws"]]
    frames, durs = [], []
    for k in range(0, 16):
        fig, ax = canvas()
        ax.text(40, 58, "Same question. Same bytes. 15 calls.", fontsize=26, weight="bold", va="center")
        ax.text(40, 102, "TypeSafe's own consistency cookbook: “Is this auto-insurance claim covered?”",
                fontsize=14, color=INK2, va="center")
        for row, (name, sub, vals, c) in enumerate([("Hosted Jev", "jev-1.13.0", jev, JEV), ("djev", "Deterministic Jev", dj, DJEV)]):
            y = 175 + row * 205
            ax.text(40, y + 8, name, fontsize=20, weight="bold", va="center")
            ax.text(40, y + 38, sub, fontsize=11.5, color=MUTED, va="center")
            for i in range(15):
                x = 40 + i * 75
                if i < k:
                    p = vals[i]
                    yes = p >= 0.5
                    box(ax, x, y + 62, 66, 84, c, YES_FILL[c] if yes else "white", "YES" if yes else "NO", f"{p:.2f}")
                else:
                    ax.add_patch(FancyBboxPatch((x, y + 62), 66, 84, boxstyle="round,pad=0,rounding_size=6",
                                                lw=1.2, edgecolor=RULE, facecolor="none", ls="--"))
            if k == 15:
                y_n = sum(v >= 0.5 for v in vals)
                txt = (f"{y_n} yes · {15 - y_n} no · 15 different answer sets" if name == "Hosted Jev"
                       else "15 × the same answer, bit for bit")
                ax.text(1160, y + 8, txt, fontsize=14, weight="bold", ha="right", va="center", color=INK)
        footer(ax, "Called 2026-09-28, identical bytes. Different models; this shows repeatability, not correctness.")
        frames.append(fig)
        durs.append(2800 if k == 15 else (900 if k == 0 else 260))
    gif(frames, OUT / "same_question.gif", durs)


def guardrail():
    data = json.loads((ROOT / "results/core/site_data.json").read_text())["guardrails"]
    ex = data["examples"][0]
    cards = data["cards"]
    jev = ex["calls"]["hosted-jev"]
    dj = ex["calls"]["djev"]
    frames, durs = [], []
    for k in range(0, 11):
        fig, ax = canvas()
        ax.text(40, 58, "A guardrail you can retry past", fontsize=26, weight="bold", va="center")
        ax.text(40, 102, f"“{ex['text']}”  (XSTest, unsafe) · TypeSafe's guardrail cookbook, strict policy",
                fontsize=13.5, color=INK2, va="center")
        for row, (name, calls, c) in enumerate([("Hosted Jev", jev, JEV), ("djev", dj, DJEV)]):
            y = 165 + row * 190
            ax.text(40, y + 8, name, fontsize=20, weight="bold", va="center")
            ax.text(40, y + 36, f"{len(calls)} identical calls", fontsize=11.5, color=MUTED, va="center")
            for i in range(10):
                x = 40 + i * 110
                if i < len(calls) and i < k:
                    a = calls[i]["action"]
                    box(ax, x, y + 58, 100, 84, c, "#fde2d9" if a == "pass" else YES_FILL[c], a.upper(),
                        f"harm {calls[i]['nouls']['harmful_request']:.2f}")
                elif i < len(calls):
                    ax.add_patch(FancyBboxPatch((x, y + 58), 100, 84, boxstyle="round,pad=0,rounding_size=6",
                                                lw=1.2, edgecolor=RULE, facecolor="none", ls="--"))
        if k == 10:
            h, d = cards["hosted-jev"]["strict"], cards["djev"]["strict"]
            ax.text(40, 560, f"Across 2,236 messages, hosted Jev changed its action on {h['consistency']['action_flips']}, and "
                    f"{h['retry_attack']['leaky_items']} unsafe ones got through on some calls only.",
                    fontsize=14, va="center")
            ax.text(40, 596, f"djev: {d['consistency']['action_flips']} and {d['retry_attack']['leaky_items']}.  "
                    f"F1 {d['detection']['all']['per_run_mean']['f1']:.3f} vs {h['detection']['all']['per_run_mean']['f1']:.3f}.",
                    fontsize=15, weight="bold", va="center")
        footer(ax, "Harm = P(harmful request); review line 0.35. Called 2026-09-28 with identical bytes.")
        frames.append(fig)
        durs.append(3200 if k == 10 else (900 if k == 0 else 330))
    gif(frames, OUT / "guardrail.gif", durs)


def consistency():
    pub = json.loads((ROOT / "tasks/typesafe_consistency/requests/jev_results.json").read_text())["choice"]["published_tables"]
    load = lambda n: json.loads((ROOT / f"results/typesafe_consistency/{n}.json").read_text())

    def ours(n, protocol):
        c = next(c for c in load(n)["conditions"] if c["kind"] == "choice" and c["protocol"] == protocol
                 and c["mode"] == "sequential")
        m = c["typesafe_metrics"]
        return [f"{m['raw_agree']:.1%}", f"{m['policy_agree']:.1%}", f"{m['mean_std']:.4f}", f"{c['distinct_answer_sets']}/15"]
    rows = []
    for name, key in [("claude-haiku-4-5  t=0", "claude-haiku-4-5 t=0"), ("claude-haiku-4-5  default", "claude-haiku-4-5 t=default"),
                      ("gpt-5.4-mini  t=0", "gpt-5.4-mini t=0"), ("gpt-5.4-mini  default", "gpt-5.4-mini t=default"),
                      ("gpt-5.5  reasoning", "gpt-5.5-reasoning"), ("claude-opus-4-8  reasoning", "claude-opus-4-8-reasoning"),
                      ("Jev 1.13  (TypeSafe, 2026-09-11)", "typesafe_choice")]:
        a = pub["agreement"]["rows"][key]
        s = pub["probability_std"]["rows"][key]
        rows.append(("published", name, [a[0], a[1], f"{s[0]:.4f}", "n/r"]))
    rows += [("ours", "Hosted Jev 1.13, fresh uid (today)", ours("hosted-jev", "uid")),
             ("ours", "Hosted Jev 1.13, identical bytes", ours("hosted-jev", "identical")),
             ("ours", "Default serving (Nimble-9B), identical", ours("default-serving", "identical")),
             ("djev", "djev (Nimble-9B), identical bytes", ours("djev", "identical")),
             ("djev", "djev, fresh uid", ours("djev", "uid"))]
    fig, ax = canvas()
    ax.text(40, 50, "TypeSafe's consistency test, extended", fontsize=26, weight="bold", va="center")
    ax.text(40, 88, "Moderation cookbook: 8 choice questions × 15 calls. Their metrics, their code, plus a stricter last column.",
            fontsize=13.5, color=INK2, va="center")
    cols = [("raw agree", 560), ("policy agree", 710), ("mean prob std", 865), ("distinct answers", 1050)]
    y0 = 130
    for label, x in cols:
        ax.text(x, y0, label, fontsize=11, color=MUTED, ha="center", weight="bold")
    for i, (kind, name, vals) in enumerate(rows):
        y = y0 + 34 + i * 35
        if kind == "djev":
            ax.add_patch(Rectangle((30, y - 17), 1140, 33, facecolor="#dce9f9", edgecolor="none"))
        if i == 7:
            ax.plot([30, 1170], [y - 18, y - 18], color=INK2, lw=1)
        ax.text(40, y, name, fontsize=13, va="center", weight="bold" if kind == "djev" else "normal",
                color=INK if kind != "published" else INK2)
        for (label, x), v in zip(cols, vals):
            ax.text(x, y, v, fontsize=13, ha="center", va="center", family="DejaVu Sans Mono",
                    weight="bold" if kind == "djev" else "normal", color=INK if kind != "published" else INK2)
    ax.text(40, y0 + 34 + len(rows) * 35 + 6,
            "Top 7: published by TypeSafe (fresh uid per call; n/r = not reported). Below the line: measured 2026-09-28.\n"
            "Policy agree: a top probability under 0.60 counts as “uncertain”.", fontsize=10.5, color=MUTED, va="center",
            linespacing=1.5)
    footer(ax, "Agreement measures repeatability, not correctness (TypeSafe makes the same point).")
    fig.savefig(OUT / "consistency.png", facecolor=BG)
    plt.close(fig)


def scoreboard():
    data = json.loads((ROOT / "results/core/site_data.json").read_text())
    h, d = data["guardrails"]["cards"]["hosted-jev"]["strict"], data["guardrails"]["cards"]["djev"]["strict"]
    fig, ax = canvas()
    ax.text(40, 60, "djev: Jev-compatible decisions that repeat", fontsize=26, weight="bold", va="center")
    ax.text(40, 102, "Open, self-hosted System One server · SGLang deterministic inference + 2 new determinism patches · one H100",
            fontsize=14, color=INK2, va="center")
    tiles = [("720 / 720", "repeats bit-identical\nunder concurrent load"),
             ("324 / 324", "decisions reproduced after a\nrestart and on another GPU"),
             (f"{h['consistency']['action_flips']} → {d['consistency']['action_flips']}",
              "guardrail actions that changed\non identical calls (of 2,236)"),
             (f"{h['retry_attack']['leaky_items']} → {d['retry_attack']['leaky_items']}",
              "unsafe messages that got\nthrough on some calls only"),
             ("282 = 282", "correct answers of 324,\ndeterminism on vs off"),
             ("122 ms", "median guard call\n(hosted Jev: 144 ms)")]
    for i, (v, k) in enumerate(tiles):
        x, y = 40 + (i % 3) * 380, 150 + (i // 3) * 225
        ax.add_patch(FancyBboxPatch((x, y), 360, 200, boxstyle="round,pad=0,rounding_size=10", lw=1.2,
                                    edgecolor=RULE, facecolor="white"))
        ax.text(x + 24, y + 68, v, fontsize=34, weight="bold", va="center", color=DJEV)
        ax.text(x + 24, y + 140, k, fontsize=14, va="center", color=INK2, linespacing=1.4)
    footer(ax, "Arrows: hosted Jev 1.13 → djev. Measured 2026-09-28; raw data and scripts in the repo.")
    fig.savefig(OUT / "scoreboard.png", facecolor=BG)
    plt.close(fig)


def root_cause():
    fig, ax = canvas()
    ax.text(40, 58, "Why SGLang's deterministic flag was not enough", fontsize=26, weight="bold", va="center")
    ax.text(40, 100, "Hybrid models (Qwen3.5 / Gated DeltaNet) carry a recurrent state computed in 64-token chunks.",
            fontsize=14, color=INK2, va="center")
    left, unit = 390, 2.85
    X = lambda t: left + t * unit
    for t in (0, 64, 128, 192, 256):
        ax.plot([X(t), X(t)], [140, 560], color=RULE, lw=1)
        ax.text(X(t), 582, str(t), ha="center", fontsize=11, color=MUTED)
    ax.text(X(256), 604, "tokens", ha="center", fontsize=11, color=MUTED)
    rows = [("Recompute from token 0", [(0, 64), (64, 128), (128, 192), (192, 256)], None, INK2, None),
            ("Default: resume at token 100", [(100, 164), (164, 228), (228, 256)], 100, DEF,
             "state copied mid-prompt from a lower-precision buffer → different bits"),
            ("djev: resume at token 64", [(64, 128), (128, 192), (192, 256)], 64, DJEV,
             "exact fp32 state at a 64-token boundary → identical bits")]
    for i, (label, chunks, cached, c, note) in enumerate(rows):
        y = 170 + i * 135
        ax.text(X(0) - 20, y + 22, label, fontsize=14, ha="right", va="center", weight="bold")
        if cached:
            ax.add_patch(Rectangle((X(0), y), X(cached) - X(0), 44, facecolor=YES_FILL.get(c, "#eee"), edgecolor="none"))
            ax.text(X(cached / 2), y + 22, "cached", ha="center", va="center", fontsize=11, color=INK2)
            ax.plot([X(cached)], [y + 22], "o", ms=12, color=c, mec="white", mew=2)
            ax.text(X(0), y + 70, note, fontsize=12.5, color=INK, va="center")
        for a, b in chunks:
            ax.add_patch(FancyBboxPatch((X(a) + 2, y), X(b) - X(a) - 4, 44, boxstyle="round,pad=0,rounding_size=4",
                                        lw=2, edgecolor=c, facecolor="none"))
    footer(ax, "Fix: checkpoint only at grid-aligned prefill ends in deterministic mode + align prefill splits (patches/).")
    fig.savefig(OUT / "root_cause.png", facecolor=BG)
    plt.close(fig)


if __name__ == "__main__":
    same_question()
    guardrail()
    consistency()
    scoreboard()
    root_cause()
    for p in sorted(OUT.iterdir()):
        print(p.name, f"{p.stat().st_size / 1024:.0f} KB")
