# Kuchařka – editor receptů pro LaTeX

Tento skript slouží k zadávání a správě receptů pro kuchařku v LaTeXu. Data jsou uložena v JSONu a z nich se automaticky generují `.tex` soubory pro Overleaf / LaTeX projekt.

## Struktura projektu

Po spuštění aplikace pracuje s adresářem, který má následující strukturu:

```text
kucharka/
├── main.tex
├── nastaveni.tex
├── seznam-receptu.tex
├── recepty/
│   ├── palacinky.tex
│   └── ...
├── obrazky/
│   └── palacinky.jpg
├── data/
│   ├── palacinky.json
│   ├── ...
│   └── recepty.json
└── ...
```

## Co aplikace dělá

- načítá a ukládá recepty jako JSON
- vygeneruje `.tex` soubor pro každý recept
- aktualizuje `seznam-receptu.tex` o `\input{recepty/<slug>}`
- udržuje `data/recepty.json` pro mobilní aplikaci
- zkopíruje vybranou fotografii do složky `obrazky/`
- ověřuje název receptu, detekuje kolize slugu a chrání data atomickým ukládáním

## Spuštění

1. Otevřete terminál v adresáři `kucharka_app/`.
2. Spusťte:

```bash
python main.py
```

3. V aplikaci zvolte tlačítkem v menu nebo v dialogu složku projektu (`kucharka/`).
4. Cesta se uloží do `config.json` vedle skriptu.

## Poznámky

- Aplikace používá pouze standardní knihovnu Pythonu a Tkinter.
- Všechna data se ukládají v UTF-8.
- LaTeX escape je řešen automaticky pro text v názvu, ingrediencích, postupu a tipu.
- Pokud je čas nebo počet porcí prázdný, aplikace jen upozorní, ale neblokuje uložení.

## Souborová struktura skriptu

```text
kucharka_app/
├── main.py             # GUI a workflow aplikace
├── recipe_logic.py     # datové modely, JSON I/O, generování LaTeXu
├── config.json         # vygenerováno při prvním výběru projektu
└── README.md
```
