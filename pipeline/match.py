"""
Bohus <-> Skeidar matching-pipeline
====================================

Leser scrapet data fra ../data/{kjede}_{kategori}.csv og produserer
en ferdig products.json som prototypen i ../public/ leser direkte.

Kjøring:
    python pipeline/match.py                 # standard: kategori=sofa
    python pipeline/match.py --kategori sofa # eksplisitt

Mappestruktur som forventes:
    bohus-pilot/
    ├── data/
    │   ├── bohus_{kategori}.csv
    │   └── skeidar_{kategori}.csv
    ├── pipeline/
    │   └── match.py        ← denne filen
    └── public/
        └── products.json   ← genereres her

For senere kategorier (senger, madrasser, stoler) er strukturen den
samme. Bohus-parsing kan trenge små justeringer per kategori (f.eks.
"antall seter" gir ikke mening for senger, der må vi parse størrelse
som "150x200" istedet). Det gjøres i parse_bohus_attributter() under.

Avhengigheter:
    pip install pandas
"""

from __future__ import annotations
import argparse
import json
import random
import re
from pathlib import Path
import pandas as pd

# ----------------------------------------------------------------------------
# Konfigurasjon
# ----------------------------------------------------------------------------
ROT = Path(__file__).parent.parent
DATA_DIR = ROT / "data"
PUBLIC_DIR = ROT / "public"

MIN_SCORE_KANDIDAT = 50
MIN_SCORE_HOY_KONFIDENS = 80
ANTALL_TOP_KANDIDATER = 3
DEMO_UTVALG_STR = 10  # antall matchpar i products.json (kuratert for prototype)


# ----------------------------------------------------------------------------
# Attributt-parsing
# ----------------------------------------------------------------------------
def parse_form(tekst: str) -> dict:
    """
    Trekker ut form-attributter fra tekst (URL-slug, navn, type).
    Returnerer: {form, antall_seter, sjeselong, xl}
    """
    if not isinstance(tekst, str):
        return {"form": None, "antall_seter": None, "sjeselong": False, "xl": False}

    s = tekst.lower().replace("ø", "o").replace("å", "a").replace("æ", "ae")
    out = {"form": None, "antall_seter": None, "sjeselong": False, "xl": False}

    if "u-sofa" in s or "usofa" in s:
        out["form"] = "u-sofa"
    elif "hjornesofa" in s:
        out["form"] = "hjornesofa"
    elif "sovesofa" in s or "sovestol" in s:
        out["form"] = "sovesofa"
    elif "lenestol" in s or "-stol" in s or s.endswith("stol"):
        out["form"] = "lenestol"
    elif "daybed" in s:
        out["form"] = "daybed"
    elif "sofagruppe" in s:
        out["form"] = "sofagruppe"
    elif re.search(r"\d[,.\-]?\d?[\-\s]?seter", s) or "sofa" in s:
        out["form"] = "rett-sofa"

    m = re.search(r"(\d)[,.\-]?(\d)?[\-\s]?seter", s)
    if m:
        whole = int(m.group(1))
        frac = m.group(2)
        out["antall_seter"] = whole + 0.5 if frac == "5" else float(whole)

    if "sjeselong" in s: out["sjeselong"] = True
    if re.search(r"\bxl\b", s) or "xl-" in s or "-xl" in s: out["xl"] = True

    return out


def parse_bohus_rad(rad: pd.Series, kategori: str) -> dict:
    """Bohus-rad → felles attributter. Per nå sofa-spesifikk, utvides senere."""
    url = rad["url"] if isinstance(rad["url"], str) else ""
    m = re.match(r"https?://[^/]+/.+?/([^/]+)$", url)
    slug = m.group(1) if m else ""
    type_text = rad["type"] if isinstance(rad["type"], str) else ""

    attrs = parse_form(slug + " " + type_text)

    # For hjørnesofaer uten eksplisitt sete-antall: estimer fra bredde
    if attrs["form"] in ("hjornesofa", "u-sofa") and attrs["antall_seter"] is None:
        bredde = rad.get("bredde_cm")
        if pd.notna(bredde):
            if bredde < 200: attrs["antall_seter_est"] = 2.5
            elif bredde < 250: attrs["antall_seter_est"] = 3.0
            elif bredde < 300: attrs["antall_seter_est"] = 3.5
            else: attrs["antall_seter_est"] = 4.0
        else:
            attrs["antall_seter_est"] = None
    else:
        attrs["antall_seter_est"] = attrs["antall_seter"]

    return attrs


