"""Задание 3. Мраморные тесты операторов rx_mini.

Для каждого оператора задания 2 — не менее двух тестов в виде мраморных
диаграмм (``marble``) плюс граничные случаи: пустой поток, ошибка
источника, ошибка в функции оператора, ранняя отписка.
"""

import itertools
from types import MappingProxyType
from typing import Any

import pytest
from rx_mini import (
    Observable,
    SafeObserver,
    Subject,
    buffer_with_count,
    catch,
    combine_latest,
    concat,
    count,
    defer,
    distinct_until_changed,
    empty,
    filter_,
    flat_map,
    from_iterable,
    map_,
    merge,
    of,
    pairwise,
    reduce_,
    retry,
    scan,
    skip,
    start_with,
    take,
    take_while,
    throw,
    to_list,
    zip_,
)
from rx_mini.core import Disposable
from rx_mini.operators import Operator
from rx_mini.testing import (
    MarbleError,
    hot,
    marble,
    materialize,
    parse_marbles,
    render_marbles,
    values,
)

ERR = MarbleError("#")
INT = MappingProxyType({str(i): i for i in range(10)})


def join(v: tuple[Any, ...]) -> str:
    """Кортеж значений → строка для диаграммы."""
    return "".join(map(str, v))


def m1(op: Operator, diagram: str, **kw: Any) -> str:
    """Мраморный тест оператора с одним источником."""
    return marble(lambda s: s.pipe(op), diagram, **kw)


def boom(*_: Any) -> Any:
    """Функция, которая всегда падает."""
    raise ValueError("boom")


# ------------------------------ создание ----------------------------------
def test_of() -> None:
    """of: все значения и завершение сразу при подписке."""
    assert marble(lambda: of("a", "b")) == "(ab|)"
    assert marble(lambda: of()) == "|"


def test_from_iterable() -> None:
    """from_iterable: холодный источник из коллекции."""
    assert marble(lambda: from_iterable("xyz")) == "(xyz|)"
    assert marble(lambda s: merge(s, from_iterable("xy")), "--a|") == (
        "(xy)-a|"
    )


def test_empty() -> None:
    """empty: только завершение."""
    assert marble(lambda: empty()) == "|"
    assert marble(lambda s: concat(empty(), s), "-a|") == "-a|"


def test_throw() -> None:
    """throw: только ошибка."""
    assert marble(lambda: throw(ERR)) == "#"
    assert marble(lambda s: merge(s, throw(ERR)), "-a|") == "#"


def test_cold_source_restarts_for_each_subscription() -> None:
    """Каждая подписка на холодный поток запускает его заново."""
    src = of(1, 2).pipe(scan(lambda a, x: a + x, 0))
    assert values(materialize(src)) == values(materialize(src)) == [1, 3]


def test_marble_parse_render_roundtrip() -> None:
    """Разбор и отрисовка диаграммы взаимно обратны."""
    d = "-a-(bc)-|"
    assert render_marbles(parse_marbles(d)) == d


# ------------------------------ преобразование ----------------------------
def test_map() -> None:
    """map_: преобразование значений, ошибка источника проходит."""
    assert m1(map_(lambda x: x * 2), "-1-2-3-|", values=INT) == "-2-4-6-|"
    assert m1(map_(str.upper), "-a--#") == "-A--#"


