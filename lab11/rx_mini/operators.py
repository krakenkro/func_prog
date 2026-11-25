"""Операторы потоков — функции высшего порядка.

Каждый оператор ``op(params)`` возвращает функцию ``Observable -> Observable``,
поэтому цепочку можно собрать методом ``pipe`` (композиция функций).
Состояние операторов (``scan``, ``take``, ``buffer`` …) создаётся *внутри
функции подписки*, поэтому у каждой подписки оно своё.

Ошибка в пользовательской функции оператора превращается в ``on_error``,
а подписка на источник освобождается.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from typing import Any

from .core import (
    CompositeDisposable,
    Disposable,
    Observable,
    SafeObserver,
    inner,
)

Operator = Callable[[Observable], Observable]
_NOTHING = object()


def identity(x: Any) -> Any:
    """Тождественная функция (ключ по умолчанию)."""
    return x


def _try(
    obs: SafeObserver, sub: SafeObserver, f: Callable[..., Any], *args: Any
) -> Any:
    """Вызвать f(*args); при исключении — on_error и отписка от источника."""
    try:
        return f(*args)
    except Exception as error:  # noqa: BLE001 - ошибка функции → поток
        obs.on_error(error)
        sub.dispose()
        return _NOTHING


# ============================ создание потоков =============================
def from_iterable(items: Iterable[Any]) -> Observable:
    """Холодный поток из элементов коллекции (каждой подписке — заново)."""

    def subscribe(obs: SafeObserver) -> Disposable:
        for value in items:
            if obs.is_stopped:
                return Disposable()
            obs.on_next(value)
        obs.on_completed()
        return Disposable()

    return Observable(subscribe)


def of(*values: Any) -> Observable:
    """Поток из перечисленных значений."""
    return from_iterable(values)


def empty() -> Observable:
    """Пустой поток: сразу on_completed."""

    def subscribe(obs: SafeObserver) -> Disposable:
        obs.on_completed()
        return Disposable()

    return Observable(subscribe)


def throw(error: Exception) -> Observable:
    """Поток, сразу завершающийся ошибкой."""

    def subscribe(obs: SafeObserver) -> Disposable:
        obs.on_error(error)
        return Disposable()

    return Observable(subscribe)


def defer(factory: Callable[[], Observable]) -> Observable:
    """Создавать поток заново при каждой подписке."""
    return Observable(lambda obs: factory().subscribe(obs))


def concat(*sources: Observable) -> Observable:
    """Последовательно: следующий источник — после завершения предыдущего."""

    def subscribe(obs: SafeObserver) -> Disposable:
        group = CompositeDisposable()

        def run(i: int) -> None:
            if i == len(sources):
                obs.on_completed()
            else:
                group.add(
                    sources[i].subscribe(
                        inner(obs, on_completed=lambda: run(i + 1))
                    )
                )

        run(0)
        return group

    return Observable(subscribe)


# ============================== преобразование ==============================
def map_(f: Callable[[Any], Any]) -> Operator:
    """Применить f к каждому значению."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            def on_next(v: Any) -> None:
                r = _try(obs, sub, f, v)
                if r is not _NOTHING:
                    obs.on_next(r)

            sub = inner(obs, on_next=on_next)
            return src.subscribe(sub)

        return Observable(subscribe)

    return op


def scan(f: Callable[[Any, Any], Any], seed: Any) -> Operator:
    """Накопление: выдаёт каждое промежуточное значение свёртки."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            state = {"acc": seed}  # своё состояние у подписки

            def on_next(v: Any) -> None:
                r = _try(obs, sub, f, state["acc"], v)
                if r is not _NOTHING:
                    state["acc"] = r
                    obs.on_next(r)

            sub = inner(obs, on_next=on_next)
            return src.subscribe(sub)

        return Observable(subscribe)

    return op


def buffer_with_count(n: int) -> Operator:
    """Группировать по n значений в кортежи (остаток — при завершении)."""
    if n <= 0:
        raise ValueError("размер буфера должен быть положительным")

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            state = {"buf": ()}

            def on_next(v: Any) -> None:
                buf = state["buf"] + (v,)
                state["buf"] = () if len(buf) == n else buf
                if len(buf) == n:
                    obs.on_next(buf)

            def on_completed() -> None:
                if state["buf"]:
                    obs.on_next(state["buf"])
                obs.on_completed()

            return src.subscribe(
                inner(obs, on_next=on_next, on_completed=on_completed)
            )

        return Observable(subscribe)

    return op


def pairwise() -> Operator:
    """Пары (предыдущее, текущее), начиная со второго значения."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            state = {"prev": _NOTHING}

            def on_next(v: Any) -> None:
                prev, state["prev"] = state["prev"], v
                if prev is not _NOTHING:
                    obs.on_next((prev, v))

            return src.subscribe(inner(obs, on_next=on_next))

        return Observable(subscribe)

    return op


