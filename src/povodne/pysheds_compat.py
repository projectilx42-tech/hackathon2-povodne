"""Keep pysheds 0.5 working with current NumPy and Numba (used for HAND and the flood path).

- NumPy >= 2.4 removed np.in1d, which pysheds still calls; np.isin is equivalent there.
- Numba >= 0.67 no longer compiles zip() over a generator, which pysheds' priority-flood depression filling
  (Grid.fill_depressions) uses: KeyError "int64 generator(func=<function count ...>)". The replacement below is the
  same algorithm (Barnes et al. 2014, priority-flood + epsilon-free pits queue) with plain counters instead of
  itertools-style count() generators; it gives identical output.
"""
from heapq import heapify, heappop, heappush

import numpy as np

_patched = False


def patch() -> None:
    """Apply both fixes once; safe to call repeatedly and with older library versions."""
    global _patched
    if _patched:
        return
    if not hasattr(np, "in1d"):
        np.in1d = np.isin
    import pysheds._sgrid as sg
    from numba import from_dtype, int64, njit
    from numba.types import Tuple
    from numba.typed import typedlist

    @njit(cache=False)
    def _pf(dem, dem_mask, tuple_type):
        open_cells = typedlist.List.empty_list(tuple_type)  # priority queue
        pits = typedlist.List.empty_list(tuple_type)  # FIFO queue
        closed_cells = dem_mask.copy()
        isertn = 0
        y, x = dem.shape

        edge = sg._left(dem_mask)[:-1]
        for k in range(len(edge)):
            row, col = k, edge[k]
            if col >= 0:
                open_cells.append((dem[row, col], isertn, row, col)); isertn += 1
                closed_cells[row, col] = True
        edge = sg._bottom(dem_mask)[:-1]
        for k in range(len(edge)):
            row, col = edge[k], k
            if row >= 0:
                open_cells.append((dem[row, col], isertn, row, col)); isertn += 1
                closed_cells[row, col] = True
        edge = np.flip(sg._right(dem_mask))[:-1]
        for k in range(len(edge)):
            row, col = y - 1 - k, edge[k]
            if col >= 0:
                open_cells.append((dem[row, col], isertn, row, col)); isertn += 1
                closed_cells[row, col] = True
        edge = np.flip(sg._top(dem_mask))[:-1]
        for k in range(len(edge)):
            row, col = edge[k], x - 1 - k
            if row >= 0:
                open_cells.append((dem[row, col], isertn, row, col)); isertn += 1
                closed_cells[row, col] = True
        heapify(open_cells)

        row_offsets = np.array([-1, -1, 0, 1, 1, 1, 0, -1])
        col_offsets = np.array([0, 1, 1, 1, 0, -1, -1, -1])
        pits_pos = 0
        while open_cells or pits_pos < len(pits):
            if pits_pos < len(pits):
                elv, _, i, j = pits[pits_pos]
                pits_pos += 1
            else:
                elv, _, i, j = heappop(open_cells)
            for n in range(8):
                row = i + row_offsets[n]
                col = j + col_offsets[n]
                if row < 0 or row >= y or col < 0 or col >= x:
                    continue
                if dem_mask[row, col] or closed_cells[row, col]:
                    continue
                if dem[row, col] <= elv:
                    dem[row, col] = elv
                    pits.append((elv, isertn, row, col)); isertn += 1
                else:
                    heappush(open_cells, (dem[row, col], isertn, row, col)); isertn += 1
                closed_cells[row, col] = True
            if pits_pos == len(pits) and len(pits) > 1024:  # queue is empty, clear it out
                pits.clear()
                pits_pos = 0
        return dem

    def _priority_flood(dem, mask, *args):
        tuple_type = Tuple([from_dtype(dem.dtype), int64, int64, int64])
        return _pf(dem, mask, tuple_type, *args)

    sg._priority_flood = _priority_flood  # sgrid.Grid.fill_depressions looks it up on the module at call time
    _patched = True
