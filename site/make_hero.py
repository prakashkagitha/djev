"""Hero animation for djev (1920x1080): same request, 15 calls, hosted Jev vs djev,
then the three properties with measured evidence. Data comes from results/.

  python site/make_hero.py            -> assets/hero/djev.mp4, djev.gif, djev_poster.png
"""

import hashlib
import json
import math
import shutil
import subprocess
from multiprocessing import Pool
from pathlib import Path

import orjson
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/hero"
FRAMES = OUT / "_frames"
FONTS = Path(__file__).resolve().parent / "fonts"
W, H, S = 1920, 1080, 2          # output size, supersampling factor
FPS, DURATION = 30, 14.0

BG = (10, 15, 26)
PANEL = (17, 24, 39)
BORDER = (31, 41, 59)
TEXT = (230, 235, 242)
MUTED = (139, 151, 169)
DIM = (55, 65, 81)
JEV = (52, 211, 166)
DJEV = (96, 165, 250)
AMBER = (251, 191, 36)

# ---------------------------------------------------------------- data
def load(name):
    d = json.loads((ROOT / f"results/typesafe_consistency/{name}.json").read_text())
    c = next(c for c in d["conditions"] if c["kind"] == "noul" and c["protocol"] == "identical"
             and c["mode"] == "sequential")
    probs = [x["covered"]["noul"] for x in c["draws"]]
    hashes = [hashlib.sha256(orjson.dumps(x, option=orjson.OPT_SORT_KEYS)).hexdigest()[:12] for x in c["draws"]]
    return probs, hashes


JEV_P, JEV_H = load("hosted-jev")
DJ_P, DJ_H = load("djev")
GUARD = json.loads((ROOT / "results/guardrails/hosted-jev/card_strict.json").read_text())["consistency"]["action_flips"]

# ---------------------------------------------------------------- helpers
_fonts = {}


def font(size, weight=400, mono=False):
    key = (size, weight, mono)
    if key not in _fonts:
        if mono:
            name = {400: "Regular", 500: "Medium", 600: "SemiBold"}.get(weight, "Regular")
            f = ImageFont.truetype(str(FONTS / f"IBMPlexMono-{name}.ttf"), size * S)
        else:
            f = ImageFont.truetype(str(FONTS / "IBMPlexSans-VF.ttf"), size * S)
            f.set_variation_by_axes([weight, 100])
        _fonts[key] = f
    return _fonts[key]


def mix(c, a, bg=BG):
    a = max(0.0, min(1.0, a))
    return tuple(round(bg[i] + (c[i] - bg[i]) * a) for i in range(3))


def ease(x):  # ease-out cubic on [0,1]
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def prog(t, start, dur):
    return ease((t - start) / dur)


class Canvas:
    def __init__(self):
        self.im = Image.new("RGB", (W * S, H * S), BG)
        self.d = ImageDraw.Draw(self.im)

    def rect(self, x, y, w, h, fill=None, outline=None, r=12, width=2):
        self.d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=r * S, fill=fill,
                                 outline=outline, width=width * S)

    def text(self, x, y, s, f, fill, anchor="la", spacing=0):
        if spacing:
            cx = x
            for ch in s:
                self.d.text((cx * S, y * S), ch, font=f, fill=fill, anchor=anchor)
                cx += f.getlength(ch) / S + spacing
            return cx
        self.d.text((x * S, y * S), s, font=f, fill=fill, anchor=anchor)
        return x + f.getlength(s) / S

    def line(self, x1, y1, x2, y2, fill, width=2):
        self.d.line([x1 * S, y1 * S, x2 * S, y2 * S], fill=fill, width=width * S)

    def out(self):
        return self.im.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- timeline (seconds)
T_HEAD = 0.0
T_CALL0, T_STEP, T_POP = 1.2, 0.24, 0.28
T_TALLY = T_CALL0 + 14 * T_STEP + 0.5
T_PILLAR = T_TALLY + 1.3
PILLAR_GAP = 0.45

X0, X1 = 96, 1824
LANE_X = 640
LANE_W = X1 - LANE_X
CHIP_GAP = 10
CHIP_W = (LANE_W - 14 * CHIP_GAP) / 15
CHIP_H = 88


def calls_done(t):
    return max(0, min(15, int((t - T_CALL0) / T_STEP) + 1)) if t >= T_CALL0 else 0


