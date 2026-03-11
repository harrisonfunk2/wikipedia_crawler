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
  - `python wikipedia_crawler_4.py`
- Run for a fixed number of pages:
  - `python wikipedia_crawler_4.py --mode max_pages --max-pages 5000`
- Change the start page:
  - `python wikipedia_crawler_4.py --start-url "https://en.wikipedia.org/wiki/Apple_Inc."`
