# wikipedia_crawler
Crawler to get linked websites from wikipedia articles

### Given a Wikipedia article URL, return:
- source_title: the title of the page 
- links: list of (linked_title, linked_url) for Wikipedia article links in the main content
  
Filters out non-article namespaces like Help:, File:, Special:, Category:, etc.

Deduplicates by linked_url.

Modes:
  - mode="max_pages": stop after visiting max_pages source pages
  - mode="infinite": run until queue is empty OR user stops with Ctrl+C

Important sets:
  - visited: pages already crawled
  - seen: pages already discovered / added to queue


## Updated wikipedia_crawler_4.py
- Run forever:
  - `python wiki_crawler_4.py`
- Run for a fixed number of pages:
  - `python wikipedia_crawler_4.py --mode max_pages --max-pages 5000`
- Change the start page:
  - `python wikipedia_crawler_4.py --start-url "https://en.wikipedia.org/wiki/Apple_Inc."`

## Updated wiki_scrape_5:
- Run with no depth limit:
  - use `-1`
  - `python wiki_scrape_5.py --start-url "https://en.wikipedia.org/wiki/Apple_Inc." --max-depth -1`
- Run from 'Apple Inc.' and stop after 3 levels:
  - `python wiki_scrape_5.py --start-url "https://en.wikipedia.org/wiki/Apple_Inc." --max-depth 3`
- Run with both page limit and depth limit:
  - `python wiki_scrape_5.py --start-url "https://en.wikipedia.org/wiki/Apple_Inc." --max-depth 3 --mode max_pages --max-pages 5000`
