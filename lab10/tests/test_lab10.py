"""Тесты ЛР 10: корректность операций и неизменность старых версий."""

import random
from collections.abc import Callable
from typing import Any

import monads as m
import plist as pl
import pqueue as pq
import pyrs_demo as pd
import pytest
import text_buffer as tb
import tree_zipper as tz
from pyrsistent import InvariantException, freeze, pvector, thaw


# ----------------------------- Задание 1 ----------------------------------
class TestPList:
    """Задание 1: персистентный список."""

    def test_basic_ops(self) -> None:
        """Базовые операции PList."""
        xs = pl.from_iterable(range(5))
        assert pl.to_list(xs) == [0, 1, 2, 3, 4]
        assert pl.length(xs) == 5 and pl.head(xs) == 0
        assert pl.to_list(pl.tail(xs)) == [1, 2, 3, 4]
        assert pl.nth(xs, 3) == 3
        assert pl.to_list(pl.take(xs, 2)) == [0, 1]
        assert pl.to_list(pl.drop(xs, 3)) == [3, 4]
        assert pl.drop(xs, 10) == pl.NIL and pl.take(xs, 0) == pl.NIL

    def test_hof(self) -> None:
        """Функции высшего порядка и свёртки."""
        xs = pl.from_iterable(range(1, 6))
        assert list(pl.map_(lambda x: x * 10, xs)) == [10, 20, 30, 40, 50]
        assert list(pl.filter_(lambda x: x % 2, xs)) == [1, 3, 5]
        assert pl.fold_left(lambda a, x: a - x, 0, xs) == -15
        assert pl.fold_right(lambda x, a: x - a, 0, xs) == 3
        assert list(pl.reverse(xs)) == [5, 4, 3, 2, 1]
        assert list(pl.append(xs, pl.from_iterable([6]))) == list(range(1, 7))

    def test_errors(self) -> None:
        """Ошибки для пустого списка и неверного индекса."""
        with pytest.raises(IndexError):
            pl.head(pl.NIL)
        with pytest.raises(IndexError):
            pl.tail(pl.NIL)
        with pytest.raises(IndexError):
            pl.nth(pl.from_iterable([1]), 1)

    def test_structural_sharing(self) -> None:
        """Новые версии разделяют неизменённые части."""
        base = pl.from_iterable([1, 2, 3])
        a, b = pl.cons(0, base), pl.cons(9, base)
        assert pl.tail(a) is pl.tail(b) is base
        joined = pl.append(pl.from_iterable([7, 8]), base)
        assert pl.drop(joined, 2) is base
        assert pl.drop(a, 1) is base

    def test_old_versions_unchanged(self) -> None:
        """Операции не меняют исходный список."""
        xs = pl.from_iterable([1, 2, 3])
        snapshot = list(xs)
        pl.cons(0, xs), pl.map_(str, xs), pl.reverse(xs), pl.append(xs, xs)
        assert list(xs) == snapshot

    def test_eq_and_long_list(self) -> None:
        """Сравнение и длинные списки без переполнения стека."""
        big = pl.from_iterable(range(50_000))
        assert pl.fold_right(lambda x, a: a + 1, 0, big) == 50_000
        assert pl.from_iterable([1, 2]) == pl.from_iterable([1, 2])
        assert pl.from_iterable([1, 2]) != pl.from_iterable([1, 3])


# ----------------------------- Задание 2 ----------------------------------
class TestPQueue:
    """Задание 2: персистентная очередь."""

    def test_fifo_against_deque(self) -> None:
        """Порядок FIFO совпадает с collections.deque."""
        ops = pq.random_ops(10_000, seed=7)
        out, q = pq.run_ops(ops)
        assert out == pq.run_ops_deque(ops)

    def test_old_versions(self) -> None:
        """Старые версии очереди сохраняются."""
        q1 = pq.from_iterable([1, 2, 3])
        q2 = q1.enqueue(4)
        _, q3 = q2.dequeue()
        assert list(q1) == [1, 2, 3] and list(q2) == [1, 2, 3, 4]
        assert list(q3) == [2, 3, 4] and len(q3) == 3
        # повторное извлечение из старой версии даёт тот же результат
        assert q2.dequeue()[0] == q2.dequeue()[0] == 1

    def test_empty(self) -> None:
        """Пустая очередь и ошибки извлечения."""
        assert pq.EMPTY_QUEUE.is_empty() and len(pq.EMPTY_QUEUE) == 0
        with pytest.raises(IndexError):
            pq.EMPTY_QUEUE.dequeue()
        with pytest.raises(IndexError):
            pq.EMPTY_QUEUE.peek()

    def test_linear_time(self) -> None:
        """Время 10⁵ операций растёт линейно."""
        t1 = min(pq.time_ops(10_000) for _ in range(3))
        t2 = min(pq.time_ops(100_000) for _ in range(3))
        assert 4 < t2 / t1 < 25  # ≈ 10 при линейном росте


