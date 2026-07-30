"""
Fetches a grant page's plain text, and separately finds downloadable
attachment links (PDF/DOCX/XLSX) for the Important Documents scrape step.
"""
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

ATTACHMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx")


class ScrapeBlockedError(Exception):
    """Raised when the target site returns 401/403/429."""


def _fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    if resp.status_code in (403, 401, 429):
        raise ScrapeBlockedError(f"Site blocked scraping (HTTP {resp.status_code})")
    resp.raise_for_status()
    return resp


def scrape(url: str) -> str:
    """Fetch a page and return its visible plain text."""
    resp = _fetch(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    lines = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th"]):
        text = element.get_text(separator=" ", strip=True)
        if text:
            lines.append(text)

    return "\n".join(lines)


def find_attachment_links(url: str) -> list[dict]:
    """
    Fetch a page and return downloadable attachment links found on it, as
    [{"url": absolute_url, "filename": "..."}]. Deduplicated by URL.
    """
    resp = _fetch(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    seen = set()
    attachments = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue
        absolute = urljoin(url, href)
        path = urlparse(absolute).path.lower()
        if not path.endswith(ATTACHMENT_EXTENSIONS):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        filename = Path(urlparse(absolute).path).name or "attachment"
        attachments.append({"url": absolute, "filename": filename})

    return attachments


def download_attachment(url: str, timeout: int = 30) -> bytes:
    resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.content


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Grant page URL to scrape")
    args = parser.parse_args()

    print(f"Fetching: {args.url}")
    text = scrape(args.url)
    print(f"\n--- Text preview (first 500 chars) ---\n{text[:500]}")

    attachments = find_attachment_links(args.url)
    print(f"\n--- Found {len(attachments)} attachment(s) ---")
    for a in attachments:
        print(f"  {a['filename']} -> {a['url']}")


if __name__ == "__main__":
    main()
