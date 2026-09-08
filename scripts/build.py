#!/usr/bin/env python3
"""Generate the static site from the local notice store."""
import csv
import html
import io
import json
import os
import re
import shutil
from urllib.parse import urlparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import meta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "data", "notices")
LEGACY = os.path.join(ROOT, "data", "notices.jsonl")
OUT = os.path.join(ROOT, "site")
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))

BRAND = CFG["brand"]
BASE = (os.environ.get("SITE_URL") or CFG["base_url"]).rstrip("/")
NOW = datetime.now(timezone.utc)
# GitHub Pages serves project sites under /<repo>/, so every in-page link
# needs that prefix. Derived from SITE_URL; empty for a root domain.
PREFIX = urlparse(BASE).path.rstrip("/") if BASE else ""
ARCHIVE_DAYS = int(CFG.get("archive_days") or 90)
# Search Console verification: the token from the "HTML tag" method.
VERIFY = (CFG.get("google_site_verification") or "").strip()
VERIFY_BING = (CFG.get("bing_site_verification") or "").strip()

CSS = """
:root{
  --paper:#f6f5f0; --ink:#14201c; --mut:#5d6b65; --line:#d8d8cf;
  --card:#fffefa; --seal:#1f5c4a; --seal-soft:#e4ece7; --flag:#9a5a12; --rule:#25342e;
}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#11150f; --ink:#e6e8e0; --mut:#98a39a; --line:#2a2f28;
  --card:#171c15; --seal:#7fc0a5; --seal-soft:#17251f; --flag:#d9a25a; --rule:#3a4239;
}}
:root[data-theme="dark"]{
  --paper:#11150f; --ink:#e6e8e0; --mut:#98a39a; --line:#2a2f28;
  --card:#171c15; --seal:#7fc0a5; --seal-soft:#17251f; --flag:#d9a25a; --rule:#3a4239;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{background:var(--paper);color:var(--ink);
  font-family:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}
a{color:var(--seal);text-decoration:none}
a:hover{text-decoration:underline;text-underline-offset:2px}
:focus-visible{outline:2px solid var(--seal);outline-offset:2px}
.wrap{max-width:1000px;margin:0 auto;padding:0 24px}
.mast{border-bottom:2px solid var(--rule);background:var(--paper)}
.mast .wrap{display:flex;align-items:baseline;gap:26px;padding:18px 24px 14px}
.logo{font-family:"Newsreader",Georgia,serif;font-weight:600;font-size:23px;
  letter-spacing:-.015em;color:var(--ink)}
.logo em{font-style:normal;color:var(--seal)}
.mast nav{margin-left:auto;display:flex;gap:20px;font-size:13px;letter-spacing:.02em}
.mast nav a{color:var(--mut)}
.mast nav a:hover{color:var(--ink)}
h1{font-family:"Newsreader",Georgia,serif;font-weight:600;font-size:clamp(28px,4.2vw,42px);
  line-height:1.12;letter-spacing:-.02em;margin:38px 0 10px;text-wrap:balance;max-width:20ch}
h2{font-family:"IBM Plex Sans",sans-serif;font-size:12px;font-weight:600;
  text-transform:uppercase;letter-spacing:.14em;color:var(--mut);
  margin:44px 0 14px;padding-bottom:7px;border-bottom:1px solid var(--line)}
.sub{color:var(--mut);max-width:60ch;font-size:16.5px}
.band{display:flex;gap:0;flex-wrap:wrap;margin:26px 0 30px;
  border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.band div{padding:13px 26px 13px 0;margin-right:26px;border-right:1px solid var(--line)}
.band div:last-child{border-right:0}
.band b{display:block;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:21px;font-weight:500;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.band span{font-size:10.5px;text-transform:uppercase;letter-spacing:.13em;color:var(--mut)}
#q{width:100%;padding:14px 16px;font-size:16px;font-family:inherit;
  border:1px solid var(--rule);border-radius:2px;background:var(--card);color:var(--ink)}
#q::placeholder{color:var(--mut)}
.filters{display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 6px}
.filters select{padding:9px 11px;border:1px solid var(--line);border-radius:2px;
  background:var(--card);color:var(--ink);font-family:inherit;font-size:13.5px}
.row{display:grid;grid-template-columns:104px 1fr 132px;gap:20px;align-items:start;
  padding:15px 0;border-bottom:1px solid var(--line)}
.row .ref{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;
  color:var(--mut);padding-top:2px;font-variant-numeric:tabular-nums}
.row .ttl{font-size:15.5px;line-height:1.45}
.row .ttl a{color:var(--ink);font-weight:500}
.row .ttl a:hover{color:var(--seal)}
.row .meta{color:var(--mut);font-size:13px;margin-top:3px}
.row .when{text-align:right;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:12.5px;color:var(--mut);font-variant-numeric:tabular-nums;padding-top:2px}
.row .when b{display:block;color:var(--ink);font-weight:500}
.row .when.soon b{color:var(--flag)}
.chip{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:10.5px;
  letter-spacing:.04em;background:var(--seal-soft);color:var(--seal);
  padding:2px 7px;border-radius:2px;margin-right:5px}
.index{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:0 34px}
.cpv{border-top:1px solid var(--line);margin:18px 0}
.cpv a{display:grid;grid-template-columns:96px 1fr auto;gap:8px 18px;align-items:baseline;
  padding:11px 4px;border-bottom:1px solid var(--line);color:var(--ink)}
.cpv a:hover{background:var(--seal-soft);text-decoration:none}
.cpv a:not([href]){color:var(--mut);cursor:default}
.cpv a:not([href]):hover{background:none}
.cpv b{font-family:"IBM Plex Mono",monospace;font-size:13px;font-weight:500;color:var(--seal)}
.cpv i{font-style:normal}
.cpv u{text-decoration:none;font-family:"IBM Plex Mono",monospace;font-size:12px;
  color:var(--mut);white-space:nowrap}
.cpv em{font-style:normal;background:var(--seal-soft);border-radius:2px}
.closed{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:11px;
  letter-spacing:.08em;text-transform:uppercase;color:var(--flag);
  border:1px solid var(--flag);border-radius:2px;padding:2px 7px;margin-top:26px}
@media(max-width:560px){.cpv a{grid-template-columns:1fr auto}.cpv b{grid-column:1/-1}}
.index a{display:flex;align-items:baseline;gap:8px;padding:7px 0;
  border-bottom:1px dotted var(--line);color:var(--ink);font-size:14px}
.index a:hover{color:var(--seal);text-decoration:none}
.index a i{font-style:normal;flex:1;border-bottom:1px dotted var(--line);
  transform:translateY(-3px)}
.index a u{text-decoration:none;font-family:"IBM Plex Mono",monospace;font-size:12px;
  color:var(--mut);font-variant-numeric:tabular-nums}
.note{border-left:3px solid var(--seal);background:var(--card);padding:20px 22px;margin:38px 0}
.note h2{margin-top:0;border:0;padding:0}
.note p{max-width:58ch;color:var(--mut)}
.btn{display:inline-block;background:var(--seal);color:var(--paper);padding:10px 20px;
  border-radius:2px;font-size:14px;font-weight:600;margin-top:14px;letter-spacing:.01em}
.btn:hover{text-decoration:none;filter:brightness(1.08)}
.crumb{font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--mut);
  letter-spacing:.05em;text-transform:uppercase;margin-top:26px}
.detail dl{display:grid;grid-template-columns:200px 1fr;gap:0;margin:26px 0;font-size:15px}
.detail dt{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.1em;
  padding:11px 0;border-bottom:1px solid var(--line)}
.detail dd{padding:11px 0;border-bottom:1px solid var(--line)}
.desc{background:var(--card);border:1px solid var(--line);padding:18px 20px;
  margin:22px 0;font-size:15px;max-width:66ch}
footer{border-top:2px solid var(--rule);margin-top:64px;padding:26px 0 52px;
  font-size:12.5px;color:var(--mut);line-height:1.7}
footer a{color:var(--mut);text-decoration:underline}
@media(max-width:660px){
  .row{grid-template-columns:1fr;gap:5px}
  .row .when{text-align:left}.row .ref{padding-top:0}
  .detail dl{grid-template-columns:1fr}.detail dt{border:0;padding-bottom:0}
  .band div{padding-right:18px;margin-right:18px}
  .mast .wrap{flex-wrap:wrap;gap:10px}
}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


def esc(s):
    return html.escape(str(s or ""))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def page(title, body, desc="", canonical="", extra_head=""):
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{f'<meta name="google-site-verification" content="{esc(VERIFY)}">' if VERIFY else ''}
{f'<meta name="msvalidate.01" content="{esc(VERIFY_BING)}">' if VERIFY_BING else ''}
{f'<link rel="canonical" href="{BASE}{canonical}">' if BASE and canonical else ''}
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(BRAND)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
{f'<meta property="og:url" content="{BASE}{canonical}">' if BASE and canonical else ''}
{f'<meta property="og:image" content="{BASE}/brand/og.png"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{BASE}/brand/og.png">' if BASE else ''}
<link rel="icon" href="/brand/avatar.png" type="image/png">
<link rel="stylesheet" href="/style.css">{extra_head}</head><body>
<header class="mast"><div class="wrap"><a class="logo" href="/">Bid<em>ledger</em></a>
<nav><a href="/sectors.html">Sectors</a><a href="/countries.html">Countries</a>
<a href="/winners.html">Who wins</a><a href="/cpv.html">CPV codes</a><a href="/export.html">CSV</a><a href="/api.html">API</a>
<a href="/alerts.html">Daily alerts</a><a href="/about.html">About</a></nav></div></header>
<div class="wrap">{body}</div>
<footer><div class="wrap">
Data source: <a href="https://ted.europa.eu/">Tenders Electronic Daily (TED)</a>, the official
journal of EU public procurement, re-used under the European Commission's open data policy.
{BRAND} is an independent service and is not affiliated with the European Union.<br>
<a href="/privacy.html">Privacy</a> &middot; <a href="/about.html">About</a> &middot; <a href="/api.html">API</a><br>
Rebuilt automatically every day &middot; last update {NOW.strftime('%d %b %Y %H:%M UTC')}
</div></footer></body></html>"""


