import itertools
import logging
import multiprocessing.dummy
import sys
from contextlib import contextmanager
from queue import Queue
from typing import Any
from typing import Callable
from typing import cast
from typing import Iterable
from typing import Iterator
from typing import no_type_check
from typing import Optional
from typing import Sequence
from typing import Tuple
from typing import TYPE_CHECKING
from typing import TypeVar
from typing import Union

from .types import MISSING
from .types import MissingType

# TODO: remove backports when we drop Python 3.7 support
if sys.version_info >= (3, 8):  # pragma: no cover
    from functools import cached_property
else:  # pragma: no cover
    from backports.cached_property import cached_property as _cprop

    def cached_property(fn: 'F') -> 'F':
        return cast('F', _cprop(fn))


_T = TypeVar('_T')
_U = TypeVar('_U')


def zero_or_one(
    it: Iterable[_U],
    make_exc: Callable[[], Exception],
    default: Union[MissingType, _T] = MISSING,
) -> Union[_U, _T]:
    things = list(it)
    if len(things) == 0:
        if isinstance(default, MissingType):
            raise make_exc()
        return default
    elif len(things) == 1:
        return things[0]
    else:
        assert False, "shouldn't get here"  # noqa: B011; # pragma: no cover


def join_paginated_iter(
    get_things: Callable[[int, Optional[_T]], Iterable[Tuple[_U, _T]]], chunk_size: int,
) -> Iterable[_U]:
    # At the moment get_things must take positional arguments.
    # We could make it work with kwargs by using protocols,
    # but mypy gets confused about partials with kwargs.
    # https://github.com/python/mypy/issues/1484

    last = None
    while True:

        things = get_things(chunk_size, last)

        # When chunk_size is 0, don't chunk the query.
        #
        # This will ensure there are no missing/duplicated entries, but
        # will block database writes until the whole generator is consumed.
        #
        # Currently not exposed through the public API.
        #
        if not chunk_size:
            yield from (t for t, _ in things)
            break

        things = list(things)
        if not things:
            break

        _, last = things[-1]

        yield from (t for t, _ in things)

        if len(things) < chunk_size:
            break


FuncType = Callable[..., Any]
F = TypeVar('F', bound=FuncType)


def chunks(n: int, iterable: Iterable[_T]) -> Iterable[Iterable[_T]]:
    """grouper(2, 'ABCDE') --> AB CD E"""
    # based on https://stackoverflow.com/a/8991553
    it = iter(iterable)
    while True:
        chunk = itertools.islice(it, n)
        try:
            first = next(chunk)
        except StopIteration:
            break
        yield itertools.chain([first], chunk)


@contextmanager
def make_pool_map(workers: int) -> Iterator[F]:
    pool = multiprocessing.dummy.Pool(workers)
    try:
        yield wrap_map(pool.imap_unordered, workers)
    finally:
        pool.close()
        pool.join()


def wrap_map(map: F, workers: int) -> F:
    """Ensure map() calls next() on its iterable in the current thread.

    multiprocessing.dummy.Pool.imap_unordered seems to pass
    the iterable to the worker threads, which call next() on it.

    For generators, this means the generator code runs in the worker thread,
    which is a problem if the generator calls stuff that shouldn't be called
    across threads; e.g., calling a sqlite3.Connection method results in:

        sqlite3.ProgrammingError: SQLite objects created in a thread
        can only be used in that same thread. The object was created
        in thread id 1234 and this is thread id 5678.

    """

    @no_type_check
    def wrapper(func, iterable):
        sentinel = object()
        queue = Queue()

        for _ in range(workers):
            queue.put(next(iterable, sentinel))

        for rv in map(func, iter(queue.get, sentinel)):
            queue.put(next(iterable, sentinel))
            yield rv

    return cast(F, wrapper)


@contextmanager
def make_noop_context_manager(thing: _T) -> Iterator[_T]:
    yield thing


class PrefixLogger(logging.LoggerAdapter):

    # if needed, add: with log.push('another prefix'): ...

    def __init__(self, logger: logging.Logger, prefixes: Sequence[str] = ()):
        super().__init__(logger, {})
        self.prefixes = tuple(prefixes)

    @staticmethod
    def _escape(s: str) -> str:  # pragma: no cover
        return '%%'.join(s.split('%'))

    def process(self, msg: str, kwargs: Any) -> Tuple[str, Any]:  # pragma: no cover
        return ': '.join(tuple(self._escape(p) for p in self.prefixes) + (msg,)), kwargs


if TYPE_CHECKING:  # pragma: no cover
    MixinBase = Exception
else:
    MixinBase = object


class FancyExceptionMixin(MixinBase):

    """Exception mixin that renders a message and __cause__ in str(e).

    The message looks something like:

        [message: ] parent as string[: CauseType: cause as string]

    The resulting exception pickles successfully;
    __cause__ still gets lost per https://bugs.python.org/issue29466,
    but a string representation of it remains stored on the exception.

    """

    #: Message; overridable.
    message: Optional[str] = None

    @property
    def _str(self) -> str:
        """The exception's unique attributes, as string; overridable."""
        return super().__str__()

    def __init__(self, *args: Any, message: Optional[str] = None, **kwargs: Any):
        super().__init__(*args, **kwargs)  # type: ignore
        if message:
            self.message = message

    @cached_property
    def __cause_name(self) -> Optional[str]:
        if not self.__cause__:
            return None
        t = type(self.__cause__)
        return f'{t.__module__}.{t.__qualname__}'

    @cached_property
    def __cause_str(self) -> Optional[str]:
        return str(self.__cause__) if self.__cause__ else None

    def __reduce__(self) -> Union[str, Tuple[Any, ...]]:
        # "prime" the cached properties before pickling
        str(self)
        return super().__reduce__()

    def __str__(self) -> str:
        parts = [self.message, self._str, self.__cause_name, self.__cause_str]
        # map is here to only to please mypy on python <3.8
        return ': '.join(map(str, filter(None, parts)))