# ----------------------------- Задание 4 ----------------------------------
class TestPyrsistent:
    """Задание 4: библиотека pyrsistent."""

    def test_config(self) -> None:
        """freeze/transform/thaw конфигурации."""
        cfg = freeze(pd.raw_config())
        new = pd.update_config(cfg)
        assert thaw(cfg) == pd.raw_config()
        assert new["db"]["port"] == 6543
        assert [s["replicas"] for s in new["services"]] == [4, 2]

    def test_evolver_equals_set(self) -> None:
        """Evolver даёт тот же результат, что и set."""
        v = pvector(range(2000))
        assert pd.batch_with_set(v, 1000) == pd.batch_with_evolver(v, 1000)
        assert list(v) == list(range(2000))

    def test_student_invariants(self) -> None:
        """Инварианты PRecord «Студент»."""
        s = pd.Student(name="A", course=1, gpa=3.0)
        assert s.set(course=2).course == 2 and s.course == 1
        with pytest.raises(InvariantException):
            pd.Student(name="A", course=5, gpa=3.0)
        with pytest.raises(InvariantException):
            pd.Student(name=" ", course=1, gpa=3.0)

    def test_graph(self) -> None:
        """Неизменяемый граф и BFS."""
        g = pd.graph_from_edges([("A", "B"), ("B", "C"), ("A", "D")])
        g2 = pd.add_edge(g, "C", "E")
        assert pd.bfs(g, "A") == ("A", "B", "D", "C")
        assert pd.bfs(g2, "A")[-1] == "E" and "E" not in g


# ----------------------------- Задание 5 ----------------------------------
class TestMonads:
    """Задание 5: монадические контейнеры."""

    @pytest.mark.parametrize(
        "unit,funcs",
        [
            (
                m.Maybe.unit,
                (lambda x: m.safe_div(1, x), lambda x: m.Maybe.unit(x + 1)),
            ),
            (
                m.ListM.unit,
                (lambda x: m.ListM((x, x + 1)), lambda x: m.ListM()),
            ),
            (
                m.Writer.unit,
                (
                    lambda x: m.Writer(x * 2, ("×2",)),
                    lambda x: m.Writer(x - 1, ("-1",)),
                ),
            ),
        ],
    )
    def test_laws(
        self, unit: Callable[[Any], Any], funcs: tuple[Callable[..., Any], ...]
    ) -> None:
        """Законы монады и функтора для трёх контейнеров."""
        assert all(m.check_laws(unit, (0, 1, 3), funcs).values())

    def test_broken_monad_detected(self) -> None:
        """check_laws находит нарушение законов."""

        class Bad(m.Writer):
            def bind(self, f: Callable[[Any], m.Writer]) -> m.Writer:
                w = f(self.value)
                return m.Writer(w.value, w.log + self.log)  # обратный порядок

        laws = m.check_laws(
            lambda x: Bad(x, ("u",)), (1,), (lambda x: m.Writer(x, ("f",)),)
        )
        assert not all(laws.values())

    def test_triples(self) -> None:
        """Пифагоровы тройки через bind."""
        assert m.pythagorean_triples(20) == (
            (3, 4, 5),
            (5, 12, 13),
            (6, 8, 10),
            (8, 15, 17),
            (9, 12, 15),
            (12, 16, 20),
        )

    def test_factorial_writer(self) -> None:
        """Факториал с журналом Writer."""
        w = m.factorial_w(5)
        assert w.value == 120 and len(w.log) == 5
        assert w.log[-1] == "5! = 5 × 24 = 120"


