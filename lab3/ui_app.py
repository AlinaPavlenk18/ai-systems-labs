import tkinter as tk
from tkinter import ttk, messagebox
import csv
import time
import os
from datetime import datetime

from grid_logic import WaveSearchLogic, OPERATORS, WALL

CANVAS_SIZE = 720


def safe_get_int(var, field_name):
    try:
        return var.get()
    except (ValueError, tk.TclError):
        messagebox.showerror("Error", f"Invalid value in field: {field_name}")
        return None


def blend(c1, c2, t):
    """Linear blend of two '#rrggbb' colours, t in [0, 1]."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * t):02x}" for x, y in zip(a, b))


class WaveApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("One-directional wave search (Lee algorithm)")
        self.geometry("1150x800")

        self.logic = WaveSearchLogic()
        self.search_generator = None
        self.current_state = None
        self.algo_elapsed_ms = 0.0
        self.animation_id = None
        self.cell = 40

        self.active_operator = None

        self._build_ui()
        self.generate_new_maze()

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

        # Maze settings
        ttk.Label(control_frame, text="Maze settings", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)

        self.rows_var = tk.IntVar(value=15)
        add_row(control_frame, "Rows (10-20):", self.rows_var)

        self.cols_var = tk.IntVar(value=15)
        add_row(control_frame, "Columns (10-20):", self.cols_var)

        self.walls_var = tk.IntVar(value=25)
        add_row(control_frame, "Walls, %:", self.walls_var)

        gen_frame = ttk.Frame(control_frame)
        gen_frame.pack(fill=tk.X, pady=(4, 2))
        ttk.Button(gen_frame, text="Generate maze", command=self.generate_new_maze).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 2))
        ttk.Button(gen_frame, text="Clear walls", command=self.clear_maze).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=(2, 0))

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Editing
        ttk.Label(control_frame, text="Edit maze (click on a cell)", font=HEADER_FONT).pack(
            pady=PADY_SECTION, anchor=tk.W)
        self.edit_mode_var = tk.StringVar(value="wall")
        ttk.Radiobutton(control_frame, text="Toggle wall (-1 / 0)",
                        variable=self.edit_mode_var, value="wall").pack(anchor=tk.W)
        ttk.Radiobutton(control_frame, text="Set start vertex",
                        variable=self.edit_mode_var, value="start").pack(anchor=tk.W)
        ttk.Radiobutton(control_frame, text="Set target vertex",
                        variable=self.edit_mode_var, value="target").pack(anchor=tk.W)

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Search parameters
        ttk.Label(control_frame, text="Wave search parameters", font=HEADER_FONT).pack(
            pady=PADY_SECTION, anchor=tk.W)

        self.operator_var = tk.StringVar(value="Up-Down-Right-Left")
        add_row(control_frame, "Operator:", self.operator_var, widget_cls=ttk.Combobox,
                values=list(OPERATORS.keys()), state="readonly")

        delay_row = ttk.Frame(control_frame)
        delay_row.pack(fill=tk.X, pady=PADY_FIELD)
        ttk.Label(delay_row, text="Delay, ms:", width=16, anchor=tk.W).pack(side=tk.LEFT)
        self.delay_var = tk.IntVar(value=200)
        ttk.Scale(delay_row, from_=0, to=1000, orient=tk.HORIZONTAL,
                  command=lambda v: self.delay_var.set(int(float(v)))).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(delay_row, textvariable=self.delay_var, width=5).pack(side=tk.LEFT)

        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X, pady=(4, 2))
        ttk.Button(btn_frame, text="Start", command=self.init_search).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(btn_frame, text="Step", command=self.step_search).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(btn_frame, text="Animate", command=self.run_animated).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        btn_frame2 = ttk.Frame(control_frame)
        btn_frame2.pack(fill=tk.X, pady=(2, 2))
        ttk.Button(btn_frame2, text="Stop", command=self.stop_animation).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(btn_frame2, text="Run to end", command=self.run_full_search).pack(
            side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(control_frame, text="Compare all operators",
                   command=self.compare_operators).pack(fill=tk.X, pady=(2, 2))

        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)

        # Results
        ttk.Label(control_frame, text="Results", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)
        self.result_status_lbl = ttk.Label(control_frame, text="Status: Waiting", foreground="blue")
        self.result_status_lbl.pack(anchor=tk.W, pady=1)
        self.result_algo_lbl = ttk.Label(control_frame, text="Operator: -", wraplength=300)
        self.result_algo_lbl.pack(anchor=tk.W, pady=1)
        self.result_cycles_lbl = ttk.Label(control_frame, text="Wave cycles: 0")
        self.result_cycles_lbl.pack(anchor=tk.W, pady=1)
        self.result_expanded_lbl = ttk.Label(control_frame, text="Expanded vertices: 0")
        self.result_expanded_lbl.pack(anchor=tk.W, pady=1)
        self.result_time_lbl = ttk.Label(control_frame, text="Time (algorithm): -")
        self.result_time_lbl.pack(anchor=tk.W, pady=1)
        self.result_path_lbl = ttk.Label(control_frame, text="Path: -", wraplength=300, justify=tk.LEFT)
        self.result_path_lbl.pack(anchor=tk.W, pady=1)

        # Legend
        ttk.Separator(control_frame, orient='horizontal').pack(fill=tk.X, pady=4)
        ttk.Label(control_frame, text="Legend", font=HEADER_FONT).pack(pady=PADY_SECTION, anchor=tk.W)
        for colour, text in [("#000000", "wall (-1)"), ("#ffffff", "free cell (0)"),
                             ("#2ecc71", "start"), ("#e74c3c", "target"),
                             ("#f39c12", "current wave front"),
                             ("#85c1e9", "wave number (darker = later)"),
                             ("#f1c40f", "shortest path")]:
            row = ttk.Frame(control_frame)
            row.pack(anchor=tk.W)
            tk.Label(row, bg=colour, width=2, relief=tk.SOLID, borderwidth=1).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Label(row, text=text).pack(side=tk.LEFT)

        # Maze canvas
        self.canvas = tk.Canvas(self, width=CANVAS_SIZE, height=CANVAS_SIZE, bg="#dddddd",
                                highlightthickness=0)
        self.canvas.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self.on_canvas_click)

    def generate_new_maze(self):
        rows = safe_get_int(self.rows_var, "Rows")
        cols = safe_get_int(self.cols_var, "Columns")
        walls = safe_get_int(self.walls_var, "Walls, %")
        if rows is None or cols is None or walls is None:
            return

        if not (2 <= rows <= 40 and 2 <= cols <= 40):
            messagebox.showerror("Error", "Rows and columns must be between 2 and 40.")
            return
        if not (0 <= walls <= 90):
            messagebox.showerror("Error", "Walls percentage must be between 0 and 90.")
            return
        if not (10 <= rows <= 20 and 10 <= cols <= 20):
            messagebox.showwarning("Warning", "Per the assignment, the maze order should be 10-20.")

        self.logic.generate_grid(rows, cols, walls)
        self._reset_search()

    def clear_maze(self):
        self.logic.clear_walls()
        self._reset_search()

    def on_canvas_click(self, event):
        c = event.x // self.cell
        r = event.y // self.cell
        mode = self.edit_mode_var.get()
        if mode == "wall":
            changed = self.logic.toggle_wall(r, c)
        elif mode == "start":
            changed = self.logic.set_start(r, c)
        else:
            changed = self.logic.set_target(r, c)
        if changed:
            self._reset_search()

    def _reset_search(self):
        self.stop_animation()
        self.search_generator = None
        self.current_state = None
        self.algo_elapsed_ms = 0.0
        self.update_results_ui("Waiting", "-", 0, 0, "-", "-")
        self.draw_maze()

    def draw_maze(self, state=None):
        self.canvas.delete("all")
        rows, cols = self.logic.rows, self.logic.cols
        self.cell = max(10, min(CANVAS_SIZE // rows, CANVAS_SIZE // cols))
        cs = self.cell

        wave = state["wave"] if state else None
        front = set(state["front"]) if state else set()
        path = set(state["path"]) if state and state["status"] == "found" else set()
        max_wave = max((max(row) for row in wave), default=1) if wave else 1
        max_wave = max(max_wave, 1)

        for r in range(rows):
            for c in range(cols):
                x0, y0 = c * cs, r * cs
                value = self.logic.grid[r][c]
                fill, text, text_colour = "#ffffff", str(value), "#999999"

                if value == WALL:
                    fill, text_colour = "#000000", "#ffffff"
                elif wave and wave[r][c] > 0:
                    t = wave[r][c] / max_wave
                    fill = blend("#d6eaf8", "#2874a6", t)
                    text = str(wave[r][c])
                    text_colour = "#000000" if t < 0.6 else "#ffffff"

                if (r, c) in front:
                    fill, text_colour = "#f39c12", "#000000"
                if (r, c) in path:
                    fill, text_colour = "#f1c40f", "#000000"
                if (r, c) == self.logic.start:
                    fill, text_colour = "#2ecc71", "#000000"
                if (r, c) == self.logic.target:
                    fill, text_colour = "#e74c3c", "#ffffff"

                self.canvas.create_rectangle(x0, y0, x0 + cs, y0 + cs, fill=fill, outline="#888888")
                self.canvas.create_text(x0 + cs / 2, y0 + cs / 2, text=text, fill=text_colour,
                                        font=("Arial", max(7, cs // 3)))

    def init_search(self):
        self.stop_animation()
        self.active_operator = self.operator_var.get()

        self.search_generator = self.logic.wave_generator(
            self.logic.start, self.logic.target, self.active_operator)

        self.current_state = None
        self.algo_elapsed_ms = 0.0
        self.update_results_ui("Search initialized", self.active_operator, 0, 0, "-", "-")
        self.draw_maze()

    def _search_finished(self):
        return (
            self.current_state is not None
            and self.current_state.get("status") in ("found", "not_found")
        )

    def _advance(self):
        if not self.search_generator or self._search_finished():
            self.init_search()

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

        self.current_state = state
        self.update_ui_from_state(state)
        return state

    def step_search(self):
        self._advance()

    def run_animated(self):
        self.stop_animation()
        if not self.search_generator or self._search_finished():
            self.init_search()
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
        path_str = " -> ".join(f"({r},{c})" for r, c in state["path"]) if state["path"] else "-"
        header = f"Operator: {state['operator']}\n"

        if state["status"] == "found":
            message = (
                header + "Path found!\n\n"
                f"Path length (steps): {len(state['path']) - 1}\n"
                f"Vertices in path: {len(state['path'])}\n"
                f"Wave cycles: {state['cycles']}\n"
                f"Expanded vertices: {state['expanded']}\n"
                f"Discovered vertices: {state['discovered']}\n"
                f"Execution time (algorithm): {elapsed_time}\n\n"
                f"Path (row, col):\n{path_str}"
            )
            messagebox.showinfo("Search results", message)
        else:
            message = (
                header + "Path not found!\n\n"
                f"Wave cycles: {state['cycles']}\n"
                f"Expanded vertices: {state['expanded']}\n"
                f"Discovered vertices: {state['discovered']}\n"
                f"Execution time (algorithm): {elapsed_time}"
            )
            messagebox.showwarning("Search results", message)

    def update_ui_from_state(self, state):
        status_text = "In progress..."
        elapsed_time = f"{self.algo_elapsed_ms:.3f} ms"
        is_finished = state["status"] in ("found", "not_found")

        if is_finished:
            status_text = "FOUND!" if state["status"] == "found" else "PATH DOES NOT EXIST"
            self.save_results_to_csv(state, elapsed_time)

        path_str = " -> ".join(f"({r},{c})" for r, c in state["path"]) if state["path"] else "-"
        self.update_results_ui(status_text, state["operator"], state["cycles"],
                               state["expanded"], path_str, elapsed_time)
        self.draw_maze(state)

        if is_finished:
            self.after(50, lambda: self.show_result_popup(state, elapsed_time))

    def update_results_ui(self, status, operator, cycles, expanded, path, elapsed_time):
        self.result_status_lbl.config(text=f"Status: {status}")
        self.result_algo_lbl.config(text=f"Operator: {operator}")
        self.result_cycles_lbl.config(text=f"Wave cycles: {cycles}")
        self.result_expanded_lbl.config(text=f"Expanded vertices: {expanded}")
        self.result_time_lbl.config(text=f"Time (algorithm): {elapsed_time}")
        self.result_path_lbl.config(text=f"Path: {path}")

    def compare_operators(self):
        """Runs all operators on the same maze and shows a table in a separate window."""
        self.stop_animation()
        win = tk.Toplevel(self)
        win.title("Operator comparison (same maze, start and target)")
        win.geometry("760x220")

        columns = ("operator", "result", "path", "cycles", "expanded", "discovered", "time")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=5)
        headers = ["Operator", "Result", "Path length", "Wave cycles",
                   "Expanded", "Discovered", "Time, ms"]
        widths = [190, 80, 80, 90, 80, 80, 80]
        for col, head, w in zip(columns, headers, widths):
            tree.heading(col, text=head)
            tree.column(col, width=w, anchor=tk.CENTER)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        for name in OPERATORS:
            state, elapsed = self.logic.run_to_end(name)
            if state is None or "error" in state:
                tree.insert("", tk.END, values=(name, "error", "-", "-", "-", "-", "-"))
                continue
            found = state["status"] == "found"
            tree.insert("", tk.END, values=(
                name,
                "found" if found else "no path",
                len(state["path"]) - 1 if found else "-",
                state["cycles"], state["expanded"], state["discovered"],
                f"{elapsed:.3f}",
            ))

        ttk.Label(win, text=f"Maze {self.logic.rows}x{self.logic.cols}, "
                            f"walls: {self.logic.wall_ratio():.1f}%").pack(pady=(0, 6))

    def save_results_to_csv(self, state, elapsed_time):
        filename = "wave_results.csv"
        file_exists = os.path.isfile(filename)

        with open(filename, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            if not file_exists:
                writer.writerow(["Timestamp", "Operator", "Maze size", "Walls %",
                                 "Start", "Target", "Result", "Path Length",
                                 "Wave cycles", "Expanded", "Discovered", "Time (algo, ms)"])
            found = state["status"] == "found"
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                state["operator"],
                f"{self.logic.rows}x{self.logic.cols}",
                f"{self.logic.wall_ratio():.1f}",
                self.logic.start,
                self.logic.target,
                "found" if found else "not found",
                len(state["path"]) - 1 if found else 0,
                state["cycles"],
                state["expanded"],
                state["discovered"],
                elapsed_time,
            ])


