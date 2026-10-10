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

    def _backtrace(self, wave, target, moves):
        path = [target]
        r, c = target
        while wave[r][c] > 1:
            for dr, dc in moves:
                nr, nc = r + dr, c + dc
                if self.in_bounds(nr, nc) and wave[nr][nc] == wave[r][c] - 1:
                    r, c = nr, nc
                    path.append((r, c))
                    break
        path.reverse()
        return path

    def wave_generator(self, start, target, operator_name):
        moves = OPERATORS[operator_name]

        if not (self.in_bounds(*start) and self.in_bounds(*target)):
            yield {"error": "Start or target vertex is outside the maze"}
            return
        if self.grid[start[0]][start[1]] == WALL or self.grid[target[0]][target[1]] == WALL:
            yield {"error": "Start or target vertex is inside an impassable cell"}
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
                "front": list(front_cells),
                "path": path,
                "cycles": cycles,
                "expanded": expanded,
                "discovered": discovered,
                "algorithm": "wave",
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

    def run_to_end(self, operator_name):
        gen = self.wave_generator(self.start, self.target, operator_name)
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