def flat_map(f: Callable[[Any], Observable]) -> Operator:
    """Каждое значение → поток f(v); все внутренние потоки сливаются.

    Завершается, когда завершены внешний и все внутренние потоки.
    """

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            group = CompositeDisposable()
            state = {"active": 1}

            def done() -> None:
                state["active"] -= 1
                if state["active"] == 0:
                    obs.on_completed()

            def on_next(v: Any) -> None:
                inner_src = _try(obs, outer, f, v)
                if inner_src is not _NOTHING:
                    state["active"] += 1
                    group.add(
                        inner_src.subscribe(inner(obs, on_completed=done))
                    )

            outer = inner(obs, on_next=on_next, on_completed=done)
            group.add(src.subscribe(outer))
            return group

        return Observable(subscribe)

    return op


# ================================ фильтрация ================================
def filter_(pred: Callable[[Any], bool]) -> Operator:
    """Пропускать только значения, для которых pred истинно."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            def on_next(v: Any) -> None:
                ok = _try(obs, sub, pred, v)
                if ok is not _NOTHING and ok:
                    obs.on_next(v)

            sub = inner(obs, on_next=on_next)
            return src.subscribe(sub)

        return Observable(subscribe)

    return op


def take(n: int) -> Operator:
    """Первые n значений, затем завершение и *отписка от источника*."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            if n <= 0:
                obs.on_completed()
                return Disposable()
            state = {"left": n}

            def on_next(v: Any) -> None:
                state["left"] -= 1
                obs.on_next(v)
                if state["left"] == 0:
                    obs.on_completed()
                    sub.dispose()  # источник видит is_stopped и стоп

            sub = inner(obs, on_next=on_next)
            return src.subscribe(sub)

        return Observable(subscribe)

    return op


def skip(n: int) -> Operator:
    """Пропустить первые n значений."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            state = {"left": n}

            def on_next(v: Any) -> None:
                if state["left"] > 0:
                    state["left"] -= 1
                else:
                    obs.on_next(v)

            return src.subscribe(inner(obs, on_next=on_next))

        return Observable(subscribe)

    return op


def distinct_until_changed(key: Callable[[Any], Any] = identity) -> Operator:
    """Подавлять подряд идущие значения с одинаковым ключом."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            state = {"last": _NOTHING}

            def on_next(v: Any) -> None:
                k = _try(obs, sub, key, v)
                if k is not _NOTHING and (
                    state["last"] is _NOTHING or k != state["last"]
                ):
                    state["last"] = k
                    obs.on_next(v)

            sub = inner(obs, on_next=on_next)
            return src.subscribe(sub)

        return Observable(subscribe)

    return op


