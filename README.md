**reader** is a minimal feed reader.

[![Build Status](https://travis-ci.org/lemon24/reader.svg?branch=master)](https://travis-ci.org/lemon24/reader)
[![Code Coverage](https://codecov.io/github/lemon24/reader/coverage.svg?branch=master)](https://codecov.io/github/lemon24/reader?branch=master)
[![Documentation Status](https://readthedocs.org/projects/pip/badge/?version=latest&style=flat)](https://reader.readthedocs.io/en/latest/?badge=latest)

Features:

* Stable and clearly documented API.
* Excellent test coverage.
* Minimal web interface.

Usage:

```bash
$ pip install git+https://github.com/lemon24/reader.git#egg=reader
```

```python
>>> from reader import Reader
>>>
>>> reader = Reader('db.sqlite')
>>> reader.add_feed('http://www.hellointernet.fm/podcast?format=rss')
>>> reader.update_feeds()
>>>
>>> entries = list(reader.get_entries())
>>> [e.title for e in entries]
['H.I. #108: Project Cyclops', 'H.I. #107: One Year of Weird', ...]
>>>
>>> reader.mark_as_read(entries[0])
>>>
>>> [e.title for e in reader.get_entries(which='unread')]
['H.I. #107: One Year of Weird', 'H.I. #106: Water on Mars', ...]
>>> [e.title for e in reader.get_entries(which='read')]
['H.I. #108: Project Cyclops']
```

Documentation: [reader.readthedocs.io](http://reader.readthedocs.io/)

