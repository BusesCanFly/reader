import sqlite3
import threading
from datetime import datetime

import pytest

import reader.core.sqlite_utils
from reader import Entry
from reader import EntryNotFoundError
from reader import Feed
from reader import FeedNotFoundError
from reader import MetadataNotFoundError
from reader import StorageError
from reader.core.storage import Storage
from reader.core.types import EntryForUpdate


def test_storage_errors_open(tmpdir):
    # try to open a directory
    with pytest.raises(StorageError):
        Storage(str(tmpdir))


@pytest.mark.parametrize('db_error_cls', reader.core.sqlite_utils.db_errors)
def test_db_errors(monkeypatch, db_path, db_error_cls):
    """...sqlite_utils.DBError subclasses should be wrapped in StorageError."""

    def open_db(*args, **kwargs):
        raise db_error_cls("whatever")

    monkeypatch.setattr(Storage, 'open_db', staticmethod(open_db))

    with pytest.raises(StorageError):
        Storage(db_path)


def test_path(db_path):
    storage = Storage(db_path)
    assert storage.path == db_path


def test_timeout(monkeypatch, db_path):
    """Storage.__init__ must pass timeout= to open_db."""

    def open_db(*args, timeout=None):
        open_db.timeout = timeout

    monkeypatch.setattr(Storage, 'open_db', staticmethod(open_db))

    timeout = object()
    Storage(db_path, timeout)

    assert open_db.timeout is timeout


def init(storage, _, __):
    Storage(storage.path, timeout=0)


def add_feed(storage, feed, __):
    storage.add_feed(feed.url + '_', datetime(2010, 1, 1))


def remove_feed(storage, feed, __):
    storage.remove_feed(feed.url)


def get_feeds(storage, _, __):
    list(storage.get_feeds())


def get_feeds_for_update(storage, _, __):
    list(storage.get_feeds_for_update())


def get_entries_for_update(storage, feed, entry):
    storage.get_entries_for_update([(feed.url, entry.id)])


def set_feed_user_title(storage, feed, __):
    storage.set_feed_user_title(feed.url, 'title')


def mark_as_stale(storage, feed, __):
    storage.mark_as_stale(feed.url)


def mark_as_read_unread(storage, feed, entry):
    storage.mark_as_read_unread(feed.url, entry.id, 1)


def update_feed(storage, feed, entry):
    storage.update_feed(feed.url, feed, None, None, entry.updated)


def update_feed_last_updated(storage, feed, entry):
    storage.update_feed(feed.url, None, None, None, entry.updated)


def add_or_update_entry(storage, feed, entry):
    storage.add_or_update_entry(feed.url, entry, entry.updated, None, 0)


def add_or_update_entries(storage, feed, entry):
    storage.add_or_update_entries([(feed.url, entry, entry.updated, None, 0)])


def get_entries_chunk_size_0(storage, _, __):
    list(storage.get_entries(chunk_size=0, now=datetime(2010, 1, 1)))


def get_entries_chunk_size_1(storage, _, __):
    list(storage.get_entries(chunk_size=1, now=datetime(2010, 1, 1)))


def iter_feed_metadata(storage, feed, __):
    list(storage.iter_feed_metadata(feed.url))


def set_feed_metadata(storage, feed, __):
    storage.set_feed_metadata(feed.url, 'key', 'value')


def delete_feed_metadata(storage, feed, __):
    storage.delete_feed_metadata(feed.url, 'key')


@pytest.mark.slow
@pytest.mark.parametrize(
    'do_stuff',
    [
        init,
        add_feed,
        remove_feed,
        get_feeds,
        get_feeds_for_update,
        get_entries_for_update,
        set_feed_user_title,
        mark_as_stale,
        mark_as_read_unread,
        update_feed,
        update_feed_last_updated,
        add_or_update_entry,
        add_or_update_entries,
        get_entries_chunk_size_0,
        get_entries_chunk_size_1,
        iter_feed_metadata,
        set_feed_metadata,
        delete_feed_metadata,
    ],
)
def test_errors_locked(db_path, do_stuff):
    """All methods should raise StorageError when the database is locked.

    """
    storage = Storage(db_path)
    storage.db.execute("PRAGMA busy_timeout = 0;")

    feed = Feed('one')
    entry = Entry('entry', datetime(2010, 1, 2))
    storage.add_feed(feed.url, datetime(2010, 1, 1))
    storage.add_or_update_entry(feed.url, entry, entry.updated, None, 0)

    in_transaction = threading.Event()
    can_return_from_transaction = threading.Event()

    def target():
        storage = Storage(db_path)
        storage.db.isolation_level = None
        storage.db.execute("BEGIN EXCLUSIVE;")
        in_transaction.set()
        can_return_from_transaction.wait()
        storage.db.execute("ROLLBACK;")

    thread = threading.Thread(target=target)
    thread.start()

    in_transaction.wait()

    try:
        with pytest.raises(StorageError) as excinfo:
            do_stuff(storage, feed, entry)
        assert 'locked' in str(excinfo.value.__cause__)
    finally:
        can_return_from_transaction.set()
        thread.join()