def take_while(pred: Callable[[Any], bool]) -> Operator:
    """Значения, пока pred истинно; затем завершение и отписка."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            def on_next(v: Any) -> None:
                ok = _try(obs, sub, pred, v)
                if ok is _NOTHING:
                    return
                if ok:
                    obs.on_next(v)
                else:
                    obs.on_completed()
                    sub.dispose()

            sub = inner(obs, on_next=on_next)
            return src.subscribe(sub)

        return Observable(subscribe)

    return op


# ============================== комбинирование ==============================
def merge(*sources: Observable) -> Observable:
    """Слияние: значения всех источников по мере поступления."""

    def subscribe(obs: SafeObserver) -> Disposable:
        if not sources:
            obs.on_completed()
            return Disposable()
        group = CompositeDisposable()
        state = {"active": len(sources)}

        def done() -> None:
            state["active"] -= 1
            if state["active"] == 0:
                obs.on_completed()

        for s in sources:
            group.add(s.subscribe(inner(obs, on_completed=done)))
        return group

    return Observable(subscribe)


def zip_(a: Observable, b: Observable) -> Observable:
    """Попарное сопоставление: i-е значение a с i-м значением b."""

    def subscribe(obs: SafeObserver) -> Disposable:
        queues: tuple[deque[Any], deque[Any]] = (deque(), deque())
        done = [False, False]

        def check_done() -> None:
            if any(d and not q for d, q in zip(done, queues, strict=True)):
                obs.on_completed()

        def on_next(i: int, v: Any) -> None:
            queues[i].append(v)
            if queues[0] and queues[1]:
                obs.on_next((queues[0].popleft(), queues[1].popleft()))
            check_done()

        def on_completed(i: int) -> None:
            done[i] = True
            check_done()

        return CompositeDisposable(
            *(
                s.subscribe(
                    inner(
                        obs,
                        on_next=lambda v, i=i: on_next(i, v),
                        on_completed=lambda i=i: on_completed(i),
                    )
                )
                for i, s in enumerate((a, b))
            )
        )

    return Observable(subscribe)


def combine_latest(a: Observable, b: Observable) -> Observable:
    """При каждом значении любого источника — пара последних значений.

    Первое значение появляется, когда оба источника выдали хотя бы по одному.
    """

    def subscribe(obs: SafeObserver) -> Disposable:
        latest = [_NOTHING, _NOTHING]
        done = [False, False]

        def on_next(i: int, v: Any) -> None:
            latest[i] = v
            if _NOTHING not in latest:
                obs.on_next((latest[0], latest[1]))

        def on_completed(i: int) -> None:
            done[i] = True
            if all(done) or latest[i] is _NOTHING:
                obs.on_completed()

        return CompositeDisposable(
            *(
                s.subscribe(
                    inner(
                        obs,
                        on_next=lambda v, i=i: on_next(i, v),
                        on_completed=lambda i=i: on_completed(i),
                    )
                )
                for i, s in enumerate((a, b))
            )
        )

    return Observable(subscribe)


def start_with(*values: Any) -> Operator:
    """Выдать values перед значениями источника."""
    return lambda src: concat(from_iterable(values), src)


# =============================== агрегирование ==============================
def reduce_(f: Callable[[Any, Any], Any], seed: Any) -> Operator:
    """Свёртка всего потока: одно значение при завершении."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            state = {"acc": seed}

            def on_next(v: Any) -> None:
                r = _try(obs, sub, f, state["acc"], v)
                if r is not _NOTHING:
                    state["acc"] = r

            def on_completed() -> None:
                obs.on_next(state["acc"])
                obs.on_completed()

            sub = inner(obs, on_next=on_next, on_completed=on_completed)
            return src.subscribe(sub)

        return Observable(subscribe)

    return op


def to_list() -> Operator:
    """Собрать все значения в кортеж."""
    return reduce_(lambda acc, v: acc + (v,), ())


def count() -> Operator:
    """Количество значений."""
    return reduce_(lambda acc, _: acc + 1, 0)


# ============================= обработка ошибок =============================
def catch(handler: Callable[[Exception], Observable]) -> Operator:
    """При ошибке переключиться на поток handler(error)."""

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            group = CompositeDisposable()

            def on_error(error: Exception) -> None:
                fallback = _try(obs, sub, handler, error)
                if fallback is not _NOTHING:
                    group.add(fallback.subscribe(inner(obs)))

            sub = inner(obs, on_error=on_error)
            group.add(src.subscribe(sub))
            return group

        return Observable(subscribe)

    return op


def retry(n: int) -> Operator:
    """Повторно подписываться при ошибке; всего не более n попыток.

    Имеет смысл для холодных источников: каждая подписка запускает их
    заново. Семантика числа n совпадает с ``reactivex.operators.retry``.
    """

    def op(src: Observable) -> Observable:
        def subscribe(obs: SafeObserver) -> Disposable:
            group = CompositeDisposable()

            def attempt(k: int) -> None:
                def on_error(error: Exception) -> None:
                    if k + 1 < n:
                        attempt(k + 1)
                    else:
                        obs.on_error(error)

                group.add(src.subscribe(inner(obs, on_error=on_error)))

            attempt(0)
            return group

        return Observable(subscribe)

    return op
