"""Ядро мини-библиотеки: Observer, Disposable, SafeObserver, Observable.

Observable — обёртка над *функцией подписки* ``SafeObserver -> Disposable``.
Ничего не происходит, пока на поток не подписались («холодный» поток);
каждая подписка заново вызывает функцию подписки.

``SafeObserver`` следит за грамматикой уведомлений
``on_next* (on_error | on_completed)?``: после терминального уведомления
остальные игнорируются, а подписка на источник освобождается.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import reduce
from typing import Any


def _noop(*_: Any) -> None:
    """Обработчик «ничего не делать»."""


@dataclass(frozen=True)
class Observer:
    """Неизменяемая тройка обработчиков уведомлений."""

    on_next: Callable[[Any], None] = _noop
    on_error: Callable[[Exception], None] = _noop
    on_completed: Callable[[], None] = _noop


class Disposable:
    """Объект отписки: действие выполняется не более одного раза."""

    def __init__(self, action: Callable[[], None] = _noop) -> None:
        """Запомнить действие освобождения ресурса."""
        self._action = action
        self.is_disposed = False

    def dispose(self) -> None:
        """Выполнить действие (повторные вызовы игнорируются)."""
        if not self.is_disposed:
            self.is_disposed = True
            self._action()


class CompositeDisposable(Disposable):
    """Группа подписок, освобождаемых вместе."""

    def __init__(self, *items: Disposable) -> None:
        """Создать группу из уже существующих подписок."""
        super().__init__()
        self._items: list[Disposable] = list(items)

    def add(self, item: Disposable) -> None:
        """Добавить подписку (если группа уже освобождена — освободить её)."""
        if self.is_disposed:
            item.dispose()
        else:
            self._items.append(item)

    def dispose(self) -> None:
        """Освободить все подписки группы."""
        if not self.is_disposed:
            self.is_disposed = True
            for item in self._items:
                item.dispose()


class SafeObserver(Disposable):
    """Наблюдатель-«предохранитель» и одновременно объект отписки.

    * соблюдает грамматику уведомлений;
    * ``is_stopped`` истинно, если остановлен он сам *или* любой наблюдатель
      ниже по цепочке — так синхронный источник узнаёт, что результат больше
      никому не нужен (это позволяет ``take(n)`` остановить бесконечный
      источник);
    * при терминальном уведомлении или ``dispose`` освобождает подписку на
      источник (``upstream``).
    """

    def __init__(
        self, observer: Observer, downstream: SafeObserver | None = None
    ) -> None:
        """Обернуть обработчики; ``downstream`` — следующий в цепочке."""
        super().__init__()
        self._observer = observer
        self._downstream = downstream
        self._stopped = False
        self._upstream: Disposable | None = None

    @property
    def is_stopped(self) -> bool:
        """Нужно ли ещё отправлять значения этому наблюдателю."""
        return self._stopped or (
            self._downstream is not None and self._downstream.is_stopped
        )

    def on_next(self, value: Any) -> None:
        """Передать значение, если поток ещё активен."""
        if not self.is_stopped:
            self._observer.on_next(value)

    def on_error(self, error: Exception) -> None:
        """Терминальное уведомление об ошибке."""
        if not self._stopped:
            self._stopped = True
            try:
                self._observer.on_error(error)
            finally:
                self.dispose()

    def on_completed(self) -> None:
        """Терминальное уведомление о завершении."""
        if not self._stopped:
            self._stopped = True
            try:
                self._observer.on_completed()
            finally:
                self.dispose()

    def set_upstream(self, upstream: Disposable) -> None:
        """Запомнить подписку на источник (или сразу освободить её)."""
        if self.is_disposed:
            upstream.dispose()
        else:
            self._upstream = upstream

    def dispose(self) -> None:
        """Отписаться: остановиться и освободить источник."""
        if not self.is_disposed:
            self.is_disposed = True
            self._stopped = True
            if self._upstream is not None:
                self._upstream.dispose()


def to_safe(
    on_next: Any = None, on_error: Any = None, on_completed: Any = None
) -> SafeObserver:
    """Привести аргументы subscribe(...) к SafeObserver.

    Принимает готовый SafeObserver, объект с методами on_next/on_error/
    on_completed (Observer, Subject) или отдельные функции-обработчики.
    """
    if isinstance(on_next, SafeObserver):
        return on_next
    if hasattr(on_next, "on_next"):
        return SafeObserver(
            Observer(on_next.on_next, on_next.on_error, on_next.on_completed)
        )
    return SafeObserver(
        Observer(on_next or _noop, on_error or _noop, on_completed or _noop)
    )


class Observable:
    """Наблюдаемый поток — обёртка над функцией подписки."""

    def __init__(
        self, subscribe: Callable[[SafeObserver], Disposable]
    ) -> None:
        """Запомнить функцию подписки (сама подписка ещё не выполняется)."""
        self._subscribe_fn = subscribe

    def subscribe(
        self,
        on_next: Any = None,
        on_error: Any = None,
        on_completed: Any = None,
    ) -> SafeObserver:
        """Подписаться; вернуть объект отписки.

        Исключение в функции подписки превращается в ``on_error``.
        """
        safe = to_safe(on_next, on_error, on_completed)
        try:
            upstream = self._subscribe_fn(safe)
        except Exception as error:  # noqa: BLE001 - ошибка источника → поток
            safe.on_error(error)
            upstream = Disposable()
        safe.set_upstream(upstream)
        return safe

    def pipe(
        self, *operators: Callable[[Observable], Observable]
    ) -> Observable:
        """Последовательно применить операторы — композиция функций."""
        return reduce(lambda acc, op: op(acc), operators, self)


def inner(
    downstream: SafeObserver,
    on_next: Any = None,
    on_error: Any = None,
    on_completed: Any = None,
) -> SafeObserver:
    """Внутренний наблюдатель оператора.

    Не заданные обработчики пересылают уведомления в ``downstream``;
    ``is_stopped`` учитывает состояние ``downstream``.
    """
    return SafeObserver(
        Observer(
            on_next or downstream.on_next,
            on_error or downstream.on_error,
            on_completed or downstream.on_completed,
        ),
        downstream,
    )
