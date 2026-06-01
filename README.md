# Bohus prisovervåking · pilot

Prototypen for Sprint Consulting sin pitch til Bohus. Viser produktmatching og prissammenligning mot Skeidar på sofa-segmentet.

## Mappestruktur

```
bohus-pilot/
├── data/                       Scrapet rådata (CSV)
│   ├── bohus_sofa.csv
│   └── skeidar_sofa.csv
├── pipeline/
│   └── match.py                Matching-pipeline (Python)
├── public/                     Frontend
│   ├── index.html              Prototypen
│   ├── products.json           Genereres av pipelinen
│   ├── competitors.json        Konkurrenter som kan vises/skjules i UI
│   └── competitor_prices.json  Plass for fremtidige priser fra andre konkurrenter
├── requirements.txt
└── vercel.json
```

## Slik gjør du endringer

**Endre produktdata (legge til nye produkter, oppdatere priser):** rediger CSV-filene i `data/`. Pipelinen leser dem som de er.

**Endre matching-logikk (terskler, scoring, attributter):** rediger `pipeline/match.py`. Konstanter ligger på toppen.

**Endre UI:** rediger `public/index.html`. Alt er én fil (HTML + CSS + JS).

**Endre konkurrenter:** rediger `public/competitors.json`. Fremtidige priser fra Fagmøbler, Møbelringen, JYSK og A-møbler kan legges i `public/competitor_prices.json`.

Etter endring i data eller pipeline: kjør `python pipeline/match.py` for å regenerere `public/products.json`.

## Førstegangs oppsett

```bash
# Klon repoet, gå inn i mappa
git clone <repo-url>
cd bohus-pilot

# aktiver virtuelt miljø
& "C:\Users\Per-ChristianGrieg\Bopris\bopris\Scripts\Activate.ps1"
pip install -r requirements.txt
```

## Kjøre lokalt

To steg:

```bash
# 1. Generer products.json fra CSV-data
python pipeline/match.py

# 2. Start lokal server
cd public && python -m http.server 8000
```

Åpne http://localhost:8000 i nettleseren.

**Alternativ:** bruk Live Server-utvidelsen i VS Code. Høyreklikk på `public/index.html` → "Open with Live Server". Auto-reload ved endringer.

Hvorfor server, ikke bare dobbeltklikk? Prototypen henter `products.json` via `fetch()`, og nettlesere blokkerer det mot lokale filer (`file://`).

## Deploy til Vercel

Engangs-oppsett:

1. Push repoet til GitHub
2. Gå til https://vercel.com og logg inn med GitHub
3. Klikk "Import Project" og velg repoet
4. Vercel detekterer `vercel.json` automatisk. Klikk "Deploy".
5. Du får en URL som `bohus-pilot.vercel.app` innen et minutt

Etter dette: hver `git push` til main re-deployer automatisk. Ingen ekstra steg.

**Viktig:** Vercel hoster den statiske siden. Pipelinen kjører fortsatt lokalt. Rutinen for dataoppdatering blir:

```bash
# Oppdater CSV-er i data/
python pipeline/match.py
git add public/products.json data/*.csv
git commit -m "Oppdatert prisdata"
git push
# Vercel deployer automatisk
```

## Pipeline-argumenter

```bash
python pipeline/match.py              # default: kategori=sofa
python pipeline/match.py --kategori sofa
python pipeline/match.py --alle       # alle matchede produkter, ikke bare top-utvalg
```

## Legge til nye kategorier (senger, madrasser, stoler)

1. Legg scrapede CSV-er i `data/`: `bohus_seng.csv`, `skeidar_seng.csv`
2. Sjekk om `parse_form()` i `pipeline/match.py` håndterer kategori-spesifikke attributter (f.eks. størrelse "150x200" for senger)
3. Kjør `python pipeline/match.py --kategori seng`
4. Oppdater frontend-filteret i `public/index.html` (fjern `disabled` på den aktuelle chip)

## Tekniske valg, kort

**Hvorfor matching i Python, ikke JavaScript?** Pipelinen er kompleks (URL-parsing per kjede, scoring, aggregering, rabattlogikk). Vil ikke re-implementere i JS. Matching-resultatet er et **artefakt** som prototypen leser.

**Hvorfor statisk hosting, ikke server-side?** Pilotens scope er å demonstrere konseptet, ikke å være en kjørende produksjonstjeneste. Daglig scraping og matching i produksjon dekkes i pitch-decket som GitHub Actions + SharePoint Lists.

**Hvorfor en mini-server lokalt?** `fetch()` mot `file://` er blokkert av CORS i moderne nettlesere. Live Server eller `python -m http.server` løser det med én kommando.
