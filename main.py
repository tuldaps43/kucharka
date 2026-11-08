from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from recipe_logic import (
    Ingredient,
    PostupKrok,
    Recipe,
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
)


class RecipeApp:
    """Hlavní GUI pro správu receptů v LaTeX kuchařce."""

    # Celé okno je rozděleno na levý panel se seznamem receptů a pravý formulář.

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Kuchařka - recepty")
        self.root.geometry("1280x820")
        self.root.minsize(1100, 700)

        self.app_dir = Path(__file__).resolve().parent
        self.config_path = self.app_dir / "config.json"
        self.project_root = get_project_root_from_config(self.config_path)

        self.current_slug: str | None = None
        self.original_recipe: Recipe | None = None
        self.recipe_list_items: dict[str, str] = {}
        self.ingredient_rows: list[dict] = []
        self.step_rows: list[dict] = []

        self._build_menu()
        self._build_layout()
        self._bind_shortcuts()

        if self.project_root.exists():
            self._refresh_recipe_list()
            self._add_empty_recipe()
        else:
            self._show_project_selection()

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Vybrat složku projektu", command=self.choose_project_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Uložit", command=self.save_current_recipe, accelerator="Ctrl+S")
        file_menu.add_command(label="Znovu sestavit recepty.json", command=self.rebuild_index)
        menubar.add_cascade(label="Soubor", menu=file_menu)
        self.root.config(menu=menubar)

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        split = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        split.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        left = ttk.Frame(split, padding=8)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        split.add(left, weight=1)

        top_left = ttk.Frame(left)
        top_left.grid(row=0, column=0, sticky="ew")
        ttk.Label(top_left, text="Recepty").grid(row=0, column=0, sticky="w")

        button_row = ttk.Frame(left)
        button_row.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        button_row.columnconfigure(0, weight=1)
        button_row.columnconfigure(1, weight=1)

        ttk.Button(button_row, text="Nový recept", command=self._add_empty_recipe).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(button_row, text="Smazat", command=self.delete_current_recipe).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.recipe_listbox = tk.Listbox(left, exportselection=False, activestyle="none")
        self.recipe_listbox.grid(row=2, column=0, sticky="nsew")
        self.recipe_listbox.bind("<<ListboxSelect>>", self._on_recipe_selected)

        right = ttk.Frame(split, padding=8)
        right.columnconfigure(0, weight=1)
        split.add(right, weight=3)

        self.form_canvas = tk.Canvas(right, borderwidth=0, highlightthickness=0)
        self.form_canvas.grid(row=0, column=0, sticky="nsew")
        self.form_scroll = ttk.Scrollbar(right, orient="vertical", command=self.form_canvas.yview)
        self.form_scroll.grid(row=0, column=1, sticky="ns")
        self.form_canvas.configure(yscrollcommand=self.form_scroll.set)

        self.form_frame = ttk.Frame(self.form_canvas)
        self.form_canvas.create_window((0, 0), window=self.form_frame, anchor="nw")
        self.form_frame.bind("<Configure>", lambda event: self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all")))

        self._build_form_fields()

        actions = ttk.Frame(self.form_frame)
        actions.grid(row=999, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Button(actions, text="Uložit", command=self.save_current_recipe).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(actions, text="Náhled .tex", command=self.preview_tex).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(self.form_frame, textvariable=self.status_var, foreground="#2a6f3a", anchor="w")
        self.status_label.grid(row=1000, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _build_form_fields(self) -> None:
        current_row = 0

        ttk.Label(self.form_frame, text="Název receptu").grid(row=current_row, column=0, sticky="w", padx=(0, 10), pady=(5, 2))
        self.nazev_var = tk.StringVar()
        ttk.Entry(self.form_frame, textvariable=self.nazev_var, width=60).grid(row=current_row, column=1, sticky="ew")
        self.nazev_var.trace_add("write", lambda *_: self._mark_dirty())
        current_row += 1

        ttk.Label(self.form_frame, text="Čas").grid(row=current_row, column=0, sticky="w", padx=(0, 10), pady=(5, 2))
        self.cas_var = tk.StringVar()
        ttk.Entry(self.form_frame, textvariable=self.cas_var, width=30).grid(row=current_row, column=1, sticky="ew")
        self.cas_var.trace_add("write", lambda *_: self._mark_dirty())
        current_row += 1

        ttk.Label(self.form_frame, text="Počet porcí").grid(row=current_row, column=0, sticky="w", padx=(0, 10), pady=(5, 2))
        self.porce_var = tk.StringVar()
        ttk.Entry(self.form_frame, textvariable=self.porce_var, width=30).grid(row=current_row, column=1, sticky="ew")
        self.porce_var.trace_add("write", lambda *_: self._mark_dirty())
        current_row += 1

        ttk.Label(self.form_frame, text="Obtížnost").grid(row=current_row, column=0, sticky="w", padx=(0, 10), pady=(5, 2))
        self.obtiznost_var = tk.StringVar()
        self.obtiznost_combo = ttk.Combobox(self.form_frame, textvariable=self.obtiznost_var, values=["snadná", "střední", "náročná"], state="normal")
        self.obtiznost_combo.grid(row=current_row, column=1, sticky="ew")
        self.obtiznost_var.trace_add("write", lambda *_: self._mark_dirty())
        current_row += 1

        ttk.Label(self.form_frame, text="Foto").grid(row=current_row, column=0, sticky="w", padx=(0, 10), pady=(5, 2))
        photo_row = ttk.Frame(self.form_frame)
        photo_row.grid(row=current_row, column=1, sticky="ew")
        self.foto_var = tk.StringVar()
        ttk.Entry(photo_row, textvariable=self.foto_var, width=50).grid(row=0, column=0, sticky="ew")
        ttk.Button(photo_row, text="Vybrat soubor", command=self._choose_photo).grid(row=0, column=1, padx=(8, 0), sticky="ew")
        photo_row.columnconfigure(0, weight=1)
        current_row += 1

        ttk.Separator(self.form_frame, orient=tk.HORIZONTAL).grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        current_row += 1

        ingred_frame = ttk.LabelFrame(self.form_frame, text="Ingredience")
        ingred_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", padx=(0, 0), pady=(0, 8))
        ingred_frame.columnconfigure(0, weight=1)
        self.ingredients_container = ttk.Frame(ingred_frame)
        self.ingredients_container.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        self.ingredients_container.columnconfigure(0, weight=1)
        self.add_ingredient_btn = ttk.Button(ingred_frame, text="Přidat ingredienci", command=self._add_ingredient_row)
        self.add_ingredient_btn.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        current_row += 1

        postup_frame = ttk.LabelFrame(self.form_frame, text="Postup")
        postup_frame.grid(row=current_row, column=0, columnspan=2, sticky="ew", padx=(0, 0), pady=(0, 8))
        postup_frame.columnconfigure(0, weight=1)
        self.steps_container = ttk.Frame(postup_frame)
        self.steps_container.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        ttk.Button(postup_frame, text="Přidat krok", command=self._add_step_row).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        current_row += 1

        ttk.Label(self.form_frame, text="Tip").grid(row=current_row, column=0, sticky="nw", padx=(0, 10), pady=(5, 2))
        self.tip_text = tk.Text(self.form_frame, height=5, width=60, wrap=tk.WORD)
        self.tip_text.grid(row=current_row, column=1, sticky="ew")
        self.tip_text.bind("<KeyRelease>", lambda event: self._mark_dirty())
        current_row += 1

        self.form_frame.columnconfigure(1, weight=1)

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-s>", lambda event: self.save_current_recipe())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _mark_dirty(self) -> None:
        if self.original_recipe is None:
            return
        current = self._collect_form_data()
        if self.original_recipe.to_dict() != current.to_dict():
            self.root.title("Kuchařka - recepty *")
        else:
            self.root.title("Kuchařka - recepty")

    def _show_project_selection(self) -> None:
        if not self.project_root.exists():
            messagebox.showinfo("Adresář projektu", "Vyberte složku projektu, ve které je struktura kuchařky.")
        self.choose_project_folder()

    def _set_status(self, message: str, *, success: bool = True) -> None:
        self.status_var.set(message)
        if self.status_label.winfo_exists():
            self.status_label.configure(foreground="#2a6f3a" if success else "#9b1c1c")

    def choose_project_folder(self) -> None:
        directory = filedialog.askdirectory(title="Vyberte složku projektu")
        if not directory:
            return
        self.project_root = Path(directory).resolve()
        save_project_root_to_config(self.config_path, self.project_root)
        self._set_status(f"Projekt: {self.project_root}")
        self._refresh_recipe_list()
        self._add_empty_recipe()

    def _refresh_recipe_list(self) -> None:
        self.recipe_listbox.delete(0, tk.END)
        self.recipe_list_items = {}
        if not self.project_root.exists():
            return
        for recipe in load_all_recipes(self.project_root):
            self.recipe_list_items[recipe.nazev] = recipe.slug
            self.recipe_listbox.insert(tk.END, recipe.nazev)

    def _add_empty_recipe(self) -> None:
        if self._has_unsaved_changes():
            answer = messagebox.askyesnocancel("Neuložené změny", "Uložit aktuální recept?")
            if answer is None:
                return
            if answer:
                self.save_current_recipe()
        self._clear_form()
        self.current_slug = None
        self.original_recipe = Recipe()
        self.root.title("Kuchařka - recepty")

    def _clear_form(self) -> None:
        self.nazev_var.set("")
        self.cas_var.set("")
        self.porce_var.set("")
        self.obtiznost_var.set("")
        self.foto_var.set("")
        self.tip_text.delete("1.0", tk.END)
        self._clear_ingredient_rows()
        self._clear_step_rows()

    def _clear_ingredient_rows(self) -> None:
        for row in self.ingredient_rows:
            for widget in row["widgets"]:
                widget.destroy()
        self.ingredient_rows = []

    def _clear_step_rows(self) -> None:
        for row in self.step_rows:
            for widget in row["widgets"]:
                widget.destroy()
        self.step_rows = []

    def _add_ingredient_row(self, data: dict | None = None) -> None:
        frame = ttk.Frame(self.ingredients_container)
        frame.grid(sticky="ew", pady=2)
        frame.columnconfigure(0, weight=2)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=3)

        qty = ttk.Entry(frame, width=8)
        qty.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        unit = ttk.Combobox(frame, values=UNIT_OPTIONS, width=10, state="normal")
        unit.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        unit.set(data.get("jednotka", "") if data else "")

        name = ttk.Entry(frame, width=28)
        name.grid(row=0, column=2, sticky="ew")

        if data:
            qty.insert(0, data.get("mnozstvi", ""))
            name.insert(0, data.get("nazev", ""))

        buttons = ttk.Frame(frame)
        buttons.grid(row=0, column=3, sticky="e", padx=(8, 0))
        up = ttk.Button(buttons, text="↑", width=3, command=lambda: self._move_ingredient_row(frame, -1))
        down = ttk.Button(buttons, text="↓", width=3, command=lambda: self._move_ingredient_row(frame, 1))
        delete = ttk.Button(buttons, text="✕", width=3, command=lambda: self._remove_ingredient_row(frame))
        up.grid(row=0, column=0)
        down.grid(row=0, column=1)
        delete.grid(row=0, column=2)

        self.ingredient_rows.append({
            "frame": frame,
            "widgets": [qty, unit, name, up, down, delete],
            "mnozstvi": qty,
            "jednotka": unit,
            "nazev": name,
        })
        self._mark_dirty()

    def _remove_ingredient_row(self, frame: ttk.Frame) -> None:
        for idx, item in enumerate(self.ingredient_rows):
            if item["frame"] is frame:
                del self.ingredient_rows[idx]
                frame.destroy()
                break
        self._mark_dirty()

    def _move_ingredient_row(self, frame: ttk.Frame, direction: int) -> None:
        idx = next((i for i, item in enumerate(self.ingredient_rows) if item["frame"] is frame), None)
        if idx is None:
            return
        target = idx + direction
        if target < 0 or target >= len(self.ingredient_rows):
            return

        self.ingredient_rows[idx], self.ingredient_rows[target] = self.ingredient_rows[target], self.ingredient_rows[idx]

        for row in self.ingredient_rows:
            row["frame"].grid_remove()

        for i, row in enumerate(self.ingredient_rows):
            row["frame"].grid(row=i, sticky="ew", pady=2)
        self._mark_dirty()

    def _add_step_row(self, data: dict | None = None) -> None:
        frame = ttk.Frame(self.steps_container)
        frame.grid(sticky="ew", pady=2)
        frame.columnconfigure(0, weight=3)
        frame.columnconfigure(1, weight=1)

        text = tk.Text(frame, height=3, wrap=tk.WORD)
        text.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        if data:
            text.insert("1.0", data.get("text", ""))

        timer = ttk.Entry(frame, width=10)
        timer.grid(row=0, column=1, sticky="ew")
        if data and data.get("casovac_min") is not None:
            timer.insert(0, str(data["casovac_min"]))

        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        up = ttk.Button(buttons, text="↑", width=3, command=lambda: self._move_step_row(frame, -1))
        down = ttk.Button(buttons, text="↓", width=3, command=lambda: self._move_step_row(frame, 1))
        delete = ttk.Button(buttons, text="✕", width=3, command=lambda: self._remove_step_row(frame))
        up.grid(row=0, column=0)
        down.grid(row=0, column=1)
        delete.grid(row=0, column=2)

        self.step_rows.append({
            "frame": frame,
            "widgets": [text, timer, up, down, delete],
            "text": text,
            "timer": timer,
        })
        text.bind("<KeyRelease>", lambda event: self._mark_dirty())
        timer.bind("<KeyRelease>", lambda event: self._mark_dirty())

    def _remove_step_row(self, frame: ttk.Frame) -> None:
        for idx, item in enumerate(self.step_rows):
            if item["frame"] is frame:
                del self.step_rows[idx]
                frame.destroy()
                break
        self._mark_dirty()

    def _move_step_row(self, frame: ttk.Frame, direction: int) -> None:
        idx = next((i for i, item in enumerate(self.step_rows) if item["frame"] is frame), None)
        if idx is None:
            return
        target = idx + direction
        if target < 0 or target >= len(self.step_rows):
            return

        self.step_rows[idx], self.step_rows[target] = self.step_rows[target], self.step_rows[idx]

        for row in self.step_rows:
            row["frame"].grid_remove()

        for i, row in enumerate(self.step_rows):
            row["frame"].grid(row=i, sticky="ew", pady=2)
        self._mark_dirty()

    def _choose_photo(self) -> None:
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
            self._mark_dirty()
        except OSError as exc:
            messagebox.showerror("Chyba při kopírování obrázku", str(exc))

    def _collect_form_data(self) -> Recipe:
        recipe = Recipe(
            slug=self.current_slug or "",
            nazev=self.nazev_var.get().strip(),
            cas=self.cas_var.get().strip(),
            porce=self.porce_var.get().strip(),
            obtiznost=self.obtiznost_var.get().strip(),
            foto=self.foto_var.get().strip(),
            ingredience=[],
            postup=[],
            tip=self.tip_text.get("1.0", tk.END).strip(),
        )

        for row in self.ingredient_rows:
            mnoz = row["mnozstvi"].get().strip()
            jednotka = row["jednotka"].get().strip()
            nazev = row["nazev"].get().strip()
            if not (mnoz or jednotka or nazev):
                continue
            recipe.ingredience.append(Ingredient(
                mnozstvi=mnoz,
                jednotka=jednotka,
                nazev=nazev,
            ))

        for row in self.step_rows:
            text = row["text"].get("1.0", tk.END).strip()
            timer_text = row["timer"].get().strip()
            if not text and not timer_text:
                continue
            try:
                timer_value = int(timer_text) if timer_text else None
            except ValueError:
                timer_value = None
            recipe.postup.append(PostupKrok(
                text=text,
                casovac_min=timer_value,
            ))

        return recipe

    def _has_unsaved_changes(self) -> bool:
        if self.original_recipe is None:
            return False
        return self.original_recipe.to_dict() != self._collect_form_data().to_dict()

    def _on_recipe_selected(self, _event=None) -> None:
        selection = self.recipe_listbox.curselection()
        if not selection:
            return
        selected_name = self.recipe_listbox.get(selection[0])
        slug = self.recipe_list_items.get(selected_name)
        if not slug:
            return
        if self._has_unsaved_changes():
            answer = messagebox.askyesnocancel("Neuložené změny", "Uložit aktuální recept?")
            if answer is None:
                self.recipe_listbox.selection_clear(0, tk.END)
                return
            if answer and not self.save_current_recipe():
                self.recipe_listbox.selection_clear(0, tk.END)
                return
        self._load_recipe(slug)

    def _load_recipe(self, slug: str) -> None:
        try:
            recipe = load_all_recipes(self.project_root)
            found = next((item for item in recipe if item.slug == slug), None)
            if found is None:
                raise FileNotFoundError(slug)
            self.current_slug = found.slug
            self.original_recipe = found
            self._clear_form()
            self.nazev_var.set(found.nazev)
            self.cas_var.set(found.cas)
            self.porce_var.set(found.porce)
            self.obtiznost_var.set(found.obtiznost)
            self.foto_var.set(found.foto)
            self.tip_text.insert("1.0", found.tip)
            for item in found.ingredience:
                self._add_ingredient_row({"mnozstvi": item.mnozstvi, "jednotka": item.jednotka, "nazev": item.nazev})
            for item in found.postup:
                self._add_step_row({"text": item.text, "casovac_min": item.casovac_min})
            self.root.title("Kuchařka - recepty")
        except (FileNotFoundError, OSError, ValueError) as exc:
            messagebox.showerror("Chyba při načtení receptu", str(exc))

    def save_current_recipe(self) -> bool:
        if not self.project_root.exists():
            messagebox.showwarning("Chybí projekt", "Vyberte nejdřív složku projektu.")
            return False
        data = self._collect_form_data()
        if not data.nazev.strip():
            messagebox.showerror("Chyba", "Název receptu je povinný.")
            return False
        if not data.cas.strip():
            messagebox.showwarning("Upozornění", "Pole „Čas“ je prázdné, uloženo bude bez hodnoty.")
        if not data.porce.strip():
            messagebox.showwarning("Upozornění", "Pole „Počet porcí“ je prázdné, uloženo bude bez hodnoty.")

        desired_slug = generate_slug(data.nazev)
        if detect_slug_conflict(self.project_root, desired_slug, self.current_slug):
            answer = messagebox.askyesno("Kolize slugu", f"Recept s názvem '{data.nazev}' by vytvořil slug '{desired_slug}', který již existuje. Chcete přepsat existující recept?")
            if not answer:
                return False

        try:
            saved = save_recipe(self.project_root, data, current_slug=self.current_slug)
            self.current_slug = saved.slug
            self.original_recipe = saved
            self._refresh_recipe_list()
            self.root.title("Kuchařka - recepty")
            self._set_status(f"Uloženo: {self.project_root / 'data' / f'{saved.slug}.json'}; {self.project_root / 'docs' / 'recepty.json'}")
            messagebox.showinfo("Uloženo", f"Recept '{saved.nazev}' byl úspěšně uložen.")
            self.root.update_idletasks()
            return True
        except RecipeConflictError as exc:
            self._set_status(f"Kolize slugu: {exc}", success=False)
            messagebox.showerror("Kolize slugu", str(exc))
            return False
        except (OSError, ValueError) as exc:
            self._set_status(f"Chyba při ukládání: {exc}", success=False)
            messagebox.showerror("Chyba při ukládání", str(exc))
            return False

    def preview_tex(self) -> None:
        if not self.project_root.exists():
            messagebox.showwarning("Chybí projekt", "Vyberte nejdřív složku projektu.")
            return
        recipe = self._collect_form_data()
        preview = tk.Toplevel(self.root)
        preview.title("Náhled .tex")
        preview.geometry("900x600")
        preview.transient(self.root)
        preview.grab_set()
        preview.focus_force()
        preview.lift()
        text_widget = tk.Text(preview, wrap=tk.WORD, font=("Consolas", 10))
        text_widget.insert("1.0", recipe_to_tex(recipe))
        text_widget.configure(state="disabled")
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def delete_current_recipe(self) -> None:
        if not self.current_slug:
            return
        recipe_name = self.nazev_var.get().strip() or self.current_slug
        if not messagebox.askyesno("Smazat recept", f"Opravdu chcete smazat recept '{recipe_name}'?"):
            return
        try:
            delete_recipe(self.project_root, self.current_slug)
            self._set_status(f"Smazáno a index znovu sestaven: {self.project_root}")
            self._add_empty_recipe()
            self._refresh_recipe_list()
        except OSError as exc:
            self._set_status(f"Chyba při mazání: {exc}", success=False)
            messagebox.showerror("Chyba při mazání", str(exc))

    def rebuild_index(self) -> None:
        if not self.project_root.exists():
            messagebox.showwarning("Chybí projekt", "Vyberte nejdřív složku projektu.")
            return
        try:
            items = update_master_index(self.project_root)
            self._set_status(f"Sestaveno {len(items)} receptů do data/recepty.json a docs/recepty.json")
            messagebox.showinfo("Index uložen", f"Recepty byly znovu sestaveny. Nalezeno: {len(items)}.")
        except Exception as exc:
            self._set_status(f"Chyba při sestavení indexu: {exc}", success=False)
            messagebox.showerror("Chyba při sestavení indexu", str(exc))

    def on_close(self) -> None:
        if self._has_unsaved_changes():
            answer = messagebox.askyesnocancel("Uložit změny?", "Máte neuložené změny. Chcete je uložit?")
            if answer is None:
                return
            if answer:
                if not self.save_current_recipe():
                    return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = RecipeApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        messagebox.showerror("Neočekávaná chyba", f"Aplikace se neočekávaně ukončila:\n{exc}")
        sys.exit(1)
