"""Add the four missing resource-metadata fields (requirement R11) to every chunk.

Reads chunks.json + cleaned_scrape_data.json, writes chunks_enriched.json with:
  engagement_category  one of the seven categories in README (judged per page by the
                       model in llm.py, cached in enrichment_cache.json so it runs once)
  college_unit         derived from the page's host and path
  contact              emails and phone numbers found on the page, up to 3 (empty if none;
                       nothing is guessed)
  retrieved_at         the git commit date of multi_seed_scrape_data.json. The scraper did
                       not record a crawl time, so this is the latest honest bound.

Run: python enrich.py            then   python vector_search.py index chunks_enriched.json
     python enrich.py --check    prints the 30-record metadata check from the test plan

Honest limitation: category is a model judgment over the page's first ~400 words;
a page about two things gets one label. college_unit is a host/path map, not an
org chart.
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

CATEGORIES = ["recruiting", "research partnerships", "capstone sponsorship", "student organizations",
              "events", "giving", "employee education", "other"]
UNITS = [  # (host, path prefix) -> unit; first match wins
    ("lf.psu.edu", "", "Learning Factory"),
    ("career.engr.psu.edu", "", "Career Resources & Employer Relations"),
    ("www.me.psu.edu", "", "Department of Mechanical Engineering"),
    ("www.engr.psu.edu", "/research", "Office of Research"),
    ("www.engr.psu.edu", "/giving", "Development and Alumni Relations"),
    ("www.engr.psu.edu", "/alumni", "Development and Alumni Relations"),
    ("www.engr.psu.edu", "/ipac", "Industrial and Professional Advisory Council"),
    ("www.engr.psu.edu", "/partnership-opportunities", "Corporate Partnerships"),
    ("www.engr.psu.edu", "/academics", "Academic Affairs"),
    ("www.engr.psu.edu", "", "College of Engineering"),
]
# PSU access ids are letters then digits (jjt5008, seb40, atsbilen). Flattened HTML can glue a
# title or phone onto the id ("Consultant814-865-4740drs199@psu.edu"), so match from the letters.
EMAIL = re.compile(r"[a-z]+\d{0,5}@psu\.edu", re.I)
PHONE = re.compile(r"814[-.]\d{3}[-.]\d{4}")
CACHE = Path("enrichment_cache.json")


def unit_for(url):
    p = urlparse(url)
    return next((u for h, pre, u in UNITS if p.netloc == h and p.path.startswith(pre)), "College of Engineering")


def contacts_for(content):
    found = list(dict.fromkeys(EMAIL.findall(content) + PHONE.findall(content)))
    return found[:3]


def scrape_commit_date(path="multi_seed_scrape_data.json"):
    try:
        return subprocess.run(["git", "log", "-1", "--format=%cI", "--", path], capture_output=True,
                              text=True, check=True).stdout.strip() or None
    except Exception:
        return None


def categorize(pages, llm=None):
    """{url: category} for every page, cached. Batches of 10 pages per model call."""
    cache = json.loads(CACHE.read_text(encoding="utf8")) if CACHE.exists() else {}
    todo = [p for p in pages if p["url"] not in cache]
    if todo:
        if llm is None:
            from llm import chat
            llm = chat
        for i in range(0, len(todo), 10):
            batch = todo[i:i + 10]
            listing = "\n\n".join(f"{j}. TITLE: {p['title']}\nURL: {p['url']}\nTEXT: {' '.join(p['content'].split()[:120])}"
                                  for j, p in enumerate(batch, 1))
            prompt = (f"Classify each page by which outside-organization need it serves. Categories: {', '.join(CATEGORIES)}.\n"
                      f"Reply with one line per page: `<number>: <category>` using the exact category names.\n\n{listing}")
            reply = llm([{"role": "user", "content": prompt}], max_tokens=1500)
            got = dict(re.findall(r"(\d+)\s*[:.)]\s*([a-z ]+)", reply.lower()))
            for j, p in enumerate(batch, 1):
                label = got.get(str(j), "other").strip()
                cache[p["url"]] = label if label in CATEGORIES else "other"
            print(f"categorized {min(i + 10, len(todo))}/{len(todo)}", file=sys.stderr)
        CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf8")
    return cache


def enrich(chunks, pages, categories, retrieved_at):
    by_url = {p["url"]: p for p in pages}
    for c in chunks:
        url = c["url"]
        c["engagement_category"] = categories.get(url, "other")
        c["college_unit"] = unit_for(url)
        c["contact"] = contacts_for(by_url[url]["content"]) if url in by_url else []
        c["retrieved_at"] = retrieved_at
    return chunks


def check(chunks, n=30):
    """The test plan's 30-record check: all six fields present per unique document."""
    seen, rows = set(), []
    for c in chunks:
        if c["document_id"] in seen:
            continue
        seen.add(c["document_id"])
        rows.append(c)
        if len(rows) == n:
            break
    fields = ["title", "engagement_category", "college_unit", "contact", "url", "retrieved_at"]
    print(f"{'#':>2} {'title':40} {'category':22} {'unit':38} contact")
    complete = 0
    for i, c in enumerate(rows, 1):
        ok = all(c.get(f) not in (None, "", []) for f in fields if f != "contact")
        complete += ok
        print(f"{i:>2} {c['title'][:40]:40} {c['engagement_category']:22} {c['college_unit'][:38]:38} "
              f"{', '.join(c['contact']) or '-'}")
    print(f"\n{complete}/{len(rows)} records have title, category, unit, url, retrieved_at; "
          f"{sum(1 for c in rows if c['contact'])}/{len(rows)} have a contact found on the page (none guessed)")
    print("category counts:", dict(Counter(c["engagement_category"] for c in rows)))


def _selfcheck():
    assert unit_for("https://lf.psu.edu/sponsors/sponsor-a-project/") == "Learning Factory"
    assert unit_for("https://www.engr.psu.edu/giving/staff.aspx") == "Development and Alumni Relations"
    assert unit_for("https://www.engr.psu.edu/") == "College of Engineering"
    assert contacts_for("Email jjt5008@psu.edu or call 814-863-1229, again jjt5008@psu.edu") == ["jjt5008@psu.edu", "814-863-1229"]
    assert contacts_for("HR Consultant814-865-4740drs199@psu.edu") == ["drs199@psu.edu", "814-865-4740"]
    fake = lambda m, **kw: "1: giving\n2: banana"
    pages = [{"url": "u1", "title": "t", "content": "x"}, {"url": "u2", "title": "t", "content": "x"}]
    global CACHE
    real, CACHE = CACHE, Path("enrichment_cache.selfcheck.json")  # never touch the real cache
    try:
        cats = categorize(pages, fake)
    finally:
        CACHE.unlink(missing_ok=True)
        CACHE = real
    assert cats == {"u1": "giving", "u2": "other"}
    print("selfcheck ok")


def main():
    if "--selfcheck" in sys.argv:
        return _selfcheck()
    chunks = json.loads(Path("chunks.json").read_text(encoding="utf8"))
    if "--check" in sys.argv:
        return check(json.loads(Path("chunks_enriched.json").read_text(encoding="utf8")))
    pages = json.loads(Path("cleaned_scrape_data.json").read_text(encoding="utf8"))
    cats = categorize(pages)
    enriched = enrich(chunks, pages, cats, scrape_commit_date())
    Path("chunks_enriched.json").write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"wrote chunks_enriched.json ({len(enriched)} chunks); category counts: "
          f"{dict(Counter(cats.values()))}")
    check(enriched)


if __name__ == "__main__":
    main()
