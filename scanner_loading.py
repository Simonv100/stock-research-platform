"""Bounded scanner loads and observable, error-aware market-data caches."""

from __future__ import annotations

from _thread import LockType
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from threading import Lock
from time import monotonic
from typing import Any, Generic, ParamSpec, TypeVar

import streamlit as st

from stock_data import StockDataError


P = ParamSpec("P")
T = TypeVar("T")
MAX_SCANNER_WORKERS = 4


@dataclass
class CacheActivity:
    reused: int = 0
    computed: int = 0
    unavailable: int = 0
    _lock: LockType = field(default_factory=Lock, repr=False)

    def record(self, missed: bool, failed: bool) -> None:
        with self._lock:
            self.reused += int(not missed)
            self.computed += int(missed)
            self.unavailable += int(failed)

    def counts(self) -> tuple[int, int, int]:
        with self._lock:
            return self.reused, self.computed, self.unavailable


@dataclass
class _Attempt:
    missed: bool = False


@dataclass(frozen=True)
class _Success(Generic[T]):
    value: T


@dataclass(frozen=True)
class _Failure:
    error: str


_activity: ContextVar[CacheActivity | None] = ContextVar("scanner_cache_activity", default=None)
_attempt: ContextVar[_Attempt | None] = ContextVar("scanner_cache_attempt", default=None)


@contextmanager
def track_cache_activity(activity: CacheActivity) -> Iterator[None]:
    token = _activity.set(activity)
    try:
        yield
    finally:
        _activity.reset(token)


class CachedMarketLoader(Generic[P, T]):
    def __init__(self, loader: Callable[P, T], ttl: int):
        self.__name__ = loader.__name__
        self.__doc__ = loader.__doc__

        @wraps(loader)
        def captured(*args: P.args, **kwargs: P.kwargs) -> _Success[T] | _Failure:
            attempt = _attempt.get()
            if attempt is not None:
                attempt.missed = True
            try:
                return _Success(loader(*args, **kwargs))
            except StockDataError as exc:
                return _Failure(str(exc))

        self._cached = st.cache_data(ttl=ttl, show_spinner=False)(captured)
        self._info = self._cached._info

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        attempt = _Attempt()
        token = _attempt.set(attempt)
        try:
            result = self._cached(*args, **kwargs)
        finally:
            _attempt.reset(token)
        activity = _activity.get()
        if activity is not None:
            activity.record(attempt.missed, isinstance(result, _Failure))
        if isinstance(result, _Failure):
            raise StockDataError(result.error)
        return result.value

    def clear(self, *args: Any, **kwargs: Any) -> None:
        self._cached.clear(*args, **kwargs)


def cache_market_data(*, ttl: int) -> Callable[[Callable[P, T]], CachedMarketLoader[P, T]]:
    def decorate(loader: Callable[P, T]) -> CachedMarketLoader[P, T]:
        return CachedMarketLoader(loader, ttl)
    return decorate


@dataclass(frozen=True)
class LoadProgress:
    completed: int
    total: int
    reused: int
    computed: int
    unavailable: int
    elapsed: float


@dataclass
class BatchResult(Generic[T]):
    values: dict[str, T]
    errors: dict[str, str]
    progress: LoadProgress


def load_symbol_batch(
    symbols: Iterable[str],
    loader: Callable[[str], T],
    on_progress: Callable[[LoadProgress], None] | None = None,
) -> BatchResult[T]:
    ordered = list(dict.fromkeys(symbols))
    activity = CacheActivity()
    started = monotonic()
    values: dict[str, T] = {}
    errors: dict[str, str] = {}

    def snapshot(completed: int) -> LoadProgress:
        return LoadProgress(completed, len(ordered), *activity.counts(), monotonic() - started)

    def load(symbol: str) -> T:
        with track_cache_activity(activity):
            return loader(symbol)

    if on_progress is not None:
        on_progress(snapshot(0))
    if not ordered:
        return BatchResult(values, errors, snapshot(0))
    executor = ThreadPoolExecutor(max_workers=min(MAX_SCANNER_WORKERS, len(ordered)))
    completed = 0
    last_update = started
    try:
        futures = {executor.submit(load, symbol): symbol for symbol in ordered}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                values[symbol] = future.result()
            except StockDataError as exc:
                errors[symbol] = str(exc)
            completed += 1
            now = monotonic()
            if on_progress is not None and (completed == len(ordered) or now - last_update >= 0.1):
                on_progress(snapshot(completed))
                last_update = now
    finally:
        # A new Streamlit rerun should not wait for every obsolete queued request.
        executor.shutdown(wait=True, cancel_futures=True)
    return BatchResult(
        {symbol: values[symbol] for symbol in ordered if symbol in values},
        {symbol: errors[symbol] for symbol in ordered if symbol in errors},
        snapshot(completed),
    )
