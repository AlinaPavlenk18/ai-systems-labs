import heapq
import json
import time
from collections import deque

import networkx as nx

# Cities of Ukraine: name -> (longitude, latitude), used as drawing positions
CITIES = {
    "Київ": (30.52, 50.45),
    "Житомир": (28.66, 50.25),
    "Вінниця": (28.47, 49.23),
    "Хмельницький": (26.99, 49.42),
    "Тернопіль": (25.59, 49.55),
    "Львів": (24.03, 49.84),
    "Луцьк": (25.33, 50.75),
    "Рівне": (26.25, 50.62),
    "Ужгород": (22.29, 48.62),
    "Івано-Франківськ": (24.71, 48.92),
    "Чернівці": (25.94, 48.29),
    "Чернігів": (31.29, 51.50),
    "Суми": (34.80, 50.91),
    "Харків": (36.23, 49.99),
    "Полтава": (34.55, 49.59),
    "Черкаси": (32.06, 49.44),
    "Кропивницький": (32.26, 48.51),
    "Дніпро": (35.05, 48.46),
    "Запоріжжя": (35.14, 47.84),
    "Донецьк": (37.80, 48.00),
    "Луганськ": (39.31, 48.57),
    "Миколаїв": (31.99, 46.97),
    "Одеса": (30.73, 46.48),
    "Херсон": (32.62, 46.64),
    "Сімферополь": (34.10, 44.95),
    "Кривий Ріг": (33.39, 47.91),
    "Маріуполь": (37.54, 47.10),
    "Мелітополь": (35.37, 46.85),
    "Севастополь": (33.52, 44.60),
}

# Distances between cities, km, two-way roads
ROADS = [
    ("Вінниця", "Житомир", 127), ("Вінниця", "Київ", 267), ("Вінниця", "Кропивницький", 320),
    ("Вінниця", "Миколаїв", 428), ("Вінниця", "Одеса", 423), ("Вінниця", "Черкаси", 341),
    ("Вінниця", "Чернівці", 276), ("Дніпро", "Донецьк", 248), ("Дніпро", "Запоріжжя", 85),
    ("Дніпро", "Кропивницький", 244), ("Дніпро", "Кривий Ріг", 146), ("Дніпро", "Полтава", 160),
    ("Дніпро", "Харків", 218), ("Донецьк", "Луганськ", 156), ("Донецьк", "Маріуполь", 113),
    ("Донецьк", "Харків", 294), ("Запоріжжя", "Мелітополь", 125),
    ("Івано-Франківськ", "Тернопіль", 133), ("Івано-Франківськ", "Ужгород", 293),
    ("Київ", "Житомир", 140), ("Київ", "Полтава", 340), ("Київ", "Суми", 333),
    ("Київ", "Черкаси", 189), ("Київ", "Чернігів", 148), ("Кропивницький", "Полтава", 246),
    ("Луганськ", "Харків", 325), ("Львів", "Івано-Франківськ", 134), ("Львів", "Луцьк", 151),
    ("Львів", "Рівне", 211), ("Львів", "Тернопіль", 127), ("Львів", "Ужгород", 268),
    ("Львів", "Чернівці", 268), ("Мелітополь", "Маріуполь", 192),
    ("Мелітополь", "Сімферополь", 250), ("Миколаїв", "Херсон", 69), ("Рівне", "Житомир", 188),
    ("Рівне", "Луцьк", 73), ("Рівне", "Тернопіль", 155), ("Харків", "Полтава", 143),
    ("Херсон", "Мелітополь", 231), ("Хмельницький", "Вінниця", 119),
    ("Хмельницький", "Житомир", 183), ("Хмельницький", "Рівне", 194),
    ("Хмельницький", "Тернопіль", 112), ("Хмельницький", "Чернівці", 187),
    ("Суми", "Харків", 184), ("Черкаси", "Полтава", 233), ("Полтава", "Суми", 175),
    ("Чернігів", "Суми", 306), ("Сімферополь", "Севастополь", 81),
]

ALGO_DIJKSTRA = "Dijkstra"
ALGO_BFS = "BFS (fewest roads)"
ALGORITHMS = [ALGO_DIJKSTRA, ALGO_BFS]

INF = float("inf")


