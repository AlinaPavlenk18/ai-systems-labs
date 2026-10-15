import random
import time

OPERATORS = {
    "Up-Down-Right-Left": [(-1, 0), (1, 0), (0, 1), (0, -1)],
    "Diagonals": [(-1, -1), (-1, 1), (1, 1), (1, -1)],
    "Combined (8 directions)": [
        (-1, 0), (1, 0), (0, 1), (0, -1),
        (-1, -1), (-1, 1), (1, 1), (1, -1),
    ],
}

ALGO_UNI = "Unidirectional"
ALGO_BI = "Bidirectional"
ALGORITHMS = [ALGO_UNI, ALGO_BI]

WALL = -1
FREE = 0


class WaveSearchLogic:
    def __init__(self):
        self.rows = 15
        self.cols = 15
        self.grid = []
        self.start = (0, 0)
        self.target = (0, 0)
        self.seed = 42

    def generate_grid(self, rows=15, cols=15, wall_percent=25, seed=42):
        self.rows = rows
        self.cols = cols
        self.seed = seed
        self.start = (0, 0)
        self.target = (rows - 1, cols - 1)

        candidates = [
            (random.Random(f"{seed}:{r}:{c}").random(), r, c)
            for r in range(rows) for c in range(cols)
            if (r, c) not in (self.start, self.target)
        ]
        candidates.sort()
        total = rows * cols
        n_walls = min(round(wall_percent / 100 * total), len(candidates))

        self.grid = [[FREE] * cols for _ in range(rows)]
        for _, r, c in candidates[:n_walls]:
            self.grid[r][c] = WALL
        return self.grid

    def clear_walls(self):
        self.grid = [[FREE] * self.cols for _ in range(self.rows)]

    def in_bounds(self, r, c):
        return 0 <= r < self.rows and 0 <= c < self.cols

    def toggle_wall(self, r, c):
        if not self.in_bounds(r, c) or (r, c) in (self.start, self.target):
            return False
        self.grid[r][c] = FREE if self.grid[r][c] == WALL else WALL
        return True

    def set_start(self, r, c):
        if not self.in_bounds(r, c) or (r, c) == self.target:
            return False
        self.grid[r][c] = FREE
        self.start = (r, c)
        return True

    def set_target(self, r, c):
        if not self.in_bounds(r, c) or (r, c) == self.start:
            return False
        self.grid[r][c] = FREE
        self.target = (r, c)
        return True

    def wall_ratio(self):
        total = self.rows * self.cols
        walls = sum(row.count(WALL) for row in self.grid)
        return walls / total * 100 if total else 0

    def _backtrace(self, wave, cell, moves):
        """Path from the wave source (value 1) to `cell`, following values downward."""
        path = [cell]
        r, c = cell
        while wave[r][c] > 1:
            for dr, dc in moves:
                nr, nc = r + dr, c + dc
                if self.in_bounds(nr, nc) and wave[nr][nc] == wave[r][c] - 1:
                    r, c = nr, nc
                    path.append((r, c))
                    break
        path.reverse()
        return path

    def _check_endpoints(self, start, target):
        if not (self.in_bounds(*start) and self.in_bounds(*target)):
            return "Start or target vertex is outside the maze"
        if self.grid[start[0]][start[1]] == WALL or self.grid[target[0]][target[1]] == WALL:
            return "Start or target vertex is inside an impassable cell"
        return None

    def wave_generator(self, start, target, operator_name, algorithm=ALGO_UNI):
        if algorithm == ALGO_UNI:
            return self._unidirectional_generator(start, target, operator_name)
        if algorithm == ALGO_BI:
            return self._bidirectional_generator(start, target, operator_name)
        raise ValueError(f"Unknown algorithm: {algorithm}")

    def _unidirectional_generator(self, start, target, operator_name):
        moves = OPERATORS[operator_name]

        error = self._check_endpoints(start, target)
        if error:
            yield {"error": error}
            return

        wave = [row[:] for row in self.grid]
        wave[start[0]][start[1]] = 1

        front = [start]
        cycles = 0
        expanded = 0
        discovered = 1

        def snapshot(status, path, front_cells):
            return {
                "status": status,
                "wave": [row[:] for row in wave],
                "wave_b": None,
                "front": list(front_cells),
                "front_a": list(front_cells),
                "front_b": [],
                "meeting": None,
                "path": path,
                "cycles": cycles,
                "expanded": expanded,
                "discovered": discovered,
                "algorithm": ALGO_UNI,
                "operator": operator_name,
            }

        yield snapshot("running", [], front)

        if start == target:
            yield snapshot("found", [start], front)
            return

        while front:
            cycles += 1
            new_front = []
            for r, c in front:
                expanded += 1
                for dr, dc in moves:
                    nr, nc = r + dr, c + dc
                    if self.in_bounds(nr, nc) and wave[nr][nc] == FREE:
                        wave[nr][nc] = wave[r][c] + 1
                        discovered += 1
                        new_front.append((nr, nc))
                        if (nr, nc) == target:
                            path = self._backtrace(wave, target, moves)
                            yield snapshot("found", path, new_front)
                            return
            front = new_front
            yield snapshot("running", [], front)

        yield snapshot("not_found", [], [])

    def _bidirectional_generator(self, start, target, operator_name):
        moves = OPERATORS[operator_name]
        algo_name = ALGO_BI

        error = self._check_endpoints(start, target)
        if error:
            yield {"error": error}
            return

        wave_a = [row[:] for row in self.grid]
        wave_b = [row[:] for row in self.grid]
        wave_a[start[0]][start[1]] = 1
        wave_b[target[0]][target[1]] = 1

        front_a = [start]
        front_b = [target]
        cycles = 0
        expanded = 0
        discovered = 1 if start == target else 2
        meeting = None

        def snapshot(status, path):
            return {
                "status": status,
                "wave": [row[:] for row in wave_a],
                "wave_b": [row[:] for row in wave_b],
                "front": list(front_a) + list(front_b),
                "front_a": list(front_a),
                "front_b": list(front_b),
                "meeting": meeting,
                "path": path,
                "cycles": cycles,
                "expanded": expanded,
                "discovered": discovered,
                "algorithm": algo_name,
                "operator": operator_name,
            }

        def expand(own, other, front):
            """Expand one layer of wave `own`. Returns (new_front, best_meeting).
            best_meeting = (vertices_in_path, own_cell, other_cell) or None."""
            nonlocal expanded, discovered
            new_front = []
            best = None
            for r, c in front:
                expanded += 1
                for dr, dc in moves:
                    nr, nc = r + dr, c + dc
                    if not self.in_bounds(nr, nc):
                        continue
                    if other[nr][nc] > 0:
                        total = own[r][c] + other[nr][nc]
                        if best is None or total < best[0]:
                            best = (total, (r, c), (nr, nc))
                    elif own[nr][nc] == FREE:
                        own[nr][nc] = own[r][c] + 1
                        discovered += 1
                        new_front.append((nr, nc))
            for r, c in new_front:
                for dr, dc in moves:
                    nr, nc = r + dr, c + dc
                    if self.in_bounds(nr, nc) and other[nr][nc] > 0:
                        total = own[r][c] + other[nr][nc]
                        if best is None or total < best[0]:
                            best = (total, (r, c), (nr, nc))
            return new_front, best

        yield snapshot("running", [])

        if start == target:
            yield snapshot("found", [start])
            return

        while front_a and front_b:
            cycles += 1
            best = None  

            for side in ("A", "B"):
                if side == "A":
                    front_a, cand = expand(wave_a, wave_b, front_a)
                    if cand:
                        best = (cand[0], cand[1], cand[2])
                else:
                    front_b, cand = expand(wave_b, wave_a, front_b)
                    if cand:
                        best = (cand[0], cand[2], cand[1])
                if best:
                    break

            if best:
                _, cell_a, cell_b = best
                meeting = (cell_a, cell_b)
                path_a = self._backtrace(wave_a, cell_a, moves)          
                path_b = self._backtrace(wave_b, cell_b, moves)[::-1]     
                yield snapshot("found", path_a + path_b)
                return

            yield snapshot("running", [])

        yield snapshot("not_found", [])

    def run_to_end(self, operator_name, algorithm=ALGO_UNI):
        gen = self.wave_generator(self.start, self.target, operator_name, algorithm)
        elapsed = 0.0
        state = None
        while True:
            t0 = time.perf_counter()
            try:
                state = next(gen)
            except StopIteration:
                break
            elapsed += (time.perf_counter() - t0) * 1000
            if "error" in state or state["status"] in ("found", "not_found"):
                break
        return state, elapsed