def test_map_function_error_stops_stream() -> None:
    """Исключение в функции map_ → on_error, дальше ничего нет."""
    assert (
        m1(
            map_(lambda x: 10 // x),
            "-1-0-2-|",
            values=INT,
            fmt=lambda v: str(v % 10),
        )
        == "-0-#"
    )
    assert m1(map_(boom), "-a-b|") == "-#"


def test_scan() -> None:
    """scan: промежуточные значения свёртки."""
    assert m1(scan(lambda a, x: a + x, 0), "-1-2-3|", values=INT) == "-1-3-6|"
    assert m1(scan(lambda a, x: a + x, ""), "-a-b-#") == "-a-ab-#"


def test_buffer_with_count() -> None:
    """buffer_with_count: пакеты по n, остаток при завершении."""
    assert (
        m1(buffer_with_count(2), "-a-b-c-d-e|", fmt=join) == "---ab---cd--(e|)"
    )
    assert m1(buffer_with_count(2), "-a-b-c-#", fmt=join) == "---ab---#"
    with pytest.raises(ValueError):
        buffer_with_count(0)


def test_pairwise() -> None:
    """pairwise: пары соседних значений."""
    assert m1(pairwise(), "-a-b-c|", fmt=join) == "---ab-bc|"
    assert m1(pairwise(), "-a-b-#", fmt=join) == "---ab-#"
    assert materialize(of(1).pipe(pairwise())) == [("C",)]


def test_flat_map() -> None:
    """flat_map: внутренние потоки сливаются."""
    assert m1(flat_map(lambda x: of(x, x)), "-a--b-|") == "-(aa)--(bb)-|"
    assert m1(flat_map(lambda x: throw(ERR)), "--a-b|") == "--#"


# -------------------------------- фильтрация ------------------------------
def test_filter() -> None:
    """filter_: только подходящие значения; ошибка предиката → on_error."""
    assert (
        m1(filter_(lambda x: x % 2 == 0), "-1-2-3-4-|", values=INT)
        == "---2---4-|"
    )
    assert m1(filter_(boom), "-1-2|", values=INT) == "-#"


def test_take() -> None:
    """take: n значений, затем завершение."""
    assert m1(take(2), "-a-b-c-|") == "-a-(b|)"
    assert m1(take(3), "-a-#") == "-a-#"
    assert materialize(of(1, 2).pipe(take(0))) == [("C",)]


def test_take_stops_infinite_source() -> None:
    """Бесконечный синхронный источник останавливается после n значений."""
    squares = from_iterable(itertools.count()).pipe(
        map_(lambda x: x * x), take(3)
    )
    assert values(materialize(squares)) == [0, 1, 4]


def test_take_unsubscribes_from_source() -> None:
    """После take(1) у субъекта не остаётся подписчиков."""
    src = Subject()
    materialize(src.pipe(take(1)))
    src.on_next(1)
    assert not src.has_observers


def test_skip() -> None:
    """skip: пропуск первых n значений."""
    assert m1(skip(2), "-a-b-c-d|") == "-----c-d|"
    assert m1(skip(5), "-a-b|") == "----|"


def test_distinct_until_changed() -> None:
    """distinct_until_changed: подавление подряд идущих повторов."""
    assert (
        m1(distinct_until_changed(), "--1--1--2--2--2--3--|")
        == "--1-----2--------3--|"
    )
    assert (
        m1(distinct_until_changed(str.lower), "-a-A-b-B-a|") == "-a---b---a|"
    )


def test_take_while() -> None:
    """take_while: значения, пока условие истинно."""
    assert m1(take_while(lambda x: x < 3), "-1-2-3-1|", values=INT) == "-1-2-|"
    assert m1(take_while(lambda x: True), "-1-#", values=INT) == "-1-#"


# ------------------------------ комбинирование ----------------------------
def test_merge() -> None:
    """merge: значения всех источников по мере поступления."""
    assert marble(merge, "-a---b|", "--x-y--|") == "-ax-yb-|"
    assert marble(merge, "-a-#", "--x-y|") == "-ax#"
    assert materialize(merge()) == [("C",)]


def test_zip() -> None:
    """zip_: попарное сопоставление по номеру."""
    assert marble(zip_, "-a-b-c|", "--x---y|", fmt=join) == "--ax---by|"
    assert marble(zip_, "-a-b|", "--x|", fmt=join) == "--ax|"


def test_combine_latest() -> None:
    """combine_latest: пара последних значений при любом событии."""
    assert (
        marble(combine_latest, "-a---b|", "--x-y--|", fmt=join)
        == "--ax-ayby-|"
    )
    assert marble(combine_latest, "-a-#", "--x|", fmt=join) == "--ax#"
    assert materialize(combine_latest(empty(), of(1))) == [("C",)]


def test_start_with() -> None:
    """start_with: значения перед источником."""
    assert m1(start_with("x"), "--a|") == "x-a|"
    assert m1(start_with("x", "y"), "-#") == "(xy)#"


# -------------------------------- агрегирование ---------------------------
def test_reduce() -> None:
    """reduce_: одно значение при завершении."""
    assert m1(reduce_(lambda a, x: a + x, 0), "-1-2-3|", values=INT) == (
        "------(6|)"
    )
    assert m1(reduce_(lambda a, x: a + x, 0), "-1-#", values=INT) == "---#"
    assert m1(reduce_(lambda a, x: a + x, 0), "---|") == "---(0|)"


def test_to_list() -> None:
    """to_list: все значения одним кортежем."""
    assert m1(to_list(), "-a-b|", fmt=join) == "----(ab|)"
    assert m1(to_list(), "--|", fmt=lambda v: str(len(v))) == "--(0|)"


def test_count() -> None:
    """count: число значений."""
    assert m1(count(), "-a-b-c|") == "------(3|)"
    assert m1(count(), "-a-#") == "---#"


# ------------------------------ ошибки ------------------------------------
def test_catch() -> None:
    """catch: при ошибке — резервный поток."""
    assert m1(catch(lambda e: of("r")), "-a-#") == "-a-(r|)"
    assert m1(catch(lambda e: of("r")), "-a-b|") == "-a-b|"


def test_retry() -> None:
    """retry: повторные подписки на холодный источник."""
    attempts = {"n": 0}

    def flaky() -> Observable:
        attempts["n"] += 1
        return of("x", "#") if attempts["n"] < 3 else of("ok")

    def failing(v: str) -> Observable:
        return throw(ERR) if v == "#" else of(v)

    src = defer(flaky).pipe(flat_map(failing), retry(3))
    assert marble(lambda: src) == "(xxok|)"
    attempts["n"] = -10
    assert marble(lambda: defer(flaky).pipe(flat_map(failing), retry(2))) == (
        "(xx#)"
    )
    # горячий источник после ошибки уже завершён — повтор бесполезен
    assert m1(retry(3), "-a-#") == "-a-#"


# ------------------------- грамматика и отписка ----------------------------
def test_grammar_no_events_after_terminal() -> None:
    """После on_completed источник уже не может ничего прислать."""

    def bad_source(obs: SafeObserver) -> Disposable:
        obs.on_next(1)
        obs.on_completed()
        obs.on_next(2)
        obs.on_error(ERR)
        return Disposable()

    assert materialize(Observable(bad_source)) == [("N", 1), ("C",)]


def test_exception_in_subscribe_becomes_error() -> None:
    """Исключение в функции подписки → on_error."""

    def explode(obs: SafeObserver) -> Disposable:
        raise ValueError("bad")

    assert materialize(Observable(explode))[0][0] == "E"


def test_early_dispose() -> None:
    """После dispose значения не приходят, подписка снята."""
    src = Subject()
    got: list[int] = []
    sub = src.pipe(map_(lambda x: x + 1)).subscribe(got.append)
    src.on_next(1)
    sub.dispose()
    src.on_next(2)
    assert got == [2] and not src.has_observers


def test_hot_source_and_late_subscriber() -> None:
    """Поздний подписчик горячего источника получает только завершение."""
    h = hot(1, 2, ("C",))
    early: list[int] = []
    h.observable.subscribe(early.append)
    h.run()
    assert early == [1, 2] and materialize(h.observable) == [("C",)]
