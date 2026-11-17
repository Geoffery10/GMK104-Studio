"""GMK104 physical geometry, independently expressed in key units.

Matrix positions were checked against the wired manufacturer's definition and
live buffer reads. Esc is (0,0), correcting the duplicate (7,13) in that file.
The knob press is matrix (5,7); its rotation is separate from the key matrix.
"""
from dataclasses import dataclass

CONTROL_NAMES = {(5, 4): "Backlight button", (5, 6): "LCD button", (5, 7): "Knob press"}
KNOB_PRESS = (5, 7)


@dataclass(frozen=True)
class Key:
    row: int
    col: int
    x: float
    y: float
    width: float = 1
    height: float = 1


def physical_keys():
    keys = [Key(0, 0, 0, 0)]
    for start, columns in ((2, range(1, 5)), (6.5, range(5, 9)),
                           (11, range(9, 13)), (15.5, [13])):
        keys.extend(Key(0, col, start + i, 0) for i, col in enumerate(columns))
    keys.extend((Key(7, 0, 16.5, 0), Key(7, 1, 17.5, 0),
                 Key(5, 4, 19, 0, 1.1, .5), Key(5, 6, 19, .5, 1.1, .5),
                 Key(5, 7, 22, 0)))
    # Main typing block.
    rows = [
        [(1, c, 2 if c == 13 else 1) for c in range(14)],
        [(2, c, 1.5 if c in (0, 13) else 1) for c in range(14)],
        [(3, 0, 1.75)] + [(3, c, 1) for c in range(1, 12)] + [(3, 13, 2.25)],
        [(4, 0, 2.25)] + [(4, c, 1) for c in range(2, 12)] + [(4, 13, 2.75)],
        [(5, c, 1.25) for c in range(3)] + [(5, 5, 6.25)] +
        [(5, c, 1.25) for c in (9, 10, 11, 12)],
    ]
    for index, row in enumerate(rows):
        x = 0
        for matrix_row, col, width in row:
            keys.append(Key(matrix_row, col, x, index + 1.25, width))
            x += width
    # Navigation cluster and arrows.
    for y, columns in ((1.25, (2, 3, 6)), (2.25, (4, 5, 7))):
        keys.extend(Key(7, col, 15.5 + i, y) for i, col in enumerate(columns))
    keys.append(Key(7, 8, 16.5, 4.25))
    keys.extend((Key(5, 13, 15.5, 5.25), Key(7, 10, 16.5, 5.25),
                 Key(7, 11, 17.5, 5.25)))
    # Numpad; tall keys occupy their full two rows.
    for y, cols in ((1.25, (0, 1, 2, 3)), (2.25, (4, 5, 6)),
                    (3.25, (7, 8, 9))):
        keys.extend(Key(6, col, 19 + i, y) for i, col in enumerate(cols))
    keys.extend((Key(6, 10, 22, 2.25, 1, 2),
                 Key(7, 9, 19, 4.25), Key(6, 11, 20, 4.25),
                 Key(6, 12, 21, 4.25), Key(7, 13, 22, 4.25, 1, 2),
                 Key(6, 13, 19, 5.25, 2), Key(7, 12, 21, 5.25)))
    return tuple(keys)


KEYS = physical_keys()
