#!/usr/bin/env python3
"""metadata_store.py — Database centrale per rating, colorlabel e tag.

Step 1 del piano "tag / colorlabel / rating": SOLO il modulo dati, senza
interfaccia. Le voci di menu, gli indicatori sulle miniature e il pannello
dedicato arrivano negli step successivi, sopra questa base.

Scelta di progettazione (concordata con l'utente):
  - UN SOLO file JSON centrale per tutta la libreria (non un sidecar per
    cartella, non embedding XMP/IPTC nei file). Motivo: tag/rating/colore
    devono valere anche per video e PDF, non solo per i formati che
    supportano EXIF/XMP scrivibile con le librerie gia' in uso
    (piexif non scrive IPTC ed e' limitato a JPEG/TIFF/WebP per il resto).
    L'embedding XMP/IPTC nei file resta un'opzione futura, da costruire
    SOPRA questo database, non al suo posto.
  - Il file viene scritto SOLO per i path che hanno almeno un valore non
    di default (rating>0, colore impostato o almeno un tag). Un file
    riportato ai valori di default esce dal database invece di restare
    come voce vuota: tiene il file piccolo e coerente nel tempo.
  - Scrittura atomica (temp + rename), stesso schema gia' usato in
    write_exif()/write_gps() di exif_editor.py, per non rischiare un file
    JSON troncato in caso di crash a meta' scrittura.
  - Lock a livello di modulo per serializzare le scritture, stesso schema
    di _history_lock in image_sorter.py.

LIMITE NOTO (non risolto in questo step, da valutare se necessario):
  le voci sono indicizzate per percorso assoluto del file. Rinominare o
  spostare un file FUORI da Image Sorter (es. da un altro programma, o da
  terminale) orfanizza la sua voce nel database — esattamente come gia'
  succede oggi per lo storico (HISTORY_FILE) quando un file scompare.
  Rinomina/spostamento fatti DENTRO Image Sorter possono essere gestiti
  agganciandosi alle stesse funzioni che gia' spostano/rinominano i file,
  ma e' rimandato a quando la UI che consuma questo modulo sara' pronta.
"""

import os
import json
import threading
import time

VERSION = "1.3.1"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

METADATA_FILE = os.path.join(SCRIPT_DIR, "image_sorter_metadata.json")

# Schema colorlabel: 5 colori stile Adobe/Lightroom, come richiesto.
# Ordine intenzionale: e' l'ordine in cui compariranno nei menu.
COLOR_LABELS = [
    ("red",    "Rosso",  "#e74c3c"),
    ("yellow", "Giallo", "#f1c40f"),
    ("green",  "Verde",  "#27ae60"),
    ("blue",   "Blu",    "#2980b9"),
    ("purple", "Viola",  "#8e44ad"),
]
COLOR_IDS   = {c[0] for c in COLOR_LABELS}
COLOR_NAME  = {c[0]: c[1] for c in COLOR_LABELS}
COLOR_HEX   = {c[0]: c[2] for c in COLOR_LABELS}

RATING_MIN = 0
RATING_MAX = 5

_DEFAULT_ENTRY = {"rating": 0, "colors": [], "tags": []}

_lock = threading.Lock()
_cache = None   # dict path -> {"rating":int, "colors":[str,...], "tags":[str,...]}
_tag_recency = None   # dict tag -> timestamp unix dell'ultimo utilizzo,
                       # per l'ordinamento "per uso recente" della nuvola
                       # di tag nella finestra dedicata (step successivo).
_tag_registry = None   # set di tutti i tag "conosciuti" dalla libreria,
                       # creati esplicitamente dal tab Impostazioni > Tag
                       # ANCHE se non ancora applicati a nessun file — a
                       # differenza di get_all_tags() (step 3), che prima
                       # di questo registro esisteva solo per i tag gia'
                       # in uso in _cache.
_tag_groups = None   # dict nome_gruppo -> [tag,...], ordine di creazione
                     # preservato (dict insertion order). Un gruppo e' un
                     # raggruppamento libero, non esclusivo: lo stesso tag
                     # puo' stare in piu' gruppi.


# ── Caricamento / salvataggio ───────────────────────────────────────────────
def _load():
    """Carica il database in _cache se non e' gia' in memoria.
    Da chiamare SEMPRE prima di leggere _cache (tiene la cache calda per
    tutta la sessione, come fa image_sorter.py con la history)."""
    global _cache, _tag_recency, _tag_registry, _tag_groups
    if _cache is not None:
        return
    data = {}
    recency = {}
    registry = None   # None = chiave assente dal file (db precedente a
                       # questa versione) -> va migrata dai tag in uso
    groups = {}
    try:
        if os.path.isfile(METADATA_FILE):
            with open(METADATA_FILE, encoding="utf-8") as f:
                raw = json.load(f)
            files = raw.get("files", {}) if isinstance(raw, dict) else {}
            for path, entry in files.items():
                if not isinstance(entry, dict):
                    continue
                data[path] = _sanitize_entry(entry)
            raw_recency = raw.get("tag_recency", {}) if isinstance(raw, dict) else {}
            if isinstance(raw_recency, dict):
                for t, ts in raw_recency.items():
                    if isinstance(t, str) and isinstance(ts, (int, float)):
                        recency[t] = float(ts)
            if isinstance(raw, dict) and "tag_registry" in raw:
                raw_registry = raw.get("tag_registry", [])
                if isinstance(raw_registry, list):
                    registry = {t for t in raw_registry if isinstance(t, str) and t.strip()}
            raw_groups = raw.get("tag_groups", {}) if isinstance(raw, dict) else {}
            if isinstance(raw_groups, dict):
                for gname, gtags in raw_groups.items():
                    if not isinstance(gname, str) or not gname.strip():
                        continue
                    if not isinstance(gtags, list):
                        continue
                    seen = set()
                    clean = []
                    for t in gtags:
                        if isinstance(t, str) and t.strip() and t not in seen:
                            seen.add(t)
                            clean.append(t)
                    groups[gname] = clean
    except Exception:
        data = {}
        recency = {}
        registry = None
        groups = {}
    if registry is None:
        # Migrazione: db scritto da una versione precedente al registro,
        # popolalo con i tag gia' in uso per non "perdere" tag esistenti
        # dal tab di gestione.
        registry = set()
        for entry in data.values():
            registry.update(entry["tags"])
    # I tag citati nei gruppi restano comunque nel registro, anche se il
    # file era incoerente per qualche motivo (edit manuale del JSON).
    for gtags in groups.values():
        registry.update(gtags)
    _cache = data
    _tag_recency = recency
    _tag_registry = registry
    _tag_groups = groups


def _sanitize_entry(entry):
    """Normalizza una entry letta dal disco: valori fuori range o di tipo
    sbagliato non devono far crollare l'app, vengono riportati ai default.

    Colorlabel multiple: il campo e' "colors" (lista), non piu' "color"
    (stringa singola) come nella prima versione del modulo — un file
    scritto dalla versione precedente aveva al massimo un colore, letto
    qui e migrato automaticamente in una lista di un elemento, cosi' i
    dati gia' salvati non si perdono passando alla nuova versione."""
    try:
        rating = int(entry.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0
    rating = max(RATING_MIN, min(RATING_MAX, rating))

    if "colors" in entry:
        raw_colors = entry.get("colors", [])
        if not isinstance(raw_colors, list):
            raw_colors = []
    else:
        # Migrazione dal vecchio formato a colore singolo (versioni del
        # modulo precedenti a questa): "color": "red" -> ["red"].
        _legacy = entry.get("color", "")
        raw_colors = [_legacy] if _legacy else []
    seen_c = set()
    colors = []
    for c in raw_colors:
        if c in COLOR_IDS and c not in seen_c:
            seen_c.add(c)
            colors.append(c)

    tags = entry.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    # dedup preservando l'ordine, scarta valori non stringa o vuoti
    seen = set()
    clean_tags = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            clean_tags.append(t)

    return {"rating": rating, "colors": colors, "tags": clean_tags}


def _is_default(entry):
    return entry["rating"] == 0 and not entry["colors"] and not entry["tags"]


def _save():
    """Scrive _cache su disco, in modo atomico. Le entry tornate al default
    vengono escluse (vedi nota nel docstring del modulo)."""
    if _cache is None:
        return
    try:
        files = {p: e for p, e in _cache.items() if not _is_default(e)}
        # tag_recency: tiene solo i tag ancora effettivamente in uso da
        # qualche file — altrimenti si accumulerebbe per sempre anche
        # dopo che un tag smette di essere usato da chiunque.
        live_tags = set()
        for e in files.values():
            live_tags.update(e["tags"])
        recency = {t: ts for t, ts in (_tag_recency or {}).items() if t in live_tags}
        payload = {"version": 1, "files": files, "tag_recency": recency,
                   "tag_registry": sorted(_tag_registry or [], key=str.lower),
                   "tag_groups": dict(_tag_groups or {})}
        tmp_path = METADATA_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, METADATA_FILE)
    except Exception:
        try:
            if os.path.isfile(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass


def _touch_tag_recency(tags):
    """Aggiorna il timestamp di "ultimo utilizzo" di uno o piu' tag —
    chiamata da add_tag/bulk_add_tag/set_tags quando un tag viene
    effettivamente applicato a un file. Va chiamata SOTTO _lock, con
    _tag_recency gia' caricato (mai da sola)."""
    global _tag_recency
    if _tag_recency is None:
        _tag_recency = {}
    now = time.time()
    for t in tags:
        _tag_recency[t] = now


# ── Lettura ──────────────────────────────────────────────────────────────
def get_meta(path):
    """Ritorna {"rating":int, "colors":[str,...], "tags":[str,...]} per
    path. Sempre una COPIA: modificare il dict ritornato non tocca il
    database (bisogna passare dalle set_*/toggle_*/add_tag/... qui sotto).

    "colors" e' una LISTA (colorlabel multiple, non un colore singolo
    come nella prima versione del modulo): un file puo' avere zero, una
    o piu' colorlabel assegnate insieme."""
    path = os.path.abspath(path)
    with _lock:
        _load()
        entry = _cache.get(path, _DEFAULT_ENTRY)
        return {"rating": entry["rating"], "colors": list(entry["colors"]),
                "tags": list(entry["tags"])}


def get_all_tags():
    """Elenco di tutti i tag distinti della libreria, ordinato
    alfabeticamente (case-insensitive) — per l'autocomplete dello step 3.

    Unione di due insiemi: i tag effettivamente applicati a qualche file
    (_cache) e quelli creati esplicitamente dal tab Impostazioni > Tag ma
    non ancora applicati a nessun file (_tag_registry, vedi create_tag)."""
    with _lock:
        _load()
        tags = set(_tag_registry or [])
        for entry in _cache.values():
            tags.update(entry["tags"])
        return sorted(tags, key=str.lower)


def get_tag_counts():
    """{tag: numero di file che lo usano in libreria} — per
    l'ordinamento "per frequenza" della nuvola di tag."""
    with _lock:
        _load()
        counts = {}
        for entry in _cache.values():
            for t in entry["tags"]:
                counts[t] = counts.get(t, 0) + 1
        return counts


def get_tags_ordered(mode="alpha"):
    """Elenco di tutti i tag distinti, ordinati secondo `mode`:
    "alpha" (alfabetico, default) — "recent" (usati piu' di recente
    prima) — "freq" (piu' usati in libreria prima).

    A parita' di criterio secondario (es. mai usato / stesso conteggio)
    l'ordine resta sempre alfabetico: si ordina prima per nome (base
    stabile), poi il sort stabile di Python preserva quell'ordine fra
    i pari merito quando si riordina per data/conteggio sopra."""
    with _lock:
        _load()
        tags = set(_tag_registry or [])
        counts = {}
        for entry in _cache.values():
            for t in entry["tags"]:
                tags.add(t)
                counts[t] = counts.get(t, 0) + 1
        recency = dict(_tag_recency or {})
    ordered = sorted(tags, key=str.lower)
    if mode == "recent":
        ordered.sort(key=lambda t: recency.get(t, 0), reverse=True)
    elif mode == "freq":
        ordered.sort(key=lambda t: counts.get(t, 0), reverse=True)
    return ordered


def has_any_metadata(path):
    """True se il file ha almeno un rating/colore/tag impostato — utile per
    decidere se disegnare un indicatore sulla miniatura senza dover
    costruire l'intero dict get_meta() per ogni thumbnail visibile."""
    path = os.path.abspath(path)
    with _lock:
        _load()
        return path in _cache   # per costruzione, in cache solo se non-default


# ── Scrittura: singolo file ─────────────────────────────────────────────────
def set_rating(path, value):
    """Imposta il rating (0-5; 0 = nessuna valutazione). Valori fuori
    range vengono ricondotti agli estremi invece di sollevare eccezione,
    coerente con _sanitize_entry."""
    path = os.path.abspath(path)
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0
    value = max(RATING_MIN, min(RATING_MAX, value))
    with _lock:
        _load()
        entry = dict(_cache.get(path, _DEFAULT_ENTRY))
        entry["rating"] = value
        entry["colors"] = list(entry["colors"])
        entry["tags"] = list(entry["tags"])
        if _is_default(entry):
            _cache.pop(path, None)
        else:
            _cache[path] = entry
        _save()


def toggle_color(path, color_id):
    """Aggiunge color_id alle colorlabel del file se non c'e' gia',
    altrimenti lo rimuove — le colorlabel sono MULTIPLE (non escludenti
    come nella prima versione del modulo, che ne ammetteva una sola):
    un file puo' avere piu' colori assegnati insieme."""
    path = os.path.abspath(path)
    if color_id not in COLOR_IDS:
        return
    with _lock:
        _load()
        entry = dict(_cache.get(path, _DEFAULT_ENTRY))
        colors = list(entry["colors"])
        if color_id in colors:
            colors.remove(color_id)
        else:
            colors.append(color_id)
        entry["colors"] = colors
        entry["tags"] = list(entry["tags"])
        if _is_default(entry):
            _cache.pop(path, None)
        else:
            _cache[path] = entry
        _save()


def add_tag(path, tag):
    tag = (tag or "").strip()
    if not tag:
        return
    path = os.path.abspath(path)
    with _lock:
        _load()
        entry = dict(_cache.get(path, _DEFAULT_ENTRY))
        entry["tags"] = list(entry["tags"])
        if tag not in entry["tags"]:
            entry["tags"].append(tag)
        _cache[path] = entry   # con un tag non e' mai default, no pop
        _touch_tag_recency([tag])
        _save()


def remove_tag(path, tag):
    path = os.path.abspath(path)
    with _lock:
        _load()
        entry = _cache.get(path)
        if entry is None:
            return
        entry = dict(entry)
        entry["tags"] = [t for t in entry["tags"] if t != tag]
        if _is_default(entry):
            _cache.pop(path, None)
        else:
            _cache[path] = entry
        _save()


def set_tags(path, tags):
    """Sostituisce l'intera lista tag (usata dal dialog di editing tag,
    step 3, dove l'utente modifica una lista e conferma in blocco)."""
    path = os.path.abspath(path)
    clean = []
    seen = set()
    for t in (tags or []):
        t = (t or "").strip()
        if t and t not in seen:
            seen.add(t)
            clean.append(t)
    with _lock:
        _load()
        entry = dict(_cache.get(path, _DEFAULT_ENTRY))
        entry["tags"] = clean
        if _is_default(entry):
            _cache.pop(path, None)
        else:
            _cache[path] = entry
        if clean:
            _touch_tag_recency(clean)
        _save()


# ── Gestione libreria tag (tab Impostazioni > Tag) ──────────────────────────
# A differenza di add_tag/set_tags (che agiscono su un file), queste
# funzioni agiscono sulla LIBRERIA: creare un tag prima ancora di
# applicarlo a un file, rinominarlo/eliminarlo ovunque venga usato, e
# raggruppare tag in "Gruppi Tag" (puramente organizzativi per ora: le
# funzioni che li sfruttano arriveranno in seguito, come richiesto).
def create_tag(name):
    """Crea un tag nella libreria senza assegnarlo a nessun file. Come
    _apply_typed() nella finestra Tag: case-insensitive, se esiste gia'
    un tag scritto diversamente solo per maiuscole/minuscole si riusa
    quello invece di crearne un duplicato concettuale. Ritorna il nome
    canonico del tag (nuovo o gia' esistente), o None se `name` e' vuoto."""
    name = (name or "").strip()
    if not name:
        return None
    with _lock:
        _load()
        existing = next((t for t in _tag_registry if t.lower() == name.lower()), None)
        if existing:
            return existing
        _tag_registry.add(name)
        _save()
        return name


def rename_tag(old, new):
    """Rinomina un tag OVUNQUE compaia: registro, tutti i file che lo
    usano, tag_recency e appartenenza ai gruppi. Se `new` esiste gia'
    (anche solo per maiuscole/minuscole), i due tag vengono uniti in
    quello esistente invece di creare un duplicato."""
    old = (old or "").strip()
    new = (new or "").strip()
    if not old or not new or old == new:
        return
    with _lock:
        _load()
        # "t != old" e' essenziale: senza, un cambio di sole maiuscole/
        # minuscole (es. "mare" -> "Mare") troverebbe SE STESSO come
        # "tag gia' esistente" (stessa forma case-insensitive) e
        # ripristinerebbe la vecchia grafia, annullando la rinomina.
        canonical = next((t for t in _tag_registry if t.lower() == new.lower() and t != old), new)
        _tag_registry.discard(old)
        _tag_registry.add(canonical)
        for path, entry in list(_cache.items()):
            if old in entry["tags"]:
                merged = [canonical if t == old else t for t in entry["tags"]]
                seen = set()
                clean = []
                for t in merged:
                    if t not in seen:
                        seen.add(t)
                        clean.append(t)
                entry = dict(entry)
                entry["tags"] = clean
                _cache[path] = entry
        if _tag_recency and old in _tag_recency:
            ts = _tag_recency.pop(old)
            _tag_recency[canonical] = max(ts, _tag_recency.get(canonical, 0))
        for gname, gtags in _tag_groups.items():
            if old in gtags:
                merged = [canonical if t == old else t for t in gtags]
                seen = set()
                clean = []
                for t in merged:
                    if t not in seen:
                        seen.add(t)
                        clean.append(t)
                _tag_groups[gname] = clean
        _save()


def delete_tag(tag):
    """Elimina un tag OVUNQUE: registro, tutti i file che lo usano,
    tag_recency e tutti i gruppi che lo contenevano."""
    tag = (tag or "").strip()
    if not tag:
        return
    with _lock:
        _load()
        _tag_registry.discard(tag)
        for path, entry in list(_cache.items()):
            if tag in entry["tags"]:
                entry = dict(entry)
                entry["tags"] = [t for t in entry["tags"] if t != tag]
                if _is_default(entry):
                    _cache.pop(path, None)
                else:
                    _cache[path] = entry
        if _tag_recency:
            _tag_recency.pop(tag, None)
        for gname, gtags in _tag_groups.items():
            if tag in gtags:
                _tag_groups[gname] = [t for t in gtags if t != tag]
        _save()


def get_tag_groups():
    """{nome_gruppo: [tag,...]} — copia, ordine di creazione preservato."""
    with _lock:
        _load()
        return {g: list(tags) for g, tags in _tag_groups.items()}


def create_tag_group(name):
    """Crea un gruppo vuoto. Case-insensitive come create_tag: se esiste
    gia' un gruppo con lo stesso nome (a meno di maiuscole/minuscole),
    ritorna quello invece di crearne uno nuovo."""
    name = (name or "").strip()
    if not name:
        return None
    with _lock:
        _load()
        existing = next((g for g in _tag_groups if g.lower() == name.lower()), None)
        if existing:
            return existing
        _tag_groups[name] = []
        _save()
        return name


def rename_tag_group(old, new):
    """Rinomina un gruppo. Se `new` esiste gia' (a meno di maiuscole/
    minuscole), i due gruppi vengono uniti (unione dei rispettivi tag)
    invece di creare un duplicato."""
    old = (old or "").strip()
    new = (new or "").strip()
    if not old or not new or old == new:
        return
    with _lock:
        _load()
        if old not in _tag_groups:
            return
        existing = next((g for g in _tag_groups if g.lower() == new.lower() and g != old), None)
        target = existing or new
        tags = _tag_groups.pop(old)
        if target in _tag_groups:
            for t in tags:
                if t not in _tag_groups[target]:
                    _tag_groups[target].append(t)
        else:
            _tag_groups[target] = tags
        _save()


def delete_tag_group(name):
    """Elimina il gruppo. I tag NON vengono toccati: un gruppo e' solo
    un raggruppamento, non un contenitore esclusivo dei suoi tag."""
    with _lock:
        _load()
        _tag_groups.pop(name, None)
        _save()


def toggle_tag_in_group(group, tag):
    """Aggiunge/toglie `tag` dal gruppo `group` (checkbox nel tab
    Impostazioni > Tag). Se il tag non era ancora nel registro/libreria
    viene creato al volo, stesso principio di create_tag."""
    group = (group or "").strip()
    tag = (tag or "").strip()
    if not group or not tag:
        return
    with _lock:
        _load()
        if group not in _tag_groups:
            return
        canonical = next((t for t in _tag_registry if t.lower() == tag.lower()), tag)
        _tag_registry.add(canonical)
        gtags = _tag_groups[group]
        if canonical in gtags:
            _tag_groups[group] = [t for t in gtags if t != canonical]
        else:
            _tag_groups[group] = gtags + [canonical]
        _save()


# ── Scrittura: multi-selezione ──────────────────────────────────────────────
# Il resto dell'app passa quasi sempre una lista "targets" (selezione
# corrente) alle azioni dei menu contestuali: queste varianti bulk evitano
# di fare N load/save separati (una sola lettura, una sola scrittura).
def bulk_set_rating(paths, value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0
    value = max(RATING_MIN, min(RATING_MAX, value))
    with _lock:
        _load()
        for path in paths:
            path = os.path.abspath(path)
            entry = dict(_cache.get(path, _DEFAULT_ENTRY))
            entry["rating"] = value
            entry["colors"] = list(entry["colors"])
            entry["tags"] = list(entry["tags"])
            if _is_default(entry):
                _cache.pop(path, None)
            else:
                _cache[path] = entry
        _save()


def bulk_toggle_color(paths, color_id):
    """Alterna color_id su piu' file in un colpo solo: se il colore e'
    GIA' presente su TUTTI i file della selezione, lo rimuove da tutti;
    altrimenti lo aggiunge a chi non ce l'ha ancora (chi lo ha gia' resta
    invariato) — stesso principio "un'unica lettura, un'unica scrittura"
    di bulk_set_rating, adattato al fatto che le colorlabel ora sono
    multiple (non un valore singolo da sovrascrivere in blocco)."""
    if color_id not in COLOR_IDS:
        return
    with _lock:
        _load()
        paths = [os.path.abspath(p) for p in paths]
        if not paths:
            return
        all_have = all(color_id in _cache.get(p, _DEFAULT_ENTRY)["colors"]
                       for p in paths)
        for path in paths:
            entry = dict(_cache.get(path, _DEFAULT_ENTRY))
            colors = list(entry["colors"])
            if all_have:
                if color_id in colors:
                    colors.remove(color_id)
            else:
                if color_id not in colors:
                    colors.append(color_id)
            entry["colors"] = colors
            entry["tags"] = list(entry["tags"])
            if _is_default(entry):
                _cache.pop(path, None)
            else:
                _cache[path] = entry
        _save()


def bulk_add_tag(paths, tag):
    tag = (tag or "").strip()
    if not tag:
        return
    with _lock:
        _load()
        for path in paths:
            path = os.path.abspath(path)
            entry = dict(_cache.get(path, _DEFAULT_ENTRY))
            entry["tags"] = list(entry["tags"])
            if tag not in entry["tags"]:
                entry["tags"].append(tag)
            _cache[path] = entry
        _touch_tag_recency([tag])
        _save()


def bulk_toggle_tag(paths, tag):
    """Alterna un tag su piu' file in un colpo solo — stesso principio
    di bulk_toggle_color: se il tag e' GIA' presente su TUTTI i file
    della selezione, lo rimuove da tutti; altrimenti lo aggiunge a chi
    non ce l'ha ancora (chi lo ha gia' resta invariato). A differenza di
    bulk_add_tag (che aggiunge soltanto, mai rimuove), questa e' la
    versione toggle usata dalla finestra Tag su una selezione multipla,
    per poter anche TOGLIERE un tag gia' applicato a tutti con un solo
    click, come gia' funziona per i colori."""
    tag = (tag or "").strip()
    if not tag:
        return
    with _lock:
        _load()
        paths = [os.path.abspath(p) for p in paths]
        if not paths:
            return
        all_have = all(tag in _cache.get(p, _DEFAULT_ENTRY)["tags"] for p in paths)
        for path in paths:
            entry = dict(_cache.get(path, _DEFAULT_ENTRY))
            tags = list(entry["tags"])
            if all_have:
                if tag in tags:
                    tags.remove(tag)
            else:
                if tag not in tags:
                    tags.append(tag)
            entry["tags"] = tags
            if _is_default(entry):
                _cache.pop(path, None)
            else:
                _cache[path] = entry
        if not all_have:
            _touch_tag_recency([tag])
        _save()


# ── Interrogazione (per il filtro dello step 6) ─────────────────────────────
def query(rating_min=None, colors_any=None, colors_all=None,
          tags_any=None, tags_all=None):
    """Ritorna la lista dei path che soddisfano TUTTI i criteri passati
    (i criteri omessi/None non filtrano). colors_any/tags_any: almeno uno
    dei colori/tag presenti; colors_all/tags_all: tutti presenti insieme
    (colorlabel multiple, stesso principio gia' usato per i tag).
    Nota: interroga solo i file che hanno gia' una entry nel database
    (quindi rating=0/nessun colore/nessun tag esclude sempre un file che
    non e' mai stato toccato — coerente col fatto che quello e' lo stato
    di default)."""
    with _lock:
        _load()
        snapshot = list(_cache.items())
    result = []
    colors_any_set = set(colors_any) if colors_any else None
    colors_all_set = set(colors_all) if colors_all else None
    tags_any_set = set(tags_any) if tags_any else None
    tags_all_set = set(tags_all) if tags_all else None
    for path, entry in snapshot:
        if rating_min is not None and entry["rating"] < rating_min:
            continue
        if colors_any_set is not None and not (colors_any_set & set(entry["colors"])):
            continue
        if colors_all_set is not None and not colors_all_set.issubset(entry["colors"]):
            continue
        if tags_any_set is not None and not (tags_any_set & set(entry["tags"])):
            continue
        if tags_all_set is not None and not tags_all_set.issubset(entry["tags"]):
            continue
        result.append(path)
    return result


# ── Manutenzione ─────────────────────────────────────────────────────────
def forget_missing_files():
    """Rimuove dal database le voci il cui file non esiste piu' su disco.
    Non chiamata automaticamente da nessuna parte in questo step: va
    agganciata a un punto esplicito della UI (es. un pulsante "pulisci
    database" nel futuro pannello metadati), non eseguita in automatico
    ad ogni avvio, per non nascondere silenziosamente dati per file su
    dischi esterni temporaneamente scollegati."""
    with _lock:
        _load()
        missing = [p for p in _cache if not os.path.isfile(p)]
        for p in missing:
            _cache.pop(p, None)
        _save()
        return len(missing)


def rename_path(old_path, new_path):
    """Sposta la voce di old_path su new_path, quando il chiamante sa GIA'
    che un file e' stato rinominato/spostato/convertito e vuole evitare
    che rating/colore/tag restino orfani sotto il percorso vecchio (vedi
    il limite noto nel docstring del modulo). Se new_path ha gia' una
    propria voce, quella vecchia viene scartata senza sovrascrivere
    silenziosamente dati piu' recenti — non e' un caso atteso in uso
    normale (un file non "eredita" i metadati di un altro), ma va escluso
    esplicitamente piuttosto che lasciarlo indefinito.
    Nessun effetto se old_path non aveva alcuna voce."""
    old_path = os.path.abspath(old_path)
    new_path = os.path.abspath(new_path)
    if old_path == new_path:
        return
    with _lock:
        _load()
        entry = _cache.pop(old_path, None)
        if entry is None:
            return
        if new_path not in _cache:
            _cache[new_path] = entry
        _save()


def rename_path_prefix(old_folder, new_folder):
    """Come rename_path, ma per un'INTERA CARTELLA spostata o
    rinominata: sposta le voci di TUTTI i file il cui percorso inizia
    con old_folder, riscrivendo quel prefisso in new_folder — invece di
    dover chiamare rename_path singolarmente per ogni file al suo
    interno (il chiamante spesso non ha nemmeno l'elenco completo,
    specie con sottocartelle annidate).
    Nessun effetto sui file la cui voce non inizia con old_folder."""
    old_folder = os.path.abspath(old_folder)
    new_folder = os.path.abspath(new_folder)
    if old_folder == new_folder:
        return
    old_prefix = old_folder + os.sep
    with _lock:
        _load()
        to_move = [p for p in _cache if p == old_folder or p.startswith(old_prefix)]
        for old_p in to_move:
            entry = _cache.pop(old_p)
            new_p = new_folder + old_p[len(old_folder):]
            if new_p not in _cache:
                _cache[new_p] = entry
        if to_move:
            _save()

