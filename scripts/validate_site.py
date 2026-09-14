#!/usr/bin/env python3
"""Fail a deployment when the generated static site is internally inconsistent."""
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASE = CFG["base_url"].rstrip("/")
PREFIX = urlsplit(BASE).path.rstrip("/")
LINK_RE = re.compile(r"(?:href|src)=[\"']([^\"']+)[\"']", re.I)


def fail(message, problems):
    problems.append(message)


def local_target(source, raw):
    value = html.unescape(raw)
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or value.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    path = unquote(parsed.path)
    if not path:
        return None
    if path.startswith("/"):
        if PREFIX and path == PREFIX:
            path = "/"
        elif PREFIX and path.startswith(PREFIX + "/"):
            path = path[len(PREFIX):]
        target = OUT / path.lstrip("/")
    else:
        target = source.parent / path
    if path.endswith("/") or not target.suffix:
        target = target / "index.html"
    return Path(os.path.abspath(target))


def main():
    problems = []
    all_files = [path for path in OUT.rglob("*") if path.is_file()]
    file_names = {os.path.normcase(os.path.abspath(path)) for path in all_files}
    required = ("index.html", "api.html", "alerts.html", "export.html", "privacy.html",
                "robots.txt", "sitemap.xml", "sitemap-index.xml",
                "sitemap-google.txt", "api/stats.json")
    for name in required:
        if not (OUT / name).is_file():
            fail(f"missing required file: {name}", problems)

    xml_files = [path for path in all_files if path.suffix.lower() == ".xml"]
    feeds = [path for path in xml_files if path.parent == OUT / "feed"]
    if len(feeds) < 20:
        fail(f"too few RSS feeds: {len(feeds)}", problems)
    for path in xml_files:
        try:
            root = ET.parse(path).getroot()
            if root.tag == "rss":
                for item in root.findall("./channel/item"):
                    parsedate_to_datetime(item.findtext("pubDate", ""))
        except Exception as exc:
            fail(f"invalid XML {path.relative_to(OUT)}: {exc}", problems)

    json_files = [path for path in all_files
                  if path.suffix.lower() == ".json" and OUT / "api" in path.parents]
    if len(json_files) < 20:
        fail(f"too few API files: {len(json_files)}", problems)
    for path in json_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            fail(f"invalid JSON {path.relative_to(OUT)}: {exc}", problems)

    try:
        urls = (OUT / "sitemap-google.txt").read_text(encoding="utf-8").splitlines()
        if not 0 < len(urls) <= 50000:
            fail(f"text sitemap URL count outside limits: {len(urls)}", problems)
        if len(urls) != len(set(urls)):
            fail("text sitemap contains duplicate URLs", problems)
        if any(not url.startswith(BASE + "/") for url in urls):
            fail("text sitemap contains a URL outside the canonical site", problems)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        xml_urls = [node.text for node in ET.parse(OUT / "sitemap.xml").getroot()
                    .findall("sm:url/sm:loc", ns)]
        if xml_urls != urls:
            fail("XML and text canonical sitemaps do not contain the same URLs", problems)
    except OSError as exc:
        fail(f"cannot read text sitemap: {exc}", problems)

    html_files = [path for path in all_files if path.suffix.lower() == ".html"]
    notice_files = sorted(path for path in html_files if path.parent == OUT / "n")
    structural_files = [path for path in html_files if path.parent != OUT / "n"]
    # Notice pages share one template. Check a stable sample from both ends;
    # scan every structurally distinct index, country, sector, CPV and winner page.
    link_files = structural_files + notice_files[:250] + notice_files[-250:]
    for source in link_files:
        text = source.read_text(encoding="utf-8")
        lowered = text.lower()
        if "gumroad.com" in lowered or "daily email" in lowered:
            fail(f"retired commercial/email copy in {source.relative_to(OUT)}", problems)
        # JavaScript templates contain partial href strings which are completed
        # in the browser; only validate links in the HTML itself.
        markup = re.sub(r"<script\b.*?</script>", "", text, flags=re.I | re.S)
        for raw in LINK_RE.findall(markup):
            target = local_target(source, raw)
            if target is None:
                continue
            if os.path.normcase(os.path.abspath(target)) not in file_names:
                fail(f"broken local link in {source.relative_to(OUT)}: {raw}", problems)
                if len(problems) >= 100:
                    break
        if len(problems) >= 100:
            break

    if problems:
        print("site validation failed:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"site valid: {len(html_files):,} HTML pages ({len(link_files):,} link-checked), "
          f"{len(xml_files)} XML files, {len(json_files)} JSON files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
