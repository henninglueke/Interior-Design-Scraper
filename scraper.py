#!/usr/bin/env python3
"""Scrape BDIA member names and email addresses.

Walks the paginated member listing at bdia.de/mitglieder/, collects each
member profile URL, then visits every profile and extracts the name (page
heading) plus the email address from the `mailto:` link behind the envelope
icon. Results are written to a CSV.

Usage:
    python scraper.py [output.csv]
"""

import csv
import sys
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

LIST_URL = (
    "https://bdia.de/mitglieder/"
    "?wpv_view_count=108796"
    "&wpv_post_search="
    "&wpv-dienstleistung=0"
    "&wpv-objektart=0"
    "&wpv-wpcf-adresse="
    "&wpv-wpcf-bdia-landesverband="
    "&wpv_filter_submit=Suchen"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

REQUEST_DELAY = 1.0
REQUEST_TIMEOUT = 30


def with_page(url: str, page: int) -> str:
    parts = urlparse(url)
    qs = parse_qs(parts.query, keep_blank_values=True)
    qs["wpv_paged"] = [str(page)]
    new_query = urlencode([(k, v) for k, vs in qs.items() for v in vs])
    return urlunparse(parts._replace(query=new_query))


def fetch(session: requests.Session, url: str) -> str:
    resp = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def extract_profile_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()
    for a in soup.select('a[href*="/mitglieder/"]'):
        href = a.get("href")
        if not href:
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.netloc and "bdia.de" not in parsed.netloc:
            continue
        path_parts = [p for p in parsed.path.split("/") if p]
        # individual profiles look like /mitglieder/<slug>/, not the listing root
        if len(path_parts) >= 2 and path_parts[0] == "mitglieder":
            clean = urlunparse(parsed._replace(query="", fragment=""))
            links.add(clean)
    return sorted(links)


def has_next_page(html: str, current_page: int) -> bool:
    if f"wpv_paged={current_page + 1}" in html:
        return True
    soup = BeautifulSoup(html, "html.parser")
    return bool(soup.select_one('a[rel="next"]'))


def parse_profile(html: str) -> tuple[str, str] | None:
    soup = BeautifulSoup(html, "html.parser")
    mailto = soup.select_one('a[href^="mailto:"]')
    if not mailto:
        return None
    email = mailto["href"][len("mailto:"):].split("?")[0].strip()
    if not email:
        return None
    name = ""
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(" ", strip=True)
    if not name and soup.title:
        name = soup.title.get_text(strip=True)
    return name, email


def collect_profile_urls(session: requests.Session) -> list[str]:
    profile_urls: set[str] = set()
    page = 1
    while True:
        url = LIST_URL if page == 1 else with_page(LIST_URL, page)
        print(f"[list] page {page}", file=sys.stderr)
        html = fetch(session, url)
        new_links = extract_profile_links(html, url)
        before = len(profile_urls)
        profile_urls.update(new_links)
        added = len(profile_urls) - before
        print(f"  {len(new_links)} links on page, {added} new", file=sys.stderr)
        if added == 0 or not has_next_page(html, page):
            break
        page += 1
        time.sleep(REQUEST_DELAY)
    return sorted(profile_urls)


def main(out_path: str) -> None:
    session = requests.Session()
    profile_urls = collect_profile_urls(session)
    print(f"[total] {len(profile_urls)} unique profiles", file=sys.stderr)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "email", "profile_url"])
        for i, profile_url in enumerate(profile_urls, 1):
            try:
                html = fetch(session, profile_url)
            except requests.RequestException as e:
                print(f"  [{i}] FAILED {profile_url}: {e}", file=sys.stderr)
                continue
            result = parse_profile(html)
            if result is None:
                print(f"  [{i}] no email on {profile_url}", file=sys.stderr)
                continue
            name, email = result
            writer.writerow([name, email, profile_url])
            f.flush()
            print(f"  [{i}/{len(profile_urls)}] {name} <{email}>", file=sys.stderr)
            time.sleep(REQUEST_DELAY)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "members.csv")
