"""
evaluation/label_web.py
-----------------------
Browser-based headline labelling tool.

Opens a simple web page where you can read headlines properly
(Sinhala, Tamil, English all render correctly in browser),
click the article link, and label each item yes/no/skip.

Usage:
    python evaluation/label_web.py --file data/labels/sinhala_labels.csv
    python evaluation/label_web.py --file data/labels/tamil_labels.csv
    python evaluation/label_web.py --file data/labels/english_labels.csv
"""

import argparse
import csv
import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Fix Windows terminal encoding so print() doesn't crash on Unicode
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Load CSV ──────────────────────────────────────────────────────────────────

def load_csv(path: Path) -> tuple[list[dict], list[str]]:
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    return rows, list(fieldnames)


def save_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── HTML builder ──────────────────────────────────────────────────────────────

def build_html(rows: list[dict], csv_name: str) -> str:
    total = len(rows)
    labelled = sum(1 for r in rows if r.get("label_relevant") in ("yes", "no"))
    unlabelled = [r for r in rows if not r.get("label_relevant")]

    items_js = json.dumps([
        {
            "idx":      i,
            "headline": r.get("headline", ""),
            "link":     r.get("link", ""),
            "outlet":   r.get("outlet", ""),
            "language": r.get("language", ""),
        }
        for i, r in enumerate(rows)
        if not r.get("label_relevant")
    ], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LankaMarket Scout — Labeller</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0d1117; color: #e6edf3; margin: 0; padding: 20px; }}
  h1 {{ color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
  .progress {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px 18px; margin-bottom: 20px; }}
  .progress-bar {{ background: #21262d; border-radius: 4px; height: 10px; margin-top: 8px; overflow: hidden; }}
  .progress-fill {{ background: #238636; height: 100%; border-radius: 4px; transition: width .4s; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 24px; }}
  .meta {{ color: #8b949e; font-size: 0.85em; margin-bottom: 8px; }}
  .headline {{ font-size: 1.25em; margin: 10px 0; line-height: 1.5; }}
  .link-btn {{ display: inline-block; background: #21262d; border: 1px solid #30363d; border-radius: 6px;
               color: #58a6ff; padding: 6px 14px; text-decoration: none; font-size: 0.85em; margin-bottom: 14px; }}
  .link-btn:hover {{ background: #30363d; }}
  .buttons {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .btn {{ padding: 10px 28px; border: none; border-radius: 6px; font-size: 1em; cursor: pointer; font-weight: 600; }}
  .btn-yes  {{ background: #238636; color: #fff; }}
  .btn-no   {{ background: #da3633; color: #fff; }}
  .btn-skip {{ background: #6e7681; color: #fff; }}
  .btn:hover {{ opacity: 0.85; }}
  .sector-row {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }}
  .sector-btn {{ padding: 7px 14px; border-radius: 6px; border: 1px solid #30363d;
                 background: #21262d; color: #e6edf3; cursor: pointer; font-size: 0.9em; }}
  .sector-btn.selected {{ border-color: #58a6ff; background: #1f3a5f; color: #58a6ff; }}
  .sub-label {{ color: #8b949e; font-size: 0.85em; margin-top: 12px; margin-bottom: 6px; }}
  .done-box {{ background: #0f2d1f; border: 1px solid #238636; border-radius: 8px; padding: 24px; text-align: center; display:none; }}
  .done-box h2 {{ color: #3fb950; }}
  .nav {{ color: #8b949e; font-size: 0.9em; margin-bottom: 14px; }}
  #save-status {{ color: #3fb950; font-size: 0.85em; margin-top: 8px; min-height: 18px; }}
</style>
</head>
<body>

<h1>🇱🇰 LankaMarket Scout — Headline Labeller</h1>

<div class="progress">
  <strong>File:</strong> {csv_name} &nbsp;|&nbsp;
  <strong>Progress:</strong> <span id="prog-text">{labelled}/{total} labelled</span>
  &nbsp;|&nbsp; <span id="remain-text">{len(unlabelled)} remaining</span>
  <div class="progress-bar"><div class="progress-fill" id="prog-fill" style="width:{int(labelled/total*100) if total else 0}%"></div></div>
</div>

<div id="card-area"></div>
<div class="done-box" id="done-box">
  <h2>✅ All items labelled!</h2>
  <p>All headlines have been labelled. You can close this tab now.</p>
  <p>Run <code>python -m evaluation.evaluate --all</code> to see your scores.</p>
</div>

<script>
const ITEMS = {items_js};
let cursor = 0;
let labelled = {labelled};
const total = {total};

const SECTORS = ["agriculture","food_retail","tourism","transport","construction","services","energy","manufacturing","logistics","finance","other"];
const DISTRICTS = ["national","Kandy","Colombo","Galle","Anuradhapura","Jaffna","Trincomalee","Kurunegala","unclear"];
const DIRECTIONS = ["positive","negative","mixed"];

let selSector = "", selDistrict = "", selDirection = "";

function updateProgress() {{
  const pct = total ? Math.round(labelled / total * 100) : 0;
  document.getElementById("prog-text").textContent = labelled + "/" + total + " labelled";
  document.getElementById("remain-text").textContent = (ITEMS.length - cursor) + " remaining";
  document.getElementById("prog-fill").style.width = pct + "%";
}}

function showCard() {{
  if (cursor >= ITEMS.length) {{
    document.getElementById("card-area").innerHTML = "";
    document.getElementById("done-box").style.display = "block";
    return;
  }}
  const item = ITEMS[cursor];
  selSector = ""; selDistrict = "national"; selDirection = "";

  document.getElementById("card-area").innerHTML = `
    <div class="nav">Item ${{cursor + 1}} of ${{ITEMS.length}} unlabelled</div>
    <div class="card">
      <div class="meta">[${{item.language.toUpperCase()}}] ${{item.outlet}}</div>
      <div class="headline" id="hl">${{item.headline}}</div>
      <a class="link-btn" href="${{item.link}}" target="_blank">🔗 Open article in new tab</a>
      <div class="buttons">
        <button class="btn btn-yes"  onclick="label('yes')">✅ Yes — Business Relevant</button>
        <button class="btn btn-no"   onclick="label('no')">❌ No — Not Relevant</button>
        <button class="btn btn-skip" onclick="label('skip')">⏭ Skip / Unsure</button>
      </div>
      <div id="extra-fields" style="display:none; margin-top:16px; border-top:1px solid #30363d; padding-top:14px;">
        <div class="sub-label">Sector (pick one):</div>
        <div class="sector-row" id="sector-row"></div>
        <div class="sub-label" style="margin-top:12px;">Direction:</div>
        <div class="sector-row" id="direction-row"></div>
        <div class="sub-label" style="margin-top:12px;">District (optional):</div>
        <div class="sector-row" id="district-row"></div>
        <button class="btn btn-yes" style="margin-top:16px;" onclick="submitYes()">✅ Confirm</button>
      </div>
      <div id="save-status"></div>
    </div>
  `;

  // Build sector buttons
  const sr = document.getElementById("sector-row");
  SECTORS.forEach(s => {{
    const b = document.createElement("button");
    b.className = "sector-btn"; b.textContent = s;
    b.onclick = () => {{ selSector = s; sr.querySelectorAll(".sector-btn").forEach(x=>x.classList.remove("selected")); b.classList.add("selected"); }};
    sr.appendChild(b);
  }});

  const dr = document.getElementById("direction-row");
  DIRECTIONS.forEach(d => {{
    const b = document.createElement("button");
    b.className = "sector-btn"; b.textContent = d;
    b.onclick = () => {{ selDirection = d; dr.querySelectorAll(".sector-btn").forEach(x=>x.classList.remove("selected")); b.classList.add("selected"); }};
    dr.appendChild(b);
  }});

  const disr = document.getElementById("district-row");
  DISTRICTS.forEach(d => {{
    const b = document.createElement("button");
    b.className = "sector-btn" + (d === "national" ? " selected" : ""); b.textContent = d;
    b.onclick = () => {{ selDistrict = d; disr.querySelectorAll(".sector-btn").forEach(x=>x.classList.remove("selected")); b.classList.add("selected"); }};
    disr.appendChild(b);
  }});
}}

function label(val) {{
  if (val === "yes") {{
    document.getElementById("extra-fields").style.display = "block";
    document.querySelector(".buttons").style.display = "none";
    return;
  }}
  save(val, "", "", "");
}}

function submitYes() {{
  if (!selSector) {{ alert("Please pick a sector first."); return; }}
  if (!selDirection) {{ alert("Please pick a direction first."); return; }}
  save("yes", selSector, selDistrict || "national", selDirection);
}}

function save(relevant, sector, district, direction) {{
  const item = ITEMS[cursor];
  const status = document.getElementById("save-status");
  status && (status.textContent = "Saving…");

  fetch("/save", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{
      idx: item.idx,
      label_relevant: relevant,
      label_sector: sector,
      label_district: district,
      label_direction: direction,
    }})
  }})
  .then(r => r.json())
  .then(d => {{
    if (d.ok) {{
      if (relevant !== "skip") labelled++;
      cursor++;
      updateProgress();
      showCard();
    }} else {{
      alert("Save error: " + d.error);
    }}
  }})
  .catch(e => alert("Network error: " + e));
}}

updateProgress();
showCard();
</script>
</body>
</html>"""


# ── Tiny HTTP server ───────────────────────────────────────────────────────────

_rows: list[dict] = []
_fieldnames: list[str] = []
_csv_path: Path = Path()
_html: str = ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silence request logs
        pass

    def do_GET(self):
        global _html
        if self.path == "/" or self.path == "/index.html":
            body = _html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global _rows, _fieldnames, _html, _csv_path
        if self.path == "/save":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            idx = data.get("idx")
            try:
                _rows[idx]["label_relevant"]  = data.get("label_relevant", "")
                _rows[idx]["label_sector"]    = data.get("label_sector", "")
                _rows[idx]["label_district"]  = data.get("label_district", "")
                _rows[idx]["label_direction"] = data.get("label_direction", "")
                save_csv(_csv_path, _rows, _fieldnames)
                # Rebuild HTML so refresh shows updated progress
                _html = build_html(_rows, _csv_path.name)
                resp = json.dumps({"ok": True}).encode()
            except Exception as e:
                resp = json.dumps({"ok": False, "error": str(e)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        else:
            self.send_response(404)
            self.end_headers()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    global _rows, _fieldnames, _html, _csv_path

    parser = argparse.ArgumentParser(
        description="LankaMarket Scout — browser-based headline labeller"
    )
    parser.add_argument("--file", required=True, metavar="CSV",
                        help="Path to the label CSV file (e.g. data/labels/sinhala_labels.csv)")
    parser.add_argument("--port", type=int, default=7878,
                        help="Local port for the web server (default: 7878)")
    args = parser.parse_args()

    _csv_path = Path(args.file)
    if not _csv_path.exists():
        print(f"File not found: {_csv_path}")
        print("Export labels first:")
        print("  python -m evaluation.label_tool --export data/labels/sinhala_labels.csv --lang si")
        sys.exit(1)

    _rows, _fieldnames = load_csv(_csv_path)

    # Ensure label columns exist
    for col in ("label_relevant", "label_sector", "label_district", "label_direction"):
        if col not in _fieldnames:
            _fieldnames.append(col)
        for row in _rows:
            row.setdefault(col, "")

    _html = build_html(_rows, _csv_path.name)

    unlabelled = sum(1 for r in _rows if not r.get("label_relevant"))
    labelled   = len(_rows) - unlabelled
    print(f"\n{'-'*55}")
    print(f"  LankaMarket Scout -- Browser Labeller")
    print(f"  File     : {_csv_path.name}")
    print(f"  Progress : {labelled}/{len(_rows)} labelled, {unlabelled} remaining")
    print(f"{'-'*55}")

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\n  Opening: {url}")
    print(f"  Press Ctrl+C to stop the server when done.\n")

    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped. Labels saved to:", _csv_path)


if __name__ == "__main__":
    main()
