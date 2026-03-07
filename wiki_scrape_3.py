import csv
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from collections import deque

WIKI_BASE = "https://en.wikipedia.org"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def get_wikipedia_links(page_url: str):
    resp = requests.get(page_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    h1 = soup.find("h1", id="firstHeading")
    source_title = h1.get_text(strip=True) if h1 else page_url

    content_div = soup.find("div", id="mw-content-text")
    if content_div is None:
        return source_title, []

    seen_urls = set()
    out = []

    for a in content_div.find_all("a", href=True):
        href = a["href"]

        # Keep only internal Wikipedia article links
        if not href.startswith("/wiki/"):
            continue

        # Skip namespaces that aren't normal article: File:, Help:, Category: etc.
        if ":" in href:
            continue

        linked_title = a.get_text(strip=True)
        if linked_title == "":
            continue

        linked_url = urljoin(WIKI_BASE, href)

        # Deduplicate links found within this one page
        if linked_url in seen_urls:
            continue
        seen_urls.add(linked_url)

        out.append((linked_title, linked_url))

    return source_title, out


def crawl_wikipedia(
    start_url: str,
    output_csv: str = "wiki_edges.csv",
    mode: str = "max_pages",   # max_pages or infinite
    max_pages: int = 100,
    sleep_s: float = 0.2,
    flush_every: int = 1000
):

    if mode not in {"max_pages", "infinite"}:
        raise ValueError("mode must be either 'max_pages' or 'infinite'")

    queue = deque([start_url])
    visited = set()
    seen = set([start_url]) 

    rows_written = 0

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["source_page", "linked_title", "linked_url"])

        try:
            while queue:
                # Stop condition for max_pages mode
                if mode == "max_pages" and len(visited) >= max_pages:
                    print(f"Reached max_pages={max_pages}. Stopping.")
                    break

                current_url = queue.popleft()

                if current_url in visited:
                    continue

                visited.add(current_url)

                try:
                    source_title, links = get_wikipedia_links(current_url)
                except requests.HTTPError as e:
                    print(f"[SKIP] HTTP error for {current_url}: {e}")
                    continue
                except requests.RequestException as e:
                    print(f"[SKIP] Request failed for {current_url}: {e}")
                    continue

                # Progress message
                if mode == "max_pages":
                    print(f"[{len(visited)}/{max_pages}] {source_title} -> {len(links)} links")
                else:
                    print(
                        f"[{len(visited)} visited | {len(queue)} queued | {len(seen)} discovered] "
                        f"{source_title} -> {len(links)} links"
                    )

                # Write edges and enqueue newly discovered pages
                for linked_title, linked_url in links:
                    writer.writerow([source_title, linked_title, linked_url])
                    rows_written += 1

                    # only add to queue if never seen before
                    if linked_url not in seen:
                        queue.append(linked_url)
                        seen.add(linked_url)

                    # Flush so progress is saved
                    if rows_written % flush_every == 0:
                        f.flush()

                time.sleep(sleep_s)

            if not queue:
                print("Queue is empty: no more new pages to discover from this start point.")

        except KeyboardInterrupt:
            print("\nStopped by user (Ctrl+C). Keeping what we have so far...")

        finally:
            f.flush()

    print(f"Done. Visited {len(visited)} pages. Wrote {rows_written} rows to {output_csv}")


if __name__ == "__main__":
    start_url = "https://en.wikipedia.org/wiki/University_of_California,_Santa_Barbara"

    # CHOOSE MODE HERE 

    # 1) Stop after N pages:
    # crawl_wikipedia(start_url, output_csv="wiki_edges.csv", mode="max_pages", max_pages=5000, sleep_s=0.2)

    # 2) Run indefinitely until queue is empty or you stop it:
    crawl_wikipedia(start_url, output_csv="wiki_edges.csv", mode="infinite", sleep_s=0.2)