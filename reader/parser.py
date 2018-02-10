import time
import datetime

import feedparser

from .types import Feed, Entry


def _datetime_from_timetuple(tt):
    return datetime.datetime.fromtimestamp(time.mktime(tt)) if tt else None

def _get_updated_published(thing, is_rss):
    # feed.get and entry.get don't work for updated due historical reasons;
    # from the docs: "As of version 5.1.1, if this key [.updated] doesn't
    # exist but [thing].published does, the value of [thing].published
    # will be returned. [...] This mapping is temporary and will be
    # removed in a future version of feedparser."

    updated = None
    published = None
    if 'updated_parsed' in thing:
        updated = _datetime_from_timetuple(thing.updated_parsed)
    if 'published_parsed' in thing:
        published = _datetime_from_timetuple(thing.published_parsed)

    if published and not updated and is_rss:
            updated, published = published, None

    return updated, published


class ParseError(Exception):

    def __init__(self, exception):
        super().__init__(exception)
        self.exception = exception

class NotModified(Exception): pass


def _make_entry(entry, is_rss):
    assert entry.id
    updated, published = _get_updated_published(entry, is_rss)
    assert updated

    return Entry(
        entry.id,
        entry.get('title'),
        entry.get('link'),
        updated,
        published,
        entry.get('summary'),
        entry.get('content'),
        entry.get('enclosures') or None,
        False,
    )


def parse(url, http_etag=None, http_last_modified=None):

    d = feedparser.parse(url, etag=http_etag, modified=http_last_modified)

    if d.get('bozo'):
        raise ParseError(url, d.get('bozo_exception'))

    if d.get('status') == 304:
        raise NotModified(url)

    http_etag = d.get('etag', http_etag)
    http_last_modified = d.get('modified', http_last_modified)

    is_rss = d.version.startswith('rss')
    updated, _ = _get_updated_published(d.feed, is_rss)

    feed = Feed(url, d.feed.get('title'), d.feed.get('link'), updated)
    entries = (_make_entry(e, is_rss) for e in d.entries)

    return feed, entries, http_etag, http_last_modified

