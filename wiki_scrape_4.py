#!/usr/bin/env python3
"""
Wikipedia crawler without SQLite.

What this version does:
- Uses the MediaWiki API (faster than scraping full HTML)
- Writes edges directly to a CSV file
- Stores only:
    source_page, linked_title
- Supports two crawl modes:
    1) max_pages
    2) infinite

Important:
- This version does NOT support true pause/resume from saved state.
- If you stop it, the CSV keeps whatever was already written.
- If you rerun it, the crawl starts over from the beginning.

Examples
--------
Run forever until you stop it:
    python wiki_crawler_no_sqlite.py

Run for only 5000 pages:
    python wiki_crawler_no_sqlite.py --mode max_pages --max-pages 5000
"""

import argparse
import csv
import time
from collections import deque
from typing import List, Tuple
from urllib.parse import quote, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_ARTICLE_PREFIX = "https://en.wikipedia.org/wiki/"


def make_session() -> requests.Session:
    """Create a requests session with retries."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "WikipediaGraphCrawler/1.0 "
                "(personal educational project)"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
    )

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def url_to_title(article_url: str) -> str:
    """
    Convert a Wikipedia article URL to a page title.
    Example:
        https://en.wikipedia.org/wiki/Apple_Inc. -> Apple Inc.
    """
    path = urlparse(article_url).path
    if not path.startswith("/wiki/"):
        raise ValueError(f"Not a Wikipedia article URL: {article_url}")
    raw_title = path[len("/wiki/") :]
    return unquote(raw_title).replace("_", " ")


def title_to_url(title: str) -> str:
    """Convert a page title to a Wikipedia article URL."""
    return WIKI_ARTICLE_PREFIX + quote(title.replace(" ", "_"), safe="()")


def fetch_links_api(session: requests.Session, page_title: str) -> Tuple[str, List[str]]:
    """
    Fetch outgoing article links for a Wikipedia page via the MediaWiki API.

    Returns
    -------
    canonical_title : str
        Canonical title returned by Wikipedia.
    linked_titles : list[str]
        Unique linked article titles in namespace 0 (main/article namespace only).
    """
    params = {
        "action": "query",
        "format": "json",
        "redirects": 1,
        "titles": page_title,
        "prop": "links",
        "plnamespace": 0,   # main/article namespace only
        "pllimit": "max",
    }

    linked_titles: List[str] = []
    seen_titles = set()
    canonical_title = page_title

    while True:
        response = session.get(WIKI_API, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        query = data.get("query", {})
        normalized = query.get("normalized", [])
        redirects = query.get("redirects", [])

        if redirects:
            canonical_title = redirects[0].get("to", canonical_title)
        elif normalized:
            canonical_title = normalized[0].get("to", canonical_title)

        pages = query.get("pages", {})
        if not pages:
            break

        page_info = next(iter(pages.values()))
        canonical_title = page_info.get("title", canonical_title)

        if "missing" in page_info:
            return canonical_title, []

        for link in page_info.get("links", []):
            title = link.get("title", "").strip()
            if not title:
                continue
            if title not in seen_titles:
                seen_titles.add(title)
                linked_titles.append(title)

        if "continue" not in data:
            break

        params.update(data["continue"])

    return canonical_title, linked_titles


def crawl_wikipedia(
    start_url: str,
    output_csv: str = "wiki_edges.csv",
    mode: str = "infinite",   # "infinite" or "max_pages"
    max_pages: int = 5000,
    sleep_s: float = 0.05,
    flush_every: int = 1000,
):
    """
    Crawl Wikipedia using a queue and write edges directly to CSV.

    This version avoids SQLite and keeps everything in memory:
      - visited: pages already crawled
      - seen: pages already discovered / added to queue
      - queue: pages waiting to be crawled

    Output CSV columns:
      source_page, linked_title
    """
    if mode not in {"infinite", "max_pages"}:
        raise ValueError("mode must be either 'infinite' or 'max_pages'")

    session = make_session()

    start_title = url_to_title(start_url)

    queue = deque([start_title])
    visited = set()
    seen = {start_title}

    rows_written = 0
    pages_processed = 0
    started_at = time.time()

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source_page", "linked_title"])

        try:
            while queue:
                if mode == "max_pages" and pages_processed >= max_pages:
                    print(f"Reached max_pages={max_pages}. Stopping.")
                    break

                current_title = queue.popleft()

                if current_title in visited:
                    continue

                try:
                    canonical_title, linked_titles = fetch_links_api(session, current_title)
                except requests.HTTPError as e:
                    print(f"[SKIP] HTTP error for {current_title}: {e}")
                    continue
                except requests.RequestException as e:
                    print(f"[SKIP] Request failed for {current_title}: {e}")
                    continue

                visited.add(canonical_title)
                pages_processed += 1

                new_pages = 0

                for linked_title in linked_titles:
                    writer.writerow([canonical_title, linked_title])
                    rows_written += 1

                    if linked_title not in seen:
                        seen.add(linked_title)
                        queue.append(linked_title)
                        new_pages += 1

                    if rows_written % flush_every == 0:
                        f.flush()

                elapsed = time.time() - started_at
                rate = pages_processed / elapsed if elapsed > 0 else 0.0

                print(
                    f"[visited={len(visited):,} | queued={len(queue):,} | discovered={len(seen):,} "
                    f"| rows={rows_written:,} | rate={rate:.2f} pages/s] "
                    f"{canonical_title} -> {len(linked_titles):,} links "
                    f"(new pages +{new_pages:,})"
                )

                if sleep_s > 0:
                    time.sleep(sleep_s)

            if not queue:
                print("Queue is empty: no more new pages to discover from this start point.")

        except KeyboardInterrupt:
            print("\nStopped by user (Ctrl+C). CSV keeps the rows already written.")

        finally:
            f.flush()
            session.close()

    print(f"Done. Visited {len(visited):,} pages. Wrote {rows_written:,} rows to {output_csv}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wikipedia crawler without SQLite")
    parser.add_argument(
        "--start-url",
        default="https://en.wikipedia.org/wiki/University_of_California,_Santa_Barbara",
        help="Starting Wikipedia article URL",
    )
    parser.add_argument(
        "--output-csv",
        default="wiki_edges.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--mode",
        choices=["infinite", "max_pages"],
        default="infinite",
        help="Crawl forever or stop after max-pages",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=5000,
        help="Pages to process when mode=max_pages",
    )
    parser.add_argument(
        "--sleep-s",
        type=float,
        default=0.05,
        help="Pause between pages in seconds",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=1000,
        help="Flush CSV to disk every N rows",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    crawl_wikipedia(
        start_url=args.start_url,
        output_csv=args.output_csv,
        mode=args.mode,
        max_pages=args.max_pages,
        sleep_s=args.sleep_s,
        flush_every=args.flush_every,
    )


if __name__ == "__main__":
    main()
