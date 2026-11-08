import tkinter as tk

import main
from recipe_logic import Recipe


def make_app(tmp_path):
    root = tk.Tk()
    root.withdraw()
    app = main.RecipeApp(root)
    app.project_root = tmp_path
    app._clear_form()
    app.nazev_var.set("Test")
    app.cas_var.set("15 min")
    app.porce_var.set("2")
    app.obtiznost_var.set("snadná")
    app.current_slug = None
    app.original_recipe = None
    return app, root


def test_save_current_recipe_shows_info(monkeypatch, tmp_path):
    app, root = make_app(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "recepty").mkdir(exist_ok=True)
    (tmp_path / "obrazky").mkdir(exist_ok=True)
    (tmp_path / "seznam-receptu.tex").write_text("", encoding="utf-8")

    monkeypatch.setattr(main, "save_recipe", lambda project_root, recipe, current_slug=None: Recipe(
        slug="test",
        nazev=recipe.nazev,
        cas=recipe.cas,
        porce=recipe.porce,
        obtiznost=recipe.obtiznost,
        foto=recipe.foto,
        tip=recipe.tip,
    ))
    calls = []
    monkeypatch.setattr(main.messagebox, "showinfo", lambda title, message: calls.append((title, message)))

    result = app.save_current_recipe()

    assert result is True
    assert calls and calls[0][0] == "Uloženo"
    root.destroy()


def test_preview_tex_raises_window(monkeypatch, tmp_path):
    app, root = make_app(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "recepty").mkdir(exist_ok=True)
    (tmp_path / "obrazky").mkdir(exist_ok=True)
    (tmp_path / "seznam-receptu.tex").write_text("", encoding="utf-8")

    class DummyPreview:
        def __init__(self):
            self.focused = False
            self.grabbed = False
            self.lifted = False

        def transient(self, *_args, **_kwargs):
            pass

        def grab_set(self):
            self.grabbed = True

        def focus_force(self):
            self.focused = True

        def lift(self):
            self.lifted = True

        def configure(self, *args, **kwargs):
            pass

        def insert(self, *args, **kwargs):
            pass

        def pack(self, *args, **kwargs):
            pass

    preview = DummyPreview()
    monkeypatch.setattr(main.tk, "Toplevel", lambda *args, **kwargs: preview)

    app.preview_tex()

    assert preview.grabbed is True
    assert preview.focused is True
    assert preview.lifted is True
    root.destroy()
