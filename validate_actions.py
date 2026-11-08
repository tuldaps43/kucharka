import tempfile
import tkinter as tk
from pathlib import Path

import main
from recipe_logic import Recipe

root = tk.Tk()
root.withdraw()

d = Path(tempfile.mkdtemp())
(d / 'data').mkdir()
(d / 'recepty').mkdir()
(d / 'obrazky').mkdir()
(d / 'seznam-receptu.tex').write_text('', encoding='utf-8')

app = main.RecipeApp(root)
app.project_root = d
app._clear_form()
app.nazev_var.set('Test')
app.cas_var.set('15 min')
app.porce_var.set('2')
app.obtiznost_var.set('snadná')
app.current_slug = None
app.original_recipe = None

calls = []
main.messagebox.showinfo = lambda title, message: calls.append((title, message))
main.save_recipe = lambda project_root, recipe, current_slug=None: Recipe(
    slug='test',
    nazev=recipe.nazev,
    cas=recipe.cas,
    porce=recipe.porce,
    obtiznost=recipe.obtiznost,
    foto=recipe.foto,
    tip=recipe.tip,
)
result = app.save_current_recipe()
print('save_result', result)
print('save_message', calls[-1])

class DummyPreview:
    def __init__(self):
        self.focused = False
        self.grabbed = False
        self.lifted = False

    def transient(self, *args, **kwargs):
        pass

    def grab_set(self):
        self.grabbed = True

    def focus_force(self):
        self.focused = True

    def lift(self):
        self.lifted = True

preview = DummyPreview()
main.tk.Toplevel = lambda *args, **kwargs: preview
app.preview_tex()
print('preview_focus', preview.focused, preview.grabbed, preview.lifted)
root.destroy()
