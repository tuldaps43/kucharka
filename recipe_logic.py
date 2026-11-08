from __future__ import annotations

"""Logika pro ukládání receptů, generování LaTeXu a správu dat v projektu kuchařky."""

import json
import os
import re
import shutil
import sys
import tempfile
import traceback
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Optional


LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

UNIT_OPTIONS = [
    "g",
    "kg",
    "ml",
    "l",
    "ks",
    "lžíce",
    "lžička",
    "stroužek",
    "špetka",
    "hrnek",
]


class RecipeConflictError(ValueError):
    """Vyskytla se kolize slugu při ukládání receptu."""


@dataclass
class Ingredient:
    mnozstvi: str = ""
    jednotka: str = ""
    nazev: str = ""

    def to_dict(self) -> dict:
        return {
            "mnozstvi": self.mnozstvi or "",
            "jednotka": self.jednotka or "",
            "nazev": self.nazev or "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Ingredient":
        return cls(
            mnozstvi=str(data.get("mnozstvi", "") or ""),
            jednotka=str(data.get("jednotka", "") or ""),
            nazev=str(data.get("nazev", "") or ""),
        )


@dataclass
class PostupKrok:
    text: str = ""
    casovac_min: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "text": self.text or "",
            "casovac_min": self.casovac_min if self.casovac_min is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PostupKrok":
        value = data or {}
        casovac = value.get("casovac_min")
        try:
            casovac_num = int(casovac) if casovac not in (None, "") else None
        except (TypeError, ValueError):
            casovac_num = None
        return cls(text=str(value.get("text", "") or ""), casovac_min=casovac_num)


@dataclass
class Recipe:
    slug: str = ""
    nazev: str = ""
    cas: str = ""
    porce: str = ""
    obtiznost: str = ""
    foto: str = ""
    ingredience: List[Ingredient] = field(default_factory=list)
    postup: List[PostupKrok] = field(default_factory=list)
    tip: str = ""

    def to_dict(self) -> dict:
        return {
            "slug": self.slug or generate_slug(self.nazev),
            "nazev": self.nazev or "",
            "cas": self.cas or "",
            "porce": self.porce or "",
            "obtiznost": self.obtiznost or "",
            "foto": self.foto or "",
            "ingredience": [item.to_dict() for item in self.ingredience],
            "postup": [item.to_dict() for item in self.postup],
            "tip": self.tip or "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Recipe":
        payload = data or {}
        recipe = cls(
            slug=str(payload.get("slug", "") or ""),
            nazev=str(payload.get("nazev", "") or ""),
            cas=str(payload.get("cas", "") or ""),
            porce=str(payload.get("porce", "") or ""),
            obtiznost=str(payload.get("obtiznost", "") or ""),
            foto=str(payload.get("foto", "") or ""),
            ingredience=[Ingredient.from_dict(item) for item in payload.get("ingredience", [])],
            postup=[PostupKrok.from_dict(item) for item in payload.get("postup", [])],
            tip=str(payload.get("tip", "") or ""),
        )
        if not recipe.slug:
            recipe.slug = generate_slug(recipe.nazev)
        return recipe

    def normalize(self) -> None:
        """Přečistí data a odstraní prázdné položky."""
        self.ingredience = [
            item for item in self.ingredience
            if (item.mnozstvi.strip() or item.jednotka.strip() or item.nazev.strip())
        ]
        self.postup = [
            item for item in self.postup
            if (item.text.strip() or (item.casovac_min is not None and item.casovac_min != ""))
        ]
        self.tip = (self.tip or "").strip()
        self.nazev = (self.nazev or "").strip()
        self.cas = (self.cas or "").strip()
        self.porce = (self.porce or "").strip()
        self.obtiznost = (self.obtiznost or "").strip()
        self.foto = (self.foto or "").strip()
        self.slug = generate_slug(self.nazev) if not self.slug else self.slug


def latex_escape(value: Any) -> str:
    text = str(value or "")
    for znak, nahrazeni in LATEX_ESCAPES.items():
        text = text.replace(znak, nahrazeni)
    return text


def generate_slug(nazev: str) -> str:
    # Slug se tvoří z názvu receptu, aby byl vhodný pro souborové jméno i pro LaTeX input.
    text = unicodedata.normalize("NFKD", (nazev or "")).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "recept"


def log_exception(context: str, exc: Exception) -> None:
    print(f"[ERROR] {context}: {exc}", file=sys.stderr)
    traceback.print_exc()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
    except Exception as exc:
        log_exception(f"write_json_atomic ({path})", exc)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except Exception as exc:
        log_exception(f"write_text_atomic ({path})", exc)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def copy_file_atomic(src: Path, dst: Path) -> None:
    if not src.exists():
        raise FileNotFoundError(f"Soubor neexistuje: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=str(dst.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(src.read_bytes())
        os.replace(tmp_path, dst)
    except Exception as exc:
        log_exception(f"copy_file_atomic ({src} -> {dst})", exc)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_text_utf8(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def ensure_project_structure(project_root: Path) -> None:
    (project_root / "data").mkdir(parents=True, exist_ok=True)
    (project_root / "recepty").mkdir(parents=True, exist_ok=True)
    (project_root / "obrazky").mkdir(parents=True, exist_ok=True)
    (project_root / "seznam-receptu.tex").touch(exist_ok=True)


def list_recipe_json_paths(project_root: Path) -> List[Path]:
    data_dir = project_root / "data"
    if not data_dir.exists():
        return []
    paths = []
    for item in sorted(data_dir.glob("*.json")):
        if item.name == "recepty.json":
            continue
        paths.append(item)
    return paths


def load_recipe_from_json(project_root: Path, slug: str) -> Recipe:
    path = project_root / "data" / f"{slug}.json"
    if not path.exists():
        raise FileNotFoundError(f"Soubor receptu neexistuje: {path}")
    payload = load_json(path)
    recipe = Recipe.from_dict(payload)
    recipe.slug = slug
    return recipe


def recipe_to_tex(recipe: Recipe) -> str:
    recipe.normalize()
    lines: List[str] = []
    lines.append(
        f"\\recept{{{latex_escape(recipe.nazev)}}}{{{latex_escape(recipe.cas)}}}{{{latex_escape(recipe.porce)}}}{{{latex_escape(recipe.obtiznost)}}}"
    )
    if recipe.foto.strip():
        lines.append("")
        lines.append(f"\\foto{{{latex_escape(recipe.foto)}}}")

    lines.append("")
    lines.append("\\begin{ingredience}")
    for item in recipe.ingredience:
        nazev = (item.nazev or "").strip()
        mnoz = (item.mnozstvi or "").strip()
        jednotka = (item.jednotka or "").strip()
        if not nazev:
            continue
        if mnoz or jednotka:
            obsah = " ".join([part for part in [mnoz, jednotka] if part]).strip()
            lines.append(f"  \\item \\textbf{{{latex_escape(obsah)}}} {latex_escape(nazev)}")
        else:
            lines.append(f"  \\item {latex_escape(nazev)}")
    lines.append("\\end{ingredience}")

    lines.append("")
    lines.append("\\begin{postup}")
    for krok in recipe.postup:
        text = (krok.text or "").strip()
        if not text:
            continue
        lines.append(f"  \\item {latex_escape(text)}")
    lines.append("\\end{postup}")

    if recipe.tip.strip():
        lines.append("")
        lines.append(f"\\tip{{{latex_escape(recipe.tip)}}}")

    return "\n".join(lines) + "\n"


def write_recipe_tex(project_root: Path, recipe: Recipe) -> None:
    recipe_path = project_root / "recepty" / f"{recipe.slug}.tex"
    write_text_atomic(recipe_path, recipe_to_tex(recipe))


def update_seznam_receptu(project_root: Path, slug: str, *, remove: bool = False) -> None:
    seznam_path = project_root / "seznam-receptu.tex"
    target_line = f"\\input{{recepty/{slug}}}"
    if not seznam_path.exists():
        seznam_path.touch()
    lines = read_text_utf8(seznam_path).splitlines()
    filtered = []
    for line in lines:
        stripped = line.strip()
        if stripped == target_line:
            if remove:
                continue
            filtered.append(line)
            continue
        filtered.append(line)

    if not remove and target_line not in [item.strip() for item in filtered]:
        if filtered and filtered[-1].strip() != "":
            filtered.append("")
        filtered.append(target_line)

    text = "\n".join(filtered)
    if text and not text.endswith("\n"):
        text += "\n"
    write_text_atomic(seznam_path, text)


def ensure_docs_structure(project_root: Path) -> Path:
    project_root = Path(project_root).resolve()
    docs_root = project_root / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)
    (docs_root / "obrazky").mkdir(parents=True, exist_ok=True)
    return docs_root


def sync_docs_images(project_root: Path) -> None:
    project_root = Path(project_root).resolve()
    source_dir = project_root / "obrazky"
    docs_dir = ensure_docs_structure(project_root) / "obrazky"

    if source_dir.exists():
        for image in sorted(source_dir.iterdir(), key=lambda item: item.name.lower()):
            if image.is_file():
                try:
                    copy_file_atomic(image, docs_dir / image.name)
                except OSError as exc:
                    log_exception(f"sync_docs_images ({image})", exc)

    for recipe in load_all_recipes(project_root):
        if not recipe.foto:
            continue
        source_path = project_root / "obrazky" / recipe.foto
        if not source_path.exists():
            continue
        try:
            copy_file_atomic(source_path, docs_dir / recipe.foto)
        except OSError as exc:
            log_exception(f"sync_docs_images used photo ({source_path})", exc)


def update_master_index(project_root: Path) -> List[dict]:
    project_root = Path(project_root).resolve()
    ensure_project_structure(project_root)
    ensure_docs_structure(project_root)

    recipes: List[dict] = []
    for item in list_recipe_json_paths(project_root):
        try:
            payload = load_json(item)
            recipe = Recipe.from_dict(payload)
            recipe.slug = recipe.slug or item.stem
            recipes.append(recipe.to_dict())
        except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            log_exception(f"update_master_index ({item})", exc)
            continue

    index_path = project_root / "data" / "recepty.json"
    write_json_atomic(index_path, recipes)
    docs_root = ensure_docs_structure(project_root)
    write_json_atomic(docs_root / "recepty.json", recipes)
    sync_docs_images(project_root)
    return recipes


def save_recipe(project_root: Path, recipe: Recipe, current_slug: Optional[str] = None) -> Recipe:
    # Ukládání probíhá atomicky: nejprve se zapíše dočasný soubor a až potom přejmenuje do cílové cesty.
    recipe.normalize()
    if not recipe.nazev.strip():
        raise ValueError("Název receptu je povinný.")

    desired_slug = recipe.slug or generate_slug(recipe.nazev)
    desired_slug = generate_slug(desired_slug)
    recipe.slug = desired_slug

    ensure_project_structure(project_root)
    data_dir = project_root / "data"
    repo_dir = project_root / "recepty"
    old_slug = current_slug or ""

    if old_slug and old_slug != desired_slug:
        if (data_dir / f"{desired_slug}.json").exists():
            raise RecipeConflictError(f"Slug '{desired_slug}' již existuje.")
        old_json = data_dir / f"{old_slug}.json"
        if old_json.exists():
            os.replace(old_json, data_dir / f"{desired_slug}.json")
        old_tex = repo_dir / f"{old_slug}.tex"
        if old_tex.exists():
            os.replace(old_tex, repo_dir / f"{desired_slug}.tex")
        update_seznam_receptu(project_root, old_slug, remove=True)

    if not old_slug and (data_dir / f"{desired_slug}.json").exists():
        raise RecipeConflictError(f"Slug '{desired_slug}' již existuje.")

    json_path = data_dir / f"{desired_slug}.json"
    write_json_atomic(json_path, recipe.to_dict())
    write_recipe_tex(project_root, recipe)
    update_seznam_receptu(project_root, desired_slug)
    update_master_index(project_root)
    return recipe


def delete_recipe(project_root: Path, slug: str) -> None:
    project_root = Path(project_root).resolve()
    ensure_project_structure(project_root)
    json_path = project_root / "data" / f"{slug}.json"
    tex_path = project_root / "recepty" / f"{slug}.tex"

    try:
        recipe = load_recipe_from_json(project_root, slug)
    except FileNotFoundError as exc:
        recipe = None
        log_exception(f"delete_recipe load ({project_root}, {slug})", exc)

    if recipe and recipe.foto:
        for base in [project_root / "obrazky", ensure_docs_structure(project_root) / "obrazky"]:
            photo_path = base / recipe.foto
            if photo_path.exists():
                photo_path.unlink()

    for path in [json_path, tex_path]:
        if path.exists():
            path.unlink()
    update_seznam_receptu(project_root, slug, remove=True)
    update_master_index(project_root)


def load_all_recipes(project_root: Path) -> List[Recipe]:
    project_root = Path(project_root).resolve()
    ensure_project_structure(project_root)
    recipes: List[Recipe] = []
    for path in list_recipe_json_paths(project_root):
        try:
            payload = load_json(path)
            recipe = Recipe.from_dict(payload)
            recipe.slug = path.stem
            recipes.append(recipe)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError) as exc:
            log_exception(f"load_all_recipes ({path})", exc)
            continue
    return sorted(recipes, key=lambda item: item.nazev.lower())


def get_project_root_from_config(config_path: Path) -> Path:
    config_path = Path(config_path).resolve()
    if not config_path.exists():
        return Path.cwd().resolve()
    try:
        payload = load_json(config_path)
        if isinstance(payload, dict) and payload.get("project_root"):
            root = Path(str(payload["project_root"]))
            if not root.is_absolute():
                root = (config_path.parent / root).resolve()
            if root.exists():
                return root.resolve()
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        log_exception(f"get_project_root_from_config ({config_path})", exc)
    return Path.cwd().resolve()


def save_project_root_to_config(config_path: Path, project_root: Path) -> None:
    project_root = Path(project_root).resolve()
    config_path = Path(config_path).resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(config_path, {"project_root": str(project_root)})


def detect_slug_conflict(project_root: Path, desired_slug: str, current_slug: Optional[str] = None) -> bool:
    if not desired_slug:
        return False
    existing = project_root / "data" / f"{desired_slug}.json"
    if not existing.exists():
        return False
    return current_slug is None or current_slug != desired_slug


def build_recepty_index(project_root: Path) -> List[dict]:
    recipes: List[dict] = []
    for recipe in load_all_recipes(project_root):
        recipes.append({
            "slug": recipe.slug,
            "nazev": recipe.nazev,
            "cas": recipe.cas,
            "porce": recipe.porce,
            "obtiznost": recipe.obtiznost,
            "foto": recipe.foto,
        })
    return recipes


def recipe_from_form_data(data: dict) -> Recipe:
    recipe = Recipe(
        slug=str(data.get("slug") or ""),
        nazev=str(data.get("nazev") or ""),
        cas=str(data.get("cas") or ""),
        porce=str(data.get("porce") or ""),
        obtiznost=str(data.get("obtiznost") or ""),
        foto=str(data.get("foto") or ""),
        ingredience=[],
        postup=[],
        tip=str(data.get("tip") or ""),
    )

    for item in data.get("ingredience", []):
        if not isinstance(item, dict):
            continue
        recipe.ingredience.append(Ingredient(
            mnozstvi=str(item.get("mnozstvi") or ""),
            jednotka=str(item.get("jednotka") or ""),
            nazev=str(item.get("nazev") or ""),
        ))

    for item in data.get("postup", []):
        if not isinstance(item, dict):
            continue
        cas = item.get("casovac_min")
        try:
            num = int(cas) if cas not in (None, "") else None
        except (TypeError, ValueError):
            num = None
        recipe.postup.append(PostupKrok(
            text=str(item.get("text") or ""),
            casovac_min=num,
        ))

    return recipe
