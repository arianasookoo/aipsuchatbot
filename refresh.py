"""Freshness check: re-fetch every indexed page and report what changed since last run.

Run: python refresh.py                 # check, write freshness.json, exit 1 if a rebuild is needed
     python refresh.py --dry-run       # check only, write nothing
     python refresh.py --rebuild       # on change: re-run scraper -> cleaner -> chunker -> index
     python refresh.py --selfcheck

Exit codes: 0 nothing changed (or --rebuild succeeded), 1 changed/removed pages (rebuild needed),
2 fetch errors only (retry later), 3 precondition (missing input file, or bs4 missing for --rebuild).

Design:
- Change detection hashes the page text extracted by a standard-library HTML parser using the
  same element rules as web-scraper.py (drop nav/header/footer/script/style, keep p/h1-h3/li).
  That text differs from BeautifulSoup's, so this script keeps its own baseline in freshness.json
  instead of comparing with the cleaner's original_content_sha256. The first run records a
  baseline for every page; real change detection starts on the second run. The first run still
  catches removed and redirected pages.
- A rebuild is the team's full chain by subprocess (vector_search.index is a full rebuild with an
  atomic swap, there is no upsert path), so nothing here touches their files or data formats.

Honest limitation: a page whose only change is inside navigation is reported unchanged, which is
the intent; a site-wide template change will mark every page changed and force one full rebuild.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from importlib.util import find_spec
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (compatible; PSU-Engagement-Navigator freshness check)"
SKIP = {"nav", "header", "footer", "script", "style", "noscript"}
KEEP = {"p", "h1", "h2", "h3", "li"}
REBUILD = [["web-scraper.py"], ["clean_scrape.py", "multi_seed_scrape_data.json"],
           ["prepare_chunks.py", "cleaned_scrape_data.json"], ["vector_search.py", "index", "chunks.json"]]


class _Extract(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip, self.keep, self.title, self.in_title, self.parts, self.buf = 0, 0, "", False, [], []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag in KEEP and not self.skip:
            self.keep += 1

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag == "title":
            self.in_title = False
        elif tag in KEEP and self.keep:
            self.keep -= 1
            if self.buf:
                self.parts.append(" ".join(self.buf))
                self.buf = []

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif self.keep and not self.skip and data.strip():
            self.buf.append(data.strip())


def extract(html):
    """(title, content) with the scraper's element rules."""
    p = _Extract()
    p.feed(html)
    return p.title.strip(), " ".join(p.parts)


def page_hash(content):
    return hashlib.sha256(re.sub(r"\s+", " ", content).strip().encode()).hexdigest()


def fetch(url, timeout=20):
    """(status, html, final_url). status 0 = network error after one retry."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf8", "replace"), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, "", url
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt:
                return 0, "", url


def classify(status, final_url, url, new_hash, prev_hash, prev_final=None):
    if status in (404, 410):
        return "removed"
    if status == 0 or status >= 400:
        return "error"
    if final_url.rstrip("/") != url.rstrip("/") and final_url.rstrip("/") != (prev_final or "").rstrip("/"):
        return "changed"  # a new redirect; one already recorded in the manifest is judged by content
    if prev_hash is None:
        return "baseline"
    return "unchanged" if new_hash == prev_hash else "changed"


def check(urls, manifest, fetch=fetch, workers=8):
    """url -> {sha256, last_checked, last_changed, status[, final_url]}"""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    prev = manifest.get("pages", {})

    def one(url):
        status, html, final = fetch(url)
        h = page_hash(extract(html)[1]) if html else prev.get(url, {}).get("sha256")
        kind = classify(status, final, url, h, prev.get(url, {}).get("sha256"), prev.get(url, {}).get("final_url"))
        entry = {"sha256": h, "last_checked": now, "status": kind,
                 "last_changed": now if kind in ("changed", "baseline") else prev.get(url, {}).get("last_changed")}
        if final.rstrip("/") != url.rstrip("/"):
            entry["final_url"] = final
        return url, entry

    with ThreadPoolExecutor(workers) as ex:
        return dict(ex.map(one, urls))


def report(pages):
    counts = {k: 0 for k in ("unchanged", "changed", "removed", "error", "baseline")}
    for e in pages.values():
        counts[e["status"]] += 1
    print(f"checked {len(pages)}: " + "  ".join(f"{k} {v}" for k, v in counts.items()))
    for url, e in sorted(pages.items(), key=lambda kv: kv[1]["status"]):
        if e["status"] not in ("unchanged", "baseline"):
            print(f"  {e['status']:9} {url}" + (f"  -> {e['final_url']}" if e.get("final_url") else ""))
    return counts


def rebuild():
    if not find_spec("bs4") or not find_spec("requests"):
        sys.exit("rebuild needs the scraper's deps: pip install requests beautifulsoup4  (exit 3)")
    for cmd in REBUILD:
        print("+", " ".join(cmd), flush=True)
        subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)


def _selfcheck():
    page = lambda body, nav="menu": f"<html><head><title>T</title></head><body><nav>{nav}</nav><p>{body}</p></body></html>"
    fake = {"u1": (200, page("same"), "u1"), "u2": (200, page("edited body"), "u2"),
            "u3": (200, page("same", nav="new menu"), "u3"), "u4": (404, "", "u4"), "u5": (0, "", "u5"),
            "u6": (200, page("same"), "u6/moved")}
    fetcher = lambda url, timeout=0: fake[url]
    base = check(list(fake), {}, fetch=fetcher, workers=2)
    assert all(e["status"] in ("baseline", "removed", "error", "changed") for e in base.values())
    assert base["u1"]["status"] == "baseline" and base["u4"]["status"] == "removed" and base["u5"]["status"] == "error"
    assert base["u6"]["status"] == "changed" and base["u6"]["final_url"] == "u6/moved"
    prev = {"pages": {u: {**e, "sha256": page_hash("same")} for u, e in base.items()}}
    again = check(["u1", "u2", "u3", "u6"], prev, fetch=fetcher, workers=2)
    assert again["u1"]["status"] == "unchanged", again["u1"]
    assert again["u2"]["status"] == "changed"
    assert again["u3"]["status"] == "unchanged"  # nav-only edit does not count
    assert again["u6"]["status"] == "unchanged"  # a redirect already on record is not a change
    assert extract(page("x")) == ("T", "x")
    print("selfcheck ok")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--input", type=Path, default=ROOT / "cleaned_scrape_data.json")
    p.add_argument("--manifest", type=Path, default=ROOT / "freshness.json")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--selfcheck", action="store_true")
    a = p.parse_args()
    if a.selfcheck:
        return _selfcheck()
    if not a.input.exists():
        sys.exit(f"missing {a.input} (exit 3)")
    urls = sorted({pg["url"] for pg in json.loads(a.input.read_text(encoding="utf8"))})
    manifest = json.loads(a.manifest.read_text(encoding="utf8")) if a.manifest.exists() else {}
    pages = check(urls, manifest)
    counts = report(pages)
    stale = counts["changed"] + counts["removed"]
    rebuilt = bool(stale and a.rebuild)
    if rebuilt:
        rebuild()  # raises on failure, so the manifest below is only written once the index matches it
    if not a.dry_run:
        a.manifest.write_text(json.dumps({"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                          "pages": pages}, indent=1), encoding="utf8")
        print(f"wrote {a.manifest.name}")
    sys.exit(0 if rebuilt else 1 if stale else 2 if counts["error"] else 0)


if __name__ == "__main__":
    main()