def iter_get_feeds(storage):
    return storage.get_feeds()


def iter_get_feeds_for_update(storage):
    return storage.get_feeds_for_update()


def iter_get_entries_chunk_size_0(storage):
    return storage.get_entries(chunk_size=0, now=datetime(2010, 1, 1))


def iter_get_entries_chunk_size_1(storage):
    return storage.get_entries(chunk_size=1, now=datetime(2010, 1, 1))


def iter_get_entries_chunk_size_2(storage):
    return storage.get_entries(chunk_size=2, now=datetime(2010, 1, 1))


def iter_get_entries_chunk_size_3(storage):
    return storage.get_entries(chunk_size=3, now=datetime(2010, 1, 1))


def iter_iter_feed_metadata(storage):
    return storage.iter_feed_metadata('two')


@pytest.mark.slow
@pytest.mark.parametrize(
    'iter_stuff',
    [
        iter_get_feeds,
        iter_get_feeds_for_update,
        pytest.param(
            iter_get_entries_chunk_size_0,
            marks=pytest.mark.xfail(raises=StorageError, strict=True),
        ),
        iter_get_entries_chunk_size_1,
        iter_get_entries_chunk_size_2,
        iter_get_entries_chunk_size_3,
    ],
)
def test_iter_locked(db_path, iter_stuff):
    """Methods that return an iterable shouldn't block the underlying storage
    if the iterable is not consumed.

    """
    storage = Storage(db_path)

    feed = Feed('one')
    entry = Entry('entry', None)
    storage.add_feed(feed.url, datetime(2010, 1, 2))
    storage.add_or_update_entry(feed.url, entry, entry.updated, None, 0)
    storage.add_feed('two', datetime(2010, 1, 1))
    storage.add_or_update_entry('two', entry, entry.updated, None, 0)
    storage.set_feed_metadata('two', '1', 1)
    storage.set_feed_metadata('two', '2', 2)

    rv = iter_stuff(storage)
    next(rv)

    # shouldn't raise an exception
    storage = Storage(db_path, timeout=0)
    storage.mark_as_read_unread(feed.url, entry.id, 1)
    storage = Storage(db_path, timeout=0)
    storage.mark_as_read_unread(feed.url, entry.id, 0)


def test_update_feed_last_updated_not_found(db_path):
    storage = Storage(db_path)
    with pytest.raises(FeedNotFoundError):
        storage.update_feed('inexistent-feed', None, None, None, datetime(2010, 1, 2))


@pytest.mark.parametrize(
    'entry_count',
    [
        # We assume the query uses 2 parameters per entry (feed URL and entry ID).
        #
        # variable_number defaults to 999 when compiling SQLite from sources
        int(999 / 2) + 1,
        # variable_number defaults to 250000 in Ubuntu 18.04 -provided SQLite
        pytest.param(int(250000 / 2) + 1, marks=pytest.mark.slow),
    ],
)
def test_get_entries_for_update_param_limit(entry_count):
    """get_entries_for_update() should work even if the number of query
    parameters goes over the variable_number SQLite run-time limit.

    https://github.com/lemon24/reader/issues/109

    """
    storage = Storage(':memory:')

    # shouldn't raise an exception
    list(
        storage.get_entries_for_update(
            ('feed', 'entry-{}'.format(i)) for i in range(entry_count)
        )
    )


class StorageNoGetEntriesForUpdateFallback(Storage):
    def _get_entries_for_update_n_queries(self, _):
        assert False, "shouldn't get called"


class StorageAlwaysGetEntriesForUpdateFallback(Storage):
    def _get_entries_for_update_one_query(self, _):
        raise sqlite3.OperationalError("too many SQL variables")


@pytest.mark.parametrize(
    'storage_cls',
    [StorageNoGetEntriesForUpdateFallback, StorageAlwaysGetEntriesForUpdateFallback],
)
def test_get_entries_for_update(storage_cls):
    storage = storage_cls(':memory:')
    storage.add_feed('feed', datetime(2010, 1, 1))
    storage.add_or_update_entry(
        'feed', Entry('one', datetime(2010, 1, 1)), datetime(2010, 1, 2), None, 0
    )

    assert list(storage.get_entries_for_update([('feed', 'one'), ('feed', 'two')])) == [
        EntryForUpdate(datetime(2010, 1, 1)),
        None,
    ]


