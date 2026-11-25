"""Дополнительное задание. Реактивное рисование мышью в tkinter.

События мыши превращаются в субъекты (``mouse_down``, ``mouse_move``,
``mouse_up``). Чистый компонент ``strokes`` описывает жест:

    mouse_down → flat_map(mouse_move … take_until(mouse_up))

и выдаёт отрезки ``((x1, y1), (x2, y2))`` — только пока кнопка нажата.
Интерфейс обновляется *только* в подписчике (рисование линии на холсте).
Компонент тестируется на TestScheduler без графического окна; окно
запускается, если в установке Python есть Tk.
"""

from __future__ import annotations

from typing import Any

import reactivex as rx
from reactivex import Observable
from reactivex import operators as ops
from reactivex.subject import Subject

Point = tuple[int, int]


def strokes(
    mouse_down: Observable, mouse_move: Observable, mouse_up: Observable
) -> Observable:
    """Отрезки линии, рисуемые перетаскиванием мыши."""
    return mouse_down.pipe(
        ops.flat_map(
            lambda start: mouse_move.pipe(
                ops.take_until(mouse_up),
                ops.start_with(start),
                ops.pairwise(),
            )
        ),
    )


def stroke_lengths(segments: Observable) -> Observable:
    """Накопленная длина нарисованных линий (для строки состояния)."""
    return segments.pipe(
        ops.map(
            lambda s: (
                ((s[1][0] - s[0][0]) ** 2 + (s[1][1] - s[0][1]) ** 2) ** 0.5
            )
        ),
        ops.scan(lambda acc, d: acc + d, 0.0),
        ops.map(lambda total: f"длина линий: {total:.0f} px"),
    )


def run_gui() -> None:
    """Оболочка: окно tkinter, события → Subject, отрисовка в подписчике."""
    import tkinter as tk

    root = tk.Tk()
    root.title("ФП: реактивное рисование")
    canvas = tk.Canvas(root, width=640, height=420, bg="white")
    canvas.pack(fill="both", expand=True)
    status = tk.Label(root, text="зажмите кнопку мыши и рисуйте")
    status.pack(fill="x")

    down, move, up = Subject(), Subject(), Subject()

    def point(e: Any) -> Point:
        return (e.x, e.y)

    canvas.bind("<ButtonPress-1>", lambda e: down.on_next(point(e)))
    canvas.bind("<B1-Motion>", lambda e: move.on_next(point(e)))
    canvas.bind("<ButtonRelease-1>", lambda e: up.on_next(point(e)))

    segments = strokes(down, move, up).pipe(ops.share())
    subs = [
        segments.subscribe(
            lambda s: canvas.create_line(
                *s[0], *s[1], width=3, fill="#1f6feb", capstyle="round"
            )
        ),
        stroke_lengths(segments).subscribe(
            lambda text: status.config(text=text)
        ),
    ]
    root.protocol(
        "WM_DELETE_WINDOW",
        lambda: ([s.dispose() for s in subs], root.destroy()),
    )
    root.mainloop()


if __name__ == "__main__":
    try:
        run_gui()
    except ImportError:
        print(
            "tkinter недоступен в этой установке Python. Демонстрация "
            "логики без окна:"
        )
        d, m, u = Subject(), Subject(), Subject()
        strokes(d, m, u).subscribe(lambda s: print("  отрезок", s))
        m.on_next((0, 0))  # движение без нажатия — нет
        d.on_next((10, 10))
        m.on_next((20, 15))
        m.on_next((30, 30))
        u.on_next((30, 30))
        m.on_next((50, 50))  # после отпускания — нет
        print(
            "  итого:",
            rx.from_iterable([((0, 0), (3, 4))])
            .pipe(lambda s: stroke_lengths(s))
            .run(),
        )
