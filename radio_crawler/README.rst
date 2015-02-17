========================
Quod Libet Radio Crawler
========================

A bunch of scripts for retrieving internet radio stream URLs and their 
metadata.

Execute in the following order:

* crawler_google.py
* clean_uris.py
* init_cache.py
* fetch_xiph.py
* fetch_tags.py
* fetch_cast.py
* fetch_tags.py (yes, twice)
* dump_taglist.py


TODO:

* Get genres from xiph, many from there don't have it in the stream
* Add a rating in the list; don't sort/rate in QL