# ----------------------------- Задание 6 ----------------------------------
class TestTextBuffer:
    """Задание 6: текстовый буфер (вариант 4)."""

    def test_ops(self) -> None:
        """Операции редактирования документа."""
        doc = tb.from_text("abc\ndef")
        assert tb.to_text(tb.insert_text(0, 1, "X")(doc)) == "aXbc\ndef"
        assert tb.to_text(tb.delete_text(1, 0, 2)(doc)) == "abc\nf"
        assert tb.to_text(tb.split_line(0, 1)(doc)) == "a\nbc\ndef"
        assert tb.to_text(tb.join_lines(0)(doc)) == "abcdef"
        assert tb.to_text(tb.insert_line(2, "z")(doc)) == "abc\ndef\nz"
        assert tb.to_text(tb.delete_line(0)(doc)) == "def"
        assert tb.to_text(tb.replace_all("e", "E")(doc)) == "abc\ndEf"

    def test_split_join_inverse(self) -> None:
        """split_line и join_lines взаимно обратны."""
        doc = tb.from_text("hello world\nx")
        assert tb.join_lines(0)(tb.split_line(0, 5)(doc)) == doc

    def test_bounds(self) -> None:
        """Проверка границ строк и столбцов."""
        doc = tb.from_text("abc")
        for op in (
            tb.set_line(1, ""),
            tb.insert_text(0, 4, "x"),
            tb.join_lines(0),
            tb.insert_line(5),
        ):
            with pytest.raises(IndexError):
                op(doc)
        assert tb.to_text(tb.delete_line(0)(doc)) == ""

    def test_undo_redo(self) -> None:
        """undo/redo и очистка redo после новой правки."""
        ed = tb.Editor.open("a")
        ed1 = ed.apply("1", tb.insert_text(0, 1, "b"))
        ed2 = ed1.apply("2", tb.insert_text(0, 2, "c"))
        assert ed2.text == "abc"
        assert ed2.undo().text == "ab" and ed2.undo().undo().text == "a"
        assert ed2.undo().undo().undo().text == "a"  # нечего отменять
        assert ed2.undo().undo().redo().redo().text == "abc"
        branch = ed2.undo().apply("3", tb.insert_text(0, 0, ">"))
        assert branch.text == ">ab" and not branch.can_redo()
        assert ed2.redo() is ed2

    def test_old_versions_and_history(self) -> None:
        """Старые версии не меняются, история полная."""
        rng = random.Random(1)
        ed = tb.Editor.open("\n".join(f"line {i}" for i in range(50)))
        snapshots = [(ed, tb.to_text(ed.present))]
        for i in range(200):
            row = rng.randrange(len(ed.present))
            op = rng.choice(
                (
                    tb.set_line(row, f"edit {i}"),
                    tb.insert_text(row, 0, "#"),
                    tb.insert_line(row, "new"),
                )
            )
            ed = ed.apply(str(i), op)
            if i % 3 == 0:
                ed = ed.undo()
            snapshots.append((ed, tb.to_text(ed.present)))
        for state, text in snapshots:
            assert tb.to_text(state.present) == text
        assert len(ed.history) == 1 + 200 + 67
        assert tb.to_text(ed.history[0].lines).startswith("line 0\n")

    def test_structural_sharing(self) -> None:
        """Новые версии разделяют неизменённые части."""
        doc = pvector(f"l{i}" for i in range(5000))
        new = tb.set_line(10, "x")(doc)
        assert new[4999] is doc[4999] and doc[10] == "l10"


# ------------------------- Дополнительное задание -------------------------
class TestZipper:
    """Дополнительное задание: zipper."""

    def test_local_change(self) -> None:
        """Локальное изменение создаёт глубина + 1 узлов."""
        tree = tz.build_complete(4)
        before = tz.to_tuple(tree)
        z = tz.Zipper.of(tree).down_right().down_left().down_right()
        f = z.focus
        new = z.replace(tz.Node(-f.value, f.left, f.right)).root()
        assert tz.to_tuple(tree) == before
        old_ids = {id(n) for n in tz.nodes(tree)}
        created = [n for n in tz.nodes(new) if id(n) not in old_ids]
        assert len(created) == z.depth + 1
        assert new.left is tree.left

    def test_navigation(self) -> None:
        """Перемещение по дереву и ошибка подъёма из корня."""
        tree = tz.build_complete(2)
        z = tz.Zipper.of(tree).down_left().up()
        assert z.root() == tree
        with pytest.raises(ValueError):
            tz.Zipper.of(tree).up()
