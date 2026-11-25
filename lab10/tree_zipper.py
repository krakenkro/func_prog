"""Дополнительное задание. Застёжка (zipper) для двоичного дерева.

Zipper хранит текущее поддерево (``focus``) и «контекст» — путь к корню
в виде персистентного стека «хлебных крошек». Каждая крошка помнит,
в какую сторону мы спустились, значение родителя и *другое* поддерево.

Спуск/подъём — O(1). Локальное изменение в глубине и сборка дерева
через ``root()`` создают ровно ``глубина + 1`` новых узлов; все поддеревья
вне пути разделяются с исходным деревом, которое остаётся неизменным.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from plist import NIL, PList, cons, is_empty, length


@dataclass(frozen=True)
class Node:
    """Узел неизменяемого двоичного дерева."""

    value: Any
    left: Node | None = None
    right: Node | None = None


@dataclass(frozen=True)
class Crumb:
    """Шаг пути: направление спуска, значение родителя, соседнее поддерево."""

    went_left: bool
    parent_value: Any
    sibling: Node | None


@dataclass(frozen=True)
class Zipper:
    """Фокус на поддереве + путь к корню."""

    focus: Node | None
    path: PList = NIL  # PList[Crumb]

    @staticmethod
    def of(tree: Node) -> Zipper:
        """Застёжка с фокусом на корне."""
        return Zipper(tree, NIL)

    @property
    def depth(self) -> int:
        """Глубина фокуса."""
        return length(self.path)

    def _require_focus(self) -> Node:
        """Текущий узел (ошибка, если фокус на пустом месте)."""
        if self.focus is None:
            raise ValueError("фокус на пустом поддереве")
        return self.focus

    def down_left(self) -> Zipper:
        """Спуститься в левое поддерево."""
        n = self._require_focus()
        return Zipper(n.left, cons(Crumb(True, n.value, n.right), self.path))

    def down_right(self) -> Zipper:
        """Спуститься в правое поддерево."""
        n = self._require_focus()
        return Zipper(n.right, cons(Crumb(False, n.value, n.left), self.path))

    def up(self) -> Zipper:
        """Подняться к родителю, собрав его узел из крошки."""
        if is_empty(self.path):
            raise ValueError("уже в корне")
        c: Crumb = self.path.head
        parent = (
            Node(c.parent_value, self.focus, c.sibling)
            if c.went_left
            else Node(c.parent_value, c.sibling, self.focus)
        )
        return Zipper(parent, self.path.tail)

    def replace(self, node: Node | None) -> Zipper:
        """Заменить поддерево в фокусе."""
        return Zipper(node, self.path)

    def root(self) -> Node | None:
        """Подняться до корня и вернуть (новое) дерево."""
        z = self
        while not is_empty(z.path):
            z = z.up()
        return z.focus


def nodes(tree: Node | None) -> Iterator[Node]:
    """Все узлы дерева (прямой обход)."""
    if tree is not None:
        yield tree
        yield from nodes(tree.left)
        yield from nodes(tree.right)


def build_complete(depth: int, start: int = 1) -> Node | None:
    """Полное двоичное дерево заданной глубины с нумерацией как в куче."""
    if depth < 0:
        return None
    return Node(
        start,
        build_complete(depth - 1, 2 * start),
        build_complete(depth - 1, 2 * start + 1),
    )


def to_tuple(tree: Node | None) -> Any:
    """Компактное представление дерева для печати/сравнения."""
    if tree is None:
        return None
    if tree.left is None and tree.right is None:
        return tree.value
    return (tree.value, to_tuple(tree.left), to_tuple(tree.right))


if __name__ == "__main__":
    tree = build_complete(3)
    assert tree is not None
    before = to_tuple(tree)
    z = Zipper.of(tree).down_left().down_right().down_left()
    print("фокус:", z.focus.value if z.focus else None, "глубина:", z.depth)
    old = z.focus
    assert old is not None
    new_tree = z.replace(Node(old.value * 100, old.left, old.right)).root()

    print("исходное:", before)
    print("новое:   ", to_tuple(new_tree))
    print("исходное дерево не изменилось:", to_tuple(tree) == before)
    old_ids = {id(n) for n in nodes(tree)}
    created = [n for n in nodes(new_tree) if id(n) not in old_ids]
    print(
        f"новых узлов: {len(created)} (глубина + 1 = {z.depth + 1}) из "
        f"{sum(1 for _ in nodes(new_tree))}"
    )
    print(
        "правое поддерево корня разделяется:",
        new_tree is not None and new_tree.right is tree.right,
    )
