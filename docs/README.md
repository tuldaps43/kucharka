# Kuchařka – mobilní webová aplikace

Tato složka obsahuje plně offline PWA pro zobrazení receptů při vaření. Aplikace běží bez build kroku, čistě v HTML, CSS a JavaScript.

## Struktura složky

```text
docs/
├── index.html
├── styles.css
├── app.js
├── service-worker.js
├── manifest.webmanifest
├── recepty.json
├── make_icons.py
├── icons/
│   ├── 192.png
│   └── 512.png
├── obrazky/
│   └── (fotografie receptů)
└── README.md
```

## Lokální spuštění

V adresáři projektu spusťte:

```bash
cd docs
python -m http.server 8000
```

Potom otevřete v prohlížeči adresu:

```text
http://localhost:8000/
```

## Nasazení na GitHub Pages

1. Pushněte obsah složky `docs/` do repozitáře.
2. V nastavení GitHub Pages nastavte zdroj na `GitHub Actions` nebo `main branch / docs folder` podle vašeho nastavení.
3. URL bude ve tvaru:

```text
https://<uzivatel>.github.io/<repo>/
```

Soubory jsou připravené pro použití v podsložce, například `/kucharka/`.

## Poznámka

- Aplikace používá relativní cesty, aby fungovala i ve podsložce GitHub Pages.
- Datový soubor `recepty.json` je načítán z `docs/` a obrázky z `docs/obrazky/`.
- Pokud chybí data nebo připojení, aplikace zkusí načíst cache z service workera.
