#!/usr/bin/env python3
"""Scrape BDIA member names and email addresses.

Reads every member profile URL from the WordPress sitemap
(`wp-sitemap-posts-person-1.xml`), then visits each profile and extracts
the name (from the page <title>) plus the email address from the first
member-specific `mailto:` link. Site-wide footer addresses (e.g.
info@bdia.de) are filtered out. Results are written to a CSV.

Usage:
    python scraper.py [output.csv]
"""

import csv
import html as html_lib
import re
import sys
import time
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

SITEMAP_URL = "https://bdia.de/wp-sitemap-posts-person-1.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

REQUEST_DELAY = 1.0
REQUEST_TIMEOUT = 30

# Site-wide addresses to ignore — these appear in the footer of every page.
EMAIL_BLOCKLIST = {"info@bdia.de"}


def fetch(session: requests.Session, url: str) -> str:
    resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def collect_profile_urls(session: requests.Session) -> list[str]:
    print(f"[sitemap] {SITEMAP_URL}", file=sys.stderr)
    xml = fetch(session, SITEMAP_URL)
    root = ET.fromstring(xml)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [loc.text.strip() for loc in root.findall(".//sm:url/sm:loc", ns) if loc.text]
    return sorted(set(urls))


def extract_name(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        title = html_lib.unescape(soup.title.string).strip()
        # Title format: "Bianca Baab – bdia bund deutscher ..."
        # Split on en-dash, em-dash, or hyphen surrounded by spaces.
        parts = re.split(r"\s[–—-]\s", title, maxsplit=1)
        return parts[0].strip()
    return ""


def extract_email(soup: BeautifulSoup) -> str:
    for a in soup.select('a[href^="mailto:"]'):
        href = a.get("href", "")
        email = href[len("mailto:"):].split("?")[0].strip().lower()
        if email and email not in EMAIL_BLOCKLIST:
            return email
    return ""


def parse_profile(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    return extract_name(soup), extract_email(soup)


def main(out_path: str) -> None:
    session = requests.Session()
    profile_urls = collect_profile_urls(session)
    print(f"[total] {len(profile_urls)} profiles in sitemap", file=sys.stderr)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "email", "profile_url"])
        for i, profile_url in enumerate(profile_urls, 1):
            try:
                html = fetch(session, profile_url)
            except requests.RequestException as e:
                print(f"  [{i}/{len(profile_urls)}] FAILED {profile_url}: {e}", file=sys.stderr)
                continue
            name, email = parse_profile(html)
            writer.writerow([name, email, profile_url])
            f.flush()
            status = f"{name} <{email}>" if email else f"{name} <NO EMAIL>"
            print(f"  [{i}/{len(profile_urls)}] {status}", file=sys.stderr)
            time.sleep(REQUEST_DELAY)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "members.csv")
