#!/usr/bin/env python3
"""One screen that says whether the machine is still running.

Nothing here is run by hand day to day, so the point of this script is to make
a cold check cheap: it asks the live site the questions that would reveal the
failures that matter, and prints a verdict per line.

    python scripts/health.py
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
BASE = (os.environ.get("SITE_URL") or CFG["base_url"]).rstrip("/")
BASE_PATH = urllib.parse.urlparse(BASE).path.rstrip("/") if BASE else ""

problems = []


def check(label, ok, detail=""):
    print(f"  {'OK  ' if ok else 'FAIL'}  {label:<34} {detail}")
    if not ok:
        problems.append(label)


def get(path, timeout=45):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "bidledger-health"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def head(path, timeout=45):
    req = urllib.request.Request(BASE + path, method="HEAD",
                                 headers={"User-Agent": "bidledger-health"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main():
    print(f"\n{CFG['brand']} — {BASE}\n")

    try:
        _, raw = get("/api/stats.json")
        stats = json.loads(raw)
    except Exception as e:
        check("the site answers at all", False, repr(e))
        print("\nNothing else can be checked while the site is down.\n")
        return 1

    built = datetime.fromisoformat(stats["generated"])
    age = (datetime.now(timezone.utc) - built).total_seconds() / 3600
    check("rebuilt recently", age < 30, f"{age:.1f} h ago")
    check("open notices present", stats["open_notices"] > 5000,
          f"{stats['open_notices']:,} open, {stats['archived_notices']:,} archived")
    check("countries and sectors", stats["countries"] > 20 and stats["sectors"] > 20,
          f"{stats['countries']} countries, {stats['sectors']} sectors")
    check("CPV vocabulary loaded", stats["cpv_codes_in_use"] > 1000,
          f"{stats['cpv_codes_in_use']:,} codes in use")

    # The archive only ever grows. A drop means something ate the history.
    arch = stats.get("archived_notices", 0)
    seen = 0
    state = os.path.join(ROOT, "data", "health_seen.json")
    if os.path.exists(state):
        try:
            seen = json.load(open(state, encoding="utf-8")).get("archived", 0)
        except (ValueError, OSError):
            seen = 0
    check("archive has not shrunk", arch >= seen,
          f"{arch:,} held, {seen:,} at the last check")
    try:
        json.dump({"archived": max(arch, seen), "at": stats["generated"]},
                  open(state, "w", encoding="utf-8"))
    except OSError:
        pass

    _, home = get("/")
    home = home.decode("utf-8", "replace")
    check("stylesheet path is prefixed", f'href="{BASE_PATH}/style.css"' in home)
    check("canonical tag present", 'rel="canonical"' in home)
    check("Search Console tag present", "google-site-verification" in home)
    check("no third-party requests", "googleapis" not in home and "gstatic" not in home)
    check("no cookies or storage code", "document.cookie" not in home
          and "localStorage" not in home)

    _, smap = get("/sitemap.xml")
    smap = smap.decode("utf-8", "replace")
    parts = smap.count("<sitemap>")
    check("sitemap is an index", parts >= 5, f"{parts} sections")
    bad = [p for p in ("core", "sectors", "countries", "cpv")
           if head(f"/sitemap-{p}.xml") != 200]
    check("sitemap sections reachable", not bad, ", ".join(bad) or "all 200")

    try:
        _, raw_text_smap = get("/sitemap-google.txt")
        text_urls = raw_text_smap.decode("utf-8").splitlines()
        text_ok = (0 < len(text_urls) <= 50000
                   and all(url.startswith(BASE + "/") for url in text_urls))
        check("Google text sitemap valid", text_ok, f"{len(text_urls):,} URLs")
    except Exception as e:
        check("Google text sitemap valid", False, repr(e))

    key = CFG.get("indexnow_key")
    check("IndexNow key file served", bool(key) and head(f"/{key}.txt") == 200)

    for path in ("/cpv.html", "/api.html", "/privacy.html", "/alerts.html"):
        check(f"page {path}", head(path) == 200)

    print()
    if problems:
        print(f"{len(problems)} problem(s): " + "; ".join(problems) + "\n")
        return 1
    print("Everything checked out.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