def parse_skeidar_rad(rad: pd.Series, kategori: str) -> dict:
    """Skeidar-rad → felles attributter."""
    url = rad["url"] if isinstance(rad["url"], str) else ""
    m = re.match(r"https?://[^/]+/.+?/.+?/.+?/([^/?]+)", url)
    slug = m.group(1) if m else ""
    variant = rad["variant"] if isinstance(rad["variant"], str) else ""
    attrs = parse_form(slug + " " + variant)
    attrs["antall_seter_est"] = attrs["antall_seter"]
    return attrs


# ----------------------------------------------------------------------------
# Aggregering
# ----------------------------------------------------------------------------
def aggreger_bohus(df: pd.DataFrame, kategori: str) -> pd.DataFrame:
    """1853 SKU → ~212 produkter (navn × type). Median som representativ pris.
    Rabatt-info: hvor mange varianter har førpris, hva er snitt-rabatten.
    """
    attrs = df.apply(lambda r: parse_bohus_rad(r, kategori), axis=1, result_type="expand")
    full = pd.concat([df.reset_index(drop=True), attrs.reset_index(drop=True)], axis=1)

    # Beregn rabatt per rad først
    full["har_førpris"] = full["førpris"].notna()
    full["rabatt_pct"] = (1 - full["nåpris"] / full["førpris"]) * 100

    return full.groupby(["navn", "type"], as_index=False).agg(
        pris=("nåpris", "median"),
        bredde=("bredde_cm", "median"),
        leverandor=("leverandor", "first"),
        merke=("merke", "first"),
        serie=("serie", "first"),
        form=("form", "first"),
        antall_seter_est=("antall_seter_est", "first"),
        sjeselong=("sjeselong", "first"),
        xl=("xl", "first"),
        url=("url", "first"),
        n_varianter=("sku", "count"),
        n_rabatt=("har_førpris", "sum"),
        pris_min=("nåpris", "min"),
        pris_maks=("nåpris", "max"),
        førpris_median=("førpris", "median"),
        rabatt_pct_median=("rabatt_pct", "median"),
    )


def aggreger_skeidar(df: pd.DataFrame, kategori: str) -> pd.DataFrame:
    """495 rader → ~120 produkter (variant)."""
    attrs = df.apply(lambda r: parse_skeidar_rad(r, kategori), axis=1, result_type="expand")
    full = pd.concat([df.reset_index(drop=True), attrs.reset_index(drop=True)], axis=1)

    return full.groupby(["variant"], as_index=False).agg(
        pris=("nåpris", "median"),
        leverandor=("leverandor", "first"),
        form=("form", "first"),
        antall_seter_est=("antall_seter_est", "first"),
        sjeselong=("sjeselong", "first"),
        xl=("xl", "first"),
        url=("url", "first"),
        førpris=("førpris", "first"),
        rabatt_pct=("rabatt_prosent", "first"),
        kampanje=("kampanje", "first"),
    )


