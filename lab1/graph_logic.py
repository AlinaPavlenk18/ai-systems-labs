import networkx as nx
import random
from collections import deque

class GraphSearchLogic:
    def __init__(self):
        self.G = None
        self.pos = {}
        self.seed = None
        self.last_num_nodes = 0
        self.last_was_tree = False

    def _generate_min_branch_tree(self, num_nodes, rng, min_branches=5):
        nodes = list(range(num_nodes))
        root = 0
        remaining = nodes[1:]
        rng.shuffle(remaining)

        branch_heads = remaining[:min_branches]
        rest = remaining[min_branches:]

        G = nx.Graph()
        G.add_node(root)
        for node in branch_heads:
            G.add_edge(root, node)

        existing = [root] + branch_heads
        for node in rest:
            parent = rng.choice(existing)
            G.add_edge(parent, node)
            existing.append(node)

        return G, root

    def _tree_positions(self, G, root, width=10.0, height=8.0):
        levels = {}
        queue = deque([(root, 0)])
        visited = {root}
        levels[0] = [root]
        max_level = 0

        while queue:
            node, level = queue.popleft()
            max_level = max(max_level, level)
            for neighbor in G.neighbors(node):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, level + 1))
                    levels.setdefault(level + 1, []).append(neighbor)

        pos = {}
        for level, nodes_at_level in levels.items():
            n = len(nodes_at_level)
            y = height / 2 - (height * level / max(max_level, 1))
            for i, node in enumerate(nodes_at_level):
                x = (i + 0.5) * (width / n) - width / 2
                pos[node] = (x, y)
        return pos

    def generate_graph(self, num_nodes=35, is_directed=False, extra_edges=8,
                        seed=42, force_tree=False, min_branches=5, empty=False):
        self.seed = seed
        rng = random.Random(seed)

        if empty:
            self.G = nx.DiGraph() if is_directed else nx.Graph()
            self.pos = {}
            self.last_num_nodes = 0
            self.last_was_tree = False
            return self.G, self.pos

        if force_tree:
            skeleton_graph, tree_root = self._generate_min_branch_tree(num_nodes, rng, min_branches)
            extra_edges = 0  
        else:
            skeleton_graph = nx.random_labeled_tree(num_nodes, seed=seed)
            tree_root = None

        nodes = list(skeleton_graph.nodes())
        for _ in range(extra_edges):
            u, v = rng.sample(nodes, 2)
            if u != v:
                skeleton_graph.add_edge(u, v)

        if is_directed:
            self.G = nx.DiGraph()
            self.G.add_nodes_from(skeleton_graph.nodes())
            for u, v in skeleton_graph.edges():
                if rng.random() > 0.5:
                    self.G.add_edge(u, v)
                else:
                    self.G.add_edge(v, u)
        else:
            self.G = nx.Graph(skeleton_graph)

        undirected_skeleton = nx.Graph(self.G) if self.G.is_directed() else self.G

        if self.pos and num_nodes == self.last_num_nodes and force_tree == self.last_was_tree:
            pass 
        else:
            if nx.is_tree(undirected_skeleton):
                root = tree_root if tree_root is not None else max(
                    undirected_skeleton.nodes(), key=lambda n: undirected_skeleton.degree(n)
                )
                self.pos = self._tree_positions(undirected_skeleton, root=root)
            else:
                self.pos = nx.kamada_kawai_layout(undirected_skeleton)

        self.last_num_nodes = num_nodes
        self.last_was_tree = force_tree

        return self.G, self.pos

    def convert_to_directed(self):
        if self.G is None or self.G.is_directed():
            return False
        new_G = nx.DiGraph()
        new_G.add_nodes_from(self.G.nodes())
        for u, v in self.G.edges():
            new_G.add_edge(u, v)
            new_G.add_edge(v, u)
        self.G = new_G
        return True

    def convert_to_undirected(self):
        if self.G is None or not self.G.is_directed():
            return False
        self.G = nx.Graph(self.G)
        return True

    def add_custom_node(self, u):
        if self.G is not None and u not in self.G.nodes:
            self.G.add_node(u)
            if self.pos:
                xs = [p[0] for p in self.pos.values()]
                ys = [p[1] for p in self.pos.values()]
                offset_x = random.uniform(-0.5, 0.5)
                offset_y = random.uniform(-0.5, 0.5)
                self.pos[u] = (max(xs) + offset_x, min(ys) + offset_y)
            else:
                self.pos[u] = (0, 0)
            return True
        return False

    def remove_custom_node(self, u):
        if self.G is not None and u in self.G.nodes:
            self.G.remove_node(u)
            if u in self.pos:
                del self.pos[u]
            return True
        return False

    def add_custom_edge(self, u, v):
        if self.G is not None and u in self.G.nodes and v in self.G.nodes:
            self.G.add_edge(u, v)
            return True
        return False

    def remove_custom_edge(self, u, v):
        removed = False
        if self.G is not None:
            if self.G.has_edge(u, v):
                self.G.remove_edge(u, v)
                removed = True
            
            if self.G.is_directed() and self.G.has_edge(v, u):
                self.G.remove_edge(v, u)
                removed = True
                
        return removed

    def replace_edge_with_arc(self, u, v):
        if self.G is None:
            return False
        if not self.G.is_directed():
            if not self.G.has_edge(u, v):
                return False
            self.convert_to_directed()
        else:
            if not (self.G.has_edge(u, v) or self.G.has_edge(v, u)):
                return False
            if not self.G.has_edge(u, v):
                self.G.add_edge(u, v)
        if self.G.has_edge(v, u):
            self.G.remove_edge(v, u)
        return True

    def replace_arc_with_edge(self, u, v):
        if self.G is None or not self.G.is_directed():
            return False
        if not (self.G.has_edge(u, v) or self.G.has_edge(v, u)):
            return False
        self.G.add_edge(u, v)
        self.G.add_edge(v, u)
        return True

    def _neighbors_of(self, node):
        if self.G.is_directed():
            return list(self.G.successors(node))
        return list(self.G.neighbors(node))

    def bfs_generator(self, start, target, order='asc'):
        if start not in self.G or target not in self.G:
            yield {"error": "Vertices do not exist in the graph"}
            return

        queue = deque([(start, [start])])
        visited = {start}
        expanded_count = 0

        while queue:
            curr, path = queue.popleft()
            expanded_count += 1

            yield {
                "current": curr,
                "visited": visited.copy(),
                "discovered": len(visited),
                "path": path,
                "status": "visiting",
                "expanded": expanded_count,
                "algorithm": "bfs",
            }

            if curr == target:
                yield {
                    "current": curr,
                    "visited": visited.copy(),
                    "discovered": len(visited),
                    "path": path,
                    "status": "found",
                    "expanded": expanded_count,
                    "algorithm": "bfs",
                }
                return

            neighbors = self._neighbors_of(curr)
            
            if order == 'asc':
                neighbors.sort()
            else:
                neighbors.sort(reverse=True)

            for n in neighbors:
                if n not in visited:
                    visited.add(n)
                    queue.append((n, path + [n]))

        yield {
            "current": None,
            "visited": visited.copy(),
            "discovered": len(visited),
            "path": [],
            "status": "not_found",
            "expanded": expanded_count,
            "algorithm": "bfs",
        }