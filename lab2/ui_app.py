import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import networkx as nx
import csv
import time
import os
from datetime import datetime

from graph_logic import GraphSearchLogic


def safe_get_int(var, field_name):
    try:
        return var.get()
    except (ValueError, tk.TclError):
        messagebox.showerror("Error", f"Invalid value in field: {field_name}")
        return None


class DFSApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DFS Visualization (Blind Search)")
        self.geometry("1150x750")

        self.logic = GraphSearchLogic()
        self.search_generator = None
        self.current_state = None
        self.algo_elapsed_ms = 0.0

        self.active_start = None
        self.active_target = None
        self.active_order = None
        self.active_algorithm = None  # "dfs" or "iddfs"

        self._build_ui()
        self.generate_new_graph()

    def _build_ui(self):
        outer_frame = ttk.Frame(self, width=340)
        outer_frame.pack(side=tk.LEFT, fill=tk.Y)
        outer_frame.pack_propagate(False)

        canvas_scroll = tk.Canvas(outer_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer_frame, orient="vertical", command=canvas_scroll.yview)
        control_frame = ttk.Frame(canvas_scroll, padding=(10, 6))

        control_frame.bind(
            "<Configure>",
            lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        )
        canvas_scroll.create_window((0, 0), window=control_frame, anchor="nw", width=320)
        canvas_scroll.configure(yscrollcommand=scrollbar.set)

        canvas_scroll.pack(side=tk.LEFT, fill=tk.Y, expand=True)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas_scroll.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas_scroll.bind_all("<MouseWheel>", _on_mousewheel)

        HEADER_FONT = ("Arial", 10, "bold")
        PADY_FIELD = 1
        PADY_SECTION = (8, 3)

        def add_row(parent, label_text, widget_var, widget_cls=ttk.Entry, **widget_kwargs):
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=PADY_FIELD)
            ttk.Label(row, text=label_text, width=16, anchor=tk.W).pack(side=tk.LEFT)
            widget = widget_cls(row, textvariable=widget_var, **widget_kwargs)
            widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
            return widget

        ttk.Label(control_frame, text="Graph settings", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)

        self.nodes_var = tk.IntVar(value=35)
        add_row(control_frame, "Vertices (>=30):", self.nodes_var)

        self.graph_type_var = tk.StringVar(value="Undirected graph")
        add_row(
            control_frame, "Graph type:", self.graph_type_var,
            widget_cls=ttk.Combobox,
            values=["Undirected graph", "Directed graph", "Tree"],
            state="readonly"
        )

        ttk.Button(control_frame, text="Generate graph", command=self.generate_new_graph).pack(fill=tk.X, pady=(4, 2))
        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Editing individual edges/arcs
        ttk.Label(control_frame, text="Edit edges/arcs", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)

        edge_row = ttk.Frame(control_frame)
        edge_row.pack(fill=tk.X, pady=PADY_FIELD)
        ttk.Label(edge_row, text="From:").pack(side=tk.LEFT)
        self.edge_u_var = tk.StringVar()
        ttk.Entry(edge_row, textvariable=self.edge_u_var, width=6).pack(side=tk.LEFT, padx=(2, 10))
        ttk.Label(edge_row, text="To:").pack(side=tk.LEFT)
        self.edge_v_var = tk.StringVar()
        ttk.Entry(edge_row, textvariable=self.edge_v_var, width=6).pack(side=tk.LEFT, padx=2)

        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X, pady=(4, 2))
        ttk.Button(btn_frame, text="Add", command=self.add_edge_ui).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(btn_frame, text="Remove", command=self.remove_edge_ui).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        btn_frame2 = ttk.Frame(control_frame)
        btn_frame2.pack(fill=tk.X, pady=(2, 2))
        ttk.Button(btn_frame2, text="-> Arc", command=self.replace_with_arc_ui).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(btn_frame2, text="<-> Edge", command=self.replace_with_edge_ui).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Search parameters
        ttk.Label(control_frame, text="DFS parameters", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)

        self.start_var = tk.IntVar(value=0)
        add_row(control_frame, "Start:", self.start_var)

        self.target_var = tk.IntVar(value=1)
        add_row(control_frame, "Target:", self.target_var)

        self.order_var = tk.StringVar(value="asc")
        add_row(control_frame, "Order:", self.order_var, widget_cls=ttk.Combobox, values=["asc", "desc"], state="readonly")

        self.shortest_path_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            control_frame,
            text="Show only shortest path (IDDFS)",
            variable=self.shortest_path_var
        ).pack(anchor=tk.W, pady=(4, 2))

        search_btn_frame = ttk.Frame(control_frame)
        search_btn_frame.pack(fill=tk.X, pady=(4, 2))
        ttk.Button(search_btn_frame, text="Start", command=self.init_search).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(search_btn_frame, text="Step", command=self.step_search).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(search_btn_frame, text="Run to end", command=self.run_full_search).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Results
        ttk.Label(control_frame, text="Results", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)
        self.result_status_lbl = ttk.Label(control_frame, text="Status: Waiting", foreground="blue")
        self.result_status_lbl.pack(anchor=tk.W, pady=1)
        self.result_algo_lbl = ttk.Label(control_frame, text="Algorithm: -")
        self.result_algo_lbl.pack(anchor=tk.W, pady=1)
        self.result_expanded_lbl = ttk.Label(control_frame, text="Expanded vertices: 0")
        self.result_expanded_lbl.pack(anchor=tk.W, pady=1)
        self.result_time_lbl = ttk.Label(control_frame, text="Time (algorithm): -")
        self.result_time_lbl.pack(anchor=tk.W, pady=1)
        self.result_path_lbl = ttk.Label(control_frame, text="Path: -", wraplength=300, justify=tk.LEFT)
        self.result_path_lbl.pack(anchor=tk.W, pady=1)

        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

    def generate_new_graph(self):
        nodes = safe_get_int(self.nodes_var, "Number of vertices")
        if nodes is None:
            return

        if nodes < 30:
            messagebox.showwarning("Warning", "Per the assignment, the graph must have order at least 30.")

        graph_choice = self.graph_type_var.get()
        is_directed = (graph_choice == "Directed graph")
        force_tree = (graph_choice == "Tree")

        if force_tree:
            messagebox.showinfo(
                "Information",
                "Tree selected: a pure tree without cycles will be "
                "generated, with a guaranteed number of branches from "
                "the root (at least 5)."
            )

        self.logic.generate_graph(
            num_nodes=nodes,
            is_directed=is_directed,
            force_tree=force_tree
        )

        self.search_generator = None
        self.current_state = None
        self.update_results_ui("Waiting", "-", 0, "-", "-")
        self.draw_graph()

    def _get_edge_inputs(self):
        try:
            u = int(self.edge_u_var.get())
            v = int(self.edge_v_var.get())
            return u, v
        except ValueError:
            messagebox.showerror("Error", "Enter numeric vertex IDs")
            return None, None

    def add_edge_ui(self):
        u, v = self._get_edge_inputs()
        if u is not None and v is not None:
            if self.logic.add_custom_edge(u, v):
                self.draw_graph()
            else:
                messagebox.showwarning("Warning", "One or both vertices do not exist.")

    def remove_edge_ui(self):
        u, v = self._get_edge_inputs()
        if u is not None and v is not None:
            if self.logic.remove_custom_edge(u, v):
                self.draw_graph()
            else:
                messagebox.showwarning("Warning", "This edge does not exist.")

    def replace_with_arc_ui(self):
        u, v = self._get_edge_inputs()
        if u is not None and v is not None:
            if self.logic.replace_edge_with_arc(u, v):
                self.draw_graph()
            else:
                messagebox.showwarning("Warning", "This connection does not exist.")

    def replace_with_edge_ui(self):
        u, v = self._get_edge_inputs()
        if u is not None and v is not None:
            if self.logic.replace_arc_with_edge(u, v):
                self.draw_graph()
            else:
                messagebox.showwarning("Warning", "This connection does not exist.")

    def draw_graph(self, current=None, visited=None, path=None):
        self.ax.clear()
        self.ax.axis('off')

        node_colors = []
        for node in self.logic.G.nodes():
            if current is not None and node == current:
                node_colors.append('#ff7f0e')
            elif path and node in path:
                node_colors.append('#2ca02c')
            elif visited and node in visited:
                node_colors.append('#1f77b4')
            else:
                node_colors.append('#cccccc')

        if self.logic.G.is_directed():
            two_way_edges = []
            one_way_edges = []
            seen = set()
            for u, v in self.logic.G.edges():
                if (u, v) in seen or (v, u) in seen:
                    continue
                if self.logic.G.has_edge(v, u):
                    two_way_edges.append((u, v))
                    seen.add((u, v))
                    seen.add((v, u))
                else:
                    one_way_edges.append((u, v))
                    seen.add((u, v))

            nx.draw_networkx_nodes(self.logic.G, self.logic.pos, ax=self.ax,
                                    node_color=node_colors, node_size=400)
            nx.draw_networkx_labels(self.logic.G, self.logic.pos, ax=self.ax,
                                     font_size=9, font_weight="bold")
            # Малюємо двосторонні зв'язки як звичайні лінії (без стрілок)
            nx.draw_networkx_edges(self.logic.G, self.logic.pos, ax=self.ax,
                                    edgelist=two_way_edges, edge_color='gray',
                                    arrows=False, width=1)
            nx.draw_networkx_edges(self.logic.G, self.logic.pos, ax=self.ax,
                                    edgelist=one_way_edges, edge_color='gray',
                                    arrows=True, arrowstyle='->', arrowsize=12, width=1)
        else:
            nx.draw(self.logic.G, self.logic.pos, ax=self.ax, with_labels=True,
                    node_color=node_colors, node_size=400, font_size=9, font_weight="bold",
                    edge_color='gray', arrows=False)

        self.canvas.draw()

    def init_search(self):
        start = safe_get_int(self.start_var, "Start vertex")
        target = safe_get_int(self.target_var, "Target vertex")
        if start is None or target is None:
            return

        self.active_start = start
        self.active_target = target
        self.active_order = self.order_var.get()

        if self.shortest_path_var.get():
            self.active_algorithm = "iddfs"
            self.search_generator = self.logic.dfs_shortest_path_generator(start, target, self.active_order)
        else:
            self.active_algorithm = "dfs"
            self.search_generator = self.logic.dfs_generator(start, target, self.active_order)

        self.current_state = None
        self.algo_elapsed_ms = 0.0
        self.update_results_ui("Search initialized", self._algo_display_name(), 0, "-", "-")
        self.draw_graph()

    def _algo_display_name(self):
        return "IDDFS (shortest path)" if self.active_algorithm == "iddfs" else "DFS (blind search)"

    def _search_finished(self):
        return (
            self.current_state is not None
            and self.current_state.get("status") in ("found", "not_found")
        )

    def step_search(self):
        if not self.search_generator or self._search_finished():
            self.init_search()
            if not self.search_generator:
                return

        try:
            t0 = time.perf_counter()
            state = next(self.search_generator)
            self.algo_elapsed_ms += (time.perf_counter() - t0) * 1000

            if "error" in state:
                messagebox.showerror("Error", state["error"])
                self.search_generator = None
                return

            if state["status"] == "new_depth_limit":
                self.update_results_ui(
                    f"IDDFS: depth limit = {state['depth_limit']}",
                    self._algo_display_name(),
                    state["expanded"],
                    "-",
                    f"{self.algo_elapsed_ms:.3f} ms"
                )
                return

            self.current_state = state
            self.update_ui_from_state(state)
        except StopIteration:
            pass

    def run_full_search(self):
        if not self.search_generator or self._search_finished():
            self.init_search()

        state = None
        try:
            while True:
                t0 = time.perf_counter()
                state = next(self.search_generator)
                self.algo_elapsed_ms += (time.perf_counter() - t0) * 1000

                if "error" in state:
                    messagebox.showerror("Error", state["error"])
                    self.search_generator = None
                    return

                if state["status"] in ("found", "not_found"):
                    break
        except StopIteration:
            pass

        if state:
            self.current_state = state
            self.update_ui_from_state(state)

    def show_result_popup(self, state, elapsed_time):
        path_str = " -> ".join(map(str, state["path"])) if state["path"] else "-"
        algo_name = self._algo_display_name()
        depth_info = ""
        if state.get("algorithm") == "iddfs":
            depth_info = f"Final depth limit: {state.get('depth_limit', '-')}\n"

        if state["status"] == "found":
            title = "Search results"
            message = (
                f"Algorithm: {algo_name}\n"
                f"Path found!\n\n"
                f"Path length: {len(state['path']) - 1}\n"
                f"Number of expanded vertices: {state['expanded']}\n"
                f"{depth_info}"
                f"Execution time (algorithm): {elapsed_time}\n"
                f"Path: {path_str}"
            )
            messagebox.showinfo(title, message)
        else:
            title = "Search results"
            message = (
                f"Algorithm: {algo_name}\n"
                f"Path not found!\n\n"
                f"Number of expanded vertices: {state['expanded']}\n"
                f"{depth_info}"
                f"Execution time (algorithm): {elapsed_time}"
            )
            messagebox.showwarning(title, message)

    def update_ui_from_state(self, state):
        status_text = "In progress..."
        elapsed_time = f"{self.algo_elapsed_ms:.3f} ms"
        is_finished = state["status"] in ("found", "not_found")

        if is_finished:
            status_text = "FOUND!" if state["status"] == "found" else "PATH DOES NOT EXIST"
            self.save_results_to_csv(state, elapsed_time)

        path_str = " -> ".join(map(str, state["path"])) if state["path"] else "-"
        self.update_results_ui(status_text, self._algo_display_name(), state["expanded"], path_str, elapsed_time)

        active_path = state["path"] if state["status"] == "found" else None
        self.draw_graph(current=state["current"], visited=state["visited"], path=active_path)

        if is_finished:
            self.after(50, lambda: self.show_result_popup(state, elapsed_time))

    def update_results_ui(self, status, algo_name, expanded, path, elapsed_time):
        self.result_status_lbl.config(text=f"Status: {status}")
        self.result_algo_lbl.config(text=f"Algorithm: {algo_name}")
        self.result_expanded_lbl.config(text=f"Expanded vertices: {expanded}")
        self.result_time_lbl.config(text=f"Time (algorithm): {elapsed_time}")
        self.result_path_lbl.config(text=f"Path: {path}")

    def save_results_to_csv(self, state, elapsed_time):
        filename = "dfs_results.csv"
        file_exists = os.path.isfile(filename)

        graph_type = "Directed" if self.logic.G.is_directed() else "Undirected"

        with open(filename, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["Timestamp", "Graph Type", "Algorithm", "Nodes",
                                  "Start", "Target", "Order", "Expanded Nodes",
                                  "Path Length", "Depth Limit (IDDFS)", "Time (algo, ms)"])

            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                graph_type,
                self._algo_display_name(),
                len(self.logic.G.nodes),
                self.active_start,
                self.active_target,
                self.active_order,
                state["expanded"],
                len(state["path"]) - 1 if state["path"] else 0,
                state.get("depth_limit", "-"),
                elapsed_time
            ])
