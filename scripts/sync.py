#!/usr/bin/env python3
"""Pull open EU public procurement calls from the official TED Search API
and merge them into a local JSONL store.

TED Search API: https://docs.ted.europa.eu/api/latest/index.html
Anonymous access, no API key required.
"""
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

_CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "config.json")
with open(_CFG_PATH, encoding="utf-8") as _f:
    ARCHIVE_DAYS = int(json.load(_f).get("archive_days") or 90)

API = "https://api.ted.europa.eu/v3/notices/search"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data", "notices")
ARCHIVE_DIR = os.path.join(ROOT, "data", "archive")
LEGACY = os.path.join(ROOT, "data", "notices.jsonl")

# Notice types that represent an open opportunity (validated against the API).
OPEN_TYPES = ["cn-standard", "cn-social", "cn-desg",
              "pin-cfc-standard", "pin-cfc-social", "qu-sy"]

FIELDS = ["publication-number", "notice-title", "buyer-name", "buyer-country",
          "classification-cpv", "deadline-receipt-request", "publication-date",
          "notice-type", "contract-nature", "place-of-performance",
          "description-proc"]

WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "30"))
PAGE_SIZE = 250
MAX_PAGES = int(os.environ.get("MAX_PAGES", "400"))
USER_AGENT = "bidledger/1.0 (open data reuse; TED Search API)"
RETRYABLE_HTTP_CODES = {403, 429, 500, 502, 503, 504}


def post(body, attempt=0):
    req = urllib.request.Request(
        API,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # TED occasionally rejects an otherwise valid anonymous request with a
        # transient 403.  A later scheduled run succeeds unchanged, so handle
        # it like the API's other temporary/rate-limit responses instead of
        # losing the whole daily build on the first page.
        if e.code in RETRYABLE_HTTP_CODES and attempt < 6:
            retry_after = e.headers.get("Retry-After") if e.headers else None
            try:
                wait = max(1, min(120, int(retry_after)))
            except (TypeError, ValueError):
                wait = min(60, 2 ** attempt * 3)
            print(f"  HTTP {e.code} -> retry in {wait}s")
            time.sleep(wait)
            return post(body, attempt + 1)
        raise
    except urllib.error.URLError:
        if attempt < 6:
            time.sleep(min(60, 2 ** attempt * 3))
            return post(body, attempt + 1)
        raise


def pick_lang(value, prefer=("eng", "ENG")):
    """TED returns multilingual dicts; prefer English, fall back to anything."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return pick_lang(value[0]) if value else ""
    if isinstance(value, dict):
        for k in prefer:
            if k in value:
                return pick_lang(value[k])
        for v in value.values():
            got = pick_lang(v)
            if got:
                return got
    return ""


def first_nuts(places):
    if not places:
        return ""
    for p in places:
        if isinstance(p, str) and len(p) > 3 and any(c.isdigit() for c in p):
            return p
    return places[0] if isinstance(places[0], str) else ""


def next_deadline(values):
    """Earliest deadline that is still in the future."""
    if not values:
        return ""
    now = datetime.now(timezone.utc)
    best = None
    for v in values:
        try:
            d = datetime.fromisoformat(str(v))
        except ValueError:
            continue
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        if d > now and (best is None or d < best):
            best = d
    return best.isoformat() if best else ""


def normalise(n):
    pid = n.get("publication-number")
    if not pid:
        return None
    cpvs = n.get("classification-cpv") or []
    cpvs = [c for c in cpvs if isinstance(c, str)]
    deadline = next_deadline(n.get("deadline-receipt-request") or [])
    if not deadline:
        return None
    desc = pick_lang(n.get("description-proc"))
    return {
        "id": pid,
        "t": pick_lang(n.get("notice-title")).strip()[:300],
        "b": pick_lang(n.get("buyer-name")).strip()[:160],
        "c": (n.get("buyer-country") or [""])[0] if isinstance(n.get("buyer-country"), list) else (n.get("buyer-country") or ""),
        "cpv": sorted({c[:2] for c in cpvs if len(c) >= 2}),
        "cpvf": cpvs[0] if cpvs else "",
        "nat": (n.get("contract-nature") or [""])[0] if isinstance(n.get("contract-nature"), list) else (n.get("contract-nature") or ""),
        "ty": n.get("notice-type") or "",
        "p": str(n.get("publication-date") or "")[:10],
        "d": deadline,
        "nuts": first_nuts(n.get("place-of-performance") or []),
        "desc": " ".join(desc.split())[:400],
    }


def fetch_all():
    query = (f"notice-type IN ({' '.join(OPEN_TYPES)}) "
             f"AND publication-date>=today(-{WINDOW_DAYS})")
    out, token, pages = {}, None, 0
    while pages < MAX_PAGES:
        body = {"query": query, "limit": PAGE_SIZE, "scope": "ACTIVE",
                "fields": FIELDS, "paginationMode": "ITERATION"}
        if token:
            body["iterationNextToken"] = token
        else:
            body["page"] = 1
        data = post(body)
        notices = data.get("notices") or []
        for n in notices:
            rec = normalise(n)
            if rec:
                out[rec["id"]] = rec
        pages += 1
        total = data.get("totalNoticeCount")
        print(f"  page {pages}: +{len(notices)} (kept {len(out)} / {total} total)")
        token = data.get("iterationNextToken")
        if not token or not notices:
            break
        time.sleep(1.0)
    return out


def shard_key(rec):
    """Group by publication month: old shards stop changing, so daily diffs stay small."""
    return (rec.get("p") or rec.get("d") or "unknown")[:7] or "unknown"


def load_store():
    store = {}
    paths = []
    if os.path.exists(LEGACY):
        paths.append(LEGACY)
    if os.path.isdir(STORE_DIR):
        paths += [os.path.join(STORE_DIR, f) for f in sorted(os.listdir(STORE_DIR))
                  if f.endswith(".jsonl")]
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    store[rec["id"]] = rec
                except (ValueError, KeyError):
                    continue
    return store


def save_store(store):
    os.makedirs(STORE_DIR, exist_ok=True)
    shards = {}
    for rec in store.values():
        shards.setdefault(shard_key(rec), []).append(rec)
    for name, recs in shards.items():
        recs.sort(key=lambda r: r["id"])
        write_lines(os.path.join(STORE_DIR, f"{name}.jsonl"),
                    (json.dumps(rec, ensure_ascii=False, sort_keys=True)
                     for rec in recs))
    # remove shards that no longer hold anything
    for f in os.listdir(STORE_DIR):
        if f.endswith(".jsonl") and f[:-6] not in shards:
            os.remove(os.path.join(STORE_DIR, f))
    if os.path.exists(LEGACY):
        os.remove(LEGACY)


def write_lines(path, lines):
    """Write a data file so that an interrupted run cannot truncate it.

    Everything here is unattended. A process killed halfway through rewriting
    a month of the archive would leave a short file, and the records past the
    cut would be gone for good — the archive is the one thing that cannot be
    fetched again from TED. Writing beside the target and renaming means the
    old file survives intact until the new one is complete.
    """
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def archive_key(rec):
    """Group the archive by the month the call closed in.

    Once a month is past, its file never changes again, so the daily commit
    stays small no matter how large the archive grows.
    """
    return (rec.get("d") or "unknown")[:7]


def archive(dropped):
    """Keep closed calls for good, in an append-only store beside the live one.

    The site only publishes the last ARCHIVE_DAYS of closed calls, to keep the
    page count in hand. The record itself is worth more than the page: a run of
    historical procurement data is the one thing here that cannot be fetched
    from TED, which only serves what is current. Throwing it away each night
    would mean starting from nothing every night.
    """
    if not dropped:
        return 0
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    by_month = {}
    for rec in dropped:
        by_month.setdefault(archive_key(rec), {})[rec["id"]] = rec

    added = 0
    for month, recs in by_month.items():
        path = os.path.join(ARCHIVE_DIR, f"{month}.jsonl")
        existing = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        r = json.loads(line)
                        existing[r["id"]] = r
        before = len(existing)
        existing.update(recs)
        added += len(existing) - before
        write_lines(path, (json.dumps(existing[rid], ensure_ascii=False,
                                      sort_keys=True)
                           for rid in sorted(existing)))
    return added


def archive_size():
    if not os.path.isdir(ARCHIVE_DIR):
        return 0
    total = 0
    for name in os.listdir(ARCHIVE_DIR):
        if name.endswith(".jsonl"):
            with open(os.path.join(ARCHIVE_DIR, name), encoding="utf-8") as f:
                total += sum(1 for line in f if line.strip())
    return total


def main():
    print(f"TED sync — window {WINDOW_DAYS} days")
    fresh = fetch_all()
    store = load_store()
    before = len(store)

    # Nothing runs here by hand, so a bad day at the API must not be allowed to
    # quietly wipe the store and publish an empty site. A pull that comes back
    # with almost nothing is treated as a failure, and the previous store and
    # the site already deployed from it are both left alone.
    now = datetime.now(timezone.utc)

    def still_open(rec):
        try:
            d = datetime.fromisoformat(rec["d"])
        except (ValueError, KeyError, TypeError):
            return False
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d > now

    # Compare like with like: the store also holds closed calls kept for the
    # archive, and that share grows every day, so the yardstick has to be the
    # open ones alone.
    # Only a full pull can be judged against the whole store; a deliberately
    # short window (WINDOW_DAYS=3, for trying things out) returns little by
    # design and must not trip the guard.
    full_pull = WINDOW_DAYS >= 14
    open_before = sum(1 for v in store.values() if still_open(v))
    if full_pull and open_before and len(fresh) < open_before * 0.4:
        raise SystemExit(
            f"aborting: the API returned {len(fresh)} notices against "
            f"{open_before} open ones already held. Refusing to overwrite the "
            f"store. Nothing was changed."
        )

    new = [k for k in fresh if k not in store]
    store.update(fresh)

    # Keep closed calls for as long as the site still publishes their page, so
    # an indexed URL never turns into a 404. build.py reads the same setting.
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_DAYS)
    kept = {}
    for k, v in store.items():
        try:
            d = datetime.fromisoformat(v["d"])
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
        except (ValueError, KeyError):
            continue
        if d > cutoff:
            kept[k] = v

    open_after = sum(1 for v in kept.values() if still_open(v))
    if full_pull and open_before and open_after < open_before * 0.5:
        raise SystemExit(
            f"aborting: open notices would fall from {open_before} to "
            f"{open_after}. That is not a normal day's expiry. Nothing was changed."
        )

    # Archive a call the day it closes, not the day it falls out of the site's
    # window: the history is the asset, and waiting sixty days to write it down
    # means a bad config or a bad night can lose it. archive() dedupes, so
    # offering the same record again on every run costs nothing.
    added = archive([v for v in store.values() if not still_open(v)])

    save_store(kept)
    print(f"store: {before} -> {len(kept)}  (+{len(new)} new, "
          f"{len(store) - len(kept)} past the {ARCHIVE_DAYS}-day window)")
    print(f"archive: +{added} kept for good, {archive_size()} closed calls held")
    meta = {"generated": datetime.now(timezone.utc).isoformat(),
            "total": len(kept), "new": len(new)}
    with open(os.path.join(ROOT, "data", "last_run.json"), "w") as f:
        json.dump(meta, f, indent=2)


if __name__ == "__main__":
    main()