def deadline_bits(iso):
    try:
        d = datetime.fromisoformat(iso)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "", 9999
    days = (d - NOW).days
    return d.strftime("%d %b %Y"), days


def card(n):
    dl, days = deadline_bits(n["d"])
    chips = "".join(f'<span class="chip">{esc(meta.cpv_label(c))[:26]}</span>'
                    for c in n.get("cpv", [])[:2])
    soon = " soon" if days <= 7 else ""
    left = f"{days} days left" if days >= 0 else ""
    return f"""<div class="row">
<div class="ref">{esc(n['id'])}</div>
<div class="ttl"><a href="/n/{esc(n['id'])}.html">{esc(n['t'])}</a>
<div class="meta">{esc(meta.country_name(n.get('c')))} &middot; {esc(n.get('b'))[:64]}</div>
<div style="margin-top:6px">{chips}</div></div>
<div class="when{soon}"><b>{esc(dl)}</b>{esc(left)}</div></div>"""


def load():
    rows, seen = [], set()
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
                rec = json.loads(line)
                if rec["id"] in seen:
                    continue
                seen.add(rec["id"])
                rows.append(rec)
    rows.sort(key=lambda r: r["d"])
    return rows


def write(path, content):
    if PREFIX and path.endswith((".html", ".xml")):
        content = (content
                   .replace('href="/', f'href="{PREFIX}/')
                   .replace('src="/', f'src="{PREFIX}/')
                   .replace("fetch('/api/", f"fetch('{PREFIX}/api/"))
    full = os.path.join(OUT, path.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def rss(title, link, items):
    entries = "".join(f"""<item><title>{esc(i['t'])}</title>
<link>{BASE}/n/{esc(i['id'])}.html</link>
<guid isPermaLink="false">{esc(i['id'])}</guid>
<pubDate>{esc(i.get('p'))}</pubDate>
<description>{esc(meta.country_name(i.get('c')))} &mdash; {esc(i.get('b'))} &mdash; deadline {esc(deadline_bits(i['d'])[0])}</description>
</item>""" for i in items[:60])
    return f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<title>{esc(title)}</title><link>{BASE}{link}</link>
<description>Open EU public tenders &mdash; {esc(title)}</description>
{entries}</channel></rss>"""


def main():
    rows = load()
    print(f"building {len(rows)} live notices")
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True)

    # A call that has closed keeps its page for ARCHIVE_DAYS instead of
    # becoming a 404: the URL is already indexed, people go on searching for
    # tenders after they close, and deleting the page throws away the only
    # thing this site accumulates. Archived pages are marked as closed, kept
    # out of every listing, and left out of the sitemap.
    everything, rows, archive = rows, [], []
    for n in everything:
        d = deadline_bits(n["d"])[1]
        if d >= 0:
            rows.append(n)
        elif d > -ARCHIVE_DAYS:
            archive.append(n)
    print(f"{len(rows)} open, {len(archive)} recently closed")

    by_country = defaultdict(list)
    by_sector = defaultdict(list)
    for n in rows:
        by_country[n.get("c") or "XXX"].append(n)
        for d in n.get("cpv", []):
            by_sector[d].append(n)

    urls = ["/", "/sectors.html", "/countries.html", "/winners.html",
            "/alerts.html", "/about.html"]

    # ---- notice pages -------------------------------------------------
    for n, closed in [(x, False) for x in rows] + [(x, True) for x in archive]:
        dl, days = deadline_bits(n["d"])
        cpv_links = ", ".join(
            f'<a href="/s/{c}.html">{esc(meta.cpv_label(c))}</a>'
            for c in n.get("cpv", []))
        desc = (f'<div class="desc">{esc(n["desc"])}</div>' if n.get("desc") else "")
        div = (n.get("cpv") or ["00"])[0]
        if closed:
            lede = (f'<p class="sub"><b>This call has closed.</b> The deadline for '
                    f'submissions was {esc(dl)}. The page is kept as a record; for '
                    f'contracts still accepting bids, see '
                    f'<a href="/s/{esc(div)}.html">{esc(meta.cpv_label(div))}</a>.</p>')
            follow = (f'<div class="note"><h2>Looking for something like this?</h2>'
                      f'<p>{esc(meta.cpv_label(div))} tenders that are still open are '
                      f'listed here, and refreshed every morning.</p>'
                      f'<a class="btn" href="/s/{esc(div)}.html">Open tenders in this sector</a></div>')
        else:
            lede = (f'<p class="sub">Open call for tenders published in the EU Official '
                    f'Journal. {("Closes in %d days." % days) if 0 <= days < 400 else ""}</p>')
            follow = ('<div class="note"><h2>Rather not check this page every morning?</h2>'
                      '<p>Get the new tenders that match your sector and country in one '
                      'daily email.</p>'
                      '<a class="btn" href="/alerts.html">Set up alerts</a></div>')
        body = f"""<div class="detail">
<div class="crumb"><a href="/">Home</a> / <a href="/c/{esc(n.get('c'))}.html">{esc(meta.country_name(n.get('c')))}</a></div>
{'<p class="closed">Closed</p>' if closed else ''}
<h1>{esc(n['t'])}</h1>
{lede}
{desc}
<dl>
<dt>Buyer</dt><dd>{esc(n.get('b')) or '&mdash;'}</dd>
<dt>Country</dt><dd><a href="/c/{esc(n.get('c'))}.html">{esc(meta.country_name(n.get('c')))}</a></dd>
<dt>Submission deadline</dt><dd class="{'due' if 0 <= days <= 7 else ''}">{esc(dl) or '&mdash;'}</dd>
<dt>Contract type</dt><dd>{esc(meta.CONTRACT_NATURE.get(n.get('nat'), n.get('nat') or '&mdash;'))}</dd>
<dt>Sector (CPV)</dt><dd>{cpv_links or '&mdash;'}</dd>
<dt>Main CPV code</dt><dd>{f'<a href="/cpv/{esc(n["cpvf"])}.html">{esc(n["cpvf"])}</a>' if n.get('cpvf') else '&mdash;'}</dd>
<dt>Place of performance</dt><dd>{esc(n.get('nuts')) or '&mdash;'}</dd>
<dt>Published</dt><dd>{esc(n.get('p'))}</dd>
<dt>TED reference</dt><dd>{esc(n['id'])}</dd>
</dl>
<p><a class="btn" href="https://ted.europa.eu/en/notice/-/detail/{esc(n['id'])}" rel="nofollow noopener" target="_blank">Read the official notice on TED &rarr;</a></p>
{follow}
</div>"""
        ld = json.dumps({
            "@context": "https://schema.org", "@type": "GovernmentService",
            "name": n["t"][:200],
            "serviceType": "Public procurement notice",
            "provider": {"@type": "GovernmentOrganization", "name": n.get("b") or "Contracting authority"},
            "areaServed": meta.country_name(n.get("c")),
            "identifier": n["id"],
            "url": f"{BASE}/n/{n['id']}.html" if BASE else "",
        }, ensure_ascii=False)
        write(f"/n/{n['id']}.html",
              page(f"{'Closed: ' if closed else ''}{n['t'][:110]} | {BRAND}", body,
                   extra_head=f'<script type="application/ld+json">{ld}</script>',
                   desc=(f"Closed call: {n['t'][:120]}. The deadline was {dl}." if closed
                         else f"{meta.country_name(n.get('c'))}: {n['t'][:130]}. Deadline {dl}."),
                   canonical=f"/n/{n['id']}.html"))
        if not closed:
            urls.append(f"/n/{n['id']}.html")


    # ---- country x sector ------------------------------------------------
    # "construction tenders in Germany" is how buyers of this data actually
    # search: a trade and a place, not a CPV number. One page per pairing that
    # has enough open work to be worth reading.
    COMBO_MIN, COMBO_PER = 5, 100
    combos = defaultdict(list)
    for n in rows:
        for d in n.get("cpv", []):
            combos[(n.get("c") or "XXX", d)].append(n)
    combos = {k: v for k, v in combos.items() if len(v) >= COMBO_MIN}

    def combo_path(c, d, pg=1):
        stem = f"{slug(meta.country_name(c))}-{slug(meta.cpv_label(d))}"[:70].strip("-")
        return f"/t/{stem}.html" if pg == 1 else f"/t/{stem}-{pg}.html"

    combo_links = defaultdict(list)   # country -> rows, for the country pages
    for (c, d), items in sorted(combos.items()):
        cname, sname = meta.country_name(c), meta.cpv_label(d)
        combo_links[c].append((d, sname, len(items)))
        codes = defaultdict(int)
        for n in items:
            if n.get("cpvf"):
                codes[n["cpvf"]] += 1
        code_rows = "".join(
            f'<a href="/cpv/{k}.html"><b>{esc(k)}</b>'
            f'<i>{esc(meta.cpv_name(k))}</i><u>{v}</u></a>'
            for k, v in sorted(codes.items(), key=lambda kv: -kv[1])[:20])
        soon = sum(1 for n in items if 0 <= deadline_bits(n["d"])[1] <= 14)
        pages = max(1, -(-len(items) // COMBO_PER))
        for pg in range(1, pages + 1):
            piece = items[(pg - 1) * COMBO_PER: pg * COMBO_PER]
            nav = ""
            if pages > 1:
                bits = []
                if pg > 1:
                    bits.append(f'<a href="{combo_path(c, d, pg - 1)}">&larr; previous</a>')
                if pg < pages:
                    bits.append(f'<a href="{combo_path(c, d, pg + 1)}">next &rarr;</a>')
                nav = f'<p class="sub">Page {pg} of {pages} &middot; {" &middot; ".join(bits)}</p>'
            body = f"""<div class="crumb"><a href="/">Home</a>
 / <a href="/c/{esc(c)}.html">{esc(cname)}</a>
 / <a href="/s/{esc(d)}.html">{esc(sname)}</a></div>
<h1>{esc(sname)} tenders in {esc(cname)}</h1>
<p class="sub">{len(items)} open call{'s' if len(items) != 1 else ''} for tenders from
contracting authorities in {esc(cname)}, classified under CPV division {esc(d)}
&mdash; {esc(sname.lower())}.
{f'{soon} of them close within a fortnight. ' if soon else ''}Sorted by closing date and
rebuilt every morning from the EU Official Journal.</p>
{nav}
{"".join(card(n) for n in piece)}
{nav}
{f'<h2>The CPV codes used here</h2><div class="cpv">{code_rows}</div>' if code_rows and pg == 1 else ''}
<div class="note"><h2>Get these by email</h2>
<p>New {esc(sname.lower())} tenders in {esc(cname)}, in one message each morning,
instead of checking this page.</p>
<a class="btn" href="/alerts.html">Set up alerts</a>
&nbsp;<a class="btn" href="/feed/s-{esc(d)}.xml">RSS for this sector</a></div>
<p class="sub">See also: <a href="/c/{esc(c)}.html">every open tender in {esc(cname)}</a>
&middot; <a href="/s/{esc(d)}.html">{esc(sname)} across the EU</a></p>"""
            title = (f"{sname} tenders in {cname} | {BRAND}" if pg == 1
                     else f"{sname} tenders in {cname} — page {pg} | {BRAND}")
            path = combo_path(c, d, pg)
            write(path, page(title, body, canonical=path,
                             desc=f"{len(items)} open public tenders for {sname.lower()} "
                                  f"in {cname}, updated daily from the EU Official Journal."))
            urls.append(path)


    # ---- who wins the work ------------------------------------------------
    # Open tenders say who is buying. These pages say who has been winning,
    # with the amounts, which is the question a company actually has before it
    # decides what to bid. Nobody else publishes this as web pages: the data is
    # public, but it arrives as an API nobody calls. Built from the aggregate
    # in data/winners.json so the workflow does not need the 98 MB store.
    winners_path = os.path.join(ROOT, "data", "winners.json")
    winners = {}
    if os.path.exists(winners_path):
        with open(winners_path, encoding="utf-8") as f:
            winners = json.load(f)

    def eur(v, plain=False):
        """Money for a reader. `plain` uses a real euro sign, for meta tags:
        an HTML entity there gets escaped and shows up as literal text."""
        sign = "€" if plain else "&euro;"
        if v is None:
            return "unknown" if plain else "&mdash;"
        if v >= 1_000_000:
            return f"{sign}{v/1_000_000:,.1f}M"
        if v >= 1_000:
            return f"{sign}{v/1_000:,.0f}k"
        return f"{sign}{v:,.0f}"

    def winner_path(c, d):
        stem = f"{slug(meta.country_name(c))}-{slug(meta.cpv_label(d))}"[:70].strip("-")
        return f"/w/{stem}.html"

    winners_by_country = defaultdict(list)
    for key, w in sorted(winners.items()):
        c, d = key.split("|")
        cname, sname = meta.country_name(c), meta.cpv_label(d)
        winners_by_country[c].append((d, sname, w["n"]))

        sup_rows = "".join(
            f'<div class="row"><div class="ref">{i+1}</div>'
            f'<div class="ttl">{esc(name)}'
            f'<div class="meta">{n} contract{"s" if n != 1 else ""} won</div></div>'
            f'<div class="when"><b>{eur(total)}</b>total awarded</div></div>'
            for i, (name, n, total) in enumerate(w["top"]))

        rec_rows = "".join(
            f'<div class="row"><div class="ref">{esc(p)}</div>'
            f'<div class="ttl"><a href="https://ted.europa.eu/en/notice/-/detail/{esc(rid)}"'
            f' rel="nofollow noopener" target="_blank">{esc(title)}</a>'
            f'<div class="meta">Won by {esc(name)} &middot; bought by {esc(buyer)}</div></div>'
            f'<div class="when"><b>{eur(val)}</b></div></div>'
            for p, rid, name, val, buyer, title in w["recent"])

        nature = ", ".join(f"{meta.CONTRACT_NATURE.get(k, k)} {v:,}"
                           for k, v in list(w["nature"].items())[:3])
        open_now = len(combos.get((c, d), []))
        body = f"""<div class="crumb"><a href="/">Home</a>
 / <a href="/c/{esc(c)}.html">{esc(cname)}</a>
 / <a href="/s/{esc(d)}.html">{esc(sname)}</a></div>
<h1>Who wins {esc(sname.lower())} contracts in {esc(cname)}</h1>
<p class="sub">{w['n']:,} contracts were awarded to {w['suppliers']:,} different
companies over the two years to July 2026, in CPV division {esc(d)}. The median
award was {eur(w['median'])}. Every row here comes from the award notice the
contracting authority published in the EU Official Journal.</p>
<dl>
<dt>Contracts awarded</dt><dd>{w['n']:,}</dd>
<dt>Distinct winners</dt><dd>{w['suppliers']:,}</dd>
<dt>Median award</dt><dd>{eur(w['median'])}</dd>
<dt>With a published value</dt><dd>{w['priced']:,} of {w['n']:,}</dd>
<dt>Contract types</dt><dd>{esc(nature) or '&mdash;'}</dd>
</dl>

<h2>The companies winning most often</h2>
{sup_rows}
<p class="sub">Ranked by number of contracts, not by value, because a single
framework agreement can carry a ceiling far larger than the work actually done
under it. Totals are the sum of published values and should be read as an order
of magnitude, not an audited figure.</p>

<h2>Most recently awarded</h2>
{rec_rows}

{f'<div class="note"><h2>{open_now} of these are open right now</h2><p>Contracts of this kind still accepting bids in {esc(cname)}, refreshed every morning.</p><a class="btn" href="{combo_path(c, d)}">Open {esc(sname.lower())} tenders in {esc(cname)} &rarr;</a></div>' if open_now else ''}

<div class="note"><h2>The whole record, as data</h2>
<p>These pages are a reading of one slice. The full run &mdash; every award in the
Union, with the winner and the value in euro &mdash; is published as a dataset you
can download and check yourself.</p>
<a class="btn" href="{CFG['dataset_url']}" rel="noopener">Contract awards dataset &rarr;</a></div>

<p class="sub">See also:
<a href="/c/{esc(c)}.html">every open tender in {esc(cname)}</a> &middot;
<a href="/s/{esc(d)}.html">{esc(sname)} across the EU</a></p>"""

        path = winner_path(c, d)
        write(path, page(
            f"Who wins {sname.lower()} contracts in {cname} | {BRAND}", body,
            canonical=path,
            desc=f"{w['n']:,} {sname.lower()} contracts awarded in {cname} over two "
                 f"years, the {w['suppliers']:,} companies that won them, and the "
                 f"amounts. Median award {eur(w['median'], plain=True)}."))
        urls.append(path)


    # ---- sector pages -------------------------------------------------
    for d, items in sorted(by_sector.items()):
        label = meta.cpv_label(d)
        cards = "".join(card(n) for n in items[:200])
        body = f"""<div class="crumb"><a href="/">Home</a> / <a href="/sectors.html">Sectors</a></div>
<h1>{esc(label)}</h1>
<p class="sub">{len(items)} open public tenders across the EU in CPV division {esc(d)},
sorted by closing date. Updated daily from the EU Official Journal.</p>
<p><a href="/feed/s-{esc(d)}.xml">RSS feed for this sector</a></p>
{cards}"""
        write(f"/s/{d}.html",
              page(f"Open EU public tenders: {label} | {BRAND}", body,
                   desc=f"{len(items)} open EU public tenders in {label}. Updated daily.",
                   canonical=f"/s/{d}.html"))
        write(f"/feed/s-{d}.xml", rss(f"{label} tenders", f"/s/{d}.html", items))
        urls.append(f"/s/{d}.html")

    # ---- country pages ------------------------------------------------
    for c, items in sorted(by_country.items()):
        name = meta.country_name(c)
        cards = "".join(card(n) for n in items[:200])
        body = f"""<div class="crumb"><a href="/">Home</a> / <a href="/countries.html">Countries</a></div>
<h1>Public tenders in {esc(name)}</h1>
<p class="sub">{len(items)} open calls for tenders from contracting authorities in
{esc(name)}, published in the EU Official Journal and sorted by closing date.</p>
<p><a href="/feed/c-{esc(c)}.xml">RSS feed for {esc(name)}</a></p>
{f'<h2>By sector in {esc(name)}</h2><div class="cpv">' + "".join(f'<a href="{combo_path(c, d)}"><b>{esc(d)}</b><i>{esc(lbl)}</i><u>{k}</u></a>' for d, lbl, k in sorted(combo_links.get(c, []), key=lambda t: -t[2])) + '</div>' if combo_links.get(c) else ''}
{f'<h2>Who has been winning in {esc(name)}</h2><p class="sub">Two years of awarded contracts, with the companies that took them.</p><div class="cpv">' + "".join(f'<a href="{winner_path(c, d)}"><b>{esc(d)}</b><i>{esc(lbl)}</i><u>{n:,} awarded</u></a>' for d, lbl, n in sorted(winners_by_country.get(c, []), key=lambda t: -t[2])) + '</div>' if winners_by_country.get(c) else ''}
<h2>All open tenders in {esc(name)}</h2>
{cards}"""
        write(f"/c/{c}.html",
              page(f"Open public tenders in {name} | {BRAND}", body,
                   desc=f"{len(items)} open public tenders in {name}, updated daily.",
                   canonical=f"/c/{c}.html"))
        write(f"/feed/c-{c}.xml", rss(f"{name} tenders", f"/c/{c}.html", items))
        urls.append(f"/c/{c}.html")

    # ---- CPV explorer --------------------------------------------------
    # A reference tool for the vocabulary itself: every CPV code TED actually
    # uses, searchable, with the number of tenders open against it right now.
    by_code = defaultdict(list)
    for n in rows:
        if n.get("cpvf"):
            by_code[n["cpvf"]].append(n)

    cpv_rows = sorted(
        ((c, lbl, len(by_code.get(c, []))) for c, lbl in meta.CPV_LABELS.items()),
        key=lambda r: r[0])
    write("/api/cpv.json",
          json.dumps(cpv_rows, ensure_ascii=False, separators=(",", ":")))

    live_codes = sum(1 for r in cpv_rows if r[2])
    div_grid = "".join(
        f'<a href="/s/{d}.html"><i>{esc(meta.cpv_label(d))}</i><u>{len(v)}</u></a>'
        for d, v in sorted(by_sector.items(), key=lambda kv: kv[0]))
    cpv_body = f"""<h1>CPV code explorer</h1>
<p class="sub">The whole Common Procurement Vocabulary &mdash; all
{len(cpv_rows):,} codes, straight from the European Commission's own list &mdash;
searchable by code or by what it means. {live_codes:,} of them have tenders open right
now; those link through to the contracts.</p>
<input id="q" type="search" autocomplete="off"
 placeholder="Search a code or a description &mdash; e.g. 45000000, catering, servers, asphalt&hellip;">
<div id="res"></div>
<div class="note"><h2>What a CPV code is</h2>
<p>Every contract notice published in the EU Official Journal is tagged with codes from
the <b>Common Procurement Vocabulary</b>, an eight-digit classification that says what is
being bought, independently of the language it is bought in. It is the only reliable way
to follow one kind of work across twenty-seven countries: a road resurfacing contract is
<b>45233220</b> whether the notice is written in Portuguese, Estonian or Greek.</p>
<p>The digits narrow from left to right. The first two are the <i>division</i>
&mdash; 45 is construction work. The third adds the <i>group</i>, the fourth the
<i>class</i>, the fifth the <i>category</i>; the remaining digits refine further, and the
final digit is a check digit. A buyer picks one main code and may add others.</p>
<p>Suppliers use them to filter: pick the codes that describe what you sell, and you can
watch the whole single market instead of one national portal.</p></div>
<h2>The {len(by_sector)} divisions</h2>
<div class="index">{div_grid}</div>"""
    write("/cpv.html", page(f"CPV code explorer — all {len(cpv_rows):,} codes | {BRAND}",
          cpv_body, extra_head=CPV_JS, canonical="/cpv.html",
          desc=f"Search all {len(cpv_rows):,} CPV procurement codes and see how many EU "
               f"tenders are open against each one. Updated daily."))
    urls.append("/cpv.html")

    # ---- one page per code that has something open ----------------------
    # Every open call has a main CPV code, so paginating these pages is what
    # makes the whole store reachable by following links. Left unpaginated,
    # two thirds of the notices are in the sitemap and nowhere else, and a
    # site with no authority does not get those crawled.
    PER = 100
    for code, items in sorted(by_code.items()):
        label = meta.cpv_name(code)
        div = code[:2]
        group = meta.cpv_group(code)
        siblings = [(c, lbl) for c, lbl, k in cpv_rows
                    if k and meta.cpv_group(c) == group and c != code][:14]
        sib = "".join(f'<a href="/cpv/{c}.html"><b>{esc(c)}</b><i>{esc(lbl)}</i></a>'
                      for c, lbl in siblings)
        countries = sorted({meta.country_name(n.get("c")) for n in items})
        # The chain of broader codes, which is the thing a search for a bare
        # CPV number is actually asking about. Levels that have open tenders
        # of their own get linked; the rest are shown for context.
        chain = []
        for par in reversed(meta.cpv_parents(code)):
            plabel = meta.cpv_name(par)
            if par in by_code:
                chain.append(f'<a href="/cpv/{par}.html"><b>{esc(par)}</b>'
                             f'<i>{esc(plabel)}</i><u>{len(by_code[par])} open</u></a>')
            else:
                chain.append(f'<a><b>{esc(par)}</b><i>{esc(plabel)}</i><u>&mdash;</u></a>')
        chain.append(f'<a><b>{esc(code)}</b><i>{esc(label)}</i>'
                     f'<u>{len(items)} open</u></a>')
        hier = (f'<h2>Where this code sits</h2><div class="cpv">{"".join(chain)}</div>'
                if len(chain) > 1 else "")

        # Who is buying under this code, which is the other half of the question.
        per_country = defaultdict(int)
        for n in items:
            per_country[n.get("c") or "XXX"] += 1
        cnt_rows = "".join(
            f'<a href="/c/{c}.html"><b>{esc(c)}</b>'
            f'<i>{esc(meta.country_name(c))}</i><u>{k}</u></a>'
            for c, k in sorted(per_country.items(), key=lambda kv: -kv[1])[:20])
        buyers = (f'<h2>Countries buying under {esc(code)}</h2>'
                  f'<div class="cpv">{cnt_rows}</div>' if cnt_rows else "")
        pages = max(1, -(-len(items) // PER))
        for pg in range(1, pages + 1):
            slice_ = items[(pg - 1) * PER: pg * PER]
            path = f"/cpv/{code}.html" if pg == 1 else f"/cpv/{code}-{pg}.html"
            nav = ""
            if pages > 1:
                prev_ = ("" if pg == 1 else
                         f'<a href="/cpv/{code}.html">&larr; first</a> '
                         if pg == 2 else
                         f'<a href="/cpv/{code}-{pg-1}.html">&larr; previous</a> ')
                next_ = ("" if pg == pages else
                         f'<a href="/cpv/{code}-{pg+1}.html">next &rarr;</a>')
                nav = (f'<p class="sub">Page {pg} of {pages} &middot; {prev_}{next_}</p>')
            head_extra = ""
            if pages > 1:
                if pg > 1:
                    p_url = (f"{BASE}/cpv/{code}.html" if pg == 2
                             else f"{BASE}/cpv/{code}-{pg-1}.html")
                    head_extra += f'<link rel="prev" href="{p_url}">'
                if pg < pages:
                    head_extra += f'<link rel="next" href="{BASE}/cpv/{code}-{pg+1}.html">'
            body = f"""<div class="crumb"><a href="/">Home</a> / <a href="/cpv.html">CPV codes</a>
 / <a href="/s/{esc(div)}.html">{esc(meta.cpv_label(div))}</a></div>
<h1>CPV {esc(code)} &mdash; {esc(label)}</h1>
<p class="sub">{len(items)} open call{'s' if len(items) != 1 else ''} for tenders across the
EU are classified under this code right now, from
{len(countries)} countr{'ies' if len(countries) != 1 else 'y'}. Sorted by closing date and
rebuilt every day from the EU Official Journal.</p>
<dl>
<dt>Code</dt><dd>{esc(code)}</dd>
<dt>Description</dt><dd>{esc(label)}</dd>
<dt>Division</dt><dd><a href="/s/{esc(div)}.html">{esc(div)} &mdash; {esc(meta.cpv_label(div))}</a></dd>
<dt>Open tenders</dt><dd>{len(items)}</dd>
<dt>Countries</dt><dd>{esc(", ".join(countries)) or '&mdash;'}</dd>
</dl>
{nav}
{"".join(card(n) for n in slice_)}
{nav}
{hier if pg == 1 else ''}
{buyers if pg == 1 else ''}
{f'<h2>Related codes in group {esc(group)}</h2><div class="cpv">{sib}</div>' if sib and pg == 1 else ''}
<div class="note"><h2>Follow this code</h2>
<p>New tenders under {esc(code)} appear here the morning they are published.
The {esc(meta.cpv_label(div))} feed carries them as they land.</p>
<a class="btn" href="/feed/s-{esc(div)}.xml">RSS for this sector</a></div>"""
            title = (f"CPV {code}: {label} — open EU tenders | {BRAND}" if pg == 1
                     else f"CPV {code}: {label} — page {pg} | {BRAND}")
            write(path, page(title, body, extra_head=head_extra,
                             desc=f"{len(items)} open EU public tenders under CPV code "
                                  f"{code} ({label}). Updated daily.",
                             canonical=path))
            urls.append(path)


    # ---- index pages --------------------------------------------------
    sec_grid = "".join(
        f'<a href="/s/{d}.html"><i>{esc(meta.cpv_label(d))}</i><u>{len(v)}</u></a>'
        for d, v in sorted(by_sector.items(), key=lambda kv: -len(kv[1])))
    write("/sectors.html", page(f"Tenders by sector | {BRAND}",
        f'<h1>Browse by sector</h1><p class="sub">EU procurement is classified with CPV codes. '
        f'Pick the division that matches what you sell.</p><div class="index">{sec_grid}</div>',
        desc="Open EU public tenders grouped by CPV sector.", canonical="/sectors.html"))

    cnt_grid = "".join(
        f'<a href="/c/{c}.html"><i>{esc(meta.country_name(c))}</i><u>{len(v)}</u></a>'
        for c, v in sorted(by_country.items(), key=lambda kv: -len(kv[1])))
    write("/countries.html", page(f"Tenders by country | {BRAND}",
        f'<h1>Browse by country</h1><p class="sub">Contracting authorities across the EU '
        f'and associated countries.</p><div class="index">{cnt_grid}</div>',
        desc="Open EU public tenders grouped by country.", canonical="/countries.html"))

    # ---- the winners hub --------------------------------------------------
    # The award pages are the part of this site nobody else publishes, and they
    # were the hardest to reach: three clicks down, behind a country page. A
    # crawler that has only seen the home page would take a long time to find
    # them, and most never would. This puts every one of them two clicks away.
    if winners_by_country:
        blocks = []
        for c, items in sorted(winners_by_country.items(),
                               key=lambda kv: (-sum(t[2] for t in kv[1]),
                                               meta.country_name(kv[0]))):
            grid = "".join(
                f'<a href="{winner_path(c, d)}"><i>{esc(lbl)}</i>'
                f'<u>{n:,} awarded</u></a>'
                for d, lbl, n in sorted(items, key=lambda t: -t[2]))
            blocks.append(f'<h2 id="{esc(c.lower())}">{esc(meta.country_name(c))}</h2>'
                          f'<div class="index">{grid}</div>')
        total_pages = sum(len(v) for v in winners_by_country.values())
        total_awards = sum(t[2] for v in winners_by_country.values() for t in v)
        write("/winners.html", page(
            f"Who wins EU public contracts | {BRAND}",
            f'<h1>Who wins the work</h1>'
            f'<p class="sub">{total_awards:,} awarded contracts across '
            f'{len(winners_by_country)} countries, grouped the way buyers classify '
            f'them. Each page names the companies that won most often, what they '
            f'were paid, and the most recent awards with a link to the official '
            f'notice.</p>'
            f'<p class="sub">Ranked by number of contracts rather than by value: a '
            f'single framework agreement can carry a ceiling far larger than the '
            f'work actually done under it.</p>'
            + "".join(blocks),
            desc=f"The companies winning EU public contracts, across {total_pages} "
                 f"country and sector combinations, with amounts and dates.",
            canonical="/winners.html"))

    # search index (compact)
    idx = [[n["id"], n["t"][:130], n.get("c", ""), n.get("cpv", []), n["d"][:10]]
           for n in rows]
    write("/api/index.json", json.dumps(idx, ensure_ascii=False, separators=(",", ":")))

    # ---- spreadsheets ----------------------------------------------------
    # The same rows the pages show, in the format most people actually work in.
    # Free, and the reason to link to us rather than describe us.
    CSV_COLS = ["reference", "title", "buyer", "country", "country_name",
                "cpv_main", "cpv_main_label", "cpv_divisions", "contract_nature",
                "place_of_performance", "published", "deadline", "page", "official_notice"]

    def csv_rows(items):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(CSV_COLS)
        for n in items:
            w.writerow([
                n["id"], n.get("t", ""), n.get("b", ""), n.get("c", ""),
                meta.country_name(n.get("c")), n.get("cpvf", ""),
                meta.cpv_name(n.get("cpvf")) if n.get("cpvf") else "",
                " ".join(n.get("cpv", [])), n.get("nat", ""), n.get("nuts", ""),
                n.get("p", ""), n.get("d", ""),
                f"{BASE}/n/{n['id']}.html",
                f"https://ted.europa.eu/en/notice/-/detail/{n['id']}",
            ])
        return buf.getvalue()

    write("/export/all-open-tenders.csv", csv_rows(rows))
    for d, items in by_sector.items():
        write(f"/export/sector-{d}.csv", csv_rows(items))
    for c, items in by_country.items():
        write(f"/export/country-{c}.csv", csv_rows(items))

    def kb(path):
        return max(1, os.path.getsize(os.path.join(OUT, path.lstrip("/"))) // 1024)

    sec_dl = "".join(
        f'<a href="/export/sector-{d}.csv"><b>{esc(d)}</b>'
        f'<i>{esc(meta.cpv_label(d))}</i><u>{len(v):,} rows</u></a>'
        for d, v in sorted(by_sector.items(), key=lambda kv: -len(kv[1])))
    cnt_dl = "".join(
        f'<a href="/export/country-{c}.csv"><b>{esc(c)}</b>'
        f'<i>{esc(meta.country_name(c))}</i><u>{len(v):,} rows</u></a>'
        for c, v in sorted(by_country.items(), key=lambda kv: -len(kv[1])))
    export_body = f"""<h1>Every open EU tender, as a spreadsheet</h1>
<p class="sub">One row per open call for tenders, with the deadline, the buyer, the CPV
code and a link to the official notice. Plain CSV, UTF-8, opens in Excel, Numbers,
LibreOffice or pandas. Rebuilt every morning from the EU Official Journal.
Free, no sign-up, and you may re-use it &mdash; it is public data.</p>
<div class="cpv">
<a href="/export/all-open-tenders.csv"><b>everything</b>
<i>All {len(rows):,} open tenders across the EU</i><u>{kb('/export/all-open-tenders.csv'):,} KB</u></a>
</div>
<h2>The columns</h2>
<div class="desc"><code>{esc(", ".join(CSV_COLS))}</code></div>
<h2>By sector</h2><div class="cpv">{sec_dl}</div>
<h2>By country</h2><div class="cpv">{cnt_dl}</div>
<div class="note"><h2>Looking for who <i>won</i>, not who is buying?</h2>
<p>Open tenders are one half of the record. The other half — every contract
award published in the Official Journal, with the winning company and the value
in euro — is a separate dataset of 374,443 rows, free to download and re-use.</p>
<a class="btn" href="{CFG['dataset_url']}" rel="noopener">Contract awards dataset &rarr;</a>
<p class="sub" style="margin-top:14px">That file covers the last twelve months and is
free. The two-year run &mdash; 719,960 awards, refreshed monthly &mdash;
<a href="{CFG['archive_url']}" rel="noopener">is sold to pay for the work</a>.</p></div>
<div class="note"><h2>Prefer JSON?</h2>
<p>The same data is available as an API with no key and no rate limit.</p>
<a class="btn" href="/api.html">API documentation</a></div>"""
    write("/export.html", page(f"Open EU tenders as CSV | {BRAND}", export_body,
          desc=f"Download all {len(rows):,} open EU public tenders as a CSV "
               f"spreadsheet, by sector or by country. Free, rebuilt daily.",
          canonical="/export.html"))
    urls.append("/export.html")

    # ---- public JSON API ------------------------------------------------
    # GitHub Pages serves these with Access-Control-Allow-Origin: *, so they
    # are usable straight from a browser with no key and no proxy. Documented
    # on /api.html; the shapes below are the contract.
    def api_notice(n):
        return {
            "id": n["id"],
            "title": n.get("t"),
            "buyer": n.get("b"),
            "country": n.get("c"),
            "country_name": meta.country_name(n.get("c")),
            "cpv_divisions": n.get("cpv", []),
            "cpv_main": n.get("cpvf"),
            "cpv_main_label": meta.cpv_name(n.get("cpvf")) if n.get("cpvf") else None,
            "contract_nature": n.get("nat"),
            "place_of_performance": n.get("nuts"),
            "published": n.get("p"),
            "deadline": n.get("d"),
            "url": f"{BASE}/n/{n['id']}.html",
            "ted_url": f"https://ted.europa.eu/en/notice/-/detail/{n['id']}",
        }

    def api(path, obj):
        write(path, json.dumps(obj, ensure_ascii=False, separators=(",", ":")))

    api("/api/stats.json", {
        "generated": NOW.isoformat(timespec="seconds"),
        "open_notices": len(rows),
        "archived_notices": len(archive),
        "countries": len(by_country),
        "sectors": len(by_sector),
        "cpv_codes_in_use": len(by_code),
        "source": "Tenders Electronic Daily (TED), European Union",
        "licence": "European Commission open data policy",
        "docs": f"{BASE}/api.html",
    })
    api("/api/countries.json", [
        {"code": c, "name": meta.country_name(c), "open_notices": len(v),
         "notices_url": f"{BASE}/api/c/{c}.json"}
        for c, v in sorted(by_country.items(), key=lambda kv: -len(kv[1]))])
    api("/api/sectors.json", [
        {"division": d, "label": meta.cpv_label(d), "open_notices": len(v),
         "notices_url": f"{BASE}/api/s/{d}.json"}
        for d, v in sorted(by_sector.items(), key=lambda kv: -len(kv[1]))])
    for c, items in by_country.items():
        api(f"/api/c/{c}.json", [api_notice(n) for n in items])
    for d, items in by_sector.items():
        api(f"/api/s/{d}.json", [api_notice(n) for n in items])



    closing = sorted(rows, key=lambda r: r["d"])[:12]
    home = f"""<h1>Every open EU public tender, in one place.</h1>
<p class="sub">{len(rows):,} live calls for tenders from {len(by_country)} countries,
pulled every day from the EU Official Journal and made searchable. Free, no account.</p>
<div class="band">
<div><b>{len(rows):,}</b><span>open tenders</span></div>
<div><b>{len(by_country)}</b><span>countries</span></div>
<div><b>{len(by_sector)}</b><span>sectors</span></div>
<div><b>daily</b><span>refresh</span></div>
</div>
<input id="q" type="search" placeholder="Search tenders — e.g. software, catering, road works, Italy…" autocomplete="off">
<div class="filters">
<select id="fc"><option value="">All countries</option>{''.join(f'<option value="{c}">{esc(meta.country_name(c))}</option>' for c in sorted(by_country, key=lambda k: meta.country_name(k)))}</select>
<select id="fs"><option value="">All sectors</option>{''.join(f'<option value="{d}">{esc(meta.cpv_label(d))}</option>' for d in sorted(by_sector))}</select>
</div>
<div id="res"><h2>Closing soonest</h2>{''.join(card(n) for n in closing)}</div>
<div class="note"><h2>Get them by email instead</h2>
<p>One short email a day with the new tenders in your sector and country.
No dashboard to remember, no account to create.</p>
<a class="btn" href="/alerts.html">Set up daily alerts</a></div>
<div class="note"><h2>And who won the ones that already closed?</h2>
<p>Every contract award published in the Official Journal &mdash; the winning company,
the buyer, the sector and the value in euro &mdash; is a separate dataset of 374,443
rows, free to download and re-use.</p>
<a class="btn" href="{CFG['dataset_url']}" rel="noopener">Contract awards dataset &rarr;</a></div>
<h2>Browse by sector</h2><div class="index">{sec_grid}</div>"""
    write("/index.html", page(f"{BRAND} — {CFG['tagline']}", home,
          desc=CFG["tagline"], canonical="/", extra_head=SEARCH_JS))

    write("/alerts.html", page(f"Daily tender alerts | {BRAND}", ALERTS_BODY,
          desc="Get new EU public tenders matching your sector by email, every morning.",
          canonical="/alerts.html"))
    write("/api.html", page(f"Free EU tenders API | {BRAND}",
          API_BODY.replace("{ARCHIVE_DAYS}", str(ARCHIVE_DAYS)),
          desc="A free, keyless JSON API of every open public tender in the EU, "
               "rebuilt daily from the official TED data.",
          canonical="/api.html"))
    urls.append("/api.html")

    write("/privacy.html", page(f"Privacy | {BRAND}", PRIVACY_BODY,
          desc="This site sets no cookies, runs no analytics and makes no third-party "
               "requests. What that means, in plain words.",
          canonical="/privacy.html"))
    urls.append("/privacy.html")

    write("/about.html", page(f"About | {BRAND}", ABOUT_BODY,
          desc=f"What {BRAND} is, where the data comes from, and how often it updates.",
          canonical="/about.html"))

    write("/robots.txt", f"User-agent: *\nAllow: /\n"
          f"Sitemap: {BASE}/sitemap.xml\n"
          f"Sitemap: {BASE}/sitemap-google.txt\n")
    # ---- sitemap index --------------------------------------------------
    # One file per section rather than one 3 MB blob: Search Console reports
    # coverage per sitemap, so a section that stops being indexed shows up
    # instead of being averaged away. Chunked well under the 50,000 URL limit.
    def section(u):
        for pre, name in (("/n/", "notices"), ("/cpv/", "cpv"), ("/t/", "trades"),
                          ("/w/", "winners"),
                          ("/s/", "sectors"), ("/c/", "countries")):
            if u.startswith(pre):
                return name
        return "core"

    groups = defaultdict(list)
    for u in urls:
        groups[section(u)].append(u)

    parts = []
    for name in ("core", "sectors", "countries", "winners", "trades", "cpv",
                 "notices"):
        chunk = groups.get(name) or []
        for i in range(0, len(chunk), 10000):
            piece = chunk[i:i + 10000]
            fname = (f"/sitemap-{name}.xml" if len(chunk) <= 10000
                     else f"/sitemap-{name}-{i // 10000 + 1}.xml")
            body = "".join(
                f"<url><loc>{BASE}{u}</loc><lastmod>{NOW.date()}</lastmod></url>"
                for u in piece)
            write(fname, '<?xml version="1.0" encoding="UTF-8"?>'
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                  f'{body}</urlset>')
            parts.append(fname)

    write("/sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>'
          '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
          + "".join(f"<sitemap><loc>{BASE}{f}</loc>"
                    f"<lastmod>{NOW.date()}</lastmod></sitemap>" for f in parts)
          + '</sitemapindex>')

    # Search Console has repeatedly failed to read the valid XML sitemap even
    # though the same fetch succeeds for Googlebot and other search engines.
    # Keep a single plain-text sitemap as the smallest possible independent
    # submission path and diagnostic: one absolute URL per UTF-8 line, with no
    # XML parser, nested index, or metadata involved.  The site currently fits
    # below Google's 50,000-URL limit for a text sitemap.
    if len(urls) > 50000:
        raise RuntimeError("sitemap-google.txt would exceed Google's 50,000 URL limit")
    write("/sitemap-google.txt", "".join(f"{BASE}{u}\n" for u in urls))
    print(f"sitemap: {len(urls)} urls across {len(parts)} XML files + text fallback")
    faces = open(os.path.join(ROOT, "assets", "fonts.css"), encoding="utf-8").read()
    write("/style.css", faces + CSS)
    shutil.copytree(os.path.join(ROOT, "assets", "fonts"),
                    os.path.join(OUT, "fonts"), dirs_exist_ok=True)
    shutil.copytree(os.path.join(ROOT, "assets", "brand"),
                    os.path.join(OUT, "brand"), dirs_exist_ok=True)
    write("/.nojekyll", "")

    # ---- IndexNow ------------------------------------------------------
    # Search engines that support IndexNow (Bing, Yandex, Seznam, Naver) are
    # told about the day's new notices instead of waiting for a crawl. The key
    # file proves we own the site. The request body is written ready to POST;
    # the workflow sends it after the deploy, so the pages are already live.
    key = CFG.get("indexnow_key") or ""
    if key and BASE:
        write(f"/{key}.txt", key)
        cutoff = (NOW.date() - timedelta(days=2)).isoformat()
        fresh = ["/", "/sectors.html", "/countries.html", "/winners.html"]
        fresh += [f"/n/{n['id']}.html" for n in rows if (n.get("p") or "") >= cutoff]
        fresh = fresh[:9000]
        body = {
            "host": urlparse(BASE).netloc,
            "key": key,
            "keyLocation": f"{BASE}/{key}.txt",
            "urlList": [BASE + u for u in fresh],
        }
        with open(os.path.join(ROOT, "indexnow.json"), "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
        print(f"indexnow: {len(fresh)} urls published since {cutoff}")

    print(f"wrote {len(urls)} pages to {OUT}")


CPV_JS = """<script>
document.addEventListener('DOMContentLoaded',function(){var D=null,q=document.getElementById('q'),res=document.getElementById('res');
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function mark(s,t){if(!t)return esc(s);var i=s.toLowerCase().indexOf(t);if(i<0)return esc(s);
return esc(s.slice(0,i))+'<em>'+esc(s.slice(i,i+t.length))+'</em>'+esc(s.slice(i+t.length))}
function draw(list,t){if(!list.length){res.innerHTML='<p class="sub">No CPV code matches that. Try a shorter word, or the first digits of a code.</p>';return}
var more=list.length>400?list.length-400:0;
res.innerHTML='<h2>'+list.length+' matching code'+(list.length==1?'':'s')+'</h2><div class="cpv">'+
list.slice(0,400).map(function(r){
var open=r[2];
return (open?'<a href="/cpv/'+r[0]+'.html">':'<a>')+'<b>'+mark(r[0],t)+'</b><i>'+
mark(r[1],t)+'</i><u>'+(open?open+' open':'none open')+'</u></a>'}).join('')+'</div>'+
(more?'<p class="sub">'+more+' more &mdash; narrow the search to see them.</p>':'')}
function run(){var t=q.value.trim().toLowerCase();
if(!t){res.innerHTML='';return}
if(!D){fetch('/api/cpv.json').then(function(r){return r.json()}).then(function(j){D=j;run()});
res.innerHTML='<p class="sub">Loading the vocabulary&hellip;</p>';return}
var out=[];for(var i=0;i<D.length;i++){var r=D[i];
if(r[0].indexOf(t)===0||r[1].toLowerCase().indexOf(t)>=0)out.push(r)}
out.sort(function(a,b){return b[2]-a[2]});draw(out,t)}
var tmr;q.addEventListener('input',function(){clearTimeout(tmr);tmr=setTimeout(run,140)});
});
</script>"""

SEARCH_JS = """<script>
document.addEventListener('DOMContentLoaded',function(){var D=null,q=document.getElementById('q');
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function load(cb){if(D)return cb();fetch('/api/index.json').then(function(r){return r.json()}).then(function(j){D=j;cb()})}
function fmt(d){try{return new Date(d).toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'})}catch(e){return ''}}
function run(){load(function(){
var t=q.value.trim().toLowerCase(),c=document.getElementById('fc').value,s=document.getElementById('fs').value;
if(!t&&!c&&!s){location.reload();return}
var w=t.split(/\\s+/).filter(Boolean),out=[];
for(var i=0;i<D.length&&out.length<300;i++){var n=D[i];
if(c&&n[2]!==c)continue;if(s&&n[3].indexOf(s)<0)continue;
if(w.length){var h=n[1].toLowerCase(),ok=true;
for(var k=0;k<w.length;k++){if(h.indexOf(w[k])<0){ok=false;break}}if(!ok)continue}
out.push(n)}
document.getElementById('res').innerHTML='<h2>'+out.length+(out.length>=300?'+':'')+' matching tenders</h2>'+
out.map(function(n){return '<div class="row"><div class="ref">'+n[0]+'</div><div class="ttl"><a href="/n/'+n[0]+'.html">'+esc(n[1])+'</a></div><div class="when"><b>'+fmt(n[4])+'</b></div></div>'}).join('')||
'<p class="sub">No open tender matches that. Try a broader term.</p>'})}
var tmr;['input','change'].forEach(function(ev){
document.getElementById('q').addEventListener(ev,function(){clearTimeout(tmr);tmr=setTimeout(run,180)});
document.getElementById('fc').addEventListener('change',run);
document.getElementById('fs').addEventListener('change',run)});});
</script>"""

ALERTS_BODY = f"""<h1>Following tenders without checking a website</h1>
<p class="sub">Nobody actually opens a procurement portal every morning. These are the
ways to have the new tenders come to you instead.</p>

<h2>RSS, per sector and per country</h2>
<p>Every sector page and every country page has its own feed. Put it in your reader,
your Slack, or your Teams channel, and new tenders arrive as they are published.
No sign-up, no email address, nothing to cancel, and nothing about you is recorded
&mdash; we never learn that you subscribed.</p>
<p><a href="/sectors.html">Pick a sector &rarr;</a> &nbsp;
<a href="/countries.html">Pick a country &rarr;</a></p>

<h2>Spreadsheets</h2>
<p>Every sector and country is also a CSV you can open in Excel or drop into your own
system: one row per open tender, with the deadline, the buyer, the CPV code and the link
to the official notice. Rebuilt every morning, same as the pages.</p>
<p><a href="/export.html">Download a spreadsheet &rarr;</a></p>

<h2>The API</h2>
<p>If you would rather wire it into something yourself, the whole index is JSON, with no
key and no rate limit.</p>
<p><a href="/api.html">Read the API documentation &rarr;</a></p>

<div class="note"><h2>Or be told when things change</h2>
<p>There is a subscribe page for that, and it is deliberately not on this site: it is
hosted by Gumroad, who receive the address, hold it, and send the messages under their
own privacy notice and their own unsubscribe link. Nothing about you is collected here
&mdash; following the link is the only thing that happens on our side, and the
<a href="/privacy.html">privacy page</a> spells out the rest.</p>
<a class="btn" href="{CFG['alerts_url']}" rel="noopener">Subscribe on Gumroad &rarr;</a></div>

<h2>Why this exists</h2>
<p>EU tender data is public and free, but it is published in a form built for lawyers,
not for the small companies that could win the work. {BRAND} does one thing: it takes
that firehose and makes it readable, searchable, and pushable.</p>"""

API_BODY = f"""<h1>A free API for open EU tenders</h1>
<p class="sub">Every page on this site is also a JSON endpoint. No key, no sign-up, no
rate limit, and <code>Access-Control-Allow-Origin: *</code> on everything &mdash; so you
can call it straight from a browser. Rebuilt once a day from the EU Official Journal.</p>

<h2>Endpoints</h2>
<div class="cpv">
<a href="/api/stats.json"><b>/api/stats.json</b><i>Counts and build time</i></a>
<a href="/api/countries.json"><b>/api/countries.json</b><i>Countries, with open tender counts</i></a>
<a href="/api/sectors.json"><b>/api/sectors.json</b><i>The 45 CPV divisions, with counts</i></a>
<a href="/api/cpv.json"><b>/api/cpv.json</b><i>Every CPV code in use: [code, label, open]</i></a>
<a href="/api/c/ITA.json"><b>/api/c/&lt;ISO3&gt;.json</b><i>Open tenders in one country</i></a>
<a href="/api/s/45.json"><b>/api/s/&lt;division&gt;.json</b><i>Open tenders in one CPV division</i></a>
<a href="/api/index.json"><b>/api/index.json</b><i>Compact search index, all open tenders</i></a>
</div>

<h2>A notice looks like this</h2>
<div class="desc"><code>{{
  "id": "533447-2026",
  "title": "Germany &ndash; Cleaning services &ndash; Unterhaltsreinigung",
  "buyer": "Landkreis Marburg-Biedenkopf",
  "country": "DEU",
  "country_name": "Germany",
  "cpv_divisions": ["90"],
  "cpv_main": "90910000",
  "cpv_main_label": "Cleaning services",
  "contract_nature": "services",
  "place_of_performance": "DE724",
  "published": "2026-08-03",
  "deadline": "2026-09-15T10:15:00+02:00",
  "url": "&hellip;/n/533447-2026.html",
  "ted_url": "https://ted.europa.eu/en/notice/-/detail/533447-2026"
}}</code></div>

<h2>Try it</h2>
<div class="desc"><code>curl -s {BASE}/api/sectors.json | jq '.[0]'

# every open construction tender in Italy
curl -s {BASE}/api/c/ITA.json | jq '[.[] | select(.cpv_divisions[]=="45")] | length'</code></div>

<h2>The catch</h2>
<p>It is a static site, so there is no query language: you fetch a whole collection and
filter it yourself. The largest file is <code>/api/index.json</code>, a few megabytes.
Everything is regenerated once a day, so cache it rather than polling.</p>
<p>Closed calls are dropped from the API the day their deadline passes, though their page
is kept for {{ARCHIVE_DAYS}} days as a record.</p>

<h2>Terms</h2>
<p>The data comes from <a href="https://ted.europa.eu/">TED</a> and is re-used under the
European Commission's open data policy; it stays free under the same terms. Attribution
is appreciated but not required. There is no uptime guarantee and no support &mdash; it is
a static file on GitHub Pages. If you build something with it,
<a href="https://github.com/jaydemks/bidledger">the code is here</a>.</p>

<div class="note"><h2>The awards, as a dataset</h2>
<p>This API covers what is open. What was already won &mdash; 374,443 contract
awards with the winning company and the value converted to euro &mdash; is
published as a dataset on Hugging Face, free and re-usable.</p>
<p><a href="{CFG['dataset_url']}" rel="noopener">huggingface.co/datasets/jaydem/eu-contract-awards</a></p></div>

<div class="note"><h2>Want the tenders, not the JSON?</h2>
<p>Every sector and country page has an RSS feed, and the daily email lands in your
inbox instead.</p>
<a class="btn" href="/alerts.html">Daily alerts</a></div>"""

CONTACT = (f'<a href="mailto:{CFG["contact_email"]}">{CFG["contact_email"]}</a>'
           if CFG.get("contact_email") else
           '<a href="https://github.com/jaydemks/bidledger/issues">an issue on the '
           'repository</a>')

PRIVACY_BODY = f"""<h1>Privacy</h1>
<p class="sub">Short version: this site collects nothing about you. No cookies, no
accounts, no analytics, no third-party requests of any kind. There is no banner to
click because there is nothing to consent to.</p>

<h2>What is stored on your device</h2>
<p>Nothing. {BRAND} sets no cookies and writes nothing to local storage. The search box
on the home page and the CPV explorer run entirely in your browser: they download a
data file and filter it locally. What you type is never sent anywhere.</p>

<h2>What is requested from other companies</h2>
<p>Nothing. Every page loads only from this domain &mdash; the stylesheet, the data
files and the typefaces are all served from here. There are no fonts from Google, no
tag managers, no embedded videos, no social buttons, no trackers. Opening a page tells
no third party that you did.</p>

<h2>What the host can see</h2>
<p>The site is a set of static files served by GitHub Pages. Like any web server,
GitHub receives the requests your browser makes and may log them, including your IP
address, for security and to run the service. That processing is GitHub's, under
<a href="https://docs.github.com/site-policy/privacy-policies/github-privacy-statement"
rel="nofollow noopener">their privacy statement</a>. We neither see nor keep those logs,
and no analytics account is attached to this site.</p>

<h2>The tender data</h2>
<p>Every notice reproduced here comes from
<a href="https://ted.europa.eu/">Tenders Electronic Daily</a>, the supplement to the
Official Journal of the European Union, retrieved through its public API and re-used
under the European Commission's open data policy. TED is the authoritative source and
every page links back to the original notice.</p>
<p>Notices name the contracting authority that published them, and their free-text
descriptions occasionally mention an individual. That material is published by the
European Union itself and is reproduced here unchanged. If a notice concerns you and you
want it changed or removed, the correction has to be made at the source, on TED, because
this site is rebuilt from it every day and would otherwise restore the old text. If you
believe something here should not be shown, write to us at {CONTACT} and we will look
at it.</p>

<h2>The one place an address can be given</h2>
<p>There is a subscribe page for people who want to hear when the data changes, and it is
deliberately somewhere else: <a href="{CFG['alerts_url']}" rel="noopener">on Gumroad</a>.
If you use it, <b>Gumroad</b> is who receives your address, stores it and sends the
messages, under
<a href="https://gumroad.com/privacy" rel="nofollow noopener">their privacy notice</a>,
with their confirmation step and their unsubscribe link in every message. They are the
data controller for that list.</p>
<p>This was a deliberate choice rather than a shortcut. Putting the form here would mean
holding addresses on this side, and the whole point of the page you are reading is that
there is nothing to hold. The link leaves; nothing arrives.</p>
<p>If that ever changes &mdash; a form on this site, an account, anything that collects
here &mdash; it will be described on this page <b>before</b> the first address is taken,
not after. Nothing is gathered quietly in the meantime.</p>

<h2>Getting in touch</h2>
<p>Questions about any of this: {CONTACT}.</p>

<p class="sub">Last reviewed {NOW.strftime('%d %B %Y')}.</p>"""

ABOUT_BODY = f"""<h1>About {BRAND}</h1>
<p class="sub">{CFG['tagline']}</p>
<h2>Where the data comes from</h2>
<p>Every notice on this site comes from
<a href="https://ted.europa.eu/">Tenders Electronic Daily</a>, the supplement to the
Official Journal of the European Union, through its official public API. TED is the
legally authoritative source; this site is a faster, more readable front door to it.
For anything binding &mdash; specifications, annexes, deadlines &mdash; always open the
official notice, which we link from every page.</p>
<h2>How often it updates</h2>
<p>A scheduled job pulls new notices from TED once a day and rebuilds every page on
this site. Notices are removed once their submission deadline has passed.</p>
<h2>What it covers</h2>
<p>Open calls for competition: contract notices, social and special services notices,
design contests, qualification systems, and prior information notices used as a call
for competition. Contract award notices &mdash; the ones announcing who already won
&mdash; are deliberately left out.</p>
<h2>Independence</h2>
<p>{BRAND} is an independent project. It is not affiliated with, endorsed by, or
operated by the European Union or any contracting authority. Data is re-used under the
European Commission's open data policy.</p>"""

if __name__ == "__main__":
    main()
