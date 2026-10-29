import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import json
import math
import os
import time
from datetime import datetime

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.collections import LineCollection, PolyCollection

from graph_logic import RoadGraphLogic, ALGORITHMS, ALGO_DIJKSTRA, INF

CSV_FILE = "search_results.csv"

COL_NODE = "#d5d8dc"
COL_SETTLED = "#5dade2"       
COL_FRONTIER = "#f39c12"       
COL_CURRENT = "#8e44ad"      
COL_START, COL_TARGET = "#2ecc71", "#e74c3c"
COL_PATH = "#f1c40f"
COL_IMPROVED, COL_NOT_IMPROVED = "#27ae60", "#95a5a6"
COL_TREE = "#aed6f1"

REGIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ukraine_regions.json")
REGION_COLOURS = ["#f6ddcc", "#d5f5e3", "#e8daef", "#fcf3cf"]
REGION_ALPHA = 0.6
COL_REGION_EDGE = "#a6acaf"
COL_BORDER = "#566573"


def load_regions():
    """Returns {'regions': [...], 'border': [...]} or None if the file is missing."""
    try:
        with open(REGIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None

# cities whose names are drawn below the vertex (to avoid overlapping in dense areas)
NAME_BELOW = {"Івано-Франківськ", "Вінниця", "Одеса", "Хмельницький", "Донецьк"}
# cities whose name and distance label are both drawn below the vertex
ALL_BELOW = {"Запоріжжя", "Чернівці", "Херсон", "Мелітополь", "Маріуполь", "Кривий Ріг",
             "Севастополь"}


def safe_get_int(var, field_name):
    try:
        return var.get()
    except (ValueError, tk.TclError):
        messagebox.showerror("Error", f"Invalid value in field: {field_name}")
        return None


def fmt_km(value):
    return "∞" if value == INF else f"{value:g}"


class DijkstraApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Dijkstra's algorithm: shortest road between cities of Ukraine")
        self.geometry("1280x820")

        self.logic = RoadGraphLogic()
        self.regions = load_regions()
        self.search_generator = None
        self.current_state = None
        self.history = []
        self.algo_elapsed_ms = 0.0
        self.animation_id = None

        self.active_start = None
        self.active_target = None
        self.active_algorithm = None
        self.pending_road_city = None

        self._build_ui()
        self.refresh_city_lists()
        self.start_var.set("Львів")
        self.target_var.set("Харків")
        self._reset_search()

    def _build_ui(self):
        outer_frame = ttk.Frame(self, width=350)
        outer_frame.pack(side=tk.LEFT, fill=tk.Y)
        outer_frame.pack_propagate(False)

        canvas_scroll = tk.Canvas(outer_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer_frame, orient="vertical", command=canvas_scroll.yview)
        control_frame = ttk.Frame(canvas_scroll, padding=(10, 6))

        control_frame.bind(
            "<Configure>",
            lambda e: canvas_scroll.configure(scrollregion=canvas_scroll.bbox("all"))
        )
        canvas_scroll.create_window((0, 0), window=control_frame, anchor="nw", width=330)
        canvas_scroll.configure(yscrollcommand=scrollbar.set)

        canvas_scroll.pack(side=tk.LEFT, fill=tk.Y, expand=True)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        def _on_mousewheel(event):
            canvas_scroll.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas_scroll.bind("<Enter>", lambda e: canvas_scroll.bind_all("<MouseWheel>", _on_mousewheel))
        canvas_scroll.bind("<Leave>", lambda e: canvas_scroll.unbind_all("<MouseWheel>"))

        HEADER_FONT = ("Arial", 10, "bold")
        PADY_FIELD = 1
        PADY_SECTION = (8, 3)

        def add_row(parent, label_text, widget_var, widget_cls=ttk.Entry, **widget_kwargs):
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=PADY_FIELD)
            ttk.Label(row, text=label_text, width=14, anchor=tk.W).pack(side=tk.LEFT)
            widget = widget_cls(row, textvariable=widget_var, **widget_kwargs)
            widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
            return widget

        def button_row(parent, buttons, pady=(2, 2)):
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, pady=pady)
            for text, cmd in buttons:
                ttk.Button(frame, text=text, command=cmd).pack(
                    side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        # Graph
        ttk.Label(control_frame, text="Road graph", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)
        self.graph_info_lbl = ttk.Label(control_frame, text="")
        self.graph_info_lbl.pack(anchor=tk.W)
        button_row(control_frame, [("Ukraine map", self.load_default_map),
                                   ("Clear graph", self.clear_graph)])
        button_row(control_frame, [("Load JSON...", self.load_graph),
                                   ("Save JSON...", self.save_graph)])
        self.show_regions_var = tk.BooleanVar(value=self.regions is not None)
        ttk.Checkbutton(control_frame, text="Show map of regions (oblasts)",
                        variable=self.show_regions_var,
                        command=lambda: self.draw_graph(self.current_state)).pack(anchor=tk.W)

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Mouse mode
        ttk.Label(control_frame, text="Click on the map", font=HEADER_FONT).pack(
            pady=PADY_SECTION, anchor=tk.W)
        self.edit_mode_var = tk.StringVar(value="road")
        for text, value in [("Pick cities for a road (2 clicks)", "road"),
                            ("Set start city", "start"),
                            ("Set target city", "target"),
                            ("Add city at click position", "add"),
                            ("Delete clicked city", "delete")]:
            ttk.Radiobutton(control_frame, text=text, variable=self.edit_mode_var,
                            value=value).pack(anchor=tk.W)

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Vertices
        ttk.Label(control_frame, text="Vertices (cities)", font=HEADER_FONT).pack(
            pady=PADY_SECTION, anchor=tk.W)
        self.city_name_var = tk.StringVar()
        add_row(control_frame, "City name:", self.city_name_var)
        button_row(control_frame, [("Add (at click)", lambda: self.edit_mode_var.set("add")),
                                   ("Remove city", self.remove_city_ui)])

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Edges
        ttk.Label(control_frame, text="Edges / arcs (roads)", font=HEADER_FONT).pack(
            pady=PADY_SECTION, anchor=tk.W)
        self.road_from_var = tk.StringVar()
        self.road_from_cb = add_row(control_frame, "From:", self.road_from_var,
                                    widget_cls=ttk.Combobox, state="readonly")
        self.road_to_var = tk.StringVar()
        self.road_to_cb = add_row(control_frame, "To:", self.road_to_var,
                                  widget_cls=ttk.Combobox, state="readonly")
        self.road_km_var = tk.IntVar(value=100)
        add_row(control_frame, "Distance, km:", self.road_km_var)
        self.one_way_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(control_frame, text="One-way (arc From -> To)",
                        variable=self.one_way_var).pack(anchor=tk.W)
        button_row(control_frame, [("Add / update", self.add_road_ui),
                                   ("Remove", self.remove_road_ui)])

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Search parameters
        ttk.Label(control_frame, text="Search parameters", font=HEADER_FONT).pack(
            pady=PADY_SECTION, anchor=tk.W)
        self.start_var = tk.StringVar()
        self.start_cb = add_row(control_frame, "Start:", self.start_var,
                                widget_cls=ttk.Combobox, state="readonly")
        self.target_var = tk.StringVar()
        self.target_cb = add_row(control_frame, "Target:", self.target_var,
                                 widget_cls=ttk.Combobox, state="readonly")
        self.start_cb.bind("<<ComboboxSelected>>", lambda e: self._reset_search())
        self.target_cb.bind("<<ComboboxSelected>>", lambda e: self._reset_search())
        ttk.Button(control_frame, text="Swap start <-> target",
                   command=self.swap_endpoints).pack(fill=tk.X, pady=(2, 2))

        self.algorithm_var = tk.StringVar(value=ALGO_DIJKSTRA)
        add_row(control_frame, "Algorithm:", self.algorithm_var, widget_cls=ttk.Combobox,
                values=ALGORITHMS, state="readonly")

        delay_row = ttk.Frame(control_frame)
        delay_row.pack(fill=tk.X, pady=PADY_FIELD)
        ttk.Label(delay_row, text="Delay, ms:", width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.delay_var = tk.IntVar(value=500)
        delay_scale = ttk.Scale(delay_row, from_=0, to=2000, orient=tk.HORIZONTAL,
                                command=lambda v: self.delay_var.set(int(float(v))))
        delay_scale.set(500)
        delay_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(delay_row, textvariable=self.delay_var, width=5).pack(side=tk.LEFT)

        button_row(control_frame, [("Start", self.init_search), ("Step", self.step_search),
                                   ("Animate", self.run_animated)], pady=(4, 2))
        button_row(control_frame, [("Stop", self.stop_animation),
                                   ("Run to end", self.run_full_search)])
        button_row(control_frame, [("Dijkstra table", self.show_labels_table),
                                   ("Compare", self.compare_algorithms)])

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Results
        ttk.Label(control_frame, text="Results", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)
        self.result_status_lbl = ttk.Label(control_frame, text="Status: Waiting", foreground="blue")
        self.result_status_lbl.pack(anchor=tk.W, pady=1)
        self.result_algo_lbl = ttk.Label(control_frame, text="Algorithm: -")
        self.result_algo_lbl.pack(anchor=tk.W, pady=1)
        self.result_current_lbl = ttk.Label(control_frame, text="Current vertex: -", wraplength=310)
        self.result_current_lbl.pack(anchor=tk.W, pady=1)
        self.result_cycles_lbl = ttk.Label(control_frame, text="Cycles: 0")
        self.result_cycles_lbl.pack(anchor=tk.W, pady=1)
        self.result_relax_lbl = ttk.Label(control_frame, text="Relaxations: 0")
        self.result_relax_lbl.pack(anchor=tk.W, pady=1)
        self.result_dist_lbl = ttk.Label(control_frame, text="Distance: -")
        self.result_dist_lbl.pack(anchor=tk.W, pady=1)
        self.result_time_lbl = ttk.Label(control_frame, text="Time (algorithm): -")
        self.result_time_lbl.pack(anchor=tk.W, pady=1)
        self.result_path_lbl = ttk.Label(control_frame, text="Path: -", wraplength=310, justify=tk.LEFT)
        self.result_path_lbl.pack(anchor=tk.W, pady=1)

        # Legend
        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)
        ttk.Label(control_frame, text="Legend", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)
        for colour, text in [(COL_START, "start city"), (COL_TARGET, "target city"),
                             (COL_NODE, "label = ∞ (not reached)"),
                             (COL_FRONTIER, "temporary label (in queue)"),
                             (COL_SETTLED, "permanent label (settled)"),
                             (COL_CURRENT, "vertex settled in this cycle"),
                             (COL_IMPROVED, "edge relaxed: label decreased"),
                             (COL_NOT_IMPROVED, "edge checked: no improvement"),
                             (COL_TREE, "shortest-path tree"),
                             (COL_PATH, "shortest path")]:
            row = ttk.Frame(control_frame)
            row.pack(anchor=tk.W)
            tk.Label(row, bg=colour, width=2, relief=tk.SOLID, borderwidth=1).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Label(row, text=text).pack(side=tk.LEFT)

        # Map canvas
        self.fig = Figure(figsize=(9, 7.5), dpi=100)
        self.fig.subplots_adjust(left=0.01, right=0.99, top=0.97, bottom=0.01)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.canvas.mpl_connect("button_press_event", self.on_canvas_click)

    # graph editing 
    def refresh_city_lists(self):
        cities = sorted(self.logic.G.nodes)
        for cb in (self.start_cb, self.target_cb, self.road_from_cb, self.road_to_cb):
            cb.config(values=cities)
        for var in (self.start_var, self.target_var, self.road_from_var, self.road_to_var):
            if var.get() not in self.logic.G:
                var.set("")
        self.graph_info_lbl.config(
            text=f"Order (cities): {self.logic.order()}    Size (roads): {self.logic.size()}")

    def _graph_changed(self):
        self.refresh_city_lists()
        self._reset_search()

    def load_default_map(self):
        self.logic.load_default_map()
        self._graph_changed()

    def clear_graph(self):
        if messagebox.askyesno("Clear graph", "Remove all cities and roads?"):
            self.logic.clear()
            self._graph_changed()

    def load_graph(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not filename:
            return
        try:
            self.logic.load_json(filename)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Error", f"Cannot load graph: {exc}")
            return
        self._graph_changed()

    def save_graph(self):
        filename = filedialog.asksaveasfilename(defaultextension=".json",
                                                filetypes=[("JSON", "*.json")])
        if filename:
            self.logic.save_json(filename)

    def remove_city_ui(self):
        name = self.city_name_var.get().strip()
        if not self.logic.remove_city(name):
            messagebox.showerror("Error", f"City '{name}' does not exist")
            return
        self._graph_changed()

    def add_road_ui(self):
        u, v = self.road_from_var.get(), self.road_to_var.get()
        km = safe_get_int(self.road_km_var, "Distance, km")
        if km is None:
            return
        if km <= 0:
            messagebox.showerror("Error", "Distance must be a positive number "
                                          "(Dijkstra's algorithm requires non-negative weights)")
            return
        if not self.logic.add_road(u, v, km, self.one_way_var.get()):
            messagebox.showerror("Error", "Choose two different existing cities")
            return
        self._graph_changed()

    def remove_road_ui(self):
        u, v = self.road_from_var.get(), self.road_to_var.get()
        if not self.logic.remove_road(u, v, self.one_way_var.get()):
            messagebox.showerror("Error", f"There is no road {u} - {v}")
            return
        self._graph_changed()

    def swap_endpoints(self):
        s, t = self.start_var.get(), self.target_var.get()
        self.start_var.set(t)
        self.target_var.set(s)
        self._reset_search()

    def _city_at(self, x, y):
        best, best_d = None, 0.35
        for name, (cx, cy) in self.logic.pos.items():
            d = math.hypot((cx - x) * math.cos(math.radians(cy)), cy - y)
            if d < best_d:
                best, best_d = name, d
        return best

    def on_canvas_click(self, event):
        if event.xdata is None or event.ydata is None:
            return
        mode = self.edit_mode_var.get()
        city = self._city_at(event.xdata, event.ydata)

        if mode == "add":
            name = self.city_name_var.get().strip()
            if not name:
                messagebox.showerror("Error", "Enter the city name first")
                return
            if not self.logic.add_city(name, event.xdata, event.ydata):
                messagebox.showerror("Error", f"City '{name}' already exists")
                return
            self.city_name_var.set("")
            self._graph_changed()
            return

        if city is None:
            return
        self.city_name_var.set(city)

        if mode == "start":
            self.start_var.set(city)
            self._reset_search()
        elif mode == "target":
            self.target_var.set(city)
            self._reset_search()
        elif mode == "delete":
            self.logic.remove_city(city)
            self._graph_changed()
        elif mode == "road":
            if self.pending_road_city is None or self.pending_road_city == city:
                self.pending_road_city = city
                self.road_from_var.set(city)
            else:
                self.road_to_var.set(city)
                u, v = self.pending_road_city, city
                if self.logic.G.has_edge(u, v):
                    self.road_km_var.set(self.logic.G[u][v]["weight"])
                self.pending_road_city = None
            self.draw_graph(self.current_state)

    def draw_graph(self, state=None):
        ax = self.ax
        ax.clear()
        ax.set_axis_off()
        G, pos = self.logic.G, self.logic.pos
        map_drawn = self._draw_regions()
        if not pos:
            ax.text(0.5, 0.5, "Empty graph: add cities", ha="center", transform=ax.transAxes)
            if not map_drawn:
                self.canvas.draw_idle()
                return

        dist = state["dist"] if state else {}
        settled = set(state["settled"]) if state else set()
        frontier = set(state["frontier"]) if state else set()
        current = state["current"] if state else None
        prev = state["prev"] if state else {}
        path = state["path"] if state else []
        final_path = state and state["status"] == "found"
        path_edges = {frozenset(e) for e in zip(path, path[1:])}
        relaxed = {frozenset((u, v)): imp for u, v, _, _, imp in state["relaxed"]} if state else {}
        tree_edges = {frozenset((n, p)) for n, p in prev.items() if p is not None}

        # edges
        for u, v, w, two_way in self.logic.roads():
            (x1, y1), (x2, y2) = pos[u], pos[v]
            key = frozenset((u, v))
            colour, lw, ls, z = "#7f8c8d", 1.2, "-", 1
            if key in tree_edges:
                colour, lw = COL_TREE, 3
            if key in relaxed:
                colour, lw = (COL_IMPROVED, 3.5) if relaxed[key] else (COL_NOT_IMPROVED, 2.5)
                ls = "-" if relaxed[key] else "--"
                z = 2
            if key in path_edges:
                colour, lw, z = (COL_PATH, 6, 3) if final_path else (COL_CURRENT, 3, 3)
            if two_way:
                ax.plot([x1, x2], [y1, y2], color=colour, lw=lw, ls=ls, zorder=z)
            else:
                ax.annotate("", xy=(x2, y2), xytext=(x1, y1), zorder=z,
                            arrowprops=dict(arrowstyle="-|>", color=colour, lw=lw, ls=ls,
                                            shrinkA=9, shrinkB=9, mutation_scale=16))
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if not two_way and G.has_edge(v, u):      # two different arcs: shift labels apart
                mx, my = x1 + (x2 - x1) * 0.62, y1 + (y2 - y1) * 0.62
            ax.text(mx, my, str(w), fontsize=7, ha="center", va="center", zorder=4,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85))

        # vertices
        start, target = self.start_var.get(), self.target_var.get()
        for n in G.nodes:
            x, y = pos[n]
            fill = COL_NODE
            if n in frontier:
                fill = COL_FRONTIER
            if n in settled:
                fill = COL_SETTLED
            if n == current and not final_path:
                fill = COL_CURRENT
            edge_col, edge_w = "#2c3e50", 1
            if n == start:
                edge_col, edge_w = COL_START, 4
            if n == target:
                edge_col, edge_w = COL_TARGET, 4
            if n == self.pending_road_city:
                edge_col, edge_w = "#000000", 3
            ax.scatter([x], [y], s=230, c=fill, edgecolors=edge_col, linewidths=edge_w, zorder=5)
            below = n in NAME_BELOW or n in ALL_BELOW
            ax.text(x, y - 0.2 if below else y + 0.2, n, fontsize=8, ha="center",
                    va="top" if below else "bottom", zorder=6, fontweight="bold")
            if state:
                label = fmt_km(dist.get(n, INF))
                if n in ALL_BELOW:
                    label_y, label_va = y - 0.45, "top"
                elif below:
                    label_y, label_va = y + 0.19, "bottom"
                else:
                    label_y, label_va = y - 0.19, "top"
                ax.text(x, label_y, label, fontsize=7.5, ha="center", va=label_va, zorder=6,
                        color="#000000" if n in settled else "#34495e",
                        bbox=dict(boxstyle="round,pad=0.15",
                                  fc="#ebf5fb" if n in settled else "#fdf2e9",
                                  ec="#5d6d7e", lw=0.5))

        ys = [p[1] for p in pos.values()] or [48.5]
        if pos:
            ax.update_datalim(list(pos.values()))
        ax.autoscale_view()
        ax.margins(0.03, 0.04)
        ax.set_aspect(1 / math.cos(math.radians(sum(ys) / len(ys))), adjustable="datalim")
        title = "Road map of Ukraine (distances in km)"
        if state:
            title = f"{state['algorithm']}: cycle {state['cycles']}"
            if current:
                title += f", current vertex: {current} ({fmt_km(dist.get(current, INF))} km)"
        ax.set_title(title, fontsize=11)
        self.canvas.draw_idle()

    def _draw_regions(self):
        """Background: coloured oblasts and the state border. Returns True if drawn."""
        if not self.regions or not self.show_regions_var.get():
            return False
        verts, colours = [], []
        for region in self.regions["regions"]:
            for ring in region["polygons"]:
                verts.append(ring)
                colours.append(REGION_COLOURS[region.get("colour", 0) % len(REGION_COLOURS)])
        polys = PolyCollection(verts, facecolors=colours, edgecolors=COL_REGION_EDGE,
                               linewidths=0.6, alpha=REGION_ALPHA, zorder=0)
        self.ax.add_collection(polys)
        border = LineCollection(self.regions["border"], colors=COL_BORDER, linewidths=1.6, zorder=0.5)
        self.ax.add_collection(border)
        self.ax.update_datalim([pt for ring in self.regions["border"] for pt in ring])
        return True

    def _reset_search(self):
        self.stop_animation()
        self.search_generator = None
        self.current_state = None
        self.history = []
        self.algo_elapsed_ms = 0.0
        self.update_results_ui("Waiting", "-", "-", 0, 0, "-", "-", "-")
        self.draw_graph()

    def init_search(self):
        self.stop_animation()
        start, target = self.start_var.get(), self.target_var.get()
        if not start or not target:
            messagebox.showerror("Error", "Choose start and target cities")
            return False
        self.active_start, self.active_target = start, target
        self.active_algorithm = self.algorithm_var.get()
        self.search_generator = self.logic.search_generator(start, target, self.active_algorithm)
        self.current_state = None
        self.history = []
        self.algo_elapsed_ms = 0.0
        self.update_results_ui("Search initialized", self.active_algorithm, "-", 0, 0, "-", "-", "-")
        self.draw_graph()
        return True

    def _search_finished(self):
        return (
            self.current_state is not None
            and self.current_state.get("status") in ("found", "not_found")
        )

    def _ensure_search(self):
        if not self.search_generator or self._search_finished():
            return self.init_search()
        return True

    def _next_state(self):
        try:
            t0 = time.perf_counter()
            state = next(self.search_generator)
            self.algo_elapsed_ms += (time.perf_counter() - t0) * 1000
        except StopIteration:
            return None
        if "error" in state:
            messagebox.showerror("Error", state["error"])
            self.search_generator = None
            return None
        self.history.append(state)
        return state

    def _advance(self):
        if not self._ensure_search():
            return None
        state = self._next_state()
        if state:
            self.current_state = state
            self.update_ui_from_state(state)
        return state

    def step_search(self):
        self._advance()

    def run_animated(self):
        self.stop_animation()
        if not self._ensure_search():
            return
        self._animation_tick()

    def _animation_tick(self):
        state = self._advance()
        if state is None or state["status"] in ("found", "not_found"):
            self.animation_id = None
            return
        self.animation_id = self.after(max(0, self.delay_var.get()), self._animation_tick)

    def stop_animation(self):
        if self.animation_id is not None:
            self.after_cancel(self.animation_id)
            self.animation_id = None

    def run_full_search(self):
        self.stop_animation()
        if not self._ensure_search():
            return
        state = None
        while True:
            new_state = self._next_state()
            if new_state is None:
                break
            state = new_state
            if state["status"] in ("found", "not_found"):
                break
        if state:
            self.current_state = state
            self.update_ui_from_state(state)

    # results 
    def update_ui_from_state(self, state):
        status_text = "In progress..."
        elapsed_time = f"{self.algo_elapsed_ms:.3f} ms"
        is_finished = state["status"] in ("found", "not_found")

        if is_finished:
            status_text = "FOUND!" if state["status"] == "found" else "PATH DOES NOT EXIST"
            self.save_results_to_csv(state, elapsed_time)

        path_str = " -> ".join(state["path"]) if state["path"] else "-"
        current = state["current"] or "-"
        if state["current"]:
            current += f" ({fmt_km(state['dist'][state['current']])} km)"
        distance = f"{state['distance']:g} km" if state["distance"] is not None else "-"
        self.update_results_ui(status_text, state["algorithm"], current, state["cycles"],
                               state["relaxations"], distance, path_str, elapsed_time)
        self.draw_graph(state)

        if is_finished:
            self.after(50, lambda: self.show_result_window(state, elapsed_time))

    def update_results_ui(self, status, algorithm, current, cycles, relaxations, distance, path,
                          elapsed_time):
        self.result_status_lbl.config(text=f"Status: {status}")
        self.result_algo_lbl.config(text=f"Algorithm: {algorithm}")
        self.result_current_lbl.config(text=f"Current vertex: {current}")
        self.result_cycles_lbl.config(text=f"Cycles (settled vertices): {cycles}")
        self.result_relax_lbl.config(text=f"Relaxations (edge checks): {relaxations}")
        self.result_dist_lbl.config(text=f"Distance: {distance}")
        self.result_time_lbl.config(text=f"Time (algorithm): {elapsed_time}")
        self.result_path_lbl.config(text=f"Path: {path}")

    def show_result_window(self, state, elapsed_time):
        found = state["status"] == "found"
        win = tk.Toplevel(self)
        win.title("Search results")
        win.geometry("600x460")

        frame = ttk.Frame(win, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        head = [
            f"Algorithm: {state['algorithm']}    |    Graph: {self.logic.order()} cities, {self.logic.size()} roads",
            f"From: {self.active_start}    To: {self.active_target}",
            ""
        ]
        if found:
            path = state["path"]
            head += [
                f"RESULT: shortest route found - {self.logic.path_length(path):g} km",
                f"Cities on the route: {len(path)}   (roads: {len(path) - 1})",
                "Route: " + " -> ".join(path),
            ]
        else:
            head.append("RESULT: the target city is unreachable from the start city")
            
        ttk.Label(frame, text="\n".join(head), justify=tk.LEFT, wraplength=570,
                  font=("Arial", 10)).pack(anchor=tk.W)

        if found:
            columns = ("n", "from", "to", "km", "total")
            tree = ttk.Treeview(frame, columns=columns, show="headings", height=7)
            for col, head_text, w in zip(columns, ["#", "From", "To", "Road, km", "Total, km"],
                                         [40, 140, 140, 80, 90]):
                tree.heading(col, text=head_text)
                tree.column(col, width=w, anchor=tk.CENTER)
            total = 0
            for i, (a, b) in enumerate(zip(path, path[1:]), 1):
                km = self.logic.G[a][b]["weight"]
                total += km
                tree.insert("", tk.END, values=(i, a, b, km, total))
            tree.pack(fill=tk.BOTH, expand=True, pady=6)
        stats = [
            f"Cycles: {state['cycles']}   |   Expanded (settled) vertices: {state['expanded']}",
            f"Relaxations (edge checks): {state['relaxations']}   |   Label decreases: {state['improvements']}",
            f"Execution time (algorithm): {elapsed_time}",
        ]
        ttk.Label(frame, text="\n".join(stats), justify=tk.LEFT,
                  font=("Arial", 10)).pack(anchor=tk.W)
                  
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=(8, 8))

    def show_labels_table(self):
        """Classic Dijkstra table: label of every city after each cycle."""
        if not self.history:
            messagebox.showinfo("Dijkstra table", "Run a search first")
            return
        states = [s for s in self.history if s["cycles"] > 0]
        if not states:
            messagebox.showinfo("Dijkstra table", "Make at least one step")
            return

        win = tk.Toplevel(self)
        win.title(f"Labels after each cycle ({states[0]['algorithm']}, "
                  f"{self.active_start} -> {self.active_target})")
        win.geometry("1100x560")

        cities = sorted(self.logic.G.nodes)
        columns = ["cycle", "vertex"] + cities
        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        tree.heading("cycle", text="Cycle")
        tree.column("cycle", width=45, anchor=tk.CENTER, stretch=False)
        tree.heading("vertex", text="Settled vertex")
        tree.column("vertex", width=120, anchor=tk.CENTER, stretch=False)
        for c in cities:
            tree.heading(c, text=c)
            tree.column(c, width=max(70, 10 * len(c)), anchor=tk.CENTER, stretch=False)

        done = set()
        for s in states:
            row = [s["cycles"], s["current"] or "-"]
            for c in cities:
                if c in done:
                    row.append("")                         # already permanent
                elif c == s["current"]:
                    row.append(f"[{fmt_km(s['dist'][c])}]")  # becomes permanent now
                else:
                    row.append(fmt_km(s["dist"].get(c, INF)))
            if s["current"]:
                done.add(s["current"])
            tree.insert("", tk.END, values=row)

        xs = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        ys = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(win, text="[x] - label becomes permanent in this cycle; "
                            "empty - label is already permanent; ∞ - city not reached yet"
                  ).pack(pady=(0, 6))

    def compare_algorithms(self):
        start, target = self.start_var.get(), self.target_var.get()
        if not start or not target:
            messagebox.showerror("Error", "Choose start and target cities")
            return
        win = tk.Toplevel(self)
        win.title(f"Dijkstra vs BFS: {start} -> {target}")
        win.geometry("1000x220")

        columns = ("algorithm", "result", "km", "cities", "cycles", "relax", "time", "path")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=4)
        headers = ["Algorithm", "Result", "Distance, km", "Cities", "Cycles", "Relaxations",
                   "Time, ms", "Route"]
        widths = [140, 70, 90, 60, 60, 85, 70, 400]
        for col, head, w in zip(columns, headers, widths):
            tree.heading(col, text=head)
            tree.column(col, width=w, anchor=tk.CENTER if col != "path" else tk.W)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        for algo in ALGORITHMS:
            state, elapsed = self.logic.run_to_end(start, target, algo)
            if state is None or "error" in state:
                tree.insert("", tk.END, values=(algo, "error", "-", "-", "-", "-", "-", "-"))
                continue
            found = state["status"] == "found"
            tree.insert("", tk.END, values=(
                algo, "found" if found else "no path",
                f"{state['distance']:g}" if found else "-",
                len(state["path"]) if found else "-",
                state["cycles"], state["relaxations"], f"{elapsed:.3f}",
                " -> ".join(state["path"]) if found else "-",
            ))
        ttk.Label(win, text=f"Graph: {self.logic.order()} cities, {self.logic.size()} roads").pack(
            pady=(0, 6))

    def save_results_to_csv(self, state, elapsed_time):
        file_exists = os.path.isfile(CSV_FILE)

        with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["Timestamp", "Algorithm", "Cities", "Roads", "Start", "Target",
                                 "Result", "Distance (km)", "Cities in path", "Cycles",
                                 "Relaxations", "Label decreases", "Time (algo, ms)", "Path"])
            found = state["status"] == "found"
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                state["algorithm"],
                self.logic.order(),
                self.logic.size(),
                self.active_start,
                self.active_target,
                "found" if found else "not found",
                state["distance"] if found else "",
                len(state["path"]) if found else 0,
                state["cycles"],
                state["relaxations"],
                state["improvements"],
                elapsed_time,
                " -> ".join(state["path"]),
            ])