# ----------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------
def score_par(b: pd.Series, s: pd.Series) -> tuple[int, list]:
    """Returner (score 0-100, begrunnelser)."""
    score = 0
    grunner = []

    b_form, s_form = b["form"], s["form"]
    if b_form is None or s_form is None:
        return 0, []

    if b_form == s_form:
        score += 40
        grunner.append(f"form={b_form}")
    elif {b_form, s_form} == {"hjornesofa", "u-sofa"}:
        score += 30
        grunner.append("hjørne/u-sofa")
    else:
        return 0, []

    pris_b, pris_s = b["pris"], s["pris"]
    if pd.notna(pris_b) and pd.notna(pris_s):
        diff = abs(pris_b - pris_s) / max(pris_b, pris_s)
        if diff < 0.10: score += 30; grunner.append(f"pris≈ ({diff*100:.0f}%)")
        elif diff < 0.20: score += 22; grunner.append(f"pris~ ({diff*100:.0f}%)")
        elif diff < 0.35: score += 12; grunner.append(f"pris~~ ({diff*100:.0f}%)")
        elif diff < 0.50: score += 4
        else: return 0, []

    sb, ss = b["antall_seter_est"], s["antall_seter_est"]
    if pd.notna(sb) and pd.notna(ss):
        if sb == ss: score += 20; grunner.append(f"{sb} seter")
        elif abs(sb - ss) <= 0.5: score += 12; grunner.append(f"{sb}~{ss} seter")

    if b["sjeselong"] == s["sjeselong"]:
        score += 5
        if b["sjeselong"]: grunner.append("sjeselong")
    if b["xl"] == s["xl"]:
        score += 5
        if b["xl"]: grunner.append("XL")

    return score, grunner


# ----------------------------------------------------------------------------
# Matching
# ----------------------------------------------------------------------------
def matche(bohus_agg: pd.DataFrame, skeidar_agg: pd.DataFrame) -> list:
    """For hvert Bohus-produkt: finn topp-N Skeidar-kandidater."""
    matches = []
    for _, b in bohus_agg.iterrows():
        if b["form"] is None:
            continue
        kandidater = []
        for _, s in skeidar_agg.iterrows():
            if s["form"] is None:
                continue
            sc, gr = score_par(b, s)
            if sc >= MIN_SCORE_KANDIDAT:
                kandidater.append({
                    "skeidar": s,
                    "score": sc,
                    "grunner": gr,
                })
        kandidater.sort(key=lambda x: -x["score"])
        matches.append({"bohus": b, "kandidater": kandidater[:ANTALL_TOP_KANDIDATER]})
    return matches


# ----------------------------------------------------------------------------
# Prishistorikk-generering (demo-data)
# ----------------------------------------------------------------------------
def gen_history(current: int, seed: int, days: int = 18) -> list:
    """Random walk rundt nåpris. Markert som demo-data i frontend."""
    rng = random.Random(seed)
    hist = [int(current)]
    for _ in range(days - 1):
        prev = hist[-1]
        if rng.random() < 0.15:
            change = rng.choice([-500, -300, -200, 200, 300, 500, 1000, -1000])
            new = max(prev * 0.85, prev + change)
            new = round(new / 10) * 10
        else:
            new = prev
        hist.append(int(new))
    hist.reverse()
    return hist


# ----------------------------------------------------------------------------
# Output: products.json
# ----------------------------------------------------------------------------
FORM_LABEL = {
    "rett-sofa": "Sofa",
    "hjornesofa": "Hjørnesofa",
    "u-sofa": "U-sofa",
    "sovesofa": "Sovesofa",
    "lenestol": "Lenestol",
}

def short_key(navn: str, idx: int, used: set) -> str:
    """Lag en kort, lesbar produkt-nøkkel for prototype-bruk."""
    first_words = navn.split("·")[0].strip().split(" ")
    skip = {"bohus", "exclusive", "by", "collection"}
    meaningful = [w for w in first_words if w.lower() not in skip]
    base = meaningful[0].lower().replace("ø", "o").replace("å", "a").replace("æ", "ae") if meaningful else f"p{idx}"
    key = base
    suffix = 1
    while key in used:
        suffix += 1
        key = f"{base}{suffix}"
    used.add(key)
    return key