class RoadGraphLogic:
    """Weighted road graph. Stored as a DiGraph: a two-way road is a pair of arcs."""

    def __init__(self):
        self.G = nx.DiGraph()
        self.pos = {}
        self.load_default_map()

    # graph construction 
    def load_default_map(self):
        self.G = nx.DiGraph()
        self.pos = {}
        for name, xy in CITIES.items():
            self.add_city(name, *xy)
        for u, v, km in ROADS:
            self.add_road(u, v, km)

    def clear(self):
        self.G = nx.DiGraph()
        self.pos = {}

    def add_city(self, name, x, y):
        name = name.strip()
        if not name or name in self.G:
            return False
        self.G.add_node(name)
        self.pos[name] = (float(x), float(y))
        return True

    def remove_city(self, name):
        if name not in self.G:
            return False
        self.G.remove_node(name)
        self.pos.pop(name, None)
        return True

    def add_road(self, u, v, weight, one_way=False):
        if u not in self.G or v not in self.G or u == v or weight <= 0:
            return False
        self.G.add_edge(u, v, weight=weight)
        if one_way:
            if self.G.has_edge(v, u):
                self.G.remove_edge(v, u)
        else:
            self.G.add_edge(v, u, weight=weight)
        return True

    def remove_road(self, u, v, one_way=False):
        removed = False
        if self.G.has_edge(u, v):
            self.G.remove_edge(u, v)
            removed = True
        if not one_way and self.G.has_edge(v, u):
            self.G.remove_edge(v, u)
            removed = True
        return removed

    def roads(self):
        result, seen = [], set()
        for u, v, d in self.G.edges(data=True):
            key = frozenset((u, v))
            if key in seen:
                continue
            seen.add(key)
            two_way = self.G.has_edge(v, u) and self.G[v][u]["weight"] == d["weight"]
            if two_way:
                result.append((u, v, d["weight"], True))
            else:
                result.append((u, v, d["weight"], False))
                if self.G.has_edge(v, u):
                    result.append((v, u, self.G[v][u]["weight"], False))
        return result

    def order(self):
        return self.G.number_of_nodes()

    def size(self):
        return len(self.roads())

    def save_json(self, filename):
        data = {
            "cities": {n: list(self.pos[n]) for n in self.G.nodes},
            "arcs": [[u, v, d["weight"]] for u, v, d in self.G.edges(data=True)],
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)

    def load_json(self, filename):
        with open(filename, encoding="utf-8") as f:
            data = json.load(f)
        self.clear()
        for name, (x, y) in data["cities"].items():
            self.add_city(name, x, y)
        for u, v, w in data["arcs"]:
            if u in self.G and v in self.G:
                self.G.add_edge(u, v, weight=w)

    # search 
    @staticmethod
    def _restore_path(prev, target):
        path = [target]
        while prev.get(path[-1]) is not None:
            path.append(prev[path[-1]])
        path.reverse()
        return path

    def path_length(self, path):
        return sum(self.G[a][b]["weight"] for a, b in zip(path, path[1:]))

    def _check_endpoints(self, start, target):
        if start not in self.G or target not in self.G:
            return "Start or target city does not exist in the graph"
        return None

    def search_generator(self, start, target, algorithm=ALGO_DIJKSTRA):
        if algorithm == ALGO_DIJKSTRA:
            return self._dijkstra_generator(start, target)
        if algorithm == ALGO_BFS:
            return self._bfs_generator(start, target)
        raise ValueError(f"Unknown algorithm: {algorithm}")

    def _dijkstra_generator(self, start, target):
        error = self._check_endpoints(start, target)
        if error:
            yield {"error": error}
            return

        dist = {n: INF for n in self.G.nodes}
        prev = {n: None for n in self.G.nodes}
        dist[start] = 0
        heap = [(0, start)]
        settled = []          # vertices with permanent labels, in order
        settled_set = set()
        cycles = relaxations = improvements = 0

        def snapshot(status, current, relaxed, path):
            frontier = [n for n in self.G.nodes if dist[n] < INF and n not in settled_set]
            return {
                "status": status,
                "algorithm": ALGO_DIJKSTRA,
                "current": current,
                "dist": dict(dist),
                "prev": dict(prev),
                "settled": list(settled),
                "frontier": frontier,
                "relaxed": relaxed,
                "path": path,
                "distance": dist[target] if status == "found" else None,
                "cycles": cycles,
                "expanded": len(settled),
                "relaxations": relaxations,
                "improvements": improvements,
                "queue_size": len(heap),
            }

        yield snapshot("running", None, [], [])

        while heap:
            d, u = heapq.heappop(heap)
            if u in settled_set or d > dist[u]:
                continue                     
            cycles += 1
            settled.append(u)
            settled_set.add(u)

            if u == target:
                path = self._restore_path(prev, target)
                yield snapshot("found", u, [], path)
                return

            relaxed = []                
            for v in sorted(self.G.successors(u)):
                if v in settled_set:
                    continue
                relaxations += 1
                new = d + self.G[u][v]["weight"]
                old = dist[v]
                improved = new < old
                if improved:
                    improvements += 1
                    dist[v] = new
                    prev[v] = u
                    heapq.heappush(heap, (new, v))
                relaxed.append((u, v, old, new, improved))

            yield snapshot("running", u, relaxed, self._restore_path(prev, u))

        yield snapshot("not_found", None, [], [])

    def _bfs_generator(self, start, target):
        """Plain breadth-first search (ignores weights) - for comparison with Dijkstra."""
        error = self._check_endpoints(start, target)
        if error:
            yield {"error": error}
            return

        dist = {n: INF for n in self.G.nodes}     # accumulated km along the BFS tree
        prev = {n: None for n in self.G.nodes}
        dist[start] = 0
        queue = deque([start])
        discovered = {start}
        settled = []
        cycles = relaxations = 0

        def snapshot(status, current, relaxed, path):
            return {
                "status": status,
                "algorithm": ALGO_BFS,
                "current": current,
                "dist": dict(dist),
                "prev": dict(prev),
                "settled": list(settled),
                "frontier": list(queue),
                "relaxed": relaxed,
                "path": path,
                "distance": self.path_length(path) if status == "found" else None,
                "cycles": cycles,
                "expanded": len(settled),
                "relaxations": relaxations,
                "improvements": len(discovered) - 1,
                "queue_size": len(queue),
            }

        yield snapshot("running", None, [], [])

        if start == target:
            settled.append(start)
            yield snapshot("found", start, [], [start])
            return

        while queue:
            u = queue.popleft()
            cycles += 1
            settled.append(u)
            relaxed = []
            for v in sorted(self.G.successors(u)):
                relaxations += 1
                if v in discovered:
                    continue
                discovered.add(v)
                prev[v] = u
                dist[v] = dist[u] + self.G[u][v]["weight"]
                queue.append(v)
                relaxed.append((u, v, INF, dist[v], True))
                if v == target:                    
                    path = self._restore_path(prev, target)
                    yield snapshot("found", v, relaxed, path)
                    return
            yield snapshot("running", u, relaxed, self._restore_path(prev, u))

        yield snapshot("not_found", None, [], [])

    def run_to_end(self, start, target, algorithm=ALGO_DIJKSTRA):
        gen = self.search_generator(start, target, algorithm)
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
