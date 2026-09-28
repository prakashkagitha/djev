"""Inject results/site_data.json (+ latency/golden variants) into site/template.html."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results/core"


def load(name):
    p = R / name
    return json.loads(p.read_text()) if p.exists() else None


data = json.loads((R / "site_data.json").read_text())
data["latency"] = {k: load(f) for k, f in {
    "off": "e4f_off.json", "off_fast": "e4f_off_fastpath.json",
    "on": "e4f_on.json", "on_memo": "e4f_on_memo.json"}.items()}
html = (ROOT / "site/template.html").read_text()
html = html.replace("/*__DATA__*/", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
out = ROOT / "site/deterministic-jev.html"
out.write_text(html)
print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