@pytest.fixture
def storage():
    return Storage(':memory:')


def test_feed_metadata(storage):
    assert set(storage.iter_feed_metadata('one')) == set()
    assert set(storage.iter_feed_metadata('one', 'key')) == set()

    with pytest.raises(FeedNotFoundError):
        storage.set_feed_metadata('one', 'key', 'value')

    with pytest.raises(MetadataNotFoundError):
        storage.delete_feed_metadata('one', 'key')

    storage.add_feed('one', datetime(2010, 1, 1))
    storage.set_feed_metadata('one', 'key', 'value')

    assert set(storage.iter_feed_metadata('one')) == {('key', 'value')}
    assert set(storage.iter_feed_metadata('one', 'key')) == {('key', 'value')}
    assert set(storage.iter_feed_metadata('one', 'second')) == set()

    storage.add_feed('two', datetime(2010, 1, 1))
    storage.set_feed_metadata('two', '2', 2)
    storage.set_feed_metadata('one', 'second', 1)

    assert set(storage.iter_feed_metadata('one')) == {('key', 'value'), ('second', 1)}
    assert set(storage.iter_feed_metadata('one', 'key')) == {('key', 'value')}
    assert set(storage.iter_feed_metadata('one', 'second')) == {('second', 1)}

    storage.delete_feed_metadata('one', 'key')

    assert set(storage.iter_feed_metadata('one')) == {('second', 1)}


def test_entry_remains_read_after_update(storage_with_two_entries):
    storage = storage_with_two_entries
    storage.mark_as_read_unread('feed', 'one', True)

    storage.add_or_update_entry(
        'feed',
        Entry('one', datetime(2010, 1, 1)),
        datetime(2010, 1, 2),
        datetime(2010, 1, 2),
        0,
    )

    assert {
        e.id for e, _ in storage.get_entries(now=datetime(2010, 1, 1), read=True)
    } == {'one'}


@pytest.fixture
def storage_with_two_entries(storage):
    storage.add_feed('feed', datetime(2010, 1, 1))
    storage.add_or_update_entry(
        'feed',
        Entry('one', datetime(2010, 1, 1)),
        datetime(2010, 1, 2),
        datetime(2010, 1, 2),
        0,
    )
    storage.add_or_update_entry(
        'feed',
        Entry('two', datetime(2010, 1, 1)),
        datetime(2010, 1, 2),
        datetime(2010, 1, 2),
        1,
    )
    return storage


def test_important_unimportant_by_default(storage_with_two_entries):
    storage = storage_with_two_entries
    assert {
        e.id for e, _ in storage.get_entries(now=datetime(2010, 1, 1), important=False)
    } == {'one', 'two'}


def test_important_get_entries(storage_with_two_entries):
    storage = storage_with_two_entries
    storage.mark_as_important_unimportant('feed', 'one', True)

    assert {e.id for e, _ in storage.get_entries(now=datetime(2010, 1, 1))} == {
        'one',
        'two',
    }
    assert {
        e.id for e, _ in storage.get_entries(now=datetime(2010, 1, 1), important=None)
    } == {'one', 'two'}
    assert {
        e.id for e, _ in storage.get_entries(now=datetime(2010, 1, 1), important=True)
    } == {'one'}
    assert {
        e.id for e, _ in storage.get_entries(now=datetime(2010, 1, 1), important=False)
    } == {'two'}


def test_important_entry_remains_important_after_update(storage_with_two_entries):
    storage = storage_with_two_entries
    storage.mark_as_important_unimportant('feed', 'one', True)

    storage.add_or_update_entry(
        'feed',
        Entry('one', datetime(2010, 1, 1)),
        datetime(2010, 1, 2),
        datetime(2010, 1, 2),
        0,
    )

    assert {
        e.id for e, _ in storage.get_entries(now=datetime(2010, 1, 1), important=True)
    } == {'one'}


def test_important_entry_important(storage_with_two_entries):
    storage = storage_with_two_entries
    storage.mark_as_important_unimportant('feed', 'one', True)

    assert {
        e.id: e.important for e, _ in storage.get_entries(now=datetime(2010, 1, 1))
    } == {'one': True, 'two': False}


def test_important_mark_as_unimportant(storage_with_two_entries):
    storage = storage_with_two_entries
    storage.mark_as_important_unimportant('feed', 'one', True)
    storage.mark_as_important_unimportant('feed', 'one', False)

    assert {
        e.id for e, _ in storage.get_entries(now=datetime(2010, 1, 1), important=True)
    } == set()


def test_important_mark_entry_not_found(storage):
    with pytest.raises(EntryNotFoundError):
        storage.mark_as_important_unimportant('feed', 'one', True)
