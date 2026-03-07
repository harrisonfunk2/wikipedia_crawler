# wikipedia_crawler
Crawler to get linked websites from wikipedia articles

Given a Wikipedia article URL, return:
  source_title: the title of the page (e.g. "Apple Inc.")
  links: list of (linked_title, linked_url) for Wikipedia article links in the main content

  Filters out non-article namespaces like Help:, File:, Special:, Category:, etc.
  Deduplicates by linked_url.