def velg_demo_matchpar(matches: list, n: int = DEMO_UTVALG_STR) -> list:
    """Plukk et variert utvalg matchpar fordelt på form, høy konfidens først."""
    forms_target = {"rett-sofa": 5, "hjornesofa": 4, "sovesofa": 2, "lenestol": 1}
    forms_count = {k: 0 for k in forms_target}
    seen_bohus = set()
    seen_skeidar = set()
    picks = []

    sortert = sorted(
        [m for m in matches if m["kandidater"] and m["kandidater"][0]["score"] >= 75],
        key=lambda x: -x["kandidater"][0]["score"],
    )
    for m in sortert:
        if len(picks) >= n: break
        b = m["bohus"]
        form = b["form"]
        if form not in forms_target: continue
        if forms_count[form] >= forms_target[form]: continue
        if b["navn"] in seen_bohus: continue
        top_var = m["kandidater"][0]["skeidar"]["variant"]
        if top_var in seen_skeidar: continue

        picks.append(m)
        seen_bohus.add(b["navn"])
        seen_skeidar.add(top_var)
        forms_count[form] += 1
    return picks


def bygg_product_entry(m: dict, idx: int, used_keys: set) -> tuple[str, dict]:
    """Bygg én entry i products.json fra et matchpar."""
    b = m["bohus"]
    top = m["kandidater"][0]
    s = top["skeidar"]

    # Display-navn (forkort lange merker)
    display = f"{b['navn']} · {b['type']}"
    display = display.replace("Bohus Exclusive by Storm Storm ", "Storm ")
    display = display.replace("Bohus Exclusive by Tone Kroken ", "Tone Kroken ")

    # Kategori-label
    form = b["form"]
    cat_label = FORM_LABEL.get(form, "Sofa")
    merke = b["merke"] if pd.notna(b.get("merke")) else None
    leverandor = b["leverandor"] if pd.notna(b.get("leverandor")) else None
    second = merke or leverandor or "Egenmerke"
    # Rens veldig lange merkenavn
    if "Storm Storm" in second: second = "Bohus Exclusive by Storm"
    if "Tone Kroken" in second: second = "Bohus Exclusive by Tone Kroken"
    category = f"{cat_label} · {second}"

    # Match-info
    score = top["score"]
    match_step = "Steg 2" if score >= 95 else "Steg 3"
    match_type = ("Steg 2 · attributter + leverandørmatch"
                  if score >= 95 else "Steg 3 · attributtbasert match")
    match_konf = "høy" if score >= 80 else "middels"

    # Gap
    gap_pct = round((b["pris"] - s["pris"]) / s["pris"] * 100, 1)

    # Rabatt - Bohus
    n_rabatt = int(b["n_rabatt"])
    n_var = int(b["n_varianter"])
    bohus_kampanje = n_rabatt > 0
    bohus_andel = round(n_rabatt / n_var * 100) if n_var else 0
    bohus_forpris = int(b["førpris_median"]) if bohus_kampanje and pd.notna(b["førpris_median"]) else None
    bohus_rabatt = int(round(b["rabatt_pct_median"])) if bohus_kampanje and pd.notna(b["rabatt_pct_median"]) else 0

    # Rabatt - Skeidar
    skeidar_forpris = int(s["førpris"]) if pd.notna(s["førpris"]) else None
    skeidar_rabatt = int(round(s["rabatt_pct"])) if pd.notna(s["rabatt_pct"]) else 0
    skeidar_kampanje = bool(s["kampanje"]) if pd.notna(s["kampanje"]) else False

    # Skeidar-leverandør (eller "egenmerke" hvis nan)
    skeidar_lev = s["leverandor"]
    if not isinstance(skeidar_lev, str) or skeidar_lev == "" or pd.isna(skeidar_lev):
        skeidar_lev = "Skeidar (egenmerke)"

    # Generer demo-prishistorikk (deterministisk seed pr. produkt)
    seed = abs(hash(b["navn"] + b["type"])) % 10**6
    hist_b = gen_history(int(b["pris"]), seed)
    hist_s = gen_history(int(s["pris"]), seed + 1)

    # Beregn "sist endret"
    last_change_idx = None
    for j in range(len(hist_b) - 1, 0, -1):
        if hist_b[j] != hist_b[j - 1]:
            last_change_idx = j
            break
    if last_change_idx is None:
        last_changed = "Mer enn 90 dager siden"
    else:
        days_ago = (17 - last_change_idx) * 5
        last_changed = "I dag" if days_ago == 0 else f"{days_ago} dager siden"

    key = short_key(display, idx, used_keys)

    entry = {
        "name": display,
        "category": category,
        "kvi": True,
        "current": int(b["pris"]),
        "varianter": n_var,
        "prisMin": int(b["pris_min"]),
        "prisMaks": int(b["pris_maks"]),
        "matchType": match_type,
        "matchStep": match_step,
        "matchConfidence": match_konf,
        "matchScore": score,
        "matchReason": ", ".join(top["grunner"]),
        "skeidarVariant": s["variant"],
        "skeidarLeverandor": skeidar_lev,
        "skeidarPrice": int(s["pris"]),
        "skeidarUrl": s["url"],
        "bohusUrl": b["url"],
        "gapPct": gap_pct,
        "lastChanged": last_changed,
        "bohusFørpris": bohus_forpris,
        "bohusRabatt": bohus_rabatt,
        "bohusKampanje": bohus_kampanje,
        "bohusKampanjeAndel": bohus_andel,
        "skeidarFørpris": skeidar_forpris,
        "skeidarRabatt": skeidar_rabatt,
        "skeidarKampanje": skeidar_kampanje,
        "history": {"bohus": hist_b, "skeidar": hist_s},
    }
    return key, entry


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Bohus <-> Skeidar matching")
    parser.add_argument("--kategori", default="sofa",
                        help="Produktkategori (sofa, seng, madrass, stol). Default: sofa")
    parser.add_argument("--alle", action="store_true",
                        help="Inkluder alle matchet produkter, ikke bare top-utvalget")
    args = parser.parse_args()

    kategori = args.kategori
    bohus_csv = DATA_DIR / f"bohus_{kategori}.csv"
    skeidar_csv = DATA_DIR / f"skeidar_{kategori}.csv"

    print(f"Bohus <-> Skeidar matching · kategori: {kategori}")
    print("=" * 60)

    for f in (bohus_csv, skeidar_csv):
        if not f.exists():
            raise FileNotFoundError(f"Mangler datafil: {f}")

    bohus = pd.read_csv(bohus_csv)
    skeidar = pd.read_csv(skeidar_csv)
    print(f"Bohus:   {len(bohus):5d} rader (fra {bohus_csv.name})")
    print(f"Skeidar: {len(skeidar):5d} rader (fra {skeidar_csv.name})")

    print("\nAggregerer...")
    bohus_agg = aggreger_bohus(bohus, kategori)
    skeidar_agg = aggreger_skeidar(skeidar, kategori)
    print(f"  Bohus: {len(bohus_agg):3d} produkter")
    print(f"  Skeidar: {len(skeidar_agg):3d} produkter")

    print("\nKjører matching...")
    matches = matche(bohus_agg, skeidar_agg)
    med_match = sum(1 for m in matches if m["kandidater"])
    hoy_konf = sum(1 for m in matches
                   if m["kandidater"] and m["kandidater"][0]["score"] >= MIN_SCORE_HOY_KONFIDENS)
    print(f"  {med_match}/{len(matches)} produkter har kandidat")
    print(f"  {hoy_konf} høy konfidens (≥{MIN_SCORE_HOY_KONFIDENS})")

    # Velg utvalg eller alle
    if args.alle:
        utvalg = [m for m in matches if m["kandidater"]]
        print(f"\nBruker alle {len(utvalg)} matchede produkter (--alle)")
    else:
        utvalg = velg_demo_matchpar(matches)
        print(f"\nPlukket {len(utvalg)} demo-matchpar (variert utvalg)")

    # Bygg products.json
    products = {}
    used_keys = set()
    for i, m in enumerate(utvalg):
        key, entry = bygg_product_entry(m, i, used_keys)
        products[key] = entry

    PUBLIC_DIR.mkdir(exist_ok=True)
    out_path = PUBLIC_DIR / "products.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Skrev {out_path.relative_to(ROT)} ({len(products)} produkter)")
    print("\nPrototypen henter denne filen automatisk når du åpner public/index.html")


if __name__ == "__main__":
    main()
