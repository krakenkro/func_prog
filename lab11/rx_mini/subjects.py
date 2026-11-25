"""Субъекты — одновременно источник и наблюдатель («горячие» потоки)."""

from __future__ import annotations

from typing import Any

from .core import Disposable, Observable, SafeObserver


class Subject(Observable):
    """Горячий поток: рассылает события всем текущим подписчикам.

    Подписчик получает только события, произошедшие *после* подписки.
    Подписавшийся после завершения сразу получает терминальное уведомление.
    """

    def __init__(self) -> None:
        """Создать субъект без подписчиков."""
        self._observers: list[SafeObserver] = []
        self._terminal: tuple[str, Exception | None] | None = None
        super().__init__(self._subscribe_impl)

    def _subscribe_impl(self, observer: SafeObserver) -> Disposable:
        """Функция подписки субъекта."""
        if self._terminal is not None:
            kind, error = self._terminal
            if kind == "E":
                observer.on_error(error)  # type: ignore[arg-type]
            else:
                observer.on_completed()
            return Disposable()
        self._observers.append(observer)
        return Disposable(lambda: self._remove(observer))

    def _remove(self, observer: SafeObserver) -> None:
        """Удалить подписчика (идемпотентно)."""
        if observer in self._observers:
            self._observers.remove(observer)

    @property
    def has_observers(self) -> bool:
        """Есть ли активные подписчики."""
        return any(not o.is_stopped for o in self._observers)

    def on_next(self, value: Any) -> None:
        """Разослать значение."""
        if self._terminal is None:
            for o in tuple(self._observers):
                o.on_next(value)

    def on_error(self, error: Exception) -> None:
        """Разослать ошибку и завершить субъект."""
        if self._terminal is None:
            self._terminal = ("E", error)
            for o in tuple(self._observers):
                o.on_error(error)
            self._observers.clear()

    def on_completed(self) -> None:
        """Разослать завершение и завершить субъект."""
        if self._terminal is None:
            self._terminal = ("C", None)
            for o in tuple(self._observers):
                o.on_completed()
            self._observers.clear()
