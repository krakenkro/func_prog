"""Задание 3: минимальные контрпримеры, найденные hypothesis.find."""

import statistics
import sys
from pathlib import Path

from hypothesis import find, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from fpkit.bugs import (  # noqa: E402
    chunks_buggy,
    median_buggy,
    rle_decode_buggy,
    rle_encode_buggy,
)

NO_DB = settings(database=None)

if __name__ == "__main__":
    xs = find(st.lists(st.integers(), min_size=1),
              lambda xs: median_buggy(xs) != statistics.median(xs),
              settings=NO_DB)
    print(f"median: эталон statistics.median, контрпример {xs}: "
          f"{median_buggy(xs)} вместо {statistics.median(xs)}")
    a = find(st.tuples(st.lists(st.integers()), st.integers(1, 10)),
             lambda a: sum(map(list, chunks_buggy(*a)), []) != a[0],
             settings=NO_DB)
    print(f"chunks: склейка частей == исходный список, контрпример "
          f"xs={a[0]}, n={a[1]}: {chunks_buggy(*a)}")
    s = find(st.text(), lambda s: rle_decode_buggy(rle_encode_buggy(s)) != s,
             settings=NO_DB)
    print(f"rle: обратимость, контрпример {s!r}: encode → "
          f"{rle_encode_buggy(s)!r}, decode → "
          f"{rle_decode_buggy(rle_encode_buggy(s))!r}")
    s2 = find(st.text(min_size=2), lambda s: s[0].isdigit() is False
              and rle_decode_buggy(rle_encode_buggy(s)) != s, settings=NO_DB)
    print(f"rle (без ведущей цифры): {s2!r} → "
          f"{rle_decode_buggy(rle_encode_buggy(s2))!r}")
