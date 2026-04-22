import argparse
import csv
import json
import os
import shutil
import time
from collections import deque
from typing import List, Tuple, Optional
from urllib.parse import quote, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_ARTICLE_PREFIX = "https://en.wikipedia.org/wiki/"
STATS_PATH = "/home/h/scraper_stats.json"


def make_session() -> requests.Session:
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
    Ex:
        https://en.wikipedia.org/wiki/Apple_Inc. -> Apple Inc.
    """
    path = urlparse(article_url).path
    if not path.startswith("/wiki/"):
        raise ValueError(f"Not a Wikipedia article URL: {article_url}")
    raw_title = path[len("/wiki/") :]
    return unquote(raw_title).replace("_", " ")


def title_to_url(title: str) -> str:
    return WIKI_ARTICLE_PREFIX + quote(title.replace(" ", "_"), safe="()")


def fetch_links_api(session: requests.Session, page_title: str) -> Tuple[str, List[str]]:
    params = {
        "action": "query",
        "format": "json",
        "redirects": 1,
        "titles": page_title,
        "prop": "links",
        "plnamespace": 0,
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


def get_disk_stats(path: str = "/") -> dict:
    total, used, free = shutil.disk_usage(path)
    used_pct = (used / total * 100.0) if total > 0 else 0.0
    free_pct = (free / total * 100.0) if total > 0 else 0.0

    return {
        "disk_total_bytes": total,
        "disk_used_bytes": used,
        "disk_free_bytes": free,
        "disk_used_percent": round(used_pct, 2),
        "disk_free_percent": round(free_pct, 2),
        "disk_total_gb": round(total / (1024**3), 2),
        "disk_used_gb": round(used / (1024**3), 2),
        "disk_free_gb": round(free / (1024**3), 2),
    }


def write_stats_file(
    path: str,
    visited_count: int,
    queue_count: int,
    discovered_count: int,
    rows_written: int,
    rate: float,
    current_title: str,
    current_depth: int,
    max_depth: Optional[int],
    mode: str,
    output_csv: str,
    started_at: float,
    status: str,
) -> None:
    disk_stats = get_disk_stats("/")

    payload = {
        "status": status,
        "visited": visited_count,
        "queued": queue_count,
        "discovered": discovered_count,
        "rows_written": rows_written,
        "rate_pages_per_s": round(rate, 3),
        "current_title": current_title,
        "current_depth": current_depth,
        "max_depth": max_depth,
        "mode": mode,
        "output_csv": output_csv,
        "started_at": started_at,
        "updated_at": time.time(),
        **disk_stats,
    }

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp_path, path)


def write_idle_stats_file(path: str, status: str) -> None:
    disk_stats = get_disk_stats("/")
    payload = {
        "status": status,
        "visited": 0,
        "queued": 0,
        "discovered": 0,
        "rows_written": 0,
        "rate_pages_per_s": 0.0,
        "current_title": "",
        "current_depth": 0,
        "max_depth": None,
        "mode": "",
        "output_csv": "",
        "started_at": None,
        "updated_at": time.time(),
        **disk_stats,
    }

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp_path, path)


def crawl_wikipedia(
    start_url: str,
    output_csv: str = "wiki_edges.csv",
    mode: str = "infinite",
    max_pages: int = 5000,
    max_depth: Optional[int] = 3,
    sleep_s: float = 0.05,
    flush_every: int = 1000,
):
    if mode not in {"infinite", "max_pages"}:
        raise ValueError("mode must be either 'infinite' or 'max_pages'")

    session = make_session()
    start_title = url_to_title(start_url)

    queue = deque([(start_title, 0)])
    visited = set()
    seen = {start_title}

    rows_written = 0
    pages_processed = 0
    started_at = time.time()

    write_stats_file(
        STATS_PATH,
        visited_count=0,
        queue_count=len(queue),
        discovered_count=len(seen),
        rows_written=0,
        rate=0.0,
        current_title=start_title,
        current_depth=0,
        max_depth=max_depth,
        mode=mode,
        output_csv=output_csv,
        started_at=started_at,
        status="starting",
    )

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source_page", "linked_title"])

        try:
            while queue:
                if mode == "max_pages" and pages_processed >= max_pages:
                    print(f"Reached max_pages={max_pages}. Stopping.")
                    write_stats_file(
                        STATS_PATH,
                        visited_count=len(visited),
                        queue_count=len(queue),
                        discovered_count=len(seen),
                        rows_written=rows_written,
                        rate=(pages_processed / (time.time() - started_at)) if (time.time() - started_at) > 0 else 0.0,
                        current_title="Reached max_pages",
                        current_depth=0,
                        max_depth=max_depth,
                        mode=mode,
                        output_csv=output_csv,
                        started_at=started_at,
                        status="finished",
                    )
                    break

                current_title, current_depth = queue.popleft()

                if current_title in visited:
                    continue

                try:
                    canonical_title, linked_titles = fetch_links_api(session, current_title)
                except requests.HTTPError as e:
                    print(f"[SKIP] HTTP error for {current_title}: {e}")
                    write_stats_file(
                        STATS_PATH,
                        visited_count=len(visited),
                        queue_count=len(queue),
                        discovered_count=len(seen),
                        rows_written=rows_written,
                        rate=(pages_processed / (time.time() - started_at)) if (time.time() - started_at) > 0 else 0.0,
                        current_title=f"HTTP error: {current_title}",
                        current_depth=current_depth,
                        max_depth=max_depth,
                        mode=mode,
                        output_csv=output_csv,
                        started_at=started_at,
                        status="running",
                    )
                    continue
                except requests.RequestException as e:
                    print(f"[SKIP] Request failed for {current_title}: {e}")
                    write_stats_file(
                        STATS_PATH,
                        visited_count=len(visited),
                        queue_count=len(queue),
                        discovered_count=len(seen),
                        rows_written=rows_written,
                        rate=(pages_processed / (time.time() - started_at)) if (time.time() - started_at) > 0 else 0.0,
                        current_title=f"Request error: {current_title}",
                        current_depth=current_depth,
                        max_depth=max_depth,
                        mode=mode,
                        output_csv=output_csv,
                        started_at=started_at,
                        status="running",
                    )
                    continue

                visited.add(canonical_title)
                pages_processed += 1
                new_pages = 0

                for linked_title in linked_titles:
                    writer.writerow([canonical_title, linked_title])
                    rows_written += 1

                    can_go_deeper = (max_depth is None) or (current_depth < max_depth)

                    if can_go_deeper and linked_title not in seen:
                        seen.add(linked_title)
                        queue.append((linked_title, current_depth + 1))
                        new_pages += 1

                    if rows_written % flush_every == 0:
                        f.flush()

                elapsed = time.time() - started_at
                rate = pages_processed / elapsed if elapsed > 0 else 0.0
                depth_text = "unlimited" if max_depth is None else str(max_depth)

                write_stats_file(
                    STATS_PATH,
                    visited_count=len(visited),
                    queue_count=len(queue),
                    discovered_count=len(seen),
                    rows_written=rows_written,
                    rate=rate,
                    current_title=canonical_title,
                    current_depth=current_depth,
                    max_depth=max_depth,
                    mode=mode,
                    output_csv=output_csv,
                    started_at=started_at,
                    status="running",
                )

                print(
                    f"[visited={len(visited):,} | queued={len(queue):,} | discovered={len(seen):,} "
                    f"| rows={rows_written:,} | rate={rate:.2f} pages/s | "
                    f"depth={current_depth}/{depth_text}] "
                    f"{canonical_title} -> {len(linked_titles):,} links "
                    f"(new pages +{new_pages:,})"
                )

                if sleep_s > 0:
                    time.sleep(sleep_s)

            if not queue:
                print("Queue is empty: no more new pages to discover from this start point.")
                write_stats_file(
                    STATS_PATH,
                    visited_count=len(visited),
                    queue_count=0,
                    discovered_count=len(seen),
                    rows_written=rows_written,
                    rate=(pages_processed / (time.time() - started_at)) if (time.time() - started_at) > 0 else 0.0,
                    current_title="Queue empty",
                    current_depth=0,
                    max_depth=max_depth,
                    mode=mode,
                    output_csv=output_csv,
                    started_at=started_at,
                    status="finished",
                )

        except KeyboardInterrupt:
            print("\nStopped by user (Ctrl+C). CSV keeps the rows already written.")
            write_stats_file(
                STATS_PATH,
                visited_count=len(visited),
                queue_count=len(queue),
                discovered_count=len(seen),
                rows_written=rows_written,
                rate=(pages_processed / (time.time() - started_at)) if (time.time() - started_at) > 0 else 0.0,
                current_title="Stopped by user",
                current_depth=0,
                max_depth=max_depth,
                mode=mode,
                output_csv=output_csv,
                started_at=started_at,
                status="stopped",
            )

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
        "--max-depth",
        type=int,
        default=3,
        help=(
            "Maximum crawl depth. "
            "0=start page only, 1=start + linked pages, 2=include grandchildren, 3=include great-grandchildren. "
            "Use -1 for no depth limit."
        ),
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

    max_depth = None if args.max_depth == -1 else args.max_depth

    os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)

    write_idle_stats_file(STATS_PATH, status="idle")

    crawl_wikipedia(
        start_url=args.start_url,
        output_csv=args.output_csv,
        mode=args.mode,
        max_pages=args.max_pages,
        max_depth=max_depth,
        sleep_s=args.sleep_s,
        flush_every=args.flush_every,
    )


if __name__ == "__main__":
    main()