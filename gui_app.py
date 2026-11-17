from __future__ import annotations

import json
import re
import subprocess
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = None
    ImageTk = None

from recipe_logic import (
    Recipe,
    Ingredient,
    PostupKrok,
    RecipeSection,
    RecipeTime,
    RecipeConflictError,
    UNIT_OPTIONS,
    copy_file_atomic,
    delete_recipe,
    detect_slug_conflict,
    generate_slug,
    get_project_root_from_config,
    load_all_recipes,
    recipe_to_tex,
    save_project_root_to_config,
    save_recipe,
    update_master_index,
    write_json_atomic,
)


class ToolTip:
    def __init__(self, widget: tk.Misc):
        self.widget = widget
        self.tip_window = None
        self.text = ""
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)

    def show(self, event=None):
        if not self.text:
            return
        if self.tip_window is None:
            self.tip_window = tk.Toplevel(self.widget)
            self.tip_window.withdraw()
            self.tip_window.overrideredirect(True)
            self.tip_window.attributes("-topmost", True)
            label = tk.Label(
                self.tip_window,
                text=self.text,
                justify=tk.LEFT,
                background="#1f2937",
                foreground="#ffffff",
                relief=tk.SOLID,
                borderwidth=1,
                padx=8,
                pady=4,
                font=("Segoe UI", 9),
            )
            label.pack()
            self.label = label
        self.tip_window.update_idletasks()
        x = self.widget.winfo_rootx() + 16
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip_window.geometry(f"+{x}+{y}")
        self.tip_window.deiconify()

    def hide(self, event=None):
        if self.tip_window is not None:
            self.tip_window.withdraw()


class RecipeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.app_dir = Path(__file__).resolve().parent
        self.config_path = self.app_dir / "config.json"
        self.window_geometry = "1200x780+120+60"
        self.appearance_mode = self._read_app_config().get("theme_mode", "system")
        ctk.set_appearance_mode(self.appearance_mode)
        ctk.set_default_color_theme("blue")
        ctk.deactivate_automatic_dpi_awareness()

        self.project_root = get_project_root_from_config(self.config_path)
        self.current_slug: str | None = None
        self.original_recipe: Recipe | None = None
        self.recipe_list_items: dict[str, str] = {}
        self.time_rows: list[dict] = []
        self.section_rows: list[dict] = []
        self.ingredient_rows: list[dict] = []
        self.step_rows: list[dict] = []
        self.preview_after_id: str | None = None
        self.toast_after_id: str | None = None
        self._build_ui()
        self._bind_shortcuts()

        if self.project_root.exists():
            self._refresh_recipe_list()
            self._add_empty_recipe()
        else:
            self._show_project_selection()

        self._apply_saved_window_state()
        self.bind("<Configure>", self._on_window_configure)
        self.bind_all("<MouseWheel>", self._handle_mousewheel, add="+")
        self.bind_all("<Button-4>", self._handle_mousewheel, add="+")
        self.bind_all("<Button-5>", self._handle_mousewheel, add="+")

    def _read_app_config(self) -> dict:
        try:
            if not self.config_path.exists():
                return {}
            with self.config_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return {}

    def _write_app_config(self) -> None:
        payload = self._read_app_config()
        payload["project_root"] = str(self.project_root)
        payload["theme_mode"] = str(self.appearance_mode)
        payload["window_geometry"] = self.geometry()
        write_json_atomic(self.config_path, payload)

    def _apply_saved_window_state(self) -> None:
        payload = self._read_app_config()
        geometry = payload.get("window_geometry")
        if isinstance(geometry, str) and geometry:
            try:
                self.geometry(geometry)
            except tk.TclError:
                pass
        self.minsize(1100, 700)

    def _on_window_configure(self, event=None):
        if event and event.widget is self:
            geometry = self.geometry()
            if geometry:
                self.window_geometry = geometry
                self._save_window_state_later()

    def _save_window_state_later(self):
        self.after_idle(self._persist_window_state)

    def _persist_window_state(self):
        self._write_app_config()

    def _build_ui(self):
        self.title("Kuchařka")
        self.geometry("1200x780")
        self.minsize(1100, 700)
        self.configure(fg_color=("#f3f4f6", "#111827"))

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.shell = ctk.CTkFrame(self, corner_radius=18, fg_color=("#f4f6fb", "#1f2937"))
        self.shell.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.shell.grid_rowconfigure(0, weight=1)
        self.shell.grid_columnconfigure(0, weight=0)
        self.shell.grid_columnconfigure(1, weight=3)
        self.shell.grid_columnconfigure(2, weight=2)

        self.left_panel = ctk.CTkFrame(self.shell, width=260, corner_radius=18, fg_color=("#ffffff", "#111827"))
        self.left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.left_panel.grid_rowconfigure(1, weight=0)
        self.left_panel.grid_rowconfigure(2, weight=1)
        self.left_panel.grid_rowconfigure(3, weight=0)

        self.header_label = ctk.CTkLabel(
            self.left_panel,
            text="Kuchařka",
            font=("Segoe UI", 20, "bold"),
            text_color=("#1f2937", "#f8fafc"),
            anchor="w",
        )
        self.header_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))

        self.search_entry = ctk.CTkEntry(self.left_panel, placeholder_text="Vyhledat recept", height=36)
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.search_entry.bind("<KeyRelease>", self._on_search_change)
        self.search_entry.bind("<Control-f>", lambda event: self.search_entry.focus_set())

        self.recipe_cards_frame = ctk.CTkScrollableFrame(self.left_panel, corner_radius=14, fg_color=("#f7f7fa", "#0f172a"))
        self.recipe_cards_frame.grid(row=2, column=0, sticky="nsew", padx=18)
        self.recipe_cards_frame.grid_columnconfigure(0, weight=1)

        self.recipe_buttons: dict[str, ctk.CTkButton] = {}

        self.left_actions = ctk.CTkFrame(self.left_panel, corner_radius=14, fg_color=("#f5f7fb", "#1e293b"))
        self.left_actions.grid(row=3, column=0, sticky="ew", padx=18, pady=(12, 10))
        self.left_actions.grid_columnconfigure(0, weight=1)
        self.left_actions.grid_columnconfigure(1, weight=1)

        self.new_recipe_btn = ctk.CTkButton(self.left_actions, text="+ Nový recept", command=self._add_empty_recipe, fg_color="#C0392B", hover_color="#a82d23")
        self.new_recipe_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.delete_recipe_btn = ctk.CTkButton(self.left_actions, text="Smazat", command=self.delete_current_recipe, fg_color=("#e7ebf3", "#334155"), text_color=("#15212f", "#f8fafc"), hover_color=("#dfe7f2", "#475569"))
        self.delete_recipe_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.project_path_label = ctk.CTkLabel(self.left_panel, text="Projekt: ...", anchor="w", text_color=("#5b6678", "#cbd5e1"), font=("Segoe UI", 9))
        self.project_path_label.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 8))
        self.project_path_label_tooltip = ToolTip(self.project_path_label)
        self.project_path_label.bind("<Button-1>", lambda event: self.choose_project_folder())

        self.change_project_btn = ctk.CTkButton(
            self.left_panel,
            text="Změnit",
            width=80,
            height=28,
            command=self.choose_project_folder,
            fg_color=("#edf3ff", "#334155"),
            text_color=("#1f2937", "#f8fafc"),
            hover_color=("#e0e9ff", "#475569"),
        )
        self.change_project_btn.grid(row=5, column=0, sticky="ew", padx=18, pady=(0, 16))

        self.main_panel = ctk.CTkFrame(self.shell, corner_radius=18, fg_color=("#ffffff", "#111827"))
        self.main_panel.grid(row=0, column=1, sticky="nsew")
        self.main_panel.grid_rowconfigure(0, weight=0)
        self.main_panel.grid_rowconfigure(1, weight=1)
        self.main_panel.grid_columnconfigure(0, weight=1)

        self.toolbar = ctk.CTkFrame(self.main_panel, corner_radius=14, fg_color=("#fff8f4", "#1e293b"))
        self.toolbar.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        self.toolbar.grid_columnconfigure(0, weight=1)
        self.toolbar.grid_columnconfigure(1, weight=1)
        self.toolbar.grid_columnconfigure(2, weight=1)
        self.toolbar.grid_columnconfigure(3, weight=1)
        self.toolbar.grid_columnconfigure(4, weight=1)

        self.save_button = ctk.CTkButton(self.toolbar, text="Uložit", command=self.save_current_recipe, fg_color="#C0392B", hover_color="#a72f26")
        self.save_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.preview_toggle_btn = ctk.CTkButton(self.toolbar, text="Náhled", command=self._toggle_preview_panel, fg_color=("#e9eef8", "#334155"), text_color=("#15212f", "#f8fafc"), hover_color=("#dfe8f8", "#475569"))
        self.preview_toggle_btn.grid(row=0, column=1, sticky="ew", padx=6)
        self.new_top_btn = ctk.CTkButton(self.toolbar, text="Nový recept", command=self._add_empty_recipe, fg_color=("#eef3ff", "#334155"), text_color=("#15212f", "#f8fafc"), hover_color=("#e2eafc", "#475569"))
        self.new_top_btn.grid(row=0, column=2, sticky="ew", padx=6)
        self.index_btn = ctk.CTkButton(self.toolbar, text="Sestavit index", command=self.rebuild_index, fg_color=("#eef3ff", "#334155"), text_color=("#15212f", "#f8fafc"), hover_color=("#e2eafc", "#475569"))
        self.index_btn.grid(row=0, column=3, sticky="ew", padx=6)
        self.git_push_btn = ctk.CTkButton(self.toolbar, text="Nahrát nové recepty na git", command=self.push_changes_to_git, fg_color=("#dbeafe", "#1d4ed8"), text_color=("#0f172a", "#ffffff"), hover_color=("#bfdbfe", "#1e40af"))
        self.git_push_btn.grid(row=0, column=4, sticky="ew", padx=(6, 0))

        self.form_scroll = ctk.CTkScrollableFrame(self.main_panel, corner_radius=16, fg_color=("#ffffff", "#0b1220"))
        self.form_scroll.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.form_scroll.grid_columnconfigure(0, weight=1)

        self.form_container = ctk.CTkFrame(self.form_scroll, fg_color="transparent")
        self.form_container.grid(row=0, column=0, sticky="ew")
        self.form_container.grid_columnconfigure(1, weight=1)

        self.empty_state = ctk.CTkLabel(
            self.form_container,
            text="Vyber recept vlevo nebo vytvoř nový",
            font=("Segoe UI", 18, "bold"),
            text_color="#7a8191",
            anchor="center",
        )
        self.empty_state.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=60)

        self.preview_panel = ctk.CTkFrame(self.shell, width=460, corner_radius=18, fg_color=("#ffffff", "#111827"))
        self.preview_panel.grid(row=0, column=2, sticky="nsew")
        self.preview_panel.grid_columnconfigure(0, weight=1)
        self.preview_panel.grid_rowconfigure(0, weight=1)

        self.preview_tabview = ctk.CTkTabview(self.preview_panel, height=200)
        self.preview_tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.preview_tabview.add("Náhled")
        self.preview_tabview.add("LaTeX")
        self.preview_tabview.set("Náhled")

        self.preview_tabview.tab("Náhled").grid_columnconfigure(0, weight=1)
        self.preview_tabview.tab("Náhled").grid_rowconfigure(0, weight=1)
        self.preview_tabview.tab("LaTeX").grid_columnconfigure(0, weight=1)
        self.preview_tabview.tab("LaTeX").grid_rowconfigure(0, weight=1)

        self.preview_scroll = ctk.CTkScrollableFrame(self.preview_tabview.tab("Náhled"), corner_radius=16, fg_color=("#fffaf7", "#0f172a"))
        self.preview_scroll.grid(row=0, column=0, sticky="nsew")
        self.preview_scroll.grid_columnconfigure(0, weight=1)

        self.preview_latex = ctk.CTkTextbox(self.preview_tabview.tab("LaTeX"), wrap="word", height=20)
        self.preview_latex.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        self.toast = ctk.CTkLabel(
            self,
            text="",
            fg_color="#1f2937",
            corner_radius=10,
            text_color="#ffffff",
            font=("Segoe UI", 10, "bold"),
            padx=16,
            pady=12,
        )
        self.toast.place(relx=0.5, rely=0.97, anchor="s")
        self.toast.place_forget()

        self._setup_dark_mode_toggle()
        self._update_project_label()
        self._render_recipe_cards(force=True)
        self._render_preview()

    def _setup_dark_mode_toggle(self):
        self.theme_switch = ctk.CTkSwitch(self.left_panel, text="Tmavý režim")
        self.theme_switch.grid(row=6, column=0, sticky="ew", padx=18, pady=(0, 10))
        self.theme_switch.configure(command=self._toggle_theme_mode)
        self.theme_switch.select() if self.appearance_mode == "dark" else self.theme_switch.deselect()

    def _toggle_theme_mode(self):
        self.appearance_mode = "dark" if self.theme_switch.get() else "light"
        ctk.set_appearance_mode(self.appearance_mode)
        self._render_recipe_cards(force=True)
        self._render_preview()
        self._persist_window_state()

    def _run_git_command(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )

    def push_changes_to_git(self):
        if not messagebox.askyesno("Git", "Nahrát nové recepty na git?\n\nAplikace provede: add, commit, push."):
            return

        if not self.project_root.exists():
            messagebox.showerror("Git", "Projektová složka neexistuje.")
            return

        inside = self._run_git_command(["git", "rev-parse", "--is-inside-work-tree"])
        if inside.returncode != 0:
            messagebox.showerror("Git", "V projektu není inicializovaný git repozitář.")
            return

        candidates = [
            self.project_root / "data",
            self.project_root / "recepty",
            self.project_root / "obrazky",
            self.project_root / "docs" / "recepty.json",
            self.project_root / "seznam-receptu.tex",
        ]
        add_paths = [str(path.relative_to(self.project_root)) for path in candidates if path.exists()]
        if not add_paths:
            self.show_toast("Git: Žádné soubory k nahrání")
            return

        add_result = self._run_git_command(["git", "add", "--", *add_paths])
        if add_result.returncode != 0:
            messagebox.showerror("Git", f"Nepodařilo se přidat soubory:\n{add_result.stderr.strip()}")
            return

        staged = self._run_git_command(["git", "diff", "--cached", "--name-only"])
        if staged.returncode != 0:
            messagebox.showerror("Git", f"Nepodařilo se zjistit staged změny:\n{staged.stderr.strip()}")
            return
        changed_files = [line.strip() for line in staged.stdout.splitlines() if line.strip()]
        if not changed_files:
            self.show_toast("Git: Žádné nové změny k odeslání")
            return

        commit_message = f"Aktualizace receptu {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        commit_result = self._run_git_command(["git", "commit", "-m", commit_message])
        if commit_result.returncode != 0:
            messagebox.showerror("Git", f"Commit selhal:\n{commit_result.stderr.strip() or commit_result.stdout.strip()}")
            return

        push_result = self._run_git_command(["git", "push"])
        if push_result.returncode != 0:
            messagebox.showerror("Git", f"Push selhal:\n{push_result.stderr.strip() or push_result.stdout.strip()}")
            return

        self.show_toast(f"Git: Odesláno {len(changed_files)} souborů")

    def _handle_mousewheel(self, event):
        if not self.form_scroll.winfo_exists() or not self.form_scroll.winfo_viewable():
            return "break"
        pointer_x = self.winfo_pointerx()
        pointer_y = self.winfo_pointery()
        form_x1 = self.form_scroll.winfo_rootx()
        form_y1 = self.form_scroll.winfo_rooty()
        form_x2 = form_x1 + self.form_scroll.winfo_width()
        form_y2 = form_y1 + self.form_scroll.winfo_height()
        if not (form_x1 <= pointer_x <= form_x2 and form_y1 <= pointer_y <= form_y2):
            return None

        delta = getattr(event, "delta", 0)
        if getattr(event, "num", None) == 4:
            steps = -3
        elif getattr(event, "num", None) == 5:
            steps = 3
        elif delta:
            base = max(1, int(abs(delta) / 120))
            steps = -base * 3 if delta > 0 else base * 3
        else:
            return "break"
        scroll_widget = getattr(self.form_scroll, "_parent_canvas", None)
        if scroll_widget is not None:
            scroll_widget.yview_scroll(steps, "units")
        return "break"

    def _toggle_preview_panel(self):
        if self.preview_panel.winfo_ismapped():
            self.preview_panel.grid_remove()
            self.preview_toggle_btn.configure(text="Zobrazit náhled")
            self.shell.grid_columnconfigure(1, weight=1)
            self.shell.grid_columnconfigure(2, weight=0)
        else:
            self.preview_panel.grid()
            self.preview_toggle_btn.configure(text="Náhled")
            self.shell.grid_columnconfigure(1, weight=3)
            self.shell.grid_columnconfigure(2, weight=2)

    def _update_project_label(self):
        project_text = str(self.project_root)
        if not project_text:
            project_text = "Projekt: nepřipraven"
        short = project_text
        if len(short) > 36:
            short = "..." + short[-33:]
        self.project_path_label.configure(text=f"Projekt: {short}")
        self.project_path_label_tooltip.text = project_text

    def _bind_shortcuts(self):
        self.bind_all("<Control-s>", lambda event: self.save_current_recipe())
        self.bind_all("<Control-n>", lambda event: self._add_empty_recipe())
        self.bind_all("<Control-f>", lambda event: self.search_entry.focus_set() or "break")
        self.bind_all("<Escape>", lambda event: self.search_entry.focus_set() if self.search_entry else None)

    def _show_project_selection(self):
        if not self.project_root.exists():
            messagebox.showinfo("Adresář projektu", "Vyberte složku projektu, ve kterém je struktura kuchařky.")
        self.choose_project_folder()

    def choose_project_folder(self):
        directory = filedialog.askdirectory(title="Vyberte složku projektu")
        if not directory:
            return
        self.project_root = Path(directory).resolve()
        save_project_root_to_config(self.config_path, self.project_root)
        self._write_app_config()
        self._update_project_label()
        self._refresh_recipe_list()
        self._add_empty_recipe()

    def _on_search_change(self, event=None):
        self._render_recipe_cards()

    def _render_recipe_cards(self, force: bool = False):
        for widget in self.recipe_cards_frame.winfo_children():
            widget.destroy()
        self.recipe_buttons.clear()

        search_term = self.search_entry.get().strip().lower()
        recipes = load_all_recipes(self.project_root) if self.project_root.exists() else []
        visible = []
        for recipe in recipes:
            if not search_term or search_term in recipe.nazev.lower() or search_term in recipe.cas.lower() or search_term in recipe.porce.lower():
                visible.append(recipe)

        if not visible:
            empty = ctk.CTkLabel(self.recipe_cards_frame, text="Žádné recepty", text_color=("#7a8191", "#cbd5e1"))
            empty.grid(row=0, column=0, sticky="ew", padx=8, pady=20)
            return

        for index, recipe in enumerate(visible):
            card_time = recipe.cas or "—"
            if recipe.casy:
                first = next((item for item in recipe.casy if item.hodnota.strip()), None)
                if first is not None:
                    label = first.popis.strip() or "Čas"
                    card_time = f"{label}: {first.hodnota}"
            card = ctk.CTkButton(
                self.recipe_cards_frame,
                text=f"{recipe.nazev}\n{card_time} • {recipe.porce or '—'}",
                anchor="w",
                height=74,
                fg_color=("#ffffff", "#1f2937") if self.current_slug != recipe.slug else "#C0392B",
                hover_color=("#f6d7d1", "#334155") if self.current_slug != recipe.slug else "#a82d23",
                text_color=("#1f2937", "#f8fafc") if self.current_slug != recipe.slug else "#ffffff",
                corner_radius=12,
                command=lambda slug=recipe.slug: self._select_recipe(slug),
            )
            card.grid(row=index, column=0, sticky="ew", padx=4, pady=(0, 8))
            self.recipe_buttons[recipe.slug] = card

    def _select_recipe(self, slug: str):
        if self._has_unsaved_changes():
            answer = messagebox.askyesnocancel("Neuložené změny", "Uložit aktuální recept?")
            if answer is None:
                return
            if answer and not self.save_current_recipe():
                return
        self._load_recipe(slug)

    def _add_empty_recipe(self):
        if self._has_unsaved_changes():
            answer = messagebox.askyesnocancel("Neuložené změny", "Uložit aktuální recept?")
            if answer is None:
                return
            if answer:
                self.save_current_recipe()
        self._clear_form()
        self.current_slug = None
        self.original_recipe = self._collect_form_data()
        self.root_title_update()
        self._render_recipe_cards()

    def _clear_form(self):
        for widget in self.form_container.winfo_children():
            widget.destroy()
        self.ingredient_rows = []
        self.step_rows = []
        self.time_rows = []
        self.section_rows = []
        self.empty_state = ctk.CTkLabel(
            self.form_container,
            text="Vyber recept vlevo nebo vytvoř nový",
            font=("Segoe UI", 18, "bold"),
            text_color="#7a8191",
            anchor="center",
        )
        self.empty_state.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=60)
        self._build_form_fields()
        self._render_preview()

    def _build_form_fields(self):
        for child in self.form_container.winfo_children():
            child.grid_forget()
        self.form_container.grid_columnconfigure(1, weight=1)

        self.empty_state = ctk.CTkLabel(
            self.form_container,
            text="",
            height=0,
            anchor="center",
            text_color="#7a8191",
        )
        self.empty_state.grid_forget()

        row = 0
        self.nazev_var = tk.StringVar()
        ctk.CTkLabel(self.form_container, text="Název receptu", anchor="w", text_color="#5b6678").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=(6, 6))
        self.nazev_entry = ctk.CTkEntry(self.form_container, textvariable=self.nazev_var, height=42)
        self.nazev_entry.grid(row=row, column=1, sticky="ew", pady=(6, 6))
        self.nazev_var.trace_add("write", lambda *_: self._mark_dirty())
        self.nazev_entry.bind("<FocusOut>", lambda event: self._schedule_preview_update())
        row += 1

        self.cas_var = tk.StringVar()
        ctk.CTkLabel(self.form_container, text="Hlavní čas", anchor="w", text_color="#5b6678").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=(6, 6))
        self.cas_entry = ctk.CTkEntry(self.form_container, textvariable=self.cas_var, width=220)
        self.cas_entry.grid(row=row, column=1, sticky="ew", pady=(6, 6))
        self.cas_var.trace_add("write", lambda *_: self._schedule_preview_update())
        row += 1

        ctk.CTkLabel(self.form_container, text="Časy receptu", font=("Segoe UI", 16, "bold"), anchor="w", text_color="#1f2937").grid(row=row, column=0, columnspan=2, sticky="ew", pady=(14, 8))
        row += 1

        self.times_section = ctk.CTkFrame(self.form_container, corner_radius=14, fg_color="#f8fafc")
        self.times_section.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.times_section.grid_columnconfigure(0, weight=1)
        self.times_container = ctk.CTkFrame(self.times_section, fg_color="transparent")
        self.times_container.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        self.times_container.grid_columnconfigure(0, weight=1)
        self.times_container.grid_columnconfigure(1, weight=1)
        self.add_time_btn = ctk.CTkButton(self.times_section, text="+ Přidat čas", command=self._add_time_row, fg_color="#edf3ff", text_color="#15212f", hover_color="#e2eafc")
        self.add_time_btn.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        row += 1

        self.porce_var = tk.StringVar()
        ctk.CTkLabel(self.form_container, text="Počet porcí", anchor="w", text_color="#5b6678").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=(6, 6))
        self.porce_entry = ctk.CTkEntry(self.form_container, textvariable=self.porce_var, width=220)
        self.porce_entry.grid(row=row, column=1, sticky="ew", pady=(6, 6))
        self.porce_var.trace_add("write", lambda *_: self._schedule_preview_update())
        row += 1

        self.obtiznost_var = tk.StringVar()
        ctk.CTkLabel(self.form_container, text="Obtížnost", anchor="w", text_color="#5b6678").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=(6, 6))
        self.obtiznost_combo = ctk.CTkComboBox(self.form_container, values=["snadná", "střední", "náročná"], variable=self.obtiznost_var)
        self.obtiznost_combo.grid(row=row, column=1, sticky="ew", pady=(6, 6))
        self.obtiznost_var.trace_add("write", lambda *_: self._schedule_preview_update())
        row += 1

        self.foto_var = tk.StringVar()
        ctk.CTkLabel(self.form_container, text="Foto", anchor="w", text_color="#5b6678").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=(6, 6))
        photo_row = ctk.CTkFrame(self.form_container, corner_radius=12, fg_color="#f8fafc")
        photo_row.grid(row=row, column=1, sticky="ew", pady=(6, 6))
        photo_row.grid_columnconfigure(0, weight=1)
        self.foto_entry = ctk.CTkEntry(photo_row, textvariable=self.foto_var)
        self.foto_entry.grid(row=0, column=0, sticky="ew", padx=(8, 6), pady=8)
        self.photo_button = ctk.CTkButton(photo_row, text="Vybrat", command=self._choose_photo, width=100, fg_color="#edf3ff", text_color="#15212f", hover_color="#e0e9ff")
        self.photo_button.grid(row=0, column=1, sticky="e", padx=(0, 8), pady=8)
        self.photo_preview = ctk.CTkLabel(photo_row, text="", width=64, height=52, corner_radius=10, fg_color="#edf2f7")
        self.photo_preview.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))
        self.foto_var.trace_add("write", lambda *_: self._schedule_preview_update())
        row += 1

        ctk.CTkLabel(self.form_container, text="Části receptu", font=("Segoe UI", 16, "bold"), anchor="w", text_color="#1f2937").grid(row=row, column=0, columnspan=2, sticky="ew", pady=(18, 8))
        row += 1

        self.sections_wrapper = ctk.CTkFrame(self.form_container, corner_radius=14, fg_color="#f8fafc")
        self.sections_wrapper.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.sections_wrapper.grid_columnconfigure(0, weight=1)
        self.sections_container = ctk.CTkFrame(self.sections_wrapper, fg_color="transparent")
        self.sections_container.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        self.sections_container.grid_columnconfigure(0, weight=1)
        self.add_section_btn = ctk.CTkButton(self.sections_wrapper, text="+ Přidat část (např. marináda)", command=self._add_section_block, fg_color="#edf3ff", text_color="#15212f", hover_color="#e2eafc")
        self.add_section_btn.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        row += 1

        ctk.CTkLabel(self.form_container, text="Tip", font=("Segoe UI", 16, "bold"), anchor="w", text_color="#1f2937").grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=(18, 8))
        self.tip_var = tk.StringVar()
        self.tip_text = ctk.CTkTextbox(self.form_container, height=120, wrap="word")
        self.tip_text.grid(row=row, column=1, sticky="ew", pady=(18, 8))
        self.tip_text.bind("<KeyRelease>", lambda event: self._schedule_preview_update())
        self.tip_text.bind("<KeyRelease>", lambda event: self._mark_dirty())
        row += 1

        self._set_status("Připraveno")
        self._render_picture_preview()
        self._add_time_row({"popis": "Příprava", "hodnota": ""})
        self._add_section_block({"nazev": "Hlavní část", "cas": "", "ingredience": [], "postup": []})

    def _add_time_row(self, data: dict | None = None):
        frame = ctk.CTkFrame(self.times_container, fg_color=("#ffffff", "#1f2937"), corner_radius=10)
        frame.grid(sticky="ew", pady=4)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        popis = ctk.CTkEntry(frame, placeholder_text="Např. Marinování")
        popis.grid(row=0, column=0, sticky="ew", padx=(8, 6), pady=8)
        hodnota = ctk.CTkEntry(frame, placeholder_text="Např. 12 h")
        hodnota.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=8)
        delete = ctk.CTkButton(frame, text="✕", width=30, height=24, fg_color=("#f9e7e3", "#7f1d1d"), text_color=("#C0392B", "#fecaca"), command=lambda: self._remove_time_row(frame))
        delete.grid(row=0, column=2, padx=(0, 8), pady=8)

        if data:
            popis.insert(0, data.get("popis", ""))
            hodnota.insert(0, data.get("hodnota", ""))

        popis.bind("<KeyRelease>", lambda _e: self._schedule_preview_update())
        hodnota.bind("<KeyRelease>", lambda _e: self._schedule_preview_update())
        popis.bind("<KeyRelease>", lambda _e: self._mark_dirty())
        hodnota.bind("<KeyRelease>", lambda _e: self._mark_dirty())
        self.time_rows.append({"frame": frame, "popis": popis, "hodnota": hodnota})

    def _remove_time_row(self, frame):
        for idx, item in enumerate(self.time_rows):
            if item["frame"] is frame:
                del self.time_rows[idx]
                frame.destroy()
                break
        self._schedule_preview_update()
        self._mark_dirty()

    def _add_section_block(self, data: dict | None = None):
        card = ctk.CTkFrame(self.sections_container, fg_color=("#ffffff", "#1f2937"), corner_radius=12)
        card.grid(sticky="ew", pady=8)
        card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(card, text="Část", text_color=("#5b6678", "#cbd5e1")).grid(row=0, column=0, sticky="w", padx=(10, 6), pady=(10, 4))
        section_name = ctk.CTkEntry(card, placeholder_text="Např. Marináda")
        section_name.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(10, 4))
        remove_btn = ctk.CTkButton(card, text="✕", width=30, height=24, fg_color=("#f9e7e3", "#7f1d1d"), text_color=("#C0392B", "#fecaca"), command=lambda: self._remove_section_block(card))
        remove_btn.grid(row=0, column=2, padx=(0, 10), pady=(10, 4))

        ctk.CTkLabel(card, text="Čas části", text_color=("#5b6678", "#cbd5e1")).grid(row=1, column=0, sticky="w", padx=(10, 6), pady=4)
        section_time = ctk.CTkEntry(card, placeholder_text="Např. 12 h")
        section_time.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=4)

        ctk.CTkLabel(card, text="Ingredience (1 řádek = 1 položka)", text_color=("#5b6678", "#cbd5e1")).grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        ingredients_text = ctk.CTkTextbox(card, height=90, wrap="word")
        ingredients_text.grid(row=3, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 6))

        ctk.CTkLabel(card, text="Postup (1 řádek = 1 krok)", text_color=("#5b6678", "#cbd5e1")).grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        steps_text = ctk.CTkTextbox(card, height=110, wrap="word")
        steps_text.grid(row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=(0, 10))

        if data:
            section_name.insert(0, data.get("nazev", ""))
            section_time.insert(0, data.get("cas", ""))
            ingredients_lines = []
            for item in data.get("ingredience", []):
                if isinstance(item, Ingredient):
                    line = " ".join(part for part in [item.mnozstvi, item.jednotka, item.nazev] if part).strip()
                elif isinstance(item, dict):
                    line = " ".join(part for part in [item.get("mnozstvi", ""), item.get("jednotka", ""), item.get("nazev", "")] if part).strip()
                else:
                    line = str(item)
                if line:
                    ingredients_lines.append(line)
            steps_lines = []
            for item in data.get("postup", []):
                if isinstance(item, PostupKrok):
                    line = item.text
                elif isinstance(item, dict):
                    line = str(item.get("text", ""))
                else:
                    line = str(item)
                if line:
                    steps_lines.append(line)
            ingredients_text.insert("1.0", "\n".join(ingredients_lines))
            steps_text.insert("1.0", "\n".join(steps_lines))

        for widget in (section_name, section_time, ingredients_text, steps_text):
            widget.bind("<KeyRelease>", lambda _e: self._schedule_preview_update())
            widget.bind("<KeyRelease>", lambda _e: self._mark_dirty())

        self.section_rows.append(
            {
                "frame": card,
                "nazev": section_name,
                "cas": section_time,
                "ingredience_text": ingredients_text,
                "postup_text": steps_text,
            }
        )

    def _remove_section_block(self, frame):
        for idx, item in enumerate(self.section_rows):
            if item["frame"] is frame:
                del self.section_rows[idx]
                frame.destroy()
                break
        if not self.section_rows:
            self._add_section_block({"nazev": "Hlavní část", "cas": "", "ingredience": [], "postup": []})
        self._schedule_preview_update()
        self._mark_dirty()

    def _mark_dirty(self):
        if self.original_recipe is None:
            return
        current = self._collect_form_data()
        if self.original_recipe.to_dict() != current.to_dict():
            self.root_title_update("*")
        else:
            self.root_title_update()

    def root_title_update(self, marker: str = "") -> None:
        suffix = " *" if marker else ""
        self.title(f"Kuchařka{suffix}")

    def _choose_photo(self):
        chosen = filedialog.askopenfilename(title="Vyberte fotografii", filetypes=[("Obrázky", "*.png *.jpg *.jpeg *.webp *.bmp")])
        if not chosen:
            return
        source = Path(chosen)
        destination = self.project_root / "obrazky" / source.name
        try:
            if destination.exists():
                destination.unlink()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            docs_destination = self.project_root / "docs" / "obrazky" / source.name
            copy_file_atomic(source, docs_destination)
            self.foto_var.set(source.name)
            self._render_picture_preview()
            self._schedule_preview_update()
            self._mark_dirty()
        except OSError as exc:
            messagebox.showerror("Chyba při kopírování obrázku", str(exc))

    def _render_picture_preview(self):
        if not hasattr(self, "photo_preview"):
            return
        value = self.foto_var.get().strip() if hasattr(self, "foto_var") else ""
        if not value:
            self.photo_preview.configure(text="Bez obrázku", fg_color="#edf2f7", text_color="#5b6678")
            return
        source = self.project_root / "obrazky" / value
        if not source.exists():
            self.photo_preview.configure(text=value, fg_color="#edf2f7", text_color="#5b6678")
            return
        if Image is not None:
            try:
                image = Image.open(source).convert("RGB")
                image = image.resize((90, 90), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self.photo_preview.configure(image=photo, text="", fg_color="#edf2f7")
                self.photo_preview.image = photo
                return
            except Exception:
                pass
        self.photo_preview.configure(text=value, fg_color="#edf2f7", text_color="#5b6678")

    def _add_ingredient_row(self, data: dict | None = None):
        frame = ctk.CTkFrame(self.ingredients_container, fg_color="#ffffff", corner_radius=10)
        frame.grid(sticky="ew", pady=6)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=2)

        qty = ctk.CTkEntry(frame, width=72, placeholder_text="Množství")
        qty.grid(row=0, column=0, sticky="ew", padx=(8, 6), pady=8)

        unit = ctk.CTkComboBox(frame, values=UNIT_OPTIONS, width=100)
        unit.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=8)
        unit.set(data.get("jednotka", "") if data else "")

        name = ctk.CTkEntry(frame, placeholder_text="Název ingredience")
        name.grid(row=0, column=2, sticky="ew", padx=(0, 6), pady=8)

        if data:
            qty.insert(0, data.get("mnozstvi", ""))
            name.insert(0, data.get("nazev", ""))

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.grid(row=0, column=3, sticky="e", padx=(4, 8), pady=8)
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)
        buttons.grid_columnconfigure(2, weight=1)

        up = ctk.CTkButton(buttons, text="↑", width=30, height=24, command=lambda: self._move_ingredient_row(frame, -1), fg_color="#edf3ff", text_color="#15212f")
        down = ctk.CTkButton(buttons, text="↓", width=30, height=24, command=lambda: self._move_ingredient_row(frame, 1), fg_color="#edf3ff", text_color="#15212f")
        delete = ctk.CTkButton(buttons, text="✕", width=30, height=24, command=lambda: self._remove_ingredient_row(frame), fg_color="#f9e7e3", text_color="#C0392B")
        up.grid(row=0, column=0, padx=2)
        down.grid(row=0, column=1, padx=2)
        delete.grid(row=0, column=2, padx=2)

        name.bind("<Return>", lambda event: self._add_ingredient_row_after(frame))
        qty.bind("<Return>", lambda event: self._add_ingredient_row_after(frame))

        self.ingredient_rows.append({"frame": frame, "mnozstvi": qty, "jednotka": unit, "nazev": name, "widgets": [qty, unit, name, up, down, delete]})
        self._schedule_preview_update(); self._mark_dirty()

    def _add_ingredient_row_after(self, current_frame):
        for index, item in enumerate(self.ingredient_rows):
            if item["frame"] is current_frame:
                inserted = self._find_ingredient_insert_index(current_frame)
                if inserted is not None:
                    self._add_ingredient_row()
                    self.ingredient_rows[-1]["nazev"].focus_set()
                return

    def _find_ingredient_insert_index(self, current_frame):
        for index, item in enumerate(self.ingredient_rows):
            if item["frame"] is current_frame:
                return index
        return None

    def _remove_ingredient_row(self, frame):
        for idx, item in enumerate(self.ingredient_rows):
            if item["frame"] is frame:
                del self.ingredient_rows[idx]
                frame.destroy()
                break
        self._schedule_preview_update(); self._mark_dirty()

    def _move_ingredient_row(self, frame, direction):
        idx = next((i for i, item in enumerate(self.ingredient_rows) if item["frame"] is frame), None)
        if idx is None:
            return
        target = idx + direction
        if target < 0 or target >= len(self.ingredient_rows):
            return
        self.ingredient_rows[idx], self.ingredient_rows[target] = self.ingredient_rows[target], self.ingredient_rows[idx]
        for row in self.ingredient_rows:
            row["frame"].grid_forget()
        for i, row in enumerate(self.ingredient_rows):
            row["frame"].grid(row=i, sticky="ew", pady=6)
        self._schedule_preview_update(); self._mark_dirty()

    def _add_step_row(self, data: dict | None = None):
        step = ctk.CTkFrame(self.steps_container, fg_color="#ffffff", corner_radius=12)
        step.grid(sticky="ew", pady=8)
        step.grid_columnconfigure(0, weight=1)
        step.grid_columnconfigure(1, weight=0)

        number = ctk.CTkLabel(step, text=f"{len(self.step_rows) + 1}.", width=26, font=("Segoe UI", 12, "bold"), text_color="#C0392B")
        number.grid(row=0, column=0, sticky="nw", padx=(12, 6), pady=(10, 0))

        text_widget = ctk.CTkTextbox(step, height=110, wrap="word")
        text_widget.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(10, 0))
        if data:
            text_widget.insert("0.0", data.get("text", ""))

        timer_row = ctk.CTkFrame(step, fg_color="transparent")
        timer_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 10))
        timer_row.grid_columnconfigure(0, weight=1)
        timer_row.grid_columnconfigure(1, weight=0)

        timer_label = ctk.CTkLabel(timer_row, text="Časovač (min)", text_color="#5b6678")
        timer_label.grid(row=0, column=0, sticky="w")
        timer_entry = ctk.CTkEntry(timer_row, width=90)
        timer_entry.grid(row=0, column=1, sticky="e", padx=(8, 0))
        if data and data.get("casovac_min") is not None:
            timer_entry.insert(0, str(data["casovac_min"]))

        buttons = ctk.CTkFrame(step, fg_color="transparent")
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", padx=12, pady=(0, 12))
        up = ctk.CTkButton(buttons, text="↑", width=30, height=24, command=lambda: self._move_step_row(step, -1), fg_color="#edf3ff", text_color="#15212f")
        down = ctk.CTkButton(buttons, text="↓", width=30, height=24, command=lambda: self._move_step_row(step, 1), fg_color="#edf3ff", text_color="#15212f")
        delete = ctk.CTkButton(buttons, text="✕", width=30, height=24, command=lambda: self._remove_step_row(step), fg_color="#f9e7e3", text_color="#C0392B")
        up.grid(row=0, column=0, padx=2)
        down.grid(row=0, column=1, padx=2)
        delete.grid(row=0, column=2, padx=2)

        text_widget.bind("<Control-Return>", lambda event: self._add_step_row())
        text_widget.bind("<KeyRelease>", lambda event: self._schedule_preview_update())
        timer_entry.bind("<KeyRelease>", lambda event: self._schedule_preview_update())

        self.step_rows.append({"frame": step, "text": text_widget, "timer": timer_entry, "widgets": [text_widget, timer_entry, up, down, delete]})
        self._mark_dirty(); self._schedule_preview_update()

    def _remove_step_row(self, frame):
        for idx, item in enumerate(self.step_rows):
            if item["frame"] is frame:
                del self.step_rows[idx]
                frame.destroy()
                break
        self._renumber_steps(); self._schedule_preview_update(); self._mark_dirty()

    def _move_step_row(self, frame, direction):
        idx = next((i for i, item in enumerate(self.step_rows) if item["frame"] is frame), None)
        if idx is None:
            return
        target = idx + direction
        if target < 0 or target >= len(self.step_rows):
            return
        self.step_rows[idx], self.step_rows[target] = self.step_rows[target], self.step_rows[idx]
        for row in self.step_rows:
            row["frame"].grid_forget()
        for i, row in enumerate(self.step_rows):
            row["frame"].grid(row=i, sticky="ew", pady=8)
        self._renumber_steps(); self._schedule_preview_update(); self._mark_dirty()

    def _renumber_steps(self):
        for index, row in enumerate(self.step_rows, start=1):
            if "label" in row:
                row["label"].configure(text=f"{index}.")
            else:
                try:
                    for widget in row["frame"].winfo_children():
                        if isinstance(widget, ctk.CTkLabel) and widget.cget("text").endswith("."):
                            widget.configure(text=f"{index}.")
                            break
                except Exception:
                    pass

    def _collect_form_data(self) -> Recipe:
        recipe = Recipe(
            slug=self.current_slug or "",
            nazev=self.nazev_var.get().strip() if hasattr(self, "nazev_var") else "",
            cas=self.cas_var.get().strip() if hasattr(self, "cas_var") else "",
            porce=self.porce_var.get().strip() if hasattr(self, "porce_var") else "",
            obtiznost=self.obtiznost_var.get().strip() if hasattr(self, "obtiznost_var") else "",
            foto=self.foto_var.get().strip() if hasattr(self, "foto_var") else "",
            ingredience=[],
            postup=[],
            casy=[],
            casti=[],
            tip=self.tip_text.get("1.0", "end").strip() if hasattr(self, "tip_text") else "",
        )
        for row in getattr(self, "time_rows", []):
            popis = row["popis"].get().strip()
            hodnota = row["hodnota"].get().strip()
            if not (popis or hodnota):
                continue
            recipe.casy.append(RecipeTime(popis=popis, hodnota=hodnota))

        for section in getattr(self, "section_rows", []):
            nazev = section["nazev"].get().strip()
            cas = section["cas"].get().strip()
            section_obj = RecipeSection(nazev=nazev, cas=cas, ingredience=[], postup=[])

            raw_ingredients = section["ingredience_text"].get("1.0", "end").splitlines()
            for line in raw_ingredients:
                value = line.strip()
                if not value:
                    continue
                section_obj.ingredience.append(self._parse_ingredient_line(value))

            raw_steps = section["postup_text"].get("1.0", "end").splitlines()
            for line in raw_steps:
                value = line.strip()
                if not value:
                    continue
                section_obj.postup.append(PostupKrok(text=value))

            if nazev or cas or section_obj.ingredience or section_obj.postup:
                recipe.casti.append(section_obj)
        return recipe

    def _parse_ingredient_line(self, line: str) -> Ingredient:
        text = (line or "").strip()
        if not text:
            return Ingredient()

        tokens = text.split()
        if not tokens:
            return Ingredient(nazev=text)

        qty_pattern = r"^\d+(?:[.,]\d+)?(?:/\d+)?$"
        qty = ""
        unit = ""

        if re.match(qty_pattern, tokens[0]):
            qty = tokens[0].replace(",", ".")
            tokens = tokens[1:]

        if tokens:
            unit_candidate = tokens[0].lower().rstrip(".")
            if unit_candidate in {value.lower() for value in UNIT_OPTIONS}:
                unit = tokens[0]
                tokens = tokens[1:]

        name = " ".join(tokens).strip()
        if not name:
            name = text
            qty = ""
            unit = ""
        return Ingredient(mnozstvi=qty, jednotka=unit, nazev=name)

    def _recipe_snapshot(self, recipe: Recipe) -> dict:
        clone = Recipe.from_dict(recipe.to_dict())
        clone.normalize()
        return clone.to_dict()

    def _has_unsaved_changes(self) -> bool:
        if self.original_recipe is None:
            return False
        return self._recipe_snapshot(self.original_recipe) != self._recipe_snapshot(self._collect_form_data())

    def _load_recipe(self, slug: str):
        try:
            recipe = load_all_recipes(self.project_root)
            found = next((item for item in recipe if item.slug == slug), None)
            if found is None:
                raise FileNotFoundError(slug)
            self.current_slug = found.slug
            self._clear_form()
            self.nazev_var.set(found.nazev)
            self.cas_var.set(found.cas)
            self.porce_var.set(found.porce)
            self.obtiznost_var.set(found.obtiznost)
            self.foto_var.set(found.foto)
            self.tip_text.insert("1.0", found.tip)

            for row in list(self.time_rows):
                row["frame"].destroy()
            self.time_rows = []
            if found.casy:
                for item in found.casy:
                    self._add_time_row({"popis": item.popis, "hodnota": item.hodnota})
            else:
                self._add_time_row({"popis": "Příprava", "hodnota": found.cas})

            for row in list(self.section_rows):
                row["frame"].destroy()
            self.section_rows = []
            if found.casti:
                for item in found.casti:
                    self._add_section_block(
                        {
                            "nazev": item.nazev,
                            "cas": item.cas,
                            "ingredience": item.ingredience,
                            "postup": item.postup,
                        }
                    )
            else:
                self._add_section_block(
                    {
                        "nazev": "Hlavní část",
                        "cas": found.cas,
                        "ingredience": found.ingredience,
                        "postup": found.postup,
                    }
                )
            self.root_title_update()
            self._render_picture_preview()
            self._render_preview()
            self._render_recipe_cards()
            self.original_recipe = self._collect_form_data()
            self.root_title_update()
        except (FileNotFoundError, OSError, ValueError):
            messagebox.showerror("Chyba při načtení receptu", "Recept se nepodařilo načíst.")

    def _set_status(self, message: str, success: bool = True):
        if hasattr(self, "status_label"):
            self.status_label.configure(text=message)
            self.status_label.configure(text_color="#2a6f3a" if success else "#9b1c1c")

    def _schedule_preview_update(self):
        if self.preview_after_id is not None:
            try:
                self.after_cancel(self.preview_after_id)
            except Exception:
                pass
        self.preview_after_id = self.after(300, self._render_preview)

    def _render_preview(self):
        if not self.current_slug and not hasattr(self, "nazev_var"):
            return
        recipe = self._collect_form_data()
        preview_root = self.preview_scroll
        for widget in preview_root.winfo_children():
            widget.destroy()

        if not recipe.nazev and not recipe.ingredience and not recipe.postup and not recipe.tip and not recipe.casti and not recipe.casy:
            placeholder = ctk.CTkLabel(preview_root, text="Zde se zobrazí náhled receptu", text_color="#7a8191", anchor="center")
            placeholder.grid(row=0, column=0, sticky="ew", padx=16, pady=40)
            return

        title = ctk.CTkLabel(preview_root, text=recipe.nazev or "Bez názvu", font=("Segoe UI", 24, "bold"), anchor="w", text_color="#1f2937")
        title.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))

        tags = ctk.CTkFrame(preview_root, corner_radius=10, fg_color="#f8fafc")
        tags.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))
        tags.grid_columnconfigure((0, 1, 2), weight=1)

        first_time = recipe.cas or "—"
        if recipe.casy:
            item = next((x for x in recipe.casy if x.hodnota.strip()), None)
            if item is not None:
                first_time = f"{item.popis or 'Čas'}: {item.hodnota}"
        ctk.CTkLabel(tags, text=f"🕒 {first_time}", text_color="#465468").grid(row=0, column=0, sticky="w", padx=12, pady=8)
        ctk.CTkLabel(tags, text=f"👥 {recipe.porce or '—'}", text_color="#465468").grid(row=0, column=1, sticky="w", padx=12, pady=8)
        ctk.CTkLabel(tags, text=f"⚑ {recipe.obtiznost or '—'}", text_color="#465468").grid(row=0, column=2, sticky="w", padx=12, pady=8)

        if recipe.casy:
            times_box = ctk.CTkFrame(preview_root, corner_radius=10, fg_color="#f8fafc")
            times_box.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))
            times_box.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(times_box, text="Časy", font=("Segoe UI", 13, "bold"), anchor="w", text_color="#1f2937").grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
            for idx, item in enumerate(recipe.casy, start=1):
                if not item.hodnota.strip():
                    continue
                ctk.CTkLabel(times_box, text=f"• {item.popis or 'Čas'}: {item.hodnota}", anchor="w", text_color="#334155").grid(row=idx, column=0, sticky="ew", padx=12, pady=2)

        preview_row = 10
        sections = recipe.casti if recipe.casti else [RecipeSection(nazev="Hlavní část", cas=recipe.cas, ingredience=recipe.ingredience, postup=recipe.postup)]
        for section in sections:
            if not (section.nazev or section.cas or section.ingredience or section.postup):
                continue
            section_box = ctk.CTkFrame(preview_root, corner_radius=12, fg_color="#fffaf7")
            section_box.grid(row=preview_row, column=0, sticky="ew", padx=18, pady=6)
            section_box.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(section_box, text=section.nazev or "Část receptu", font=("Segoe UI", 14, "bold"), anchor="w", text_color="#1f2937").grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
            if section.cas.strip():
                ctk.CTkLabel(section_box, text=f"⏱ {section.cas}", anchor="w", text_color="#5b6678").grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

            if section.ingredience:
                ctk.CTkLabel(section_box, text="Ingredience", font=("Segoe UI", 12, "bold"), anchor="w", text_color="#334155").grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 4))
                for idx, item in enumerate(section.ingredience, start=1):
                    text = f"{item.mnozstvi} {item.jednotka} {item.nazev}".strip()
                    ctk.CTkLabel(section_box, text=f"• {text}", anchor="w", text_color="#2b3443").grid(row=2 + idx, column=0, sticky="ew", padx=12, pady=1)

            if section.postup:
                offset = 3 + len(section.ingredience)
                ctk.CTkLabel(section_box, text="Postup", font=("Segoe UI", 12, "bold"), anchor="w", text_color="#334155").grid(row=offset, column=0, sticky="ew", padx=12, pady=(8, 4))
                for idx, item in enumerate(section.postup, start=1):
                    ctk.CTkLabel(section_box, text=f"{idx}. {item.text}", anchor="w", wraplength=260).grid(row=offset + idx, column=0, sticky="ew", padx=12, pady=1)
            preview_row += 1

        if recipe.tip:
            tip_box = ctk.CTkFrame(preview_root, corner_radius=12, fg_color="#f5f7ff")
            tip_box.grid(row=1000, column=0, sticky="ew", padx=18, pady=(14, 10))
            ctk.CTkLabel(tip_box, text="Tip", font=("Segoe UI", 12, "bold"), text_color="#1f2937").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))
            ctk.CTkLabel(tip_box, text=recipe.tip, wraplength=240, anchor="w").grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))

        latex_value = recipe_to_tex(recipe)
        self.preview_latex.delete("1.0", "end")
        self.preview_latex.insert("1.0", latex_value)

    def _refresh_recipe_list(self):
        self._render_recipe_cards(force=True)

    def save_current_recipe(self) -> bool:
        if not self.project_root.exists():
            messagebox.showwarning("Chybí projekt", "Vyberte nejdřív složku projektu.")
            return False
        data = self._collect_form_data()
        if not data.nazev.strip():
            messagebox.showerror("Chyba", "Název receptu je povinný.")
            return False

        desired_slug = generate_slug(data.nazev)
        if detect_slug_conflict(self.project_root, desired_slug, self.current_slug):
            answer = messagebox.askyesno("Kolize slugu", f"Recept s názvem '{data.nazev}' by vytvořil slug '{desired_slug}', který již existuje. Chcete přepsat existující recept?")
            if not answer:
                return False

        try:
            saved = save_recipe(self.project_root, data, current_slug=self.current_slug)
            self.current_slug = saved.slug
            self._refresh_recipe_list()
            self.original_recipe = self._collect_form_data()
            self.root_title_update()
            self._set_status(f"Uloženo: {saved.slug}.json, {saved.slug}.tex, recepty.json")
            self.show_toast(f"Uloženo: {saved.slug}.json, {saved.slug}.tex, recepty.json")
            self._render_preview()
            return True
        except RecipeConflictError as exc:
            self._set_status(f"Kolize slugu: {exc}", success=False)
            messagebox.showerror("Kolize slugu", str(exc))
            return False
        except (OSError, ValueError) as exc:
            self._set_status(f"Chyba při ukládání: {exc}", success=False)
            messagebox.showerror("Chyba při ukládání", str(exc))
            return False

    def show_toast(self, message: str):
        self.toast.configure(text=message)
        self.toast.place(relx=0.5, rely=0.97, anchor="s")
        if self.toast_after_id is not None:
            try:
                self.after_cancel(self.toast_after_id)
            except Exception:
                pass
        self.toast_after_id = self.after(2600, self.toast.place_forget)

    def preview_tex(self):
        recipe = self._collect_form_data()
        tex_text = recipe_to_tex(recipe)
        self.preview_tabview.set("LaTeX")
        self.preview_latex.delete("1.0", "end")
        self.preview_latex.insert("1.0", tex_text)

    def delete_current_recipe(self):
        if not self.current_slug:
            return
        recipe_name = self.nazev_var.get().strip() if hasattr(self, "nazev_var") else self.current_slug
        if not messagebox.askyesno("Smazat recept", f"Opravdu chcete smazat recept '{recipe_name}'?"):
            return
        try:
            delete_recipe(self.project_root, self.current_slug)
            self.show_toast(f"Smazáno: {self.current_slug}")
            self._add_empty_recipe()
            self._refresh_recipe_list()
        except OSError as exc:
            self._set_status(f"Chyba při mazání: {exc}", success=False)
            messagebox.showerror("Chyba při mazání", str(exc))

    def rebuild_index(self):
        if not self.project_root.exists():
            messagebox.showwarning("Chybí projekt", "Vyberte nejdřív složku projektu.")
            return
        try:
            items = update_master_index(self.project_root)
            self._set_status(f"Sestaveno {len(items)} receptů do data/recepty.json a docs/recepty.json")
            self.show_toast(f"Index obnoven: {len(items)} receptů")
        except Exception as exc:
            self._set_status(f"Chyba při sestavení indexu: {exc}", success=False)
            messagebox.showerror("Chyba při sestavení indexu", str(exc))

    def _show_empty_state(self):
        if hasattr(self, "empty_state"):
            self.empty_state.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=60)

    def on_close(self):
        if self._has_unsaved_changes():
            answer = messagebox.askyesnocancel("Uložit změny?", "Máte neuložené změny. Chcete je uložit?")
            if answer is None:
                return
            if answer:
                if not self.save_current_recipe():
                    return
        self.destroy()


def main():
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    app = RecipeApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