def draw(t):
    c = Canvas()
    a = prog(t, T_HEAD, 0.7)
    dy = (1 - a) * 18
    # header
    c.text(X0, 78 + dy, "SAME REQUEST  ·  SAME BYTES  ·  15 CALLS", font(20, 500, mono=True), mix(MUTED, a), spacing=1.5)
    c.text(X0, 112 + dy, "“Is this insurance claim covered?”", font(56, 600), mix(TEXT, a))
    c.text(X0, 190 + dy, "One yes/no question from TypeSafe's own consistency cookbook, sent byte-for-byte identical.",
           font(24, 400), mix(MUTED, a))
    c.text(X1, 84 + dy, "djev", font(52, 700), mix(DJEV, a), anchor="ra")

    # request card
    card_a = prog(t, 0.35, 0.7)
    cy = 270 + (1 - card_a) * 24
    c.rect(X0, cy, 490, 420, fill=mix(PANEL, card_a), outline=mix(BORDER, card_a), r=16)
    mono = font(21, 400, mono=True)
    lines = [("POST", DJEV, " /v1/systemone"), ("{", MUTED, ""), ('  "state": {', TEXT, ""),
             ('    "claim":  { … },', MUTED, ""), ('    "policy": { … }', MUTED, ""), ("  },", TEXT, ""),
             ('  "questions": {', TEXT, ""), ('    "covered": {', TEXT, ""), ('      "type": "noul"', JEV, ""),
             ("    }", TEXT, ""), ("  }", TEXT, ""), ("}", MUTED, "")]
    for i, (s1, col, s2) in enumerate(lines):
        yy = cy + 30 + i * 31
        x = c.text(X0 + 28, yy, s1, font(21, 600, mono=True) if s1 == "POST" else mono, mix(col, card_a))
        if s2:
            c.text(x, yy, s2, mono, mix(TEXT, card_a))
    # x15 badge that pulses on every call
    n = calls_done(t)
    pulse = 0.0
    if T_CALL0 <= t < T_CALL0 + 15 * T_STEP:
        k = (t - T_CALL0) % T_STEP / T_STEP
        pulse = math.sin(math.pi * min(1, k * 2)) * 0.5
    bx, by = X0 + 490 - 118, cy + 22
    c.rect(bx, by, 96, 46, fill=mix(DJEV, card_a * (0.22 + pulse * 0.5)), outline=mix(DJEV, card_a), r=23)
    c.text(bx + 48, by + 23, f"×{max(n, 15) if t > T_CALL0 + 15 * T_STEP else 15}", font(24, 600, mono=True),
           mix(TEXT, card_a), anchor="mm")

    # lanes
    for li, (name, sub, probs, hashes, col) in enumerate(
            [("Jev", "hosted · jev-1.13.0", JEV_P, JEV_H, JEV), ("djev", "self-hosted · deterministic", DJ_P, DJ_H, DJEV)]):
        la = prog(t, 0.6 + li * 0.15, 0.7)
        y = 268 + li * 222
        c.text(LANE_X, y + (1 - la) * 16, name, font(34, 700), mix(TEXT, la))
        c.text(LANE_X + (78 if name == "Jev" else 92), y + 12 + (1 - la) * 16, sub, font(19, 400, mono=True), mix(MUTED, la))
        # hash ticker
        if n:
            h = hashes[n - 1]
            changed = n > 1 and hashes[n - 1] != hashes[n - 2] and (t - (T_CALL0 + (n - 1) * T_STEP)) < 0.18
            hc = AMBER if changed else (TEXT if name == "Jev" else DJEV)
            x = c.text(X1 - 330, y + 12, "answer sha256 ", font(19, 400, mono=True), mix(MUTED, la))
            c.text(x, y + 10, h, font(21, 600, mono=True), mix(hc, la))
        # chips
        for i in range(15):
            x = LANE_X + i * (CHIP_W + CHIP_GAP)
            cy2 = y + 58
            start = T_CALL0 + i * T_STEP
            p = prog(t, start, T_POP)
            if t < start:
                c.rect(x, cy2, CHIP_W, CHIP_H, fill=None, outline=mix(BORDER, la), r=10, width=2)
                continue
            sc = 0.86 + 0.14 * p
            w, hh = CHIP_W * sc, CHIP_H * sc
            xx, yy = x + (CHIP_W - w) / 2, cy2 + (CHIP_H - hh) / 2
            yes = probs[i] >= 0.5
            fill = mix(col, 0.22 * p, PANEL) if yes else mix(PANEL, p)
            edge = tuple(round(BORDER[k] + (col[k] - BORDER[k]) * p) for k in range(3))
            c.rect(xx, yy, w, hh, fill=fill, outline=edge, r=10, width=2)
            c.text(x + CHIP_W / 2, cy2 + 32, "YES" if yes else "NO", font(22, 700), mix(TEXT, p), anchor="mm")
            c.text(x + CHIP_W / 2, cy2 + 62, f"{probs[i]:.2f}", font(18, 400, mono=True), mix(MUTED, p), anchor="mm")
        # tally
        yes_n = sum(p >= 0.5 for p in probs[:n])
        ty = y + 168
        if n:
            base = f"YES {yes_n}  ·  NO {n - yes_n}" if name == "Jev" else f"YES {yes_n}"
            x = c.text(LANE_X, ty, base, font(22, 600, mono=True), mix(TEXT, la))
            ta = prog(t, T_TALLY, 0.6)
            if ta > 0:
                if name == "Jev":
                    c.text(x + 18, ty, f"→  {len(set(hashes))} different answers to the same request",
                           font(22, 500), mix(AMBER, ta))
                else:
                    c.text(x + 18, ty, "→  15 × the same answer, bit for bit", font(22, 500), mix(DJEV, ta))

    # pillars
    c.line(X0, 760, X1, 760, mix(BORDER, prog(t, T_PILLAR - 0.3, 0.6)), width=2)
    pillars = [("DETERMINISTIC", "720 / 720", "repeats bit-identical while other\ntraffic shares the GPU"),
               ("REPEATABLE", f"{GUARD} → 0", "guardrail decisions that change on an\nidentical retry (Jev → djev), of 2,236"),
               ("AUDITABLE", "324 / 324", "decisions replayed exactly after a restart\nand on another GPU, keyed by a fingerprint")]
    colw = (X1 - X0 - 2 * 56) / 3
    for i, (lab, big, small) in enumerate(pillars):
        pa = prog(t, T_PILLAR + i * PILLAR_GAP, 0.7)
        x = X0 + i * (colw + 56)
        yy = 792 + (1 - pa) * 22
        c.rect(x, yy + 2, 6, 150, fill=mix(DJEV, pa), r=3)
        c.text(x + 28, yy, lab, font(19, 600, mono=True), mix(DJEV, pa), spacing=2)
        c.text(x + 28, yy + 34, big, font(46, 700), mix(TEXT, pa))
        for j, ln in enumerate(small.split("\n")):
            c.text(x + 28, yy + 98 + j * 30, ln, font(21, 400), mix(MUTED, pa))

    # footer
    fa = prog(t, T_PILLAR + 1.4, 0.8)
    c.text(X0, 1010, "Open, Jev-compatible  ·  SGLang deterministic kernels + patches for hybrid models  ·  MIT",
           font(20, 400), mix(MUTED, fa))
    c.text(X1, 1010, "github.com/prakashkagitha/djev", font(21, 600, mono=True), mix(DJEV, fa), anchor="ra")
    return c.out()


def render(i):
    draw(i / FPS).save(FRAMES / f"{i:04d}.png")


def main():
    if FRAMES.exists():
        shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True)
    n = int(FPS * DURATION)
    with Pool(48) as pool:
        pool.map(render, range(n))
    draw(DURATION).save(OUT / "djev_poster.png")
    ff = shutil.which("ffmpeg")
    subprocess.run([ff, "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(FRAMES / "%04d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "slow",
                    "-movflags", "faststart", str(OUT / "djev.mp4")], check=True)
    vf = "fps=20,scale=1920:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle"
    subprocess.run([ff, "-loglevel", "error", "-y", "-framerate", str(FPS), "-i", str(FRAMES / "%04d.png"),
                    "-vf", vf, "-loop", "0", str(OUT / "djev.gif")], check=True)
    shutil.rmtree(FRAMES)
    for p in sorted(OUT.iterdir()):
        print(p.name, f"{p.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
