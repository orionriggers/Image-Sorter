# timeline.py — Timeline, mappa GPS, scansione ricorsiva
VERSION = "1.45.0"
# Visualizzazione profonda: scansione ricorsiva, timeline per data/luogo, mappa GPS
# Dipendenze: reverse_geocode, folium (pip install reverse-geocode folium)

import os, sys, threading, datetime, tempfile, webbrowser, subprocess
import shutil
import html as _html
import concurrent.futures
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ExifTags, ImageOps
try:
    import pillow_avif  # registra supporto AVIF
except ImportError:
    pass
try:
    import importlib.util as _ilu_db
    import os as _os_db
    _ee_path = _os_db.path.join(_os_db.path.dirname(_os_db.path.abspath(__file__)),
                                "exif_editor.py")
    _ee_spec = _ilu_db.spec_from_file_location("exif_editor", _ee_path)
    _ee_mod  = _ilu_db.module_from_spec(_ee_spec)
    _ee_spec.loader.exec_module(_ee_mod)
    _open_exif_editor_db = _ee_mod.open_exif_editor
    _EXIF_EDITOR_OK = True
except Exception:
    _EXIF_EDITOR_OK = False
Image.MAX_IMAGE_PIXELS = None  # disabilita il limite DecompressionBomb

# ── Costanti visive (ereditate da image_sorter se disponibili) ────────────────
try:
    from image_sorter import (BG_COLOR, PANEL_COLOR, ACCENT_COLOR, HUD_CYAN,
                               TEXT_COLOR, MUTED_COLOR, HIGHLIGHT, SUCCESS,
                               WARNING, PRIVACY_RED, hud_apply, tk_safe, open_in_filemanager,
                               send_to_trash, KEYS, KEY_COLORS, get_keypad_cols,
                               _translate_widgets, T, _Tf, _post_menu, get_video_frame,
                               save_config, add_rating_row_reserve, attach_rating_overlay,
                               metadata_store, _METADATA_STORE_AVAILABLE,
                               draw_colorlabel_dots, repaint_colorlabel_dots,
                               timeline_rating_row_sizes, _launch_video_player,
                               _os_clipboard_set_files, _os_clipboard_get_files)
    _STANDALONE = False
except ImportError:
    BG_COLOR    = "#0a0f1a"
    PANEL_COLOR = "#0d1117"
    ACCENT_COLOR= "#1a2a3a"
    HUD_CYAN    = "#00c8ff"
    TEXT_COLOR  = "#c8d8e8"
    MUTED_COLOR = "#4a6080"
    HIGHLIGHT   = "#2a4a6a"
    SUCCESS     = "#2ecc71"
    WARNING     = "#e67e22"
    def hud_apply(w, color=None): w.configure(bg=BG_COLOR)
    PRIVACY_RED = "#ff2020"
    def T(k, l=None, **kw): return k
    def _Tf(t, l=None, **kw): return t.format(**kw) if kw else t
    def _translate_widgets(w, l): pass
    def tk_safe(s): return ''.join(c for c in str(s) if ord(c) < 0x10000)
    def get_video_frame(path, size=(640,480)): return None
    def save_config(data): pass
    def add_rating_row_reserve(menu):
        menu.add_command(label="", state="disabled")
        return menu.index("end")
    def attach_rating_overlay(menu, row_index, targets, on_change=None):
        return None
    def draw_colorlabel_dots(parent, cur_colors, on_pick, size=14, pad=2):
        return []
    def repaint_colorlabel_dots(dots, cur_colors, size=14):
        pass
    def timeline_rating_row_sizes(tw):
        return 11, 13, 4, 2, 23
    def _launch_video_player(filepath):
        try:
            subprocess.Popen(["xdg-open", filepath],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False
    def _os_clipboard_set_files(widget, paths, cut=False):
        pass
    def _os_clipboard_get_files(widget):
        return [], False
    _METADATA_STORE_AVAILABLE = False
    class _StubMetadataStoreStandalone:
        @staticmethod
        def get_meta(path): return {"rating": 0, "colors": [], "tags": []}
        @staticmethod
        def set_rating(path, value): pass
        @staticmethod
        def bulk_set_rating(paths, value): pass
        @staticmethod
        def toggle_color(path, color_id): pass
        @staticmethod
        def bulk_toggle_color(paths, color_id): pass
        @staticmethod
        def rename_path(old_path, new_path): pass
        @staticmethod
        def rename_path_prefix(old_folder, new_folder): pass
    metadata_store = _StubMetadataStoreStandalone()
    def _post_menu(menu, x, y, root_win=None):
        try:
            menu.tk_popup(x, y)
        finally:
            try: menu.grab_release()
            except Exception: pass
    def open_in_filemanager(p):
        for fm in ["nautilus","nemo","thunar","dolphin","xdg-open"]:
            try: subprocess.Popen([fm, p]); return
            except FileNotFoundError: pass
    def send_to_trash(p):
        import shutil; shutil.move(p, os.path.expanduser("~/.local/share/Trash/files/"))
    KEYS = [str(i) for i in range(1,10)] + ["0"]
    KEY_COLORS = ["#c0392b","#e67e22","#f1c40f","#2ecc71","#1abc9c",
                  "#3498db","#9b59b6","#e91e63","#795548","#607d8b"]
    _STANDALONE = True

# ── Formati supportati ────────────────────────────────────────────────────────
IMG_EXT  = {".jpg",".jpeg",".png",".gif",".bmp",".tiff",".tif",".webp",".heic",".heif",".avif",".pnm",".pbm",".pgm",".ppm"}
VID_EXT  = {".mp4",".mov",".avi",".mkv",".webm",".m4v",".flv"}
ALL_EXT  = IMG_EXT | VID_EXT

THUMB_W  = 160
THUMB_H  = 120
PAGE_SIZE = 120   # thumbnail per pagina (lazy loading)

# Palette colori per distinguere le cartelle sorgente
FOLDER_PALETTE = [
    "#00c8ff",  # ciano
    "#f0a030",  # arancio
    "#50e890",  # verde
    "#e060e0",  # viola
    "#f05050",  # rosso
    "#f0e050",  # giallo
]

# ── GPS helpers ───────────────────────────────────────────────────────────────
def _dms_to_deg(dms, ref):
    try:
        d, m, s = (float(x) for x in dms)
        val = d + m/60 + s/3600
        return -val if ref in ("S","W") else val
    except Exception:
        return None

def get_exif_data(path):
    """Apre il file UNA sola volta e restituisce (date, gps_or_None).
    Più efficiente di chiamare get_date_exif e get_gps separatamente.
    """
    dt, gps = None, None
    try:
        img  = Image.open(path)
        exif = img.getexif()
        # Data scatto
        raw = exif.get(0x9003) or exif.get(0x0132)
        if raw:
            try:
                dt = datetime.datetime.strptime(str(raw)[:19], "%Y:%m:%d %H:%M:%S")
            except Exception:
                pass
        # GPS
        gps_ifd = exif.get_ifd(0x8825)
        if gps_ifd:
            lat = _dms_to_deg(gps_ifd.get(2), gps_ifd.get(1, "N"))
            lon = _dms_to_deg(gps_ifd.get(4), gps_ifd.get(3, "E"))
            if lat is not None and lon is not None:
                gps = (lat, lon)
    except Exception:
        pass
    if dt is None:
        try:
            dt = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        except Exception:
            pass
    return dt, gps

def get_gps(path):
    """Compatibilità — usa get_exif_data internamente."""
    return get_exif_data(path)[1]

def get_date_exif(path):
    """Compatibilità — usa get_exif_data internamente."""
    return get_exif_data(path)[0]

def get_location_name(lat, lon):
    """Restituisce 'Città, Regione, Paese' offline."""
    try:
        import reverse_geocode
        r = reverse_geocode.get((lat, lon))
        parts = [r.get("city",""), r.get("state",""), r.get("country","")]
        return ", ".join(p for p in parts if p)
    except Exception:
        return ""

# ── Scansione file ────────────────────────────────────────────────────────────
def scan_files(root_dirs, progress_cb=None, max_depth=None, private_folders=None, unlocked=None):
    """
    Scansiona ricorsivamente le cartelle.
    Restituisce lista di dict:
      { path, ext, date, gps, location, moved_to }
    """
    def _walk(root, max_d):
        root = root.rstrip(os.sep)
        base_depth = root.count(os.sep)
        pf = [os.path.abspath(p) for p in (private_folders or [])]
        ul = set(os.path.abspath(p) for p in (unlocked or []))
        for dirpath, dirs, files in os.walk(root):
            cur_depth = dirpath.count(os.sep) - base_depth
            if max_d is not None and cur_depth >= max_d:
                dirs[:] = []; yield dirpath, files; continue
            # Filtra sottocartelle private non sbloccate
            if pf:
                def _priv(d):
                    ap=os.path.abspath(d)
                    for p in pf:
                        if ap==p or ap.startswith(p+os.sep):
                            return p not in ul
                    return False
                dirs[:] = [d for d in dirs
                           if not _priv(os.path.join(dirpath,d))]
            yield dirpath, files

    results = []
    total   = 0
    for root in root_dirs:
        for _, files in _walk(root, max_depth):
            total += sum(1 for f in files if os.path.splitext(f)[1].lower() in ALL_EXT)

    done = 0
    for root in root_dirs:
        for dirpath, files in _walk(root, max_depth):
            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()
                if ext not in ALL_EXT:
                    continue
                fpath = os.path.join(dirpath, fname)
                # Apertura unica per data + GPS
                if ext in IMG_EXT:
                    dt, gps = get_exif_data(fpath)
                else:
                    dt  = get_date_exif(fpath)
                    gps = None
                loc   = ""  # risolto in batch dopo
                results.append({
                    "path":     fpath,
                    "ext":      ext,
                    "date":     dt,
                    "gps":      gps,
                    "location": loc,
                    "moved_to": None,
                })
                done += 1
                if progress_cb and done % 20 == 0:
                    progress_cb(done, total)  # può sollevare StopIteration
                # Cede CPU ogni 10 file per non saturare la ventola
                if done % 10 == 0:
                    import time
                    time.sleep(0.002)

    if progress_cb:
        progress_cb(done, total)

    # Risolvi GPS → luogo in batch
    gps_items = [(i, r["gps"]) for i, r in enumerate(results) if r["gps"]]
    if gps_items:
        try:
            import reverse_geocode
            coords   = [g for _, g in gps_items]
            resolved = reverse_geocode.search(coords)
            for (i, _), r in zip(gps_items, resolved):
                parts = [r.get("city",""), r.get("state",""), r.get("country","")]
                results[i]["location"] = ", ".join(p for p in parts if p)
        except Exception:
            pass

    return results

def sort_files(items, mode, reverse=True):
    """Ordina la lista per data o posizione.
    reverse=True  = piu' recenti prima (default)
    reverse=False = piu' vecchie prima
    """
    if mode == "location":
        return sorted(items,
            key=lambda x: (x["location"] or "zzz",
                           x["date"] or datetime.datetime.min),
            reverse=False)  # per location mantieni ordine alfab.
    else:
        return sorted(items,
            key=lambda x: x["date"] or datetime.datetime.min,
            reverse=reverse)

def group_by_month(items):
    """Raggruppa per anno-mese. Restituisce [(label, location_hint, [items])]."""
    groups = {}
    order  = []
    for item in items:
        if item["date"]:
            key = item["date"].strftime("%Y-%m")
            lbl = item["date"].strftime("%B %Y")
        else:
            key = "0000-00"
            lbl = "Data sconosciuta"
        if key not in groups:
            groups[key] = {"label": lbl, "items": [], "locations": {}}
            order.append(key)
        groups[key]["items"].append(item)
        loc = item.get("location","")
        if loc:
            groups[key]["locations"][loc] = groups[key]["locations"].get(loc, 0) + 1

    result = []
    for key in order:
        g    = groups[key]
        locs = g["locations"]
        loc_hint = max(locs, key=locs.get) if locs else ""
        result.append((g["label"], loc_hint, g["items"]))
    return result

# ── Mappa Folium ──────────────────────────────────────────────────────────────
# ── Mappa GPS: anteprime nei marcatori ──────────────────────────────────────
# Le miniature vengono incorporate nell'HTML in base64 (nessun file esterno
# da tenere in giro: la mappa resta un singolo file apribile e spostabile).
# Ognuna pesa ~8-12KB, quindi con qualche centinaio di foto si resta
# nell'ordine di pochi MB; oltre il tetto sotto, i marcatori tornano icone
# semplici per non generare un file che il browser fatica ad aprire.
MAP_THUMB_MAX  = 400   # oltre questo numero di foto: solo icone
MAP_THUMB_SIZE = 160   # lato massimo: mostrata a 56px sulla mappa e intera
                       # nel popup — una sola immagine per entrambi gli usi
MAP_THUMB_ZOOM = 12    # da questo livello di zoom in su compaiono le foto


def _map_thumb_b64(path, size=MAP_THUMB_SIZE):
    """Miniatura JPEG in base64, pronta per un attributo src.

    Restituisce None se il file non e' leggibile: in quel caso il marcatore
    resta un'icona normale, senza lasciare buchi nella mappa.
    """
    import base64
    from io import BytesIO
    img = None
    try:
        ext = os.path.splitext(path)[1].lower()
        if ext in VID_EXT:
            img = get_video_frame(path, size=(size, size))
            if img is None:
                return None
        else:
            img = Image.open(path)
            if ext in (".jpg", ".jpeg"):
                # draft(): decodifica ridotta gia' in fase di lettura, molto
                # piu' veloce su file grandi. Solo JPEG lo supporta.
                try:
                    img.draft("RGB", (size * 2, size * 2))
                except Exception:
                    pass
            img = ImageOps.exif_transpose(img)
        img.thumbnail((size, size), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=70, optimize=True)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return None
    finally:
        try:
            if img is not None:
                img.close()
        except Exception:
            pass


try:
    from image_sorter import (is_non_jpeg_image, FMT_DOT_FILL, FMT_DOT_OUTLINE)
except Exception:                       # uso standalone
    FMT_DOT_FILL, FMT_DOT_OUTLINE = "#ff9800", "#4a2a00"
    def is_non_jpeg_image(filepath):
        ext = os.path.splitext(filepath)[1].lower()
        return ext in IMG_EXT and ext not in (".jpg", ".jpeg")


def _hud(win, color=None):
    """Bordo HUD sulla finestra; funziona anche in uso standalone."""
    try:
        from image_sorter import hud_apply as _ha
        _ha(win, color) if color else _ha(win)
    except Exception:
        try:
            win.config(highlightbackground=HUD_CYAN, highlightthickness=2,
                       highlightcolor=HUD_CYAN)
        except Exception:
            pass


def build_map(items, out_path=None, progress=None):
    """Genera HTML con Folium MarkerCluster e lo salva/apre.

    I marcatori mostrano l'anteprima della foto quando la mappa e'
    abbastanza ingrandita; sotto quel livello le anteprime resterebbero
    sovrapposte e illeggibili, quindi si riducono a un punto colorato.
    La stessa anteprima compare, piu' grande, nel popup del marcatore.

    progress: callback opzionale progress(fatte, totale) per aggiornare
    una barra di stato durante la generazione delle miniature (la parte
    lenta: apre un file per foto).
    """
    try:
        import folium
        from folium.plugins import MarkerCluster
    except ImportError:
        messagebox.showerror("Mappa", "Installa folium:\npip install folium --user", parent=None)
        return

    gps_items = [i for i in items if i.get("gps")]
    if not gps_items:
        messagebox.showinfo("Mappa GPS", "Nessuna immagine con dati GPS trovata.", parent=None)
        return

    lats = [i["gps"][0] for i in gps_items]
    lons = [i["gps"][1] for i in gps_items]
    center = (sum(lats)/len(lats), sum(lons)/len(lons))

    m  = folium.Map(location=center, zoom_start=5)
    mc = MarkerCluster(name="Foto").add_to(m)

    # Oltre il tetto si rinuncia alle anteprime: meglio una mappa leggera
    # che un HTML da decine di MB.
    with_thumbs = len(gps_items) <= MAP_THUMB_MAX
    total = len(gps_items)

    for idx, item in enumerate(gps_items):
        lat, lon = item["gps"]
        name     = os.path.basename(item["path"])
        dt_str   = item["date"].strftime("%d/%m/%Y %H:%M") if item["date"] else "—"
        loc      = item.get("location","")
        # I nomi di file possono contenere <, > o virgolette, che inseriti
        # grezzi nell'HTML romperebbero il popup: vanno sempre convertiti.
        e_name = _html.escape(name)
        e_loc  = _html.escape(loc)
        e_path = _html.escape(item["path"])

        b64 = _map_thumb_b64(item["path"]) if with_thumbs else None
        if progress:
            try:
                progress(idx + 1, total)
            except Exception:
                pass
        img_tag = (f'<img class="isph-big" '
                   f'src="data:image/jpeg;base64,{b64}">') if b64 else ""
        popup_html = (
            f"{img_tag}"
            f"<b>{e_name}</b><br>"
            f"📅 {dt_str}<br>"
            f"📍 {e_loc}<br>"
            f"<small>{e_path}</small>"
        )
        if b64:
            # DivIcon a dimensione FISSA: il contenuto (foto o punto) cambia
            # con lo zoom, il contenitore no — cosi' l'ancora resta al centro
            # e il marcatore non si sposta quando le anteprime compaiono o
            # scompaiono.
            border = "#22cc66" if item.get("moved_to") else "#00c8ff"
            icon = folium.DivIcon(
                icon_size=(60, 60), icon_anchor=(30, 30),
                html=(f'<div class="isph" style="--isb:{border}">'
                      f'<img src="data:image/jpeg;base64,{b64}">'
                      f'<span class="isdot"></span></div>'))
        else:
            icon = folium.Icon(
                color="blue" if not item.get("moved_to") else "green",
                icon="camera", prefix="fa")
        folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=name,
            icon=icon,
        ).add_to(mc)

    folium.LayerControl().add_to(m)

    if with_thumbs:
        # Lo scambio foto/punto avviene aggiungendo una classe al contenitore
        # della mappa, non ricreando i marcatori: e' immediato anche con
        # centinaia di foto e non interferisce con il raggruppamento.
        m.get_root().header.add_child(folium.Element("""
<style>
.isph{width:60px;height:60px;display:flex;align-items:center;
      justify-content:center;}
.isph img{width:56px;height:56px;object-fit:cover;border-radius:4px;
      border:2px solid var(--isb,#00c8ff);background:#0a0f1a;
      box-shadow:0 2px 6px rgba(0,0,0,.6);}
.isph .isdot{display:none;width:12px;height:12px;border-radius:50%;
      background:var(--isb,#00c8ff);border:2px solid #fff;
      box-shadow:0 1px 3px rgba(0,0,0,.6);}
.leaflet-container.iszoomout .isph img{display:none;}
.leaflet-container.iszoomout .isph .isdot{display:block;}
img.isph-big{max-width:100%;border-radius:4px;margin-bottom:6px;display:block;}
</style>"""))
        # ATTENZIONE ALL'ORDINE: folium inserisce gli script aggiunti qui
        # PRIMA della creazione della mappa, dentro lo stesso blocco
        # <script>. Referenziare la variabile della mappa al momento del
        # parsing solleverebbe quindi un ReferenceError, che interrompe
        # l'intero blocco — compresa la creazione della mappa stessa:
        # risultato, pagina completamente bianca.
        # Per questo il codice sta dentro una funzione eseguita al 'load'
        # della pagina, quando la mappa esiste di sicuro, e la cerca su
        # window invece di riferirla direttamente. Se non la trova, le
        # anteprime restano semplicemente sempre visibili.
        m.get_root().script.add_child(folium.Element(f"""
(function(){{
  function _init(){{
    var _m = window["{m.get_name()}"];
    if (!_m || !_m.getContainer) return;
    function _upd(){{
      var c = _m.getContainer();
      if (!c) return;
      if (_m.getZoom() < {MAP_THUMB_ZOOM}) c.classList.add('iszoomout');
      else c.classList.remove('iszoomout');
    }}
    _m.on('zoomend', _upd);
    _upd();
  }}
  if (document.readyState === 'complete') _init();
  else window.addEventListener('load', _init);
}})();"""))

    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".html", prefix="deep_map_")
        os.close(fd)

    m.save(out_path)
    webbrowser.open(f"file://{out_path}", new=2)
    return out_path

# ── Thumbnail cache (LRU) ───────────────────────────────────────────────────
from collections import OrderedDict as _OD
_thumb_cache = _OD()
_THUMB_CACHE_MAX = 300

def make_thumb(path, w=THUMB_W, h=THUMB_H):
    # mtime nella chiave: se il file viene modificato (es. ritagliato o
    # ruotato altrove) dopo essere finito in cache, la vecchia miniatura
    # non viene più restituita — senza questo, la Timeline poteva mostrare
    # per un tempo indefinito (fino all'espulsione LRU) l'anteprima
    # precedente alla modifica.
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0
    key = (path, w, h, mtime)
    if key in _thumb_cache:
        _thumb_cache.move_to_end(key)
        return _thumb_cache[key]
    try:
        img = Image.open(path)
        # Draft mode: decodifica diretta a risoluzione ridotta per i JPEG
        # grandi (foto da fotocamera moderna), molto più veloce che
        # decodificare tutto e poi rimpicciolire.
        if hasattr(img, "draft") and os.path.splitext(path)[1].lower() in (".jpg", ".jpeg"):
            img.draft("RGB", (w * 2, h * 2))
        # Sicurezza memoria: immagini enormi vengono prima ridotte
        # velocemente prima del rimpicciolimento di qualità finale.
        if img.width * img.height > 4000 * 4000:
            img.thumbnail((2000, 2000), Image.Resampling.NEAREST)
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        try: img.close()  # rilascia file descriptor
        except Exception: pass
        _thumb_cache[key] = tk_img
        if len(_thumb_cache) > _THUMB_CACHE_MAX:
            _thumb_cache.popitem(last=False)
        return tk_img
    except Exception:
        return None

_THUMB_EXECUTOR = None
def _get_thumb_executor():
    """Pool di thread CONDIVISO fra tutte le finestre Timeline per il
    caricamento delle miniature (_add_thumb_cell) — prima ogni cella
    apriva un threading.Thread proprio, fino a PAGE_SIZE (120) thread
    del sistema operativo avviati insieme ad ogni pagina caricata o
    scrollata: overhead di creazione thread e contesa GIL sprecati
    invece di limitare il parallelismo reale, specialmente pesante con
    cartelle da migliaia di foto. Un pool piccolo e fisso, non uno per
    finestra: anche con piu' Timeline aperte insieme il numero totale
    di decodifiche concorrenti resta limitato."""
    global _THUMB_EXECUTOR
    if _THUMB_EXECUTOR is None:
        _THUMB_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
            max_workers=6, thread_name_prefix="timeline-thumb")
    return _THUMB_EXECUTOR


# ── Finestra principale DeepBrowser ──────────────────────────────────────────
class DeepBrowser:
    """Visualizzazione profonda — timeline, mappa GPS, lazy loading."""

    def __init__(self, parent, sorter=None, initial_dirs=None, browse_fn=None):
        self.sorter   = sorter
        self._browse_fn = browse_fn  # browse_folder_hud da image_sorter
        self.items    = []        # lista completa dei file scansionati
        self.filtered = []        # lista filtrata/ordinata visualizzata
        self._scan_thread = None
        self._stop_flag   = False
        self._page        = 0     # pagina corrente lazy loading
        self._selected    = set() # set di path selezionati
        self._last_sel    = None  # ultimo cliccato (anchor Shift)
        self._focus_item  = None  # item corrente per frecce
        self._sort_reverse = True  # True = piu' recenti prima
        self._view_mode   = "timeline"  # timeline | grid | map
        self._sort_mode   = "date_shot"
        self._filter_key  = None  # (tipo, valore) per filtro pannello sx
        self._thumb_scale = 1.0   # 1.0 = normale, 1.5 = grande

        win = tk.Toplevel(parent)
        win.withdraw()
        win.title(f"Timeline  v{VERSION}")
        win.configure(bg=BG_COLOR)
        win.geometry("1200x780")
        win.minsize(700, 500)
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", self._close)
        win.bind("<Escape>", lambda e: self._close())
        win.bind("<Delete>",  lambda e: self._delete_selected())
        win.bind("<KP_Delete>", lambda e: self._delete_selected())
        # Ctrl+A: mancava del tutto (Naviga ce l'ha gia'), segnalato da Carlo.
        win.bind("<Control-a>", lambda e: self._sel_all())
        win.bind("<Control-A>", lambda e: self._sel_all())
        # Ctrl+C/X/V: mancava del tutto (Naviga ce l'ha gia'), segnalato
        # da Carlo insieme al Ctrl+A qui sopra. "Incolla" (Ctrl+V) va
        # nella cartella del file attualmente a fuoco, se c'e' n'e' uno.
        win.bind("<Control-c>", lambda e:
            self._clipboard_set(sorted(self._selected), "copy")
            if self._selected else None)
        win.bind("<Control-x>", lambda e:
            self._clipboard_set(sorted(self._selected), "cut")
            if self._selected else None)
        win.bind("<Control-v>", lambda e:
            self._clipboard_paste(os.path.dirname(self._focus_item["path"]))
            if getattr(self, "_focus_item", None) else None)
        if self.sorter:
            win.bind("<Control-z>", lambda e: self.sorter._undo_last())
            win.bind("<Control-Z>", lambda e: self.sorter._undo_last())
            # Tasti preset 1-9/0: spostano i file selezionati nel preset attivo
            def _make_preset_handler(k):
                def _handler(e=None):
                    sel = list(self._selected)
                    if not sel:
                        return
                    preset = self.sorter.config.get("active_preset", "")
                    batch = []   # [(originale, destinazione effettiva), ...]
                    for path in sel:
                        try:
                            dst = self.sorter._move_to_preset_file(
                                k, preset, path, skip_history=True)
                            if dst:
                                batch.append((path, dst))
                        except Exception:
                            pass
                    # Registra tutto come un'unica voce annullabile, come
                    # già fa _move_selected_to per il menu contestuale:
                    # prima questo percorso non finiva affatto nello
                    # Storico persistente.
                    self._register_moves(batch)
                    # Rimuovi dalla vista SOLO i file spostati davvero
                    # (prima sparivano anche quelli rimasti sul disco per
                    # un errore, es. permessi negati sulla destinazione)
                    moved = {o for o, d in batch}
                    self._selected.clear()
                    self.items = [i for i in self.items
                                  if i["path"] not in moved]
                    self.filtered = [i for i in self.filtered
                                     if i["path"] not in moved]
                    self._render()
                return _handler
            for _k in list("123456789") + ["0"]:
                win.bind(f"<KeyPress-{_k}>", _make_preset_handler(_k))
        hud_apply(win)
        # Non usiamo grab_set per lasciare accessibile la finestra principale
        self.win = win

        self._build()
        # Mostra subito la riga del preset attivo (spenta, nessuna
        # selezione ancora) invece di lasciarla nascosta finche' non si
        # seleziona un file — richiesto da Carlo, coerente con Naviga.
        self._update_sel_bar()

        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        _saved_wh = None
        if self.sorter:
            _saved_wh = self.sorter.config.get("timeline_window_size")
        if _saved_wh and isinstance(_saved_wh, (list, tuple)) and len(_saved_wh) == 2:
            ww, wh = _saved_wh
        else:
            ww, wh = 1200, min(780, sh-80)
        wx = (sw - ww) // 2
        wy = (sh - wh) // 2
        win.geometry(f"{ww}x{wh}+{wx}+{wy}")
        win.deiconify()

        if initial_dirs:
            for d in initial_dirs:
                self._add_folder(d)

        # Traduzione interfaccia
        _lang = (sorter.config.get("language","it") if sorter else "it")
        if _lang != "it":
            win.after(100, lambda: _translate_widgets(win, _lang))

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build(self):
        w = self.win
        w.columnconfigure(0, weight=1)
        w.rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_body()

    def _build_toolbar(self):
        tb = tk.Frame(self.win, bg=PANEL_COLOR, height=44)
        tb.grid(row=0, column=0, sticky="ew")
        tb.pack_propagate(False)
        self._toolbar = tb

        # Cartelle sorgente
        tk.Button(tb, text="+ Cartella", font=("TkFixedFont",9,"bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=10,
                  activebackground=HIGHLIGHT,
                  command=self._pick_folder).pack(side="left", padx=6, pady=6, ipady=2)

        self._folder_frame = tk.Frame(tb, bg=PANEL_COLOR)
        self._folder_frame.pack(side="left", fill="y")
        self._folder_labels = []  # lista di (path, label_widget)

        # Separatore
        tk.Frame(tb, bg=MUTED_COLOR, width=1).pack(side="left", fill="y", pady=6, padx=6)

        # Scansiona / Stop
        self._scan_btn = tk.Button(tb, text="Scansiona", font=("TkFixedFont",9,"bold"),
                  bg=HUD_CYAN, fg=BG_COLOR, relief="flat", padx=10,
                  activebackground=HIGHLIGHT,
                  command=self._start_scan)
        self._scan_btn.pack(side="left", padx=4, pady=6, ipady=2)

        self._stop_btn = tk.Button(tb, text="Stop", font=("TkFixedFont",9),
                  bg=WARNING, fg="white", relief="flat", padx=8,
                  activebackground=HIGHLIGHT,
                  command=self._stop_scan, state="disabled")
        self._stop_btn.pack(side="left", padx=2, pady=6, ipady=2)

        tk.Frame(tb, bg=MUTED_COLOR, width=1).pack(side="left", fill="y", pady=6, padx=6)

        # Vista — OptionMenu compatto
        self._view_var = tk.StringVar(value="Timeline")
        self._view_map = {"Timeline": "timeline", "Griglia": "grid"}
        view_om = tk.OptionMenu(tb, self._view_var,
                                "Timeline", "Griglia",
                                command=lambda _: self._apply_view())
        view_om.config(font=("TkFixedFont",8,"bold"), bg=ACCENT_COLOR,
                       fg=TEXT_COLOR, activebackground=HIGHLIGHT,
                       relief="flat", padx=4, pady=0, highlightthickness=0)
        view_om["menu"].config(font=("TkFixedFont",8), bg=ACCENT_COLOR, fg=TEXT_COLOR)
        view_om.pack(side="left", padx=4)

        tk.Frame(tb, bg=MUTED_COLOR, width=1).pack(side="left", fill="y", pady=6, padx=6)

        # Ordina — OptionMenu compatto
        tk.Label(tb, text="Ord:", font=("TkFixedFont",8),
                 bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="left", padx=(4,2))
        _slang = (self.sorter.config.get("language","it") if self.sorter else "it")
        _ss = T("sort_shot",_slang); _sf = T("sort_file",_slang); _sp = T("sort_place",_slang)
        self._sort_var = tk.StringVar(value=_ss)
        self._sort_map = {_ss: "date_shot", _sf: "date_file", _sp: "location"}
        sort_om = tk.OptionMenu(tb, self._sort_var,
                                _ss, _sf, _sp,
                                command=lambda _: self._apply_sort())
        sort_om.config(font=("TkFixedFont",8), bg=ACCENT_COLOR,
                       fg=TEXT_COLOR, activebackground=HIGHLIGHT,
                       relief="flat", padx=4, pady=0, highlightthickness=0)
        sort_om["menu"].config(font=("TkFixedFont",8), bg=ACCENT_COLOR, fg=TEXT_COLOR)
        sort_om.pack(side="left", padx=2)

        # Profondita scansione
        tk.Frame(tb, bg=MUTED_COLOR, width=1).pack(side="left", fill="y", pady=6, padx=6)
        tk.Label(tb, text="Prof:", font=("TkFixedFont",8),
                 bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="left", padx=(4,2))
        self._depth_var = tk.IntVar(value=0)
        self._depth_lbl = tk.Label(tb, text="Illimitata",
                                   font=("TkFixedFont",8,"bold"),
                                   bg=PANEL_COLOR, fg=HUD_CYAN, width=9)
        self._depth_lbl.pack(side="left")
        tk.Scale(tb, from_=0, to=5, orient="horizontal",
                 variable=self._depth_var, length=60,
                 showvalue=0, bg=PANEL_COLOR, fg=HUD_CYAN,
                 troughcolor=ACCENT_COLOR, highlightthickness=0, bd=0,
                 command=self._on_depth_change
                 ).pack(side="left", padx=(0,6))

        # Bottone ordine cronologico
        tk.Frame(tb, bg=MUTED_COLOR, width=1).pack(
            side="left", fill="y", pady=6, padx=6)
        self._rev_btn = tk.Button(tb, text="9-1",
                                  font=("TkFixedFont",8),
                                  bg=ACCENT_COLOR, fg=HUD_CYAN,
                                  relief="flat", padx=6,
                                  activebackground=HIGHLIGHT,
                                  command=self._toggle_order)
        self._rev_btn.pack(side="left", padx=(0,4), ipady=2)

        # Bottone dimensione anteprime
        self._size_btn = tk.Button(tb, text="1x",
                                   font=("TkFixedFont",8),
                                   bg=ACCENT_COLOR, fg=TEXT_COLOR,
                                   relief="flat", padx=6,
                                   activebackground=HIGHLIGHT,
                                   command=self._toggle_thumb_size)
        self._size_btn.pack(side="left", padx=(0,4), ipady=2)

        # Checkbox "Ratings": mostra/nasconde la riga di stelle+pallini
        # colore sotto le miniature della griglia — stesso principio del
        # check "Ratings" di Naviga, stato ricordato tra le sessioni.
        if _METADATA_STORE_AVAILABLE:
            self._show_ratings_var = tk.BooleanVar(
                value=(self.sorter.config.get("timeline_show_ratings", True)
                      if self.sorter else True))
            self._show_ratings = self._show_ratings_var.get()
            tk.Checkbutton(tb, text="Ratings", variable=self._show_ratings_var,
                           font=("TkFixedFont",8), bg=PANEL_COLOR,
                           fg=MUTED_COLOR, selectcolor=ACCENT_COLOR,
                           activebackground=PANEL_COLOR, activeforeground=HUD_CYAN,
                           command=self._toggle_show_ratings
                           ).pack(side="left", padx=(2,4))

        # Checkbox "Preset": mostra/nasconde la barra destinazioni rapide
        # sotto la griglia (gia' presente, _sort_bar/_update_sel_bar, ma
        # finora sempre visibile con una selezione attiva) — stesso
        # principio del check "Preset" di Naviga, stato ricordato tra le
        # sessioni. Richiede self.sorter: senza, non c'e' preset attivo
        # da cui prendere le destinazioni (vedi _update_sel_bar).
        if self.sorter:
            self._show_preset_row_var = tk.BooleanVar(
                value=self.sorter.config.get("timeline_show_preset_row", True))
            tk.Checkbutton(tb, text="Preset", variable=self._show_preset_row_var,
                           font=("TkFixedFont",8), bg=PANEL_COLOR,
                           fg=MUTED_COLOR, selectcolor=ACCENT_COLOR,
                           activebackground=PANEL_COLOR, activeforeground=HUD_CYAN,
                           command=self._toggle_show_preset_row
                           ).pack(side="left", padx=(2,4))

        # Checkbox "Tag": mostra/nasconde la nuvola di tag cliccabili per
        # la selezione corrente — stesso principio e stessa nuvola di
        # Naviga (FolderBrowser._build_tag_row), qui adattata a
        # self._selected. Richiesto da Carlo, che aveva notato il check
        # "Ratings" gia' presente ma non i suoi equivalenti.
        if self.sorter and _METADATA_STORE_AVAILABLE:
            self._show_tag_row_var = tk.BooleanVar(
                value=self.sorter.config.get("timeline_show_tag_row", True))
            tk.Checkbutton(tb, text="Tag", variable=self._show_tag_row_var,
                           font=("TkFixedFont",8), bg=PANEL_COLOR,
                           fg=MUTED_COLOR, selectcolor=ACCENT_COLOR,
                           activebackground=PANEL_COLOR, activeforeground=HUD_CYAN,
                           command=self._toggle_show_tag_row
                           ).pack(side="left", padx=(2,4))

        # Mappa GPS (destra)
        tk.Button(tb, text="Mappa GPS", font=("TkFixedFont",9),
                  bg="#1a3a5a", fg=HUD_CYAN, relief="flat", padx=10,
                  activebackground=HIGHLIGHT,
                  command=self._open_map).pack(side="right", padx=8, pady=6, ipady=2)

        # Bottone Deck
        if self.sorter:
            self._deck_btn = tk.Button(tb, text="Deck", font=("TkFixedFont",9),
                      bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=10,
                      activebackground=HIGHLIGHT,
                      command=self.sorter._toggle_keypad)
            self._deck_btn.pack(side="right", padx=4, pady=6, ipady=2)
            self.sorter._keypad_btn_ref_db = self._deck_btn
            # Aggiorna subito il colore se il deck è già aperto
            if self.sorter.keypad_popup:
                cols = get_keypad_cols(self.sorter.config)
                self.sorter._update_keypad_btn(cols)

    def _build_body(self):
        body = tk.Frame(self.win, bg=BG_COLOR)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0, minsize=185)  # colonna sx fissa
        body.columnconfigure(1, weight=1)               # colonna dx espandibile
        body.rowconfigure(0, weight=1)
        self._body = body

        # ── Pannello sinistro: navigatore ─────────────────────────────────────
        left = tk.Frame(body, bg=PANEL_COLOR, width=185)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)
        left.pack_propagate(False)
        self._left = left

        # Status in fondo — va dichiarato prima di nav_canvas (expand=True)
        _bl=tk.Frame(left,bg=PANEL_COLOR,width=185)
        _bl.pack(side="bottom",fill="x")
        _bl.pack_propagate(False)
        tk.Frame(_bl,bg=ACCENT_COLOR,height=1).pack(fill="x")
        self._count_lbl=tk.Label(_bl,text="",font=("TkFixedFont",7,"bold"),
            bg=PANEL_COLOR,fg=HUD_CYAN,anchor="w")
        self._count_lbl.pack(anchor="w",padx=4,pady=(1,0))
        self._status_lbl=tk.Label(_bl,text="Pronto.",font=("TkFixedFont",7),
            bg=PANEL_COLOR,fg=MUTED_COLOR,anchor="w")
        self._status_lbl.pack(anchor="w",padx=4,pady=(0,2))

        nav_canvas = tk.Canvas(left, bg=PANEL_COLOR, highlightthickness=0)
        nav_scroll = ttk.Scrollbar(left, orient="vertical", command=nav_canvas.yview)
        nav_canvas.configure(yscrollcommand=nav_scroll.set)
        nav_scroll.pack(side="right", fill="y")
        nav_canvas.pack(side="left", fill="both", expand=True)
        self._nav_inner = tk.Frame(nav_canvas, bg=PANEL_COLOR)
        nav_canvas.create_window((0,0), window=self._nav_inner, anchor="nw")
        def _nav_scroll_update(e):
            ch=nav_canvas.winfo_height(); ih=self._nav_inner.winfo_height()
            nav_canvas.configure(scrollregion=(0,0,
                self._nav_inner.winfo_width(),max(ih,ch)))
        self._nav_inner.bind("<Configure>", _nav_scroll_update)
        self._nav_canvas = nav_canvas
        # Scroll rotella sul pannello sinistro
        for _w in [nav_canvas, self._nav_inner]:
            _w.bind("<Button-4>",
                lambda e: nav_canvas.yview_scroll(-3,"units"))
            _w.bind("<Button-5>",
                lambda e: nav_canvas.yview_scroll( 3,"units"))
            _w.bind("<MouseWheel>",
                lambda e: nav_canvas.yview_scroll(-1 if e.delta>0 else 1,"units"))

        # ── Pannello destro: griglia/timeline ────────────────────────────────
        # Avvolto in un ttk.PanedWindow (non gridato direttamente in body)
        # per poter aggiungere il pannello anteprima come un vero secondo
        # pannello ridimensionabile trascinando il divisore, invece che
        # con una larghezza fissa non regolabile.
        right_paned = ttk.PanedWindow(body, orient="horizontal")
        right_paned.grid(row=0, column=1, sticky="nsew")
        self._right_paned = right_paned

        right = tk.Frame(right_paned, bg=BG_COLOR)
        right_paned.add(right, weight=3)
        right.columnconfigure(0, weight=1)
        # Barra progress (layout originale invariato)
        self._prog_frame=tk.Frame(right,bg=PANEL_COLOR,height=3)
        self._prog_frame.grid(row=0,column=0,columnspan=2,sticky="ew")
        self._prog_bar=tk.Frame(self._prog_frame,bg=HUD_CYAN,height=3)
        self._prog_bar.place(relwidth=0,relheight=1)
        # (contatore file durante scan: usa _count_lbl)
        right.rowconfigure(1,weight=1)

        self._canvas = tk.Canvas(right, bg=BG_COLOR, highlightthickness=0)
        vsb = ttk.Scrollbar(right, orient="vertical", command=self._canvas.yview)
        def _yscroll_cmd(first, last):
            vsb.set(first, last)
            if float(last) > 0.85:
                self.win.after(1, self._maybe_load_more)
        self._canvas.configure(yscrollcommand=_yscroll_cmd)
        vsb.grid(row=1, column=1, sticky="ns")
        self._canvas.grid(row=1, column=0, sticky="nsew")
        self._inner = tk.Frame(self._canvas, bg=BG_COLOR)
        self._win_id = self._canvas.create_window((0,0), window=self._inner, anchor="nw")
        self._canvas.bind("<Configure>",
            lambda e: (self._canvas.itemconfig(self._win_id, width=e.width),
                       self._on_canvas_resize(e)))
        self._inner.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        # Scroll: bind sulla finestra intera per non perdere mai lo scroll
        def _scroll_up(e):   self._canvas.yview_scroll(-3,"units")
        def _scroll_dn(e):   self._canvas.yview_scroll( 3,"units")
        def _scroll_mw(e):   self._canvas.yview_scroll(-1 if e.delta>0 else 1,"units")
        self._scroll_up = _scroll_up
        self._scroll_dn = _scroll_dn
        self._scroll_mw = _scroll_mw
        # Scroll smart: rotella va al pannello sotto il mouse
        def _smart_scroll(units):
            def _fn(e):
                # Controlla se il mouse è sul pannello sinistro
                lx = self._left.winfo_rootx()
                lw = self._left.winfo_width()
                if lx <= e.x_root <= lx + lw:
                    if self._nav_inner.winfo_height()>self._nav_canvas.winfo_height():
                        self._nav_canvas.yview_scroll(units,"units")
                else:
                    self._canvas.yview_scroll(units,"units")
            return _fn
        def _smart_mw(e):
            lx = self._left.winfo_rootx()
            lw = self._left.winfo_width()
            u  = -1 if e.delta > 0 else 1
            if lx <= e.x_root <= lx + lw:
                if self._nav_inner.winfo_height()>self._nav_canvas.winfo_height():
                    self._nav_canvas.yview_scroll(u,"units")
            else:
                self._canvas.yview_scroll(u,"units")
        self.win.bind("<Button-4>",   _smart_scroll(-3), "+")
        self.win.bind("<Button-5>",   _smart_scroll( 3), "+")
        self.win.bind("<MouseWheel>", _smart_mw, "+")
        # Frecce: bind sulla finestra intera,
        # ma solo se il focus non è su un Entry o Text
        def _arrow_guard(fn):
            def _wrapped(e):
                try:
                    w = self.win.focus_get()
                    if isinstance(w, (tk.Entry, tk.Text)): return
                except Exception: pass
                fn(e)
            return _wrapped
        for _ak in ("<Right>","<Left>","<Down>","<Up>"):
            self.win.bind(_ak, _arrow_guard(self._on_arrow), "+")
        for _sk in ("<Shift-Right>","<Shift-Left>",
                    "<Shift-Down>","<Shift-Up>"):
            self.win.bind(_sk, _arrow_guard(self._on_shift_arrow), "+")


        # Smistamento (visibile solo se sorter disponibile). Figlie di
        # "body", NON di "right": "right" e' solo UN pannello del
        # PanedWindow orizzontale (l'altro e' l'anteprima ingrandita),
        # quindi gridarle dentro "right" le confinava sotto la sola
        # griglia miniature, mentre l'anteprima — un pannello A SE',
        # alto quanto l'intero right_paned — proseguiva fino in fondo
        # alla finestra accanto a loro: la colonna anteprima appariva
        # piu' alta della griglia e "tagliava" le due righe, segnalato
        # da Carlo. Qui sotto invece sono a tutta larghezza, SOTTO al
        # PanedWindow intero (griglia + anteprima), che quindi resta
        # alto solo quanto la griglia miniature — coerente, come chiesto.
        body.rowconfigure(1, weight=0)
        body.rowconfigure(2, weight=0)
        if self.sorter:
            self._sort_bar = tk.Frame(body, bg=PANEL_COLOR)
            # A TUTTA LARGHEZZA (colonna 0 e 1: nav sinistra + griglia/
            # anteprima), non solo column=1 — altrimenti inizia sotto la
            # colonna destra invece che dal bordo sinistro della
            # finestra (bug reale, segnalato da Carlo). Stesso principio
            # gia' corretto in FolderBrowser._tag_row_frame
            # (image_sorter.py), da cui questa barra e' stata adattata.
            self._sort_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
            self._sort_bar.grid_remove()

        # Nuvola di tag cliccabili per la selezione corrente — stesso
        # principio della riga "Preset" qui sopra, ma per i tag (vedi
        # checkbox "Tag" e _build_tag_row).
        if self.sorter and _METADATA_STORE_AVAILABLE:
            self._tag_row_frame = tk.Frame(body, bg=BG_COLOR)
            # Stesso motivo del _sort_bar qui sopra: a tutta larghezza,
            # non solo sotto la colonna destra.
            self._tag_row_frame.grid(row=2, column=0, columnspan=2, sticky="ew")
            self._tag_row_frame.grid_remove()
            self._tag_btn_refs = {}
            self._tag_row_inner = None

        # ── Pulsante toggle anteprima + pannello anteprima ingrandita ──
        # Pulsante flottante con place() sopra l'angolo del pannello
        # principale, fuori dal grid: non partecipa alla negoziazione
        # dello spazio tra le colonne e non si può trascinare per errore
        # (a differenza di una striscia-maniglia gridata).
        self._preview_toggle_btn = tk.Button(
            right, text="<", font=("TkFixedFont", 9),
            bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", bd=0,
            activebackground=HIGHLIGHT, cursor="hand2",
            command=self._toggle_preview_pane)
        self._preview_toggle_btn.place(relx=1.0, rely=0.0, anchor="ne",
                                        x=-2, y=2, width=20, height=20)
        self._preview_toggle_btn.lift()

        self._preview_pane = tk.Frame(right_paned, bg=PANEL_COLOR)
        self._preview_pane.rowconfigure(0, weight=1)
        self._preview_pane.columnconfigure(0, weight=1)
        self._preview_label = tk.Label(self._preview_pane, bg=PANEL_COLOR,
                                        cursor="hand2")
        self._preview_label.grid(row=0, column=0, sticky="nsew")
        self._preview_label.bind(
            "<Button-3>",
            lambda e: self._context_menu(e, self._focus_item)
                      if getattr(self, '_focus_item', None) else None)
        self._preview_label.bind(
            "<Double-Button-1>",
            lambda e: self._open_file(self._focus_item["path"])
                      if getattr(self, '_focus_item', None) else None)
        self._preview_photo = None
        self._preview_current_path = None
        self._preview_visible = False   # nascosto di default
        self._preview_resize_job = None
        # Stelle + pallini colore: stessa idea di Naviga
        # (FolderBrowser._preview_rating_row in image_sorter.py) — widget
        # persistenti, ridipinti da _refresh_preview_rating() ad ogni
        # cambio di self._preview_current_path.
        if _METADATA_STORE_AVAILABLE:
            self._preview_rating_row = tk.Frame(self._preview_pane, bg=PANEL_COLOR)
            self._preview_rating_row.grid(row=1, column=0, sticky="ew",
                                          padx=6, pady=(4, 4))
            _prf_stars = tk.Frame(self._preview_rating_row, bg=PANEL_COLOR)
            _prf_stars.pack(side="left", padx=(0, 10))
            self._preview_stars = []
            for _i in range(1, 6):
                _star = tk.Label(_prf_stars, text="*",
                                 font=("TkFixedFont", 12, "bold"),
                                 bg=PANEL_COLOR, fg=MUTED_COLOR, cursor="hand2")
                _star.pack(side="left", padx=2)
                _star.bind("<Button-1>",
                           lambda e, i=_i: self._click_preview_star(i))
                self._preview_stars.append(_star)
            _prf_dots = tk.Frame(self._preview_rating_row, bg=PANEL_COLOR)
            _prf_dots.pack(side="right", padx=(10, 0))
            self._preview_color_dots = draw_colorlabel_dots(
                _prf_dots, "", lambda cid: self._click_preview_colorlabel(cid))
        self._preview_pane.bind("<Configure>", self._on_preview_pane_configure)
        if self.sorter and self.sorter.config.get("timeline_preview_visible", False):
            self.win.after_idle(self._toggle_preview_pane)

    def _toggle_preview_pane(self):
        """Mostra/nasconde il pannello di anteprima ingrandita a destra.
        Stato e proporzioni (posizione del divisore) vengono ricordati in
        config tra una sessione e l'altra (se sorter è disponibile — non
        in modalità standalone)."""
        cfg = self.sorter.config if self.sorter else None
        if self._preview_visible:
            if cfg is not None:
                try:
                    cfg["timeline_preview_sash"] = self._right_paned.sashpos(0)
                except Exception:
                    pass
            try:
                self._right_paned.forget(self._preview_pane)
            except Exception:
                pass
            self._preview_visible = False
            self._preview_toggle_btn.config(text="<")
        else:
            try:
                self._right_paned.add(self._preview_pane, weight=2)
            except Exception:
                pass
            self._preview_visible = True
            self._preview_toggle_btn.config(text=">")
            if cfg is not None:
                saved_pos = cfg.get("timeline_preview_sash")
                if saved_pos:
                    def _restore_sash():
                        try:
                            self._right_paned.sashpos(0, saved_pos)
                        except Exception:
                            pass
                    # Piu' tentativi, non solo due ravvicinati: se
                    # _toggle_preview_pane() viene eseguita presto (l'
                    # after_idle che la programma puo' venire "svegliato"
                    # in anticipo da un update_idletasks() successivo in
                    # __init__, prima che win.geometry()/deiconify()
                    # abbiano davvero portato la finestra alla sua
                    # dimensione finale), un vero window manager puo'
                    # impiegare piu' di 90ms per applicarla — un margine
                    # che con soli due tentativi ravvicinati (20/90ms) a
                    # volte non basta, lasciando il divisore fissato su
                    # una larghezza sbagliata (colonna centrale schiacciata
                    # dalla destra, segnalato da Carlo). Stessi ritardi
                    # gia' usati con successo per lo stesso problema in
                    # Naviga (_set_sash, FolderBrowser in image_sorter.py).
                    self.win.after(20, _restore_sash)
                    self.win.after(90, _restore_sash)
                    self.win.after(500, _restore_sash)
                    self.win.after(1000, _restore_sash)
            self.win.after_idle(self._update_preview_pane)
        if cfg is not None:
            cfg["timeline_preview_visible"] = self._preview_visible
            save_config(cfg)

    def _on_preview_pane_configure(self, event):
        """Ridisegna l'anteprima quando il pannello cambia dimensione,
        con un piccolo ritardo per non rigenerare l'immagine ad ogni
        pixel durante il trascinamento della finestra."""
        if not self._preview_visible:
            return
        if self._preview_resize_job:
            try: self.win.after_cancel(self._preview_resize_job)
            except Exception: pass
        self._preview_resize_job = self.win.after(
            150, lambda: self._update_preview_pane(force=True))

    def _update_preview_pane(self, force=False):
        """Aggiorna l'anteprima ingrandita nel pannello destro in base al
        file attualmente selezionato/con focus. Ridimensiona l'immagine
        (o il frame video) per riempire lo spazio disponibile nel
        pannello, mantenendo le proporzioni.

        I video vengono elaborati in un thread separato (estrazione frame
        via ffmpeg può richiedere un tempo non trascurabile): altrimenti,
        con l'anteprima aperta, ogni singolo click su un video
        bloccherebbe l'interfaccia per tutta la durata dell'estrazione.
        Le immagini restano sincrone (già veloci con la modalità draft)."""
        if not self._preview_visible:
            return
        path = None
        if len(self._selected) == 1:
            path = next(iter(self._selected))
        elif getattr(self, '_focus_item', None):
            path = self._focus_item.get("path")
        if not path or not os.path.isfile(path):
            self._preview_label.config(image="", text="")
            self._preview_photo = None
            self._preview_current_path = None
            self._refresh_preview_rating()
            return
        if not force and path == self._preview_current_path:
            return
        w = max(50, self._preview_pane.winfo_width() - 12)
        h = max(50, self._preview_pane.winfo_height() - 12)
        ext = os.path.splitext(path)[1].lower()
        # Contrassegna questa richiesta: un risultato di una richiesta
        # superata (es. click rapidi su più video di fila) viene scartato
        # invece di sovrascrivere per errore un'anteprima più recente.
        self._preview_gen = getattr(self, '_preview_gen', 0) + 1
        gen = self._preview_gen

        if ext in VID_EXT:
            def _worker():
                try:
                    img = get_video_frame(path, size=(w, h))
                    if img is not None:
                        img = img.convert("RGB")
                        img.thumbnail((w, h), Image.Resampling.LANCZOS)
                except Exception:
                    img = None
                try:
                    self.win.after(0, lambda: self._apply_preview_image(img, path, gen))
                except Exception:
                    pass   # finestra chiusa nel frattempo: nessun problema
            threading.Thread(target=_worker, daemon=True).start()
            return

        try:
            img = Image.open(path)
            if hasattr(img, "draft") and ext in (".jpg", ".jpeg"):
                img.draft("RGB", (w*2, h*2))
            img = ImageOps.exif_transpose(img)
            img = img.convert("RGB")
            img.thumbnail((w, h), Image.Resampling.LANCZOS)
        except Exception:
            img = None
        self._apply_preview_image(img, path, gen)

    def _apply_preview_image(self, img, path, gen):
        """Applica l'immagine (PIL, già ridimensionata) al pannello
        anteprima — solo se è ancora la richiesta più recente."""
        if gen != getattr(self, '_preview_gen', gen):
            return
        if img is None:
            self._preview_label.config(image="", text="")
            self._preview_photo = None
            self._refresh_preview_rating()
            return
        try:
            photo = ImageTk.PhotoImage(img)
            self._preview_photo = photo   # riferimento vivo
            self._preview_label.config(image=photo, text="")
            self._preview_current_path = path
            self._refresh_preview_rating()
        except Exception:
            pass

    def _click_preview_star(self, i):
        path = self._preview_current_path
        if not path:
            return
        cur = metadata_store.get_meta(path)["rating"]
        metadata_store.set_rating(path, 0 if cur == i else i)
        self._sync_grid_item(path)
        self._refresh_preview_rating()

    def _click_preview_colorlabel(self, cid):
        path = self._preview_current_path
        if not path:
            return
        metadata_store.toggle_color(path, cid)
        self._sync_grid_item(path)
        self._refresh_preview_rating()

    def _sync_grid_item(self, path):
        """Trova l'item della griglia corrispondente a path (se ancora
        visibile con la vista/filtro correnti) e ne ridipinge la riga
        stelle+pallini — il file mostrato in anteprima puo' provenire
        sia dalla selezione singola sia dal focus (vedi
        _update_preview_pane), non solo da self._focus_item."""
        for _it in self.filtered:
            if _it.get("path") == path:
                self._refresh_rating_row(_it)
                return

    def _refresh_preview_rating(self):
        """Ridipinge la riga stelle+pallini del pannello anteprima in base
        a self._preview_current_path — stessa idea di Naviga
        (FolderBrowser._refresh_preview_rating in image_sorter.py)."""
        if not _METADATA_STORE_AVAILABLE or not hasattr(self, "_preview_stars"):
            return
        path = self._preview_current_path
        if not path:
            for _s in self._preview_stars:
                try: _s.config(fg=MUTED_COLOR)
                except Exception: pass
            repaint_colorlabel_dots(self._preview_color_dots, [])
            return
        meta = metadata_store.get_meta(path)
        cur = meta["rating"]
        for _idx, _s in enumerate(self._preview_stars, start=1):
            try: _s.config(fg=HUD_CYAN if cur >= _idx else MUTED_COLOR)
            except Exception: pass
        repaint_colorlabel_dots(self._preview_color_dots, meta["colors"])

    def _build_statusbar(self):
        pass

    def _pick_folder(self):
        if self._browse_fn:
            d = self._browse_fn(self.win,
                                title="Scegli cartella da esplorare")
            if d: self._add_folder(d)
        else:
            d = filedialog.askdirectory(parent=self.win,
                                        title="Scegli cartella da esplorare")
            if d: self._add_folder(d)

    def _add_folder(self, path):
        if any(t[0] == path for t in self._folder_labels):
            return
        name = os.path.basename(path) or path
        frm  = tk.Frame(self._folder_frame, bg=ACCENT_COLOR)
        frm.pack(side="left", padx=2, pady=6)
        tk.Label(frm, text=tk_safe(name[:18]),
                 font=("TkFixedFont",8), bg=ACCENT_COLOR,
                 fg=HUD_CYAN).pack(side="left", padx=(4,2), pady=2)
        tk.Button(frm, text="x", font=("TkFixedFont",7),
                  bg=ACCENT_COLOR, fg=MUTED_COLOR, relief="flat", bd=0,
                  activebackground=HIGHLIGHT,
                  command=lambda p=path, f=frm: self._remove_folder(p,f)
                  ).pack(side="left", padx=2)
        self._folder_labels.append((path, frm))

    def _remove_folder(self, path, frm):
        self._folder_labels = [t for t in self._folder_labels if t[0] != path]
        frm.destroy()

    # ── Scansione ─────────────────────────────────────────────────────────────
    def _start_scan(self):
        dirs = [t[0] for t in self._folder_labels]
        if not dirs:
            self.sorter._show_toast("Aggiungi almeno una cartella sorgente.", duration=2000) if self.sorter else None
            return
        if self._scan_thread and self._scan_thread.is_alive():
            return
        self._stop_flag = False
        self._scan_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._status("Scansione in corso...", "#e67e22")
        self._prog_bar.place(relwidth=0)
        self._count_lbl.config(text="")
        self.items = []

        def _run():
            def _prog(done, total):
                if self._stop_flag:
                    raise StopIteration("Scansione interrotta")
                pct = done/total if total else 0
                self.win.after(0, lambda p=pct: self._prog_bar.place(relwidth=p))
                self.win.after(0, lambda d=done, t=total: (
                    self._status(f"{d}/{t} file...", "#e67e22"),
                    self._count_lbl.config(text=f"{d} / {t}")))
            try:
                depth = self._depth_var.get()
                max_d = None if depth == 0 else depth
                pf = getattr(self.sorter,"_private_folders",[]) if self.sorter else []
                ul = getattr(self.sorter,"_unlocked_private",set()) if self.sorter else set()
                items = scan_files(dirs, _prog, max_depth=max_d,
                                   private_folders=pf, unlocked=ul)
            except StopIteration:
                # Stop richiesto: resetta UI
                self.win.after(0, lambda: self._scan_btn.config(state="normal"))
                self.win.after(0, lambda: self._stop_btn.config(state="disabled"))
                self.win.after(0, lambda: self._count_lbl.config(text=""))
                return
            except Exception as ex:
                self.win.after(0, lambda e=ex: self._status(f"Errore: {e}", WARNING))
                return
            finally:
                self.win.after(0, lambda: self._scan_btn.config(state="normal"))
                self.win.after(0, lambda: self._stop_btn.config(state="disabled"))
            if not self._stop_flag:
                self.win.after(0, lambda: self._scan_done(items))

        self._scan_thread = threading.Thread(target=_run, daemon=True)
        self._scan_thread.start()

    def _stop_scan(self):
        self._stop_flag = True
        self._stop_btn.config(state="disabled")
        self._scan_btn.config(state="normal")
        self._status("Scansione interrotta.", MUTED_COLOR)
        self._prog_bar.place(relwidth=0)

    def _scan_done(self, items):
        self.items    = items
        self.filtered = sort_files(items, self._sort_mode, self._sort_reverse)
        self._prog_bar.place(relwidth=1)
        n_gps = sum(1 for i in items if i.get("gps"))
        self._status("Scansione completata.", SUCCESS)
        self._count_lbl.config(text=f"{len(items)} file  |  {n_gps} con GPS")
        self._build_nav()
        self._render()
        self.win.after(1000, lambda: self._prog_bar.place(relwidth=0))

    # ── Navigatore sinistro ───────────────────────────────────────────────────
    def _build_nav(self):
        # Assicura che la mappa colori sia aggiornata
        if not hasattr(self, '_dir_color_map'):
            self._compute_dir_color_map()
        # Disabilita Configure per evitare scrollregion errata durante build
        self._nav_inner.unbind("<Configure>")
        for w in self._nav_inner.winfo_children():
            w.destroy()
        self._nav_canvas.configure(scrollregion=(0,0,0,0))
        self._nav_canvas.yview_moveto(0)

        def _nav_btn(text, cmd, indent=0, color=TEXT_COLOR):
            btn = tk.Button(self._nav_inner, text=tk_safe(text),
                            font=("TkFixedFont",8), bg=PANEL_COLOR,
                            fg=color, relief="flat", bd=0, anchor="w",
                            padx=8+indent*12,
                            activebackground=HIGHLIGHT, activeforeground=HUD_CYAN,
                            command=cmd)
            btn.pack(fill="x", pady=1)
            return btn

        tk.Label(self._nav_inner,
                 text=f"{len(self.items)} file",
                 font=("TkFixedFont",9,"bold"), bg=PANEL_COLOR,
                 fg=HUD_CYAN, anchor="w"
                 ).pack(fill="x", padx=8, pady=(8,0))
        _nav_btn("Tutti i file", lambda: self._filter(None), color=TEXT_COLOR)

        # Per anno
        years = {}
        for item in self.filtered:
            y = item["date"].year if item["date"] else 0
            years.setdefault(y, 0)
            years[y] += 1

        tk.Label(self._nav_inner, text="  Anno", font=("TkFixedFont",7,"bold"),
                 bg=PANEL_COLOR, fg=MUTED_COLOR).pack(anchor="w", padx=8, pady=(8,2))
        for y in sorted(years, reverse=True):
            label = str(y) if y else "Sconosciuto"
            _nav_btn(f"{label}  ({years[y]})", lambda yr=y: self._filter(("year",yr)),
                     indent=1)

        # Per luogo
        locs = {}
        for item in self.filtered:
            loc = item.get("location","")
            if loc:
                city = loc.split(",")[0].strip()
                locs.setdefault(city, 0)
                locs[city] += 1

        if locs:
            tk.Label(self._nav_inner, text="  Luogo", font=("TkFixedFont",7,"bold"),
                     bg=PANEL_COLOR, fg=MUTED_COLOR).pack(anchor="w", padx=8, pady=(8,2))
            for loc in sorted(locs, key=lambda x: -locs[x])[:20]:
                _nav_btn(f"{loc}  ({locs[loc]})",
                         lambda l=loc: self._filter(("location", l)), indent=1)

        # Per cartella — con rimando cromatico
        dirs_seen = []
        for item in self.filtered:
            d = os.path.dirname(item["path"])
            if d not in dirs_seen:
                dirs_seen.append(d)

        if dirs_seen:
            tk.Label(self._nav_inner, text="  Cartella",
                     font=("TkFixedFont",7,"bold"),
                     bg=PANEL_COLOR, fg=MUTED_COLOR
                     ).pack(anchor="w", padx=8, pady=(8,2))

            for d in dirs_seen:
                col = getattr(self, "_dir_color_map", {}).get(d,
                      FOLDER_PALETTE[dirs_seen.index(d) % len(FOLDER_PALETTE)])
                n   = sum(1 for i in self.filtered
                          if os.path.dirname(i["path"]) == d)
                short = os.path.basename(d) or d
                if len(short) > 22:
                    short = short[:20] + ".."

                row = tk.Frame(self._nav_inner, bg=PANEL_COLOR)
                row.pack(fill="x", padx=8, pady=1)

                # Niente pallino qui (c'era, tolto su richiesta di
                # Carlo): con le colorlabel delle foto ormai in giro
                # nella stessa barra laterale, un altro pallino colorato
                # accanto al nome cartella si confondeva con quelli — il
                # colore del testo del nome basta gia' da solo a fare da
                # rimando cromatico.
                tk.Button(row,
                          text=tk_safe(f"{short}  ({n})"),
                          font=("TkFixedFont",8),
                          bg=PANEL_COLOR, fg=col,
                          relief="flat", bd=0, anchor="w",
                          activebackground=HIGHLIGHT,
                          activeforeground="white",
                          command=lambda folder=d:
                              self._filter(("folder", folder))
                          ).pack(side="left", fill="x", expand=True)

        # Per valutazione — stesso stile delle sezioni sopra (Anno/Luogo/
        # Cartella): click filtra sui file con QUELLA valutazione o
        # superiore (stesso criterio di metadata_store.query(rating_min=)).
        if _METADATA_STORE_AVAILABLE:
            rating_counts = {}
            for item in self.filtered:
                _r = metadata_store.get_meta(item["path"])["rating"]
                if _r > 0:
                    rating_counts[_r] = rating_counts.get(_r, 0) + 1
            if rating_counts:
                tk.Label(self._nav_inner, text="  Valutazione",
                         font=("TkFixedFont",7,"bold"),
                         bg=PANEL_COLOR, fg=MUTED_COLOR
                         ).pack(anchor="w", padx=8, pady=(8,2))
                for _r in range(5, 0, -1):
                    _n = rating_counts.get(_r, 0)
                    if _n == 0:
                        continue
                    _nav_btn(f"{'*'*_r}  ({_n})",
                             lambda rr=_r: self._filter(("rating", rr)),
                             indent=1, color=HUD_CYAN)

            # Per colorlabel — un file puo' comparire sotto piu' di un
            # colore (colorlabel multiple, non escludenti).
            color_counts = {}
            for item in self.filtered:
                for _c in metadata_store.get_meta(item["path"])["colors"]:
                    color_counts[_c] = color_counts.get(_c, 0) + 1
            if color_counts:
                tk.Label(self._nav_inner, text="  Colore",
                         font=("TkFixedFont",7,"bold"),
                         bg=PANEL_COLOR, fg=MUTED_COLOR
                         ).pack(anchor="w", padx=8, pady=(8,2))
                for _cid, _cname, _chex in metadata_store.COLOR_LABELS:
                    _n = color_counts.get(_cid, 0)
                    if _n == 0:
                        continue
                    _row = tk.Frame(self._nav_inner, bg=PANEL_COLOR)
                    _row.pack(fill="x", padx=8, pady=1)
                    _dot = tk.Canvas(_row, width=10, height=10,
                                     bg=PANEL_COLOR, highlightthickness=0)
                    _dot.create_oval(1, 1, 9, 9, fill=_chex, outline="")
                    _dot.pack(side="left", padx=(8,4))
                    tk.Button(_row, text=tk_safe(f"{_cname}  ({_n})"),
                              font=("TkFixedFont",8), bg=PANEL_COLOR, fg=_chex,
                              relief="flat", bd=0, anchor="w",
                              activebackground=HIGHLIGHT, activeforeground="white",
                              command=lambda c=_cid: self._filter(("color", c))
                              ).pack(side="left", fill="x", expand=True)

        # Bottone mappa
        tk.Frame(self._nav_inner, bg=MUTED_COLOR, height=1).pack(fill="x", pady=8)
        tk.Button(self._nav_inner, text="Mappa GPS",
                  font=("TkFixedFont",8,"bold"), bg="#1a3a5a",
                  fg=HUD_CYAN, relief="flat", padx=8,
                  activebackground=HIGHLIGHT,
                  command=self._open_map).pack(fill="x", padx=8, pady=4, ipady=3)
        n_gps = sum(1 for i in self.items if i.get("gps"))
        tk.Label(self._nav_inner, text=f"{n_gps} con GPS",
                 font=("TkFixedFont",7), bg=PANEL_COLOR,
                 fg=MUTED_COLOR, anchor="w"
                 ).pack(fill="x", padx=10, pady=(0,4))
        # Reset scroll e ripristino bind dopo costruzione widget
        def _nav_done():
            if not self._nav_canvas.winfo_exists(): return
            self._nav_canvas.update_idletasks()
            ch=self._nav_canvas.winfo_height()
            ih=self._nav_inner.winfo_height()
            self._nav_canvas.configure(scrollregion=(
                0,0,self._nav_inner.winfo_width(),max(ih,ch)))
        self._nav_canvas.after(100, _nav_done)

    def _filter(self, key):
        self._filter_key = key
        if key is None:
            self.filtered = sort_files(self.items, self._sort_mode, self._sort_reverse)
        elif key[0] == "year":
            yr = key[1]
            self.filtered = sort_files(
                [i for i in self.items
                 if (i["date"].year if i["date"] else 0) == yr],
                self._sort_mode, self._sort_reverse)
        elif key[0] == "location":
            loc = key[1]
            self.filtered = sort_files(
                [i for i in self.items
                 if loc in (i.get("location","").split(",")[0].strip())],
                self._sort_mode, self._sort_reverse)
        elif key[0] == "folder":
            folder = key[1]
            self.filtered = sort_files(
                [i for i in self.items
                 if os.path.dirname(i["path"]) == folder],
                self._sort_mode, self._sort_reverse)
        elif key[0] == "rating":
            min_r = key[1]
            self.filtered = sort_files(
                [i for i in self.items
                 if metadata_store.get_meta(i["path"])["rating"] >= min_r],
                self._sort_mode, self._sort_reverse)
        elif key[0] == "color":
            cid = key[1]
            self.filtered = sort_files(
                [i for i in self.items
                 if cid in metadata_store.get_meta(i["path"])["colors"]],
                self._sort_mode, self._sort_reverse)
        self._page = 0
        self._render()

    # ── Rendering ─────────────────────────────────────────────────────────────
    def _on_depth_change(self, val=None):
        n = self._depth_var.get()
        if n == 0:
            self._depth_lbl.config(text="Illimitata")
        elif n == 1:
            self._depth_lbl.config(text="1 livello")
        else:
            self._depth_lbl.config(text=f"{n} livelli")

    def _tw(self):
        """Larghezza anteprima corrente."""
        return int(THUMB_W * self._thumb_scale)

    def _th(self):
        """Altezza anteprima corrente."""
        return int(THUMB_H * self._thumb_scale)

    def _toggle_thumb_size(self):
        """Alterna tra dimensione normale (1x) e grande (1.5x)."""
        self._thumb_scale = 2.0 if self._thumb_scale == 1.0 else 1.0
        lbl = "2x" if self._thumb_scale == 2.0 else "1x"
        self._size_btn.config(
            text=lbl,
            bg=HUD_CYAN if self._thumb_scale == 2.0 else ACCENT_COLOR,
            fg="#0a1a2e" if self._thumb_scale == 2.0 else TEXT_COLOR)
        self._page = 0
        self._render()

    def _toggle_show_ratings(self):
        """Mostra/nasconde la riga di stelle+pallini colore sotto le
        miniature della griglia — stesso principio del check "Ratings"
        di Naviga (FolderBrowser._toggle_show_ratings in
        image_sorter.py). Stato ricordato in config tra le sessioni,
        ricarica per applicare subito la scelta: l'altezza delle celle
        cambia (niente spazio vuoto sprecato quando la riga e'
        disattivata), non basta nascondere i widget gia' creati."""
        self._show_ratings = self._show_ratings_var.get()
        if self.sorter:
            cfg = self.sorter.config
            cfg["timeline_show_ratings"] = self._show_ratings
            save_config(cfg)
        self._page = 0
        self._render()

    def _toggle_show_preset_row(self):
        """Mostra/nasconde la barra destinazioni rapide sotto la griglia
        — stesso principio del check "Preset" di Naviga
        (FolderBrowser._toggle_show_preset_row in image_sorter.py).
        Stato ricordato in config tra le sessioni."""
        if self.sorter:
            self.sorter.config["timeline_show_preset_row"] = self._show_preset_row_var.get()
            save_config(self.sorter.config)
        self._update_sel_bar()

    def _toggle_show_tag_row(self):
        """Mostra/nasconde la nuvola di tag cliccabili per la selezione
        corrente — stesso principio del check "Tag" di Naviga
        (FolderBrowser._toggle_show_tag_row in image_sorter.py). Stato
        ricordato in config tra le sessioni."""
        if self.sorter:
            self.sorter.config["timeline_show_tag_row"] = self._show_tag_row_var.get()
            save_config(self.sorter.config)
        if not self._show_tag_row_var.get():
            self._tag_row_frame.grid_remove()
        self._build_tag_row()

    def _toggle_order(self):
        """Inverte l'ordine cronologico."""
        self._sort_reverse = not self._sort_reverse
        lbl = "9-1" if self._sort_reverse else "1-9"
        self._rev_btn.config(text=lbl)
        # Riordina filtered con il nuovo verso, poi ridisegna
        base = self.filtered if self._filter_key else self.items
        self.filtered = sort_files(base, self._sort_mode, self._sort_reverse)
        self._page = 0
        self._render()

    def _apply_view(self):
        label = self._view_var.get()
        self._view_mode = getattr(self, "_view_map", {}).get(label, label)
        if self._view_mode == "map":
            self._open_map()
            prev = self._last_view if hasattr(self, "_last_view") else "Timeline"
            self._view_var.set(prev)
            return
        self._last_view = label
        self._page = 0
        self._render()

    def _apply_sort(self):
        label = self._sort_var.get()
        self._sort_mode = getattr(self, "_sort_map", {}).get(label, label)
        self.filtered   = sort_files(
            self.filtered if self._filter_key else self.items,
            self._sort_mode, self._sort_reverse)
        self._page = 0
        self._render()

    def _compute_dir_color_map(self):
        """Calcola la mappa cartella→colore su tutti gli item (non solo filtered).
        Garantisce colori stabili indipendentemente dal filtro attivo.
        """
        dirs_seen = []
        for item in self.items:   # usa self.items (tutti) non self.filtered
            d = os.path.dirname(item["path"])
            if d not in dirs_seen:
                dirs_seen.append(d)
        self._dir_color_map = {
            d: FOLDER_PALETTE[i % len(FOLDER_PALETTE)]
            for i, d in enumerate(dirs_seen)
        }

    def _render(self):
        """Svuota il pannello e ridisegna la prima pagina."""
        # Bordo rosso se almeno una cartella scansionata è privata
        if self.sorter and self.items:
            from image_sorter import _is_private
            pf = self.sorter._private_folders
            any_priv = pf and any(_is_private(i["path"], pf)
                                  for i in self.items)
            hud_apply(self.win, PRIVACY_RED if any_priv else HUD_CYAN)
        self._selected.clear()
        if hasattr(self,"_sort_bar"): self._sort_bar.grid_remove()
        for w in self._inner.winfo_children():
            w.destroy()
        # Reset scroll in cima e scrollregion
        self._canvas.yview_moveto(0)
        self._canvas.configure(scrollregion=(0,0,0,0))
        self._page = 0
        # Mappa cartella → colore (calcolata su tutti gli item, non solo filtered)
        self._compute_dir_color_map()
        # Dopo il rendering, carica pagine aggiuntive se la finestra è grande
        self.win.after(200, self._fill_visible)
        # Click sul canvas di sfondo deseleziona tutto
        self._canvas.bind("<Button-1>", self._click_background)

        view = self._view_mode
        if view == "timeline":
            self._render_timeline(0, PAGE_SIZE)
        else:
            self._render_grid(0, PAGE_SIZE)

    def _render_timeline(self, start, end):
        """Visualizza gruppi per mese con header, lazy da start a end."""
        items_slice = self.filtered[start:end]
        if start == 0:
            groups = group_by_month(self.filtered[:end])
        else:
            # Aggiungi solo i nuovi item all'ultimo gruppo o crea nuovi gruppi
            groups = group_by_month(items_slice)

        canvas_w = max(self._canvas.winfo_width(), 600)

        for month_lbl, loc_hint, group_items in groups:
            # Header mese — cliccabile: seleziona tutti i file del gruppo.
            # Click normale = solo questo mese (deseleziona il resto),
            # Ctrl+click = aggiunge al gruppo gia' selezionato, come per le
            # miniature.
            hdr = tk.Frame(self._inner, bg=BG_COLOR, cursor="hand2")
            hdr.pack(fill="x", padx=12, pady=(16,4))
            lbl_m = tk.Label(hdr, text=tk_safe(month_lbl),
                             font=("TkFixedFont",14,"bold"),
                             bg=BG_COLOR, fg=TEXT_COLOR, cursor="hand2")
            lbl_m.pack(side="left")
            hdr_widgets = [hdr, lbl_m]
            if loc_hint:
                lbl_l = tk.Label(hdr, text=f"  @ {tk_safe(loc_hint)}",
                                 font=("TkFixedFont",9),
                                 bg=BG_COLOR, fg=MUTED_COLOR, cursor="hand2")
                lbl_l.pack(side="left", padx=8)
                hdr_widgets.append(lbl_l)
            lbl_n = tk.Label(hdr, text=f"  [{len(group_items)}]",
                             font=("TkFixedFont",9),
                             bg=BG_COLOR, fg=MUTED_COLOR, cursor="hand2")
            lbl_n.pack(side="left")
            hdr_widgets.append(lbl_n)
            for _w in hdr_widgets:
                _w.bind("<Button-1>",
                        lambda e, g=group_items: self._select_group(g, False))
                _w.bind("<Control-Button-1>",
                        lambda e, g=group_items: self._select_group(g, True))

            # Griglia justified
            row_frame = None
            cols = max(1, (canvas_w - 24) // (self._tw() + 8))

            for i, item in enumerate(group_items):
                if i % cols == 0:
                    row_frame = tk.Frame(self._inner, bg=BG_COLOR)
                    row_frame.pack(fill="x", padx=12, pady=2)
                self._add_thumb_cell(row_frame, item)

        self._page = end // PAGE_SIZE

    def _render_grid(self, start, end):
        """Griglia flat senza raggruppamento."""
        canvas_w = max(self._canvas.winfo_width(), 600)
        cols     = max(1, (canvas_w - 24) // (self._tw() + 8))
        items    = self.filtered[start:end]

        for i, item in enumerate(items):
            col = i % cols
            if col == 0:
                row_frame = tk.Frame(self._inner, bg=BG_COLOR)
                row_frame.pack(fill="x", padx=12, pady=2)
            self._add_thumb_cell(row_frame, item)

        self._page = end // PAGE_SIZE

    def _add_thumb_cell(self, parent, item):
        """Crea una cella thumbnail con overlay stato."""
        is_moved = bool(item.get("moved_to"))

        # Altezza riga stelle+colorlabel proporzionale alla dimensione
        # miniatura corrente (1x/2x): funzione dedicata alla Timeline
        # (timeline_rating_row_sizes), non quella di Naviga — la
        # Timeline ha piu' spazio a disposizione alle stesse proporzioni
        # e merita stelle/pallini piu' grandi, senza toccare le
        # dimensioni di Naviga. Zero se la riga e' disattivata dal check
        # "Ratings": niente spazio vuoto sprecato.
        _rating_row_h = (timeline_rating_row_sizes(self._tw())[4]
                         if getattr(self, "_show_ratings", True) else 0)
        cell = tk.Frame(parent, bg=PANEL_COLOR,
                        width=self._tw()+4, height=self._th()+36+_rating_row_h)
        cell.pack(side="left", padx=3, pady=3)
        cell.pack_propagate(False)

        # Colore sottocartella diretta → bordo colorato attorno al canvas
        fpath = item["path"]
        item_dir = os.path.dirname(fpath)
        src_color = getattr(self, "_dir_color_map", {}).get(item_dir)

        # Canvas per thumbnail + overlay
        # Bordo colorato per cartella sorgente tramite highlightbackground
        border_color = src_color if src_color else "#1a1a2a"
        border_w = 3 if src_color else 0
        c = tk.Canvas(cell, width=self._tw(), height=self._th(),
                      bg="#1a1a2a", highlightthickness=border_w,
                      highlightbackground=border_color)
        c.pack(padx=2, pady=(2,0))

        # Cattura dimensioni ora (thread-safe: non accede a self nel thread)
        _tw = self._tw()
        _th = self._th()

        # Carica thumbnail in thread
        def _load(path=item["path"], cv=c, moved=is_moved, tw=_tw, th=_th):
            try:
              ext = os.path.splitext(path)[1].lower()
              img = make_thumb(path, tw, th)
            except Exception:
              import traceback; traceback.print_exc()
              img = None
              ext = os.path.splitext(path)[1].lower()

            def _show(i=img, cv=cv, is_vid=(ext in VID_EXT), tw=tw, th=th):
                if not cv.winfo_exists(): return
                cv.delete("all")
                if i:
                    cv.create_image(tw//2, th//2,
                                    anchor="center", image=i)
                    cv._img = i
                elif is_vid:
                    cx, cy = tw//2, th//2
                    r = min(tw, th) // 5
                    cv.create_oval(cx-r, cy-r, cx+r, cy+r,
                                   fill="#1a1a2a", outline="#555577", width=2)
                    pts = [cx-r//2, cy-r//2,
                           cx-r//2, cy+r//2,
                           cx+r//2, cy]
                    cv.create_polygon(pts, fill="#8888cc", outline="")
                    cv.create_text(tw//2, th-10,
                                   text=ext.upper().lstrip("."),
                                   fill="#8888cc",
                                   font=("TkFixedFont", 7))
                if moved:
                    cv.create_rectangle(0, th-18, tw, th,
                                        fill="#1a4a1a", outline="")
                    cv.create_text(tw//2, th-9,
                                   text=f"OK {item['moved_to'][:20]}",
                                   fill=SUCCESS, font=("TkFixedFont",7,"bold"))
                # Indicatore GPS: pallino verde in alto a destra
                if item.get("gps"):
                    r = 6
                    x0, y0 = tw - r - 4, r + 4
                    cv.create_oval(x0-r, y0-r, x0+r, y0+r,
                                   fill="#00e060", outline="#003a18", width=1,
                                   tags="gps_dot")
                # Indicatore formato: pallino ambra sotto quello GPS (o al
                # suo posto se la foto non ha coordinate)
                if is_non_jpeg_image(item["path"]):
                    r = 6
                    x0 = tw - r - 4
                    y0 = r + 4 + (2 * r + 4 if item.get("gps") else 0)
                    cv.create_oval(x0-r, y0-r, x0+r, y0+r,
                                   fill=FMT_DOT_FILL, outline=FMT_DOT_OUTLINE,
                                   width=1, tags="fmt_dot")

            self.win.after(0, _show)
        _get_thumb_executor().submit(_load)

        # Binding GPS sul canvas — apre mappa singola foto
        if item.get("gps"):
            def _open_single_map(e, it=item):
                # Verifica click sul pallino (angolo in alto a destra)
                tw_ = self._tw()
                r = 8   # area di click leggermente più grande del pallino
                x0 = tw_ - r - 4
                y0 = r + 4
                if abs(e.x - x0) <= r and abs(e.y - y0) <= r:
                    build_map([it], out_path=None)
            c.bind("<Button-1>", _open_single_map, add=True)

        # Nome file
        name = os.path.basename(item["path"])
        name_lbl = tk.Label(cell, text=tk_safe(name[:22]),
                            font=("TkFixedFont",7), bg=PANEL_COLOR,
                            fg=MUTED_COLOR if is_moved else TEXT_COLOR,
                            anchor="w", wraplength=self._tw())
        name_lbl.pack(fill="x", padx=2)

        # Data + GPS
        info = ""
        if item["date"]:
            info = item["date"].strftime("%d/%m/%Y")
        has_gps = bool(item.get("gps"))
        if item.get("location"):
            city = item["location"].split(",")[0].strip()
            info += f"  @ {city[:12]}"
        info_row = tk.Frame(cell, bg=PANEL_COLOR)
        info_row.pack(fill="x", padx=2)
        if has_gps:
            tk.Label(info_row, text="*", font=("TkFixedFont",7,"bold"),
                     bg=PANEL_COLOR, fg="#00c8ff"
                     ).pack(side="left")
        if info:
            tk.Label(info_row, text=tk_safe(info), font=("TkFixedFont",6),
                     bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="left")

        # Riga di stelle (rating): visualizzazione e modifica diretta
        # dalla griglia, non solo dal menu tasto destro. item["_rating_row"]
        # / item["_rating_stars"] tengono il riferimento per ridipingerla
        # dopo un click, senza ricostruire l'intera cella.
        if _METADATA_STORE_AVAILABLE and getattr(self, "_show_ratings", True):
            self._build_rating_row(cell, item)

        # Click singolo/doppio e tasto destro su celle
        for widget in [cell, c, name_lbl]:
            widget.bind("<Button-1>",
                        lambda e, it=item: self._sel_click(e, it))
            widget.bind("<Button-3>",
                        lambda e, it=item: self._context_menu(e, it))
        for widget in [c, name_lbl]:
            widget.bind("<Double-Button-1>",
                        lambda e, p=item["path"]: self._open_file(p))

        item["_cell"]      = cell       # riferimento per update overlay
        item["_src_color"] = src_color  # colore cartella sorgente
        item["_canvas"]    = c          # riferimento canvas per selezione

    def _build_rating_row(self, cell, item):
        """Riga di stelle + pallini cliccabili sotto il nome file, stessa
        idea gia' usata in Naviga (FolderBrowser._build_rating_row in
        image_sorter.py) — qui non condivisa direttamente perche' la
        Timeline lavora su 'item' (dict con 'path'), non solo su un
        percorso, ma la logica di interazione e' identica: click sulla
        stella N imposta il rating a N, ricliccare la stella che e' gia'
        il rating corrente lo azzera; stesso principio di toggle per i
        pallini colore.

        Stelle e pallini affiancati ma CENTRATI nella cella come gruppo
        unico (non allargati bordo-a-bordo): stessa correzione applicata
        a Naviga, per non farli confondere con le celle accanto.

        Dimensioni PROPORZIONALI alla dimensione miniatura corrente
        (1x/2x, self._tw()): funzione dedicata alla Timeline
        (timeline_rating_row_sizes), che ha piu' spazio disponibile di
        Naviga alle stesse proporzioni — vedi il commento nella
        funzione stessa (image_sorter.py) sul perche' non e' quella
        condivisa con Naviga."""
        fpath = item["path"]
        _star_fs, _dot_sz, _gap, _dot_pad, _row_h = timeline_rating_row_sizes(self._tw())
        row = tk.Frame(cell, bg=PANEL_COLOR)
        row.pack()

        stars_f = tk.Frame(row, bg=PANEL_COLOR)
        stars_f.pack(side="left", padx=(0, _gap))
        item["_rating_stars"] = []
        cur = metadata_store.get_meta(fpath)["rating"]
        for _i in range(1, 6):
            _fg = HUD_CYAN if cur >= _i else MUTED_COLOR
            _star = tk.Label(stars_f, text="*", font=("TkFixedFont", _star_fs, "bold"),
                             bg=PANEL_COLOR, fg=_fg, cursor="hand2")
            _star.pack(side="left")
            _star.bind("<Button-1>",
                       lambda e, i=_i, it=item: self._click_rating_star(it, i))
            item["_rating_stars"].append(_star)

        dots_f = tk.Frame(row, bg=PANEL_COLOR)
        dots_f.pack(side="left")
        cur_colors = metadata_store.get_meta(fpath)["colors"]
        item["_color_dots"] = draw_colorlabel_dots(
            dots_f, cur_colors,
            lambda cid, it=item: self._click_colorlabel_dot(it, cid),
            size=_dot_sz, pad=_dot_pad)
        item["_rating_dot_size"] = _dot_sz   # per il repaint in _refresh_rating_row

    def _click_rating_star(self, item, i):
        """Click su una stella: se il file cliccato fa parte di una
        selezione multipla, applica la stessa valutazione a TUTTI i
        file selezionati — stessa correzione fatta in Naviga
        (image_sorter.py), stesso principio "un click, tutta la
        selezione" invece di toccare solo la cella sotto il cursore."""
        fpath = item["path"]
        cur = metadata_store.get_meta(fpath)["rating"]
        new_val = 0 if cur == i else i
        if fpath in self._selected and len(self._selected) > 1:
            targets = self._selected
            metadata_store.bulk_set_rating(targets, new_val)
            for it in self.filtered:
                if it["path"] in targets:
                    self._refresh_rating_row(it)
        else:
            metadata_store.set_rating(fpath, new_val)
            self._refresh_rating_row(item)
        # Se il file appena modificato e' anche quello mostrato in
        # anteprima, quel pannello restava con le stelle vecchie finche'
        # non si cambiava immagine — segnalato da Carlo.
        # _refresh_preview_rating() si basa su _preview_current_path, e'
        # innocua da chiamare anche quando non c'entra nulla col click.
        self._refresh_preview_rating()

    def _click_colorlabel_dot(self, item, cid):
        """Click su un pallino colore: stessa estensione alla selezione
        multipla di _click_rating_star, con bulk_toggle_color."""
        fpath = item["path"]
        if fpath in self._selected and len(self._selected) > 1:
            targets = self._selected
            metadata_store.bulk_toggle_color(targets, cid)
            for it in self.filtered:
                if it["path"] in targets:
                    self._refresh_rating_row(it)
        else:
            metadata_store.toggle_color(fpath, cid)
            self._refresh_rating_row(item)
        # Stesso motivo di _click_rating_star qui sopra.
        self._refresh_preview_rating()

    def _refresh_rating_row(self, item):
        """Ridipinge SOLO la riga di stelle e pallini della cella indicata
        — chiamata dopo un click diretto sulla griglia e anche dal menu
        tasto destro (_context_menu, via attach_rating_overlay's
        on_change), cosi' un cambiamento fatto da li' si vede subito
        anche nella griglia."""
        if not _METADATA_STORE_AVAILABLE:
            return
        meta = metadata_store.get_meta(item["path"])
        stars = item.get("_rating_stars")
        if stars:
            cur = meta["rating"]
            for _idx, _star in enumerate(stars, start=1):
                try:
                    if _star.winfo_exists():
                        _star.config(fg=HUD_CYAN if cur >= _idx else MUTED_COLOR)
                except Exception:
                    pass
        dots = item.get("_color_dots")
        if dots:
            repaint_colorlabel_dots(dots, meta["colors"],
                                    size=item.get("_rating_dot_size", 8))

    # ── Selezione ─────────────────────────────────────────────────────────
    _UNSEL_BG = PANEL_COLOR
    _SEL_BG   = "#0a2a1a"   # sfondo cella selezionata (verde molto scuro)

    def _sel_click(self, e, item):
        """Click sinistro — comportamento standard OS:
           click singolo  : seleziona solo questo, deseleziona gli altri
           Ctrl+click     : aggiunge/rimuove questo dalla selezione
           Shift+click    : seleziona range dall'anchor a questo
        """
        self.win.focus_set()
        path = item["path"]
        ctrl  = bool(e.state & 0x0004)
        shift = bool(e.state & 0x0001)

        if ctrl:
            # Ctrl: toggle singolo, mantieni gli altri
            if path in self._selected:
                self._desel_item(item)
            else:
                self._sel_item(item)
                self._last_sel = path   # aggiorna anchor
        elif shift and self._last_sel:
            # Shift: range dall'anchor all'item corrente
            items = self._get_flat_items()
            paths = [i["path"] for i in items]
            if self._last_sel in paths and path in paths:
                i0 = paths.index(self._last_sel)
                i1 = paths.index(path)
                a, b = min(i0, i1), max(i0, i1)
                # Deseleziona tutto fuori dal range, seleziona il range
                self._clear_sel_silent()
                for i in items[a:b+1]:
                    self._sel_item(i)
            else:
                self._clear_sel()
                self._sel_item(item)
                self._last_sel = path
        else:
            # Click semplice: selezione singola
            self._clear_sel()
            self._sel_item(item)
            self._last_sel = path

        self._focus_item = item
        self._update_sel_bar()
        self._update_preview_pane()

    def _toggle_sel(self, item):
        if item["path"] in self._selected:
            self._desel_item(item)
        else:
            self._sel_item(item)

    def _sel_all(self):
        """Seleziona tutti i file della vista corrente (Ctrl+A) —
        mancava del tutto in Timeline (Naviga ce l'ha gia'), segnalato
        da Carlo."""
        for item in self._get_flat_items():
            if item["path"] not in self._selected:
                self._sel_item(item)
        self._update_sel_bar()
        self._update_preview_pane()

    def _clipboard_set(self, files, mode):
        """Copia/taglia file verso la clipboard REALE del sistema
        operativo — stessa funzione condivisa usata da Naviga
        (image_sorter.py), stessa interoperabilita' con file manager
        esterni (Nemo, Nautilus, Thunar...). Copia/Taglia/Incolla
        mancava del tutto in Timeline, segnalato da Carlo.

        Per "Taglia": stesso principio di Naviga — i file vengono
        spostati SUBITO nella cartella di attesa dedicata
        (CUT_STAGING_DIR in image_sorter.py), perche' Nemo (verificato)
        non si fida di un segnale taglia ricevuto da un programma
        esterno. Registrato nello Storico (azione "cut_staged")."""
        if mode == "cut":
            from image_sorter import move_to_cut_staging as _mcs, append_history as _ah
            _staged = []
            for fp in files:
                dest = _mcs(fp)
                if dest:
                    _ah({"action": "cut_staged", "files": [fp], "dest": dest})
                    _staged.append(dest)
                else:
                    _staged.append(fp)
            files = _staged
            self._start_scan()
        _used_xclip = _os_clipboard_set_files(self.win, files, cut=(mode == "cut"))
        verb = "Copiati" if mode == "copy" else "Tagliati"
        if _used_xclip:
            self._status(f"{verb} {len(files)} file — incolla con tasto destro",
                         HUD_CYAN if mode == "copy" else WARNING)
        else:
            # xclip non installato: funziona solo dentro Image Sorter —
            # vedi lo stesso avviso in Naviga (image_sorter.py).
            self._status(
                f"{verb} {len(files)} file (solo dentro Image Sorter — "
                "installa xclip per incollare anche in Nemo/Nautilus)",
                "#e74c3c")

    def _clipboard_paste(self, dest_folder):
        """Incolla i file dalla clipboard di sistema nella cartella
        indicata — funziona sia con file copiati/tagliati da qui che da
        un file manager esterno.

        A differenza di Naviga, qui un conflitto di nome si risolve da
        solo con un suffisso numerico invece di aprire un dialogo di
        scelta (Timeline non ne ha uno dedicato, e non era lo scopo di
        questa aggiunta) — non sovrascrive comunque mai in silenzio un
        file scegliendo un nome gia' occupato."""
        if not dest_folder or not os.path.isdir(dest_folder):
            return
        clip_files, is_cut = _os_clipboard_get_files(self.win)
        if not clip_files:
            return
        done, errors, pairs = 0, [], []
        for src_path in clip_files:
            if not os.path.isfile(src_path):
                continue
            dst_path = os.path.join(dest_folder, os.path.basename(src_path))
            if os.path.dirname(src_path) == dest_folder:
                continue  # stesso file, stessa cartella: niente da fare
            base, ext = os.path.splitext(os.path.basename(src_path))
            i = 1
            while os.path.exists(dst_path):
                dst_path = os.path.join(dest_folder, f"{base}_{i}{ext}")
                i += 1
            try:
                if is_cut:
                    shutil.move(src_path, dst_path)
                    if _METADATA_STORE_AVAILABLE:
                        metadata_store.rename_path(src_path, dst_path)
                else:
                    shutil.copy2(src_path, dst_path)
                done += 1
                pairs.append((src_path, dst_path))
            except Exception as ex:
                errors.append(str(ex))
        if pairs:
            try:
                from image_sorter import append_history as _ah
                _ah({
                    "action": "moved_browser_batch" if is_cut else "copied_browser",
                    "files": [o for o, d in pairs],
                    "dests": [d for o, d in pairs],
                    "dest":  dest_folder,
                    "note":  os.path.basename(dest_folder)})
            except Exception:
                pass
        verb = "spostati" if is_cut else "copiati"
        msg = f"{done} file {verb}"
        if errors:
            msg += f" — {len(errors)} errori"
        self._status(msg, SUCCESS if not errors else "#e74c3c")
        # La vista non si aggiorna da sola sui nuovi file: serve
        # rifare la scansione per vederli comparire.
        if pairs:
            self._start_scan()

    def _geotag_batch(self, src_item, others):
        """Copia le coordinate di src_item su tutti gli altri file.

        Scrive solo il blocco GPS (write_gps), non l'intero EXIF: cosi'
        autore, copyright e descrizione degli altri file restano intatti.
        Le posizioni precedenti vengono memorizzate nello storico, quindi
        l'operazione e' annullabile — comprese le foto che una posizione
        non ce l'avevano, che tornano senza.
        """
        try:
            from exif_editor import GPS_WRITABLE_EXT
        except Exception:
            self._status("piexif non installato: pip install piexif --user",
                         "#e74c3c")
            return
        lat, lon = src_item["gps"]
        writable = [i for i in others
                    if os.path.splitext(i["path"])[1].lower() in GPS_WRITABLE_EXT]
        skipped = len(others) - len(writable)
        if not writable:
            self._status("Nessun file in un formato che accetta il GPS.", "#e74c3c")
            return
        if not self._gps_confirm(
                f"Assegnare la posizione di\n"
                f"{os.path.basename(src_item['path'])}\n"
                f"{lat:.5f}, {lon:.5f}\n\na {len(writable)} file?"
                + (f"\n\n{skipped} file saltati: formato non scrivibile."
                   if skipped else "")):
            return
        self._gps_write([i["path"] for i in writable], lat, lon)

    def _gps_confirm(self, message):
        """Conferma in stile HUD, coerente con il resto del programma.

        Usa il dialogo dell'applicazione principale quando disponibile; in
        modalita' standalone (Timeline aperta da sola) non esiste nessun
        sorter, quindi si ripiega sul dialogo di sistema.
        """
        if self.sorter and hasattr(self.sorter, "_hud_yesno"):
            return self.sorter._hud_yesno(
                "Posizione GPS", message,
                yes_label="Assegna", no_label="Annulla", parent=self.win)
        # Dialogo in stile HUD come il resto del programma; il messagebox
        # di sistema resta solo come ripiego per l'uso standalone, dove
        # l'istanza principale (e i suoi dialoghi) non esiste.
        if self.sorter:
            return self.sorter._hud_yesno(
                "Posizione GPS", message,
                yes_label="Assegna", no_label="Annulla", parent=self.win)
        return messagebox.askyesno("Posizione GPS", message, parent=self.win)

    def _gps_write(self, paths, lat, lon):
        """Scrive la posizione e aggiorna subito le celle interessate."""
        try:
            from image_sorter import apply_gps_to_files
        except Exception:
            self._status("Funzione non disponibile in modalita' standalone.",
                         "#e74c3c")
            return
        done, skipped, errors, done_paths = apply_gps_to_files(paths, lat, lon)
        # Aggiorna il modello e disegna subito il pallino verde: prima la
        # posizione appena assegnata compariva solo dopo un nuovo
        # caricamento della vista. SOLO per i file su cui la scrittura e'
        # DAVVERO riuscita (done_paths) — bug corretto: prima si
        # aggiornava la cache per TUTTI i "paths" richiesti, quindi un
        # file la cui scrittura falliva in silenzio (EXIF non standard,
        # permessi...) risultava comunque "corretto" a video, mentre sul
        # disco restava la posizione vecchia. Segnalato da Carlo.
        touched = set(done_paths)
        seen = set()
        for it in self.items + self.filtered:
            if it["path"] in touched and id(it) not in seen:
                seen.add(id(it))
                it["gps"] = (lat, lon)
                self._draw_gps_dot(it)
        msg = f"Posizione assegnata a {done} file."
        if skipped:
            msg += f" {skipped} saltati (formato)."
        if errors:
            # Il primo errore per esteso, non solo il conteggio: senza,
            # non c'era modo di sapere QUALE file avesse fallito la
            # scrittura ne' perche' (segnalato da Carlo).
            msg += f" {len(errors)} errori — {errors[0]}"
        self._status(msg, SUCCESS if done else "#e74c3c")

    def _draw_item_dots(self, item, cv=None):
        """(Ri)disegna ENTRAMBI i pallini sulla miniatura gia' a video.

        Unico punto in cui vengono disegnati fuori dal primo rendering:
        ogni operazione che ridisegna la miniatura (rotazione) o cambia il
        file (conversione) deve ripassare di qui, altrimenti i pallini
        spariscono o restano quelli di prima. La posizione del pallino
        formato dipende dalla presenza di quello GPS, quindi vanno
        ridisegnati insieme e non uno per volta.
        """
        cv = cv or item.get("_canvas")
        if not cv:
            return
        try:
            if not cv.winfo_exists():
                return
            cv.delete("gps_dot")
            cv.delete("fmt_dot")
            tw = self._tw()
            r  = 6
            x0 = tw - r - 4
            y  = r + 4
            if item.get("gps"):
                cv.create_oval(x0-r, y-r, x0+r, y+r,
                               fill="#00e060", outline="#003a18", width=1,
                               tags="gps_dot")
                y += 2 * r + 4
            if is_non_jpeg_image(item["path"]):
                cv.create_oval(x0-r, y-r, x0+r, y+r,
                               fill=FMT_DOT_FILL, outline=FMT_DOT_OUTLINE,
                               width=1, tags="fmt_dot")
        except Exception:
            pass

    def _draw_gps_dot(self, item):
        """Compatibilita': ridisegna i pallini dopo un geotag."""
        self._draw_item_dots(item)

    def _gps_copy(self, item):
        """Copia negli appunti condivisi la posizione della foto."""
        g = item.get("gps")
        if not g:
            try:
                from exif_editor import read_gps
                g = read_gps(item["path"])
            except Exception:
                g = None
        if not g:
            self._status("Nessuna posizione GPS in questo file.", "#e74c3c")
            return
        try:
            from image_sorter import gps_clip_set
            gps_clip_set(g[0], g[1])
        except Exception:
            self._status("Funzione non disponibile in modalita' standalone.",
                         "#e74c3c")
            return
        self._status(f"Posizione copiata: {g[0]:.5f}, {g[1]:.5f}", SUCCESS)

    def _gps_enter(self, items):
        """Chiede le coordinate a mano (incollate da Maps) e le applica."""
        try:
            from image_sorter import parse_coords, gps_clip_set
        except Exception:
            self._status("Funzione non disponibile in modalita' standalone.",
                         "#e74c3c")
            return
        if not (self.sorter and hasattr(self.sorter, "_hud_prompt")):
            from tkinter import simpledialog as _sd
            txt = _sd.askstring(
                "Posizione GPS", "Coordinate (es. 45.452519, 9.163573):",
                parent=self.win)
        else:
            txt = self.sorter._hud_prompt(
                "Posizione GPS",
                f"Coordinate da assegnare a {len(items)} file:",
                hint="Es. 45.452519, 9.163573   —   45\u00b027'09\"N 9\u00b009'48\"E\n"
                     "Accetta anche un link di Google Maps",
                ok_label="Assegna", parent=self.win)
        if not txt:
            return
        coords = parse_coords(txt)
        if not coords:
            self._status("Coordinate non riconosciute.", "#e74c3c")
            return
        lat, lon = coords
        gps_clip_set(lat, lon)      # utile per riusarle subito altrove
        self._gps_write([i["path"] for i in items], lat, lon)

    def _gps_paste(self, items):
        """Incolla sui file indicati la posizione copiata."""
        try:
            from image_sorter import gps_clip_get
            clip = gps_clip_get()
        except Exception:
            clip = None
        if not clip:
            return
        lat, lon = clip
        if not self._gps_confirm(f"Assegnare la posizione\n{lat:.5f}, {lon:.5f}"
                                 f"\n\na {len(items)} file?"):
            return
        self._gps_write([i["path"] for i in items], lat, lon)

    def _select_group(self, group_items, additive):
        """Seleziona tutti i file di un gruppo (header del mese cliccato).

        Se il gruppo e' gia' interamente selezionato, un click normale lo
        deseleziona: cosi' lo stesso gesto serve sia a prendere sia a
        lasciare, senza dover cercare lo sfondo su cui cliccare.
        """
        paths = [i["path"] for i in group_items]
        if not paths:
            return
        # Toggle solo se la selezione corrente e' ESATTAMENTE questo
        # gruppo: se il mese fa parte di una selezione piu' ampia (es.
        # accumulata con Ctrl), un click normale deve ridurla a questo
        # mese, non svuotare tutto.
        already = (set(paths) == set(self._selected))
        if not additive:
            self._clear_sel_silent()
        # Gli item della griglia sono quelli in self.filtered: si agisce
        # su quelli, perche' sono gli unici a cui e' agganciata una cella
        # da colorare.
        wanted = set(paths)
        targets = [i for i in self.filtered if i["path"] in wanted]
        if already and not additive:
            pass                      # era tutto selezionato: resta deselezionato
        else:
            for it in targets:
                if it["path"] not in self._selected:
                    self._sel_item(it)
        self._last_sel = targets[-1] if (targets and not already) else None
        self._focus_item = targets[-1] if (targets and not already) else None
        self._update_sel_bar()
        self._update_preview_pane()

    def _clear_sel_silent(self):
        """Deseleziona tutto senza aggiornare la barra."""
        for item in self.filtered:
            if item["path"] in self._selected:
                self._desel_item(item)
        self._selected.clear()

    def _clear_sel(self):
        self._clear_sel_silent()
        self._last_sel = None

    # click fuori dalle celle (sul canvas di sfondo) → deseleziona tutto
    def _click_background(self, e):
        self._clear_sel()
        self._update_sel_bar()
        self._focus_item = None
        self._update_preview_pane()

    def _update_sel_bar(self):
        """Aggiorna la barra destinazioni in fondo e la nuvola di tag.

        Le destinazioni del preset ATTIVO (quello impostato in cima in
        Impostazioni) restano ora SEMPRE visibili, anche senza alcuna
        selezione — solo "spente" (state=disabled) in quel caso, invece
        di far collassare l'intera riga come prima: richiesto da Carlo,
        coerente con lo stesso cambiamento in Naviga (vedi
        FolderBrowser._build_sel_bar/_refresh_sel_bar_enabled in
        image_sorter.py)."""
        if not hasattr(self,"_sort_bar") or not self.sorter: return
        show_preset = (getattr(self, "_show_preset_row_var", None) is None
                       or self._show_preset_row_var.get())
        for w in self._sort_bar.winfo_children():
            w.destroy()
        if not show_preset:
            self._sort_bar.grid_remove()
        else:
            n = len(self._selected)
            self._sort_bar.grid()
            tk.Label(self._sort_bar, text=f"  {n} selezionati  ",
                     font=("TkFixedFont",9,"bold"),
                     bg=PANEL_COLOR, fg=SUCCESS).pack(side="left", padx=4)
            preset_name = self.sorter.config.get("active_preset","")
            slots = self.sorter.config["presets"].get(preset_name, {})
            state = "normal" if n > 0 else "disabled"
            for k in KEYS:
                slot = slots.get(k, {})
                dest = slot.get("path","").strip()
                if not dest: continue
                lbl   = slot.get("label", k) or k
                short = lbl[:8] + "." if len(lbl)>8 else lbl
                col   = KEY_COLORS[KEYS.index(k)]
                tk.Button(self._sort_bar, text=f"{k} {short}",
                          font=("TkFixedFont",8,"bold"),
                          bg=col, fg="white", relief="flat", padx=5,
                          activebackground=HIGHLIGHT,
                          disabledforeground=MUTED_COLOR,
                          state=state,
                          command=lambda d=dest: self._move_selected_to(d)
                          ).pack(side="left", padx=2, pady=3, ipady=2)
        self._build_tag_row()

    def _build_tag_row(self):
        """Nuvola di tag cliccabili per la selezione corrente — porting
        di FolderBrowser._build_tag_row (image_sorter.py) adattato a
        self._selected (un set, non una lista) e alla griglia Timeline.
        Un tag evidenziato (sfondo ciano) e' gia' presente sul file
        selezionato (o su TUTTI i file con selezione multipla, stesso
        principio "tutti-o-nessuno" della finestra Tag). Riusa i
        bottoni gia' creati invece di distruggerli/ricrearli ad ogni
        cambio di selezione (stesso motivo del porting originale: evita
        il lampeggio quando l'insieme dei tag in libreria non cambia)."""
        if not self.sorter or not _METADATA_STORE_AVAILABLE:
            return
        if not hasattr(self, "_tag_row_frame"):
            return
        if not self._show_tag_row_var.get():
            for w in self._tag_row_frame.winfo_children():
                w.destroy()
            self._tag_btn_refs = {}
            self._tag_row_inner = None
            self._tag_row_frame.grid_remove()
            return
        targets = list(self._selected)
        if not targets:
            for w in self._tag_row_frame.winfo_children():
                w.destroy()
            self._tag_btn_refs = {}
            self._tag_row_inner = None
            self._tag_row_frame.grid_remove()
            return
        self._tag_row_frame.grid()
        if len(targets) == 1:
            applied = set(metadata_store.get_meta(targets[0])["tags"])
        else:
            sets = [set(metadata_store.get_meta(p)["tags"]) for p in targets]
            applied = set.intersection(*sets) if sets else set()

        def _on_tag_click(tag):
            # Rilegge la selezione AL MOMENTO DEL CLICK, non quella
            # catturata da questa chiusura alla costruzione — stesso
            # difetto e stessa correzione del porting originale (i
            # bottoni riusati restano legati alla chiusura della prima
            # costruzione).
            cur_targets = list(self._selected)
            if not cur_targets:
                return
            if len(cur_targets) == 1:
                cur_applied = set(metadata_store.get_meta(cur_targets[0])["tags"])
                if tag in cur_applied:
                    metadata_store.remove_tag(cur_targets[0], tag)
                else:
                    metadata_store.add_tag(cur_targets[0], tag)
            else:
                metadata_store.bulk_toggle_tag(cur_targets, tag)
            self._update_sel_bar()

        sort_mode = self.sorter.config.get("tag_sort_mode", "alpha")
        all_tags = metadata_store.get_tags_ordered(sort_mode)

        if list(self._tag_btn_refs.keys()) != all_tags:
            for w in self._tag_row_frame.winfo_children():
                w.destroy()
            self._tag_btn_refs = {}
            self._tag_row_inner = tk.Frame(self._tag_row_frame, bg=BG_COLOR)
            self._tag_row_inner.pack(side="left", fill="both", expand=True,
                                     padx=2, pady=2)
            for t in all_tags:
                btn = tk.Button(self._tag_row_inner, text=t,
                          font=("TkFixedFont", 8),
                          relief="flat", padx=6,
                          activebackground=HIGHLIGHT, activeforeground="white",
                          command=lambda tg=t: _on_tag_click(tg))
                btn.pack(side="left", padx=2, pady=2, ipady=1)
                self._tag_btn_refs[t] = btn

        for t, btn in self._tag_btn_refs.items():
            is_on = t in applied
            btn.config(font=("TkFixedFont", 8, "bold" if is_on else "normal"),
                       bg=(HUD_CYAN if is_on else ACCENT_COLOR),
                       fg=("#0a1a2e" if is_on else TEXT_COLOR))

    def _register_moves(self, batch):
        """Registra nello storico (in memoria + persistente) un gruppo di
        spostamenti appena eseguiti.

        Voce SINGOLA se il file è uno solo, batch se sono più di uno:
        prima un singolo file spostato dalla Timeline veniva comunque
        registrato come "batch", con l'etichetta sbagliata nello Storico
        ("Spostato batch (Timeline)") e senza miniatura di anteprima,
        perché per le voci batch il campo 'dest' è una CARTELLA e non un
        file da cui generare l'anteprima.
        """
        if not self.sorter or not batch:
            return
        if len(batch) == 1:
            orig, dst = batch[0]
            self.sorter.history.append(("moved_timeline", orig, dst))
            entry = {"action": "moved_timeline", "files": [orig],
                     "dest": dst, "note": "da Timeline"}
        else:
            self.sorter.history.append(("moved_timeline_batch", batch))
            entry = {"action": "moved_timeline_batch",
                     "files": [o for o, d in batch],
                     "dests": [d for o, d in batch],
                     "dest":  os.path.dirname(batch[0][1]),
                     "note":  f"{len(batch)} file da Timeline"}
        if len(self.sorter.history) > 30:
            self.sorter.history.pop(0)
        try:
            from image_sorter import append_history as _ah
            _ah(entry)
        except Exception:
            pass

    def _move_selected_to(self, dest):
        """Sposta tutti i file selezionati nella destinazione (batch annullabile)."""
        items_to_move = [i for i in self.filtered
                         if i["path"] in self._selected]
        if not items_to_move:
            return
        batch = []   # [(orig, dest_effettivo), ...]
        for item in items_to_move:
            orig = item["path"]
            self._move_item(item, dest, skip_history=True)
            if item["path"] != orig:   # spostamento riuscito
                batch.append((orig, item["path"]))
        # Registra tutto come un'unica voce annullabile (singola o batch)
        self._register_moves(batch)
        self._selected.clear()
        self._update_sel_bar()

    def _get_flat_items(self):
        """Lista piatta di tutti gli item visibili in ordine griglia."""
        return self.filtered

    def _ncols(self):
        cw = max(self._canvas.winfo_width(), 600)
        return max(1, (cw - 24) // (self._tw() + 8))

    def _on_arrow(self, e):
        """Freccia senza Shift: sposta selezione su singolo item."""
        items = self._get_flat_items()
        if not items: return
        ncols = self._ncols()
        ks = e.keysym
        delta = {"Right":1,"Left":-1,"Down":ncols,"Up":-ncols}.get(ks,0)
        if delta == 0: return
        cur = getattr(self,"_focus_item",None)
        paths = [i["path"] for i in items]
        cur_path = cur["path"] if cur and cur["path"] in paths else None
        idx = paths.index(cur_path) if cur_path else 0
        new_idx = max(0, min(len(items)-1, idx+delta))
        new_item = items[new_idx]
        self._clear_sel()
        self._toggle_sel(new_item)
        self._focus_item = new_item
        self._last_sel   = new_item["path"]
        self._update_sel_bar()
        # Scroll diretto tramite winfo_rooty (non dipende da lazy loading)
        self._scroll_by_abs(new_item)

    def _on_shift_arrow(self, e):
        """Shift+freccia: estende la selezione mantenendo anchor fisso."""
        items = self._get_flat_items()
        if not items: return
        ncols = self._ncols()
        ks = e.keysym.replace("Shift_","")
        delta = {"Right":1,"Left":-1,"Down":ncols,"Up":-ncols}.get(ks,0)
        if delta == 0: return
        paths = [i["path"] for i in items]
        anchor = getattr(self,"_last_sel",None)
        focus  = getattr(self,"_focus_item",None)
        anchor_path = anchor if anchor in paths else paths[0]
        focus_path  = focus["path"] if focus and focus["path"] in paths else anchor_path
        anchor_idx  = paths.index(anchor_path)
        focus_idx   = paths.index(focus_path)
        new_idx = max(0, min(len(items)-1, focus_idx+delta))
        new_item = items[new_idx]
        self._focus_item = new_item
        # Aggiorna solo le celle che cambiano
        old_set = set(paths[min(anchor_idx,focus_idx):max(anchor_idx,focus_idx)+1])
        new_set = set(paths[min(anchor_idx,new_idx):max(anchor_idx,new_idx)+1])
        for p in old_set - new_set:
            item = next((i for i in items if i["path"]==p),None)
            if item: self._desel_item(item)
        for p in new_set - old_set:
            item = next((i for i in items if i["path"]==p),None)
            if item: self._sel_item(item)
        self._update_sel_bar()
        self._scroll_to_item(new_item)

    def _sel_item(self, item):
        """Evidenzia la selezione con un BORDO attorno alla sola
        miniatura — non piu' uno sfondo cambiato sulla cella intera
        (colorava anche gli spazi di padding attorno a nome file e riga
        rating, stesso difetto gia' corretto in Naviga con
        _set_cell_selected — qui era rimasto lo schema vecchio, mai
        allineato). Stesso colore verde di Naviga (#2ecc71), non piu'
        bianco, per coerenza visiva fra i due programmi — segnalato da
        Carlo."""
        self._selected.add(item["path"])
        cv = item.get("_canvas")
        if cv and cv.winfo_exists():
            try:
                cv.config(highlightthickness=4, highlightbackground="#2ecc71",
                         highlightcolor="#2ecc71")
            except Exception:
                pass

    def _desel_item(self, item):
        self._selected.discard(item["path"])
        cv = item.get("_canvas")
        src_color = item.get("_src_color")
        if cv and cv.winfo_exists():
            try:
                if src_color:
                    # Solo il bordo sottile del canvas torna al colore
                    # cartella (era cosi' anche alla creazione della
                    # cella, prima di ogni selezione).
                    cv.config(highlightthickness=3, highlightbackground=src_color)
                else:
                    cv.config(highlightthickness=0)
            except Exception: pass

    def _scroll_by_abs(self, item):
        """Scrolla usando coordinate assolute — funziona sempre."""
        cell = item.get("_cell")
        if not cell or not cell.winfo_exists(): return
        def _do():
            try:
                # Posizione assoluta cella vs canvas
                cell_abs  = cell.winfo_rooty()
                canvas_abs= self._canvas.winfo_rooty()
                canvas_h  = self._canvas.winfo_height()
                inner_h   = max(self._inner.winfo_height(), 1)
                if inner_h <= canvas_h: return
                cell_h    = cell.winfo_height()
                # posizione relativa al canvas visibile
                rel_y = cell_abs - canvas_abs
                if rel_y < 8:
                    frac = max(0.0,
                        (self._canvas.yview()[0]*inner_h + rel_y - 8) / inner_h)
                    self._canvas.yview_moveto(frac)
                elif rel_y + cell_h > canvas_h - 8:
                    frac = min(1.0,
                        (self._canvas.yview()[0]*inner_h + rel_y + cell_h - canvas_h + 8) / inner_h)
                    self._canvas.yview_moveto(frac)
            except Exception: pass
        self.win.after(1, _do)

    def _scroll_to_item(self, item):
        """Scrolla il canvas per rendere visibile la cella.
        Se la cella non è ancora nel lazy loading, carica le pagine mancanti
        senza distruggere quelle esistenti.
        """
        cell = item.get("_cell")
        if not cell or not cell.winfo_exists():
            # Cella non ancora caricata — aggiungi pagine fino a trovarla
            try:
                idx = self.filtered.index(item)
            except ValueError:
                return
            needed_page = idx // PAGE_SIZE
            while self._page < needed_page:
                next_start = (self._page + 1) * PAGE_SIZE
                if self._view_mode == "timeline":
                    self._render_timeline(next_start, next_start + PAGE_SIZE)
                else:
                    self._render_grid(next_start, next_start + PAGE_SIZE)
            # Riprova dopo che tkinter ha costruito i widget
            self.win.after(30, lambda: self._scroll_to_item(item))
            return
        # Cella esiste: calcola posizione e scrolla
        def _do(c=cell):
            if not c or not c.winfo_exists(): return
            try:
                inner_h  = max(self._inner.winfo_height(), 1)
                canvas_h = max(self._canvas.winfo_height(), 1)
                if inner_h <= canvas_h: return
                cell_y = c.winfo_y()
                cell_h = max(c.winfo_height(), 10)
                view_top = self._canvas.yview()[0] * inner_h
                view_bot = view_top + canvas_h
                if cell_y < view_top + 8:
                    self._canvas.yview_moveto(
                        max(0.0, (cell_y - 8) / inner_h))
                elif cell_y + cell_h > view_bot - 8:
                    self._canvas.yview_moveto(
                        min(1.0, (cell_y + cell_h - canvas_h + 8) / inner_h))
            except Exception: pass
        self.win.after(1, _do)

    def _fill_visible(self):
        """Carica pagine aggiuntive finché il contenuto riempie la vista
        o non ci sono più item da caricare.
        Necessario quando la prima pagina è troppo corta per riempire lo schermo.
        """
        if not self.filtered or not self.win.winfo_exists(): return
        canvas_h = self._canvas.winfo_height()
        inner_h  = self._inner.winfo_height()
        next_start = (self._page + 1) * PAGE_SIZE
        if next_start >= len(self.filtered): return
        # Se il contenuto non riempie ancora la finestra, carica altra pagina
        if inner_h < canvas_h * 1.5:
            self._page += 1
            if self._view_mode == "timeline":
                self._render_timeline(next_start, next_start + PAGE_SIZE)
            else:
                self._render_grid(next_start, next_start + PAGE_SIZE)
            # Ricontrolla dopo che i widget sono stati creati
            self.win.after(150, self._fill_visible)

    def _on_canvas_resize(self, e):
        """Riposiziona le colonne se la larghezza è cambiata significativamente."""
        new_w = e.width
        old_w = getattr(self, "_last_canvas_w", 0)
        if abs(new_w - old_w) > (self._tw() + 8):  # cambia almeno una colonna
            self._last_canvas_w = new_w
            if self.filtered:
                self.win.after(150, self._render)  # debounce
                return
        self._maybe_load_more()

    def _maybe_load_more(self):
        """Lazy loading: carica altra pagina quando si avvicina al fondo."""
        if not self.filtered: return
        yv = self._canvas.yview()
        if yv[1] > 0.85:
            next_start = (self._page + 1) * PAGE_SIZE
            if next_start < len(self.filtered):
                self._page += 1
                if self._view_mode == "timeline":
                    self._render_timeline(next_start,
                                          next_start + PAGE_SIZE)
                else:
                    self._render_grid(next_start,
                                      next_start + PAGE_SIZE)

    # ── Azioni sui file ───────────────────────────────────────────────────────
    def _open_file(self, path):
        """Naviga al file nel sorter principale, o apre col sistema.

        Un video lancia SUBITO un player esterno invece di navigare al
        file nel visualizzatore principale, che per un video mostra solo
        un fotogramma statico — richiesto da Carlo, stesso trattamento
        del comando "Apri" di Naviga (FolderBrowser._open_or_play)."""
        ext = os.path.splitext(path)[1].lower()
        if ext in VID_EXT:
            if not _launch_video_player(path) and self.sorter:
                self.sorter._hud_alert("Player mancante",
                    "Nessun player video trovato.\n"
                    "Installa mpv o vlc: sudo apt install mpv",
                    parent=self.win)
            return
        if self.sorter:
            try:
                folder = os.path.dirname(path)
                # Carica la cartella nel sorter e naviga al file
                if self.sorter.source_folder != folder:
                    self.sorter.source_folder = folder
                    self.sorter.images = self.sorter._load_images()
                if path in self.sorter.images:
                    self.sorter.current_index = self.sorter.images.index(path)
                else:
                    self.sorter.current_index = 0
                self.sorter.root.after(0, self.sorter._show_image)
                self.sorter.root.lift()
                self.sorter.root.focus_force()
                # Focus sulla canvas per ricevere i tasti freccia
                def _give_focus():
                    try: self.sorter.canvas.focus_set()
                    except Exception: pass
                self.sorter.root.after(100, _give_focus)
                return
            except Exception:
                pass
        try:
            subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    def _context_menu(self, event, item):
        # Chiudi sempre il menu precedente senza logica di toggle
        prev = getattr(self, "_cur_menu", None)
        if prev:
            try: prev.unpost(); prev.destroy()
            except Exception: pass
        self._cur_menu = None
        self._cur_menu_item = item

        # Se l'item cliccato è nella selezione, il menu agisce su tutti i selezionati
        # altrimenti agisce solo sull'item cliccato (senza cambiare la selezione)
        if item["path"] in self._selected and len(self._selected) > 1:
            targets = [i for i in self.filtered if i["path"] in self._selected]
            multi = True
        else:
            targets = [item]
            multi = False

        n = len(targets)
        menu = tk.Menu(self.win, tearoff=0, bg=PANEL_COLOR, fg=TEXT_COLOR,
                       activebackground=HIGHLIGHT, activeforeground="white",
                       font=("TkFixedFont",9))
        self._cur_menu = menu

        # Intestazione
        if multi:
            menu.add_command(label=f"{n} file selezionati", state="disabled",
                             font=("TkFixedFont",8,"bold"))
        else:
            fname = os.path.basename(item["path"])
            short = fname if len(fname)<=32 else fname[:30]+".."
            menu.add_command(label=short, state="disabled",
                             font=("TkFixedFont",8,"bold"))
        menu.add_separator()

        # Apri / Apri cartella — solo su singolo
        if not multi:
            menu.add_command(label="Apri",
                             command=lambda: self._open_file(item["path"]))
            menu.add_command(label="Apri cartella",
                             command=lambda: open_in_filemanager(
                                 os.path.dirname(item["path"])))
            menu.add_command(label="Copia percorso",
                             command=lambda: (
                                 self.win.clipboard_clear(),
                                 self.win.clipboard_append(item["path"])))
            menu.add_separator()
            menu.add_command(label="Rinomina...",
                             command=lambda: self._rename_item(item))

        # Copia/Taglia/Incolla — fuori dal blocco "solo singolo" qui
        # sopra: funzionano anche su una selezione multipla, come in
        # Naviga. Mancava del tutto in Timeline, segnalato da Carlo.
        menu.add_separator()
        _target_paths = [t["path"] for t in targets]
        # Tag: come Copia/Taglia, funziona anche su selezione multipla
        # (bulk_toggle_tag). Solo se Timeline e' stata aperta agganciata
        # al programma principale (self.sorter None se avviata da sola).
        if self.sorter:
            menu.add_command(label="Tag...",
                             command=lambda: self.sorter._open_tag_window(
                                 item["path"], targets=_target_paths))
        menu.add_command(label="Copia",
                         command=lambda: self._clipboard_set(_target_paths, "copy"))
        menu.add_command(label="Taglia",
                         command=lambda: self._clipboard_set(_target_paths, "cut"))
        _clip_files, _clip_is_cut = _os_clipboard_get_files(self.win)
        if _clip_files:
            _mode_lbl = "Sposta" if _clip_is_cut else "Copia"
            menu.add_command(
                label=f"Incolla qui ({_mode_lbl} {len(_clip_files)} file)",
                command=lambda: self._clipboard_paste(
                    os.path.dirname(item["path"])))

        # Ruota — su tutti i selezionati (solo immagini)
        rot_targets = [i for i in targets
                       if os.path.splitext(i["path"])[1].lower()
                       in {".jpg",".jpeg",".png",".bmp",".tiff",".tif",".webp"}]
        if rot_targets:
            lbl_cw  = f"Ruota 90° orario  ({len(rot_targets)})" if multi else "Ruota 90° orario  [C]"
            lbl_ccw = f"Ruota 90° antiorario  ({len(rot_targets)})" if multi else "Ruota 90° antiorario  [A]"
            menu.add_command(label=lbl_cw,
                             command=lambda t=rot_targets: [self._rotate_item(i, 90) for i in t])
            menu.add_command(label=lbl_ccw,
                             command=lambda t=rot_targets: [self._rotate_item(i, -90) for i in t])

        # EXIF — su tutti i selezionati compatibili
        # Solo i formati che piexif sa RISCRIVERE (JPEG e WebP): su TIFF e
        # HEIC il salvataggio fallisce in silenzio. Insieme condiviso con
        # image_sorter per non avere due elenchi che divergono.
        try:
            from image_sorter import EXIF_WRITE_EXT as _EXW
        except Exception:
            _EXW = {".jpg", ".jpeg", ".webp"}
        exif_targets = [i for i in targets
                        if os.path.splitext(i["path"])[1].lower() in _EXW]
        if _EXIF_EDITOR_OK and exif_targets:
            menu.add_separator()
            lbl_exif = (f"Modifica EXIF  ({len(exif_targets)} file)..."
                        if multi else "Modifica EXIF...")
            menu.add_command(label=lbl_exif,
                             command=lambda t=exif_targets: _open_exif_editor_db(
                                 self.win, [i["path"] for i in t]))

        # Converti — su tutti i selezionati compatibili
        conv_targets = [i for i in targets
                        if os.path.splitext(i["path"])[1].lower()
                        in {".webp",".png",".bmp",".tiff",".tif",".gif",".jpg",".jpeg"}]
        if conv_targets:
            menu.add_separator()
            jpg_targets = [i for i in conv_targets
                           if os.path.splitext(i["path"])[1].lower() != ".jpg"]
            if jpg_targets:
                lbl = f"Converti in JPG  ({len(jpg_targets)})" if multi else "Converti in JPG"
                menu.add_command(label=lbl,
                                 command=lambda t=jpg_targets: [self._convert_item(i,"jpg") for i in t])
            lbl_gif = f"Converti in GIF  ({len(conv_targets)})" if multi else "Converti in GIF"
            menu.add_command(label=lbl_gif,
                             command=lambda t=conv_targets: [self._convert_item(i,"gif") for i in t])

        # Mappa GPS — solo singolo
        if not multi and item.get("gps"):
            menu.add_separator()
            menu.add_command(label="Mostra su mappa",
                             command=lambda: build_map([item]))

        # Geotag di gruppo: prende la posizione della foto su cui si e'
        # cliccato e la assegna a tutte le altre selezionate. Utile per
        # foto scattate nello stesso posto da una macchina senza GPS.
        # Compare solo se la foto cliccata una posizione ce l'ha davvero.
        # La voce si basa sulla SELEZIONE, non su "multi": prima compariva
        # solo se la foto cliccata faceva parte della selezione, quindi
        # cliccando sulla foto con il GPS per usarla come sorgente — il
        # gesto piu' naturale — non compariva mai.
        # Sorgente: la foto cliccata se ha una posizione, altrimenti, se
        # fra i selezionati ce n'e' UNA SOLA con la posizione, quella.
        _sel_paths = set(self._selected)
        _src = item if item.get("gps") else None
        if _src is None:
            _con_gps = [i for i in self.filtered
                        if i["path"] in _sel_paths and i.get("gps")]
            if len(_con_gps) == 1:
                _src = _con_gps[0]
        if _src is not None:
            others = [i for i in self.filtered
                      if i["path"] in _sel_paths and i["path"] != _src["path"]]
            if others:
                _lbl = ("Assegna questa posizione ai selezionati  "
                        f"({len(others)})" if _src is item else
                        "Assegna la posizione di "
                        f"{os.path.basename(_src['path'])[:24]} ai selezionati  "
                        f"({len(others)})")
                menu.add_separator()
                menu.add_command(
                    label=_lbl,
                    command=lambda it=_src, o=list(others): self._geotag_batch(it, o))

        # Copia / incolla della posizione GPS — appunti condivisi con Naviga
        try:
            from exif_editor import GPS_WRITABLE_EXT as _GWE
            from image_sorter import gps_clip_get as _gcg
        except Exception:
            _GWE, _gcg = None, None
        if _GWE:
            _gps_t = [i for i in targets
                      if os.path.splitext(i["path"])[1].lower() in _GWE]
            _sep = False
            if not multi and item.get("gps"):
                menu.add_separator(); _sep = True
                menu.add_command(label="Copia posizione GPS",
                                 command=lambda it=item: self._gps_copy(it))
            if _gcg and _gcg() and _gps_t:
                if not _sep:
                    menu.add_separator(); _sep = True
                _lbl_p = (f"Incolla posizione GPS  ({len(_gps_t)})"
                          if len(_gps_t) > 1 else "Incolla posizione GPS")
                menu.add_command(
                    label=_lbl_p,
                    command=lambda t=list(_gps_t): self._gps_paste(t))
            if _gps_t:
                if not _sep:
                    menu.add_separator()
                _lbl_i = (f"Inserisci posizione GPS...  ({len(_gps_t)})"
                          if len(_gps_t) > 1 else "Inserisci posizione GPS...")
                menu.add_command(
                    label=_lbl_i,
                    command=lambda t=list(_gps_t): self._gps_enter(t))

        # Valutazione — stesso meccanismo di image_sorter.py (menu tasto
        # destro in Naviga sulle miniature). Mancava qui: la Timeline ha un
        # menu contestuale proprio, indipendente da _thumb_context_menu().
        # Riga riservata + overlay sovrapposto (add_rating_row_reserve /
        # attach_rating_overlay, importate da image_sorter.py): stelle
        # visibili subito dentro il menu, non un popup separato da aprire
        # con un click in piu' — vedi il commento in image_sorter.py
        # _thumb_context_menu sul perche' ne' cascata ne' columnbreak
        # andavano bene per questo.
        try:
            from image_sorter import _METADATA_STORE_AVAILABLE as _MS_OK
        except Exception:
            _MS_OK = False
        _rating_row_idx = None
        if _MS_OK:
            menu.add_separator()
            _rt_paths = [i["path"] for i in targets]
            _rating_row_idx = add_rating_row_reserve(menu)

        # Cestino — su tutti
        menu.add_separator()
        lbl_trash = f"Sposta nel cestino  ({n})" if multi else "Sposta nel cestino"
        menu.add_command(label=lbl_trash,
                         command=lambda t=targets: self._trash_items(t))

        # Preset destinazione — su tutti
        if self.sorter:
            menu.add_separator()
            preset_name = self.sorter.config.get("active_preset","")
            slots = self.sorter.config["presets"].get(preset_name, {})
            for k in KEYS:
                slot = slots.get(k, {})
                dest = slot.get("path","").strip()
                if not dest: continue
                lbl  = slot.get("label", k) or k
                cnt  = f" ({n})" if multi else ""
                menu.add_command(
                    label=f"  {k}  →  {lbl}{cnt}",
                    command=lambda d=dest, t=targets: [self._move_item(i, d) for i in t])

        # Proprietà — solo singolo
        if not multi:
            menu.add_separator()
            menu.add_command(label="Proprietà...",
                             command=lambda: self._show_properties(item["path"]))
            # Ripristina — solo se file nello storico recente
            if self.sorter:
                from image_sorter import find_history_entry as _fhe
                _hist = _fhe(item["path"], days=10)
                if _hist:
                    _rlbl = {
                        "moved":                "Ripristina (spostato)",
                        "moved_browser":        "Ripristina (spostato)",
                        "moved_timeline":       "Ripristina (spostato)",
                        "moved_timeline_batch": "Ripristina batch",
                        "cropped":              "Ripristina originale (ritagliato)",
                    }.get(_hist.get("action",""), "Ripristina")
                    menu.add_separator()
                    menu.add_command(label=_rlbl,
                                     command=lambda p=item["path"]:
                                         self.sorter._ripristina_file(p))

        def _cleanup(e=None):
            self._cur_menu = None
            self._cur_menu_item = None
        menu.bind("<Unmap>", lambda e: _cleanup())

        # Rete di sicurezza aggiuntiva per la chiusura al click fuori E al
        # cambio di focus (es. Alt-Tab su un'altra applicazione): il solo
        # click-fuori-dall'app non basta, perché passando a un'altra
        # finestra non si genera nessun ButtonPress dentro Timeline —
        # serve anche <FocusOut> sulla finestra stessa. Bind mirati sulla
        # sola finestra Timeline (self.win), rimossi in modo preciso
        # tramite i rispettivi funcid — NON bind_all/unbind_all, che sono
        # globali a tutta l'applicazione e rimuoverebbero anche binding
        # di altre finestre.
        _closed = [False]
        _bid = [None]
        _bid_focus = [None]
        def _unbind_all_extra():
            try: self.win.unbind("<ButtonPress>", _bid[0])
            except Exception: pass
            try: self.win.unbind("<FocusOut>", _bid_focus[0])
            except Exception: pass
            try:
                if _bid_root[0] and self.sorter and self.sorter.root.winfo_exists():
                    self.sorter.root.unbind("<ButtonPress>", _bid_root[0])
            except Exception: pass
        import time as _time
        _open_ts = [_time.monotonic()]
        _bid_root = [None]

        def _close_extra(e):
            if _closed[0]:
                return
            try:
                wx, wy = menu.winfo_rootx(), menu.winfo_rooty()
                ww, wh = menu.winfo_width(), menu.winfo_height()
                if wx <= e.x_root <= wx+ww and wy <= e.y_root <= wy+wh:
                    return   # click dentro il menu: lascialo gestire a tk
            except Exception:
                pass
            _closed[0] = True
            _unbind_all_extra()
            try:
                if menu.winfo_exists(): menu.unpost()
            except Exception: pass
            _cleanup()
        def _do_close():
            _closed[0] = True
            _unbind_all_extra()
            try:
                if menu.winfo_exists(): menu.unpost()
            except Exception: pass
            _cleanup()

        # Sorveglianza del focus mentre il menu e' aperto.
        # Perche' non basta l'evento <FocusOut> della finestra: quello
        # scatta UNA sola volta, quando il menu si apre e prende il focus.
        # Da quel momento la finestra Timeline il focus non ce l'ha piu',
        # quindi cliccando su un'altra applicazione o sulla barra di
        # sistema non arriva nessun nuovo FocusOut e il menu restava
        # aperto. Si controlla quindi periodicamente DOVE si trova il
        # focus, finche' il menu e' visibile.
        # Sorveglianza mentre il menu e' aperto.
        # Il controllo sul solo focus non bastava: su questo window manager
        # focus_displayof() non risulta mai "dentro l'applicazione" mentre
        # il menu e' visibile, quindi la condizione di chiusura non
        # scattava mai e il menu restava aperto cambiando applicazione.
        # Si guarda percio' DOVE si trova il puntatore: winfo_containing()
        # restituisce un widget solo se il punto e' sopra una finestra di
        # questo programma, None se e' sopra un'altra applicazione o la
        # barra di sistema. Due letture consecutive fuori (400ms) chiudono:
        # una sola potrebbe essere un passaggio casuale del mouse.
        _outside = [0]
        def _poll_focus():
            if _closed[0]:
                return
            try:
                if not menu.winfo_exists() or not menu.winfo_ismapped():
                    return
                if _time.monotonic() - _open_ts[0] > 0.35:
                    px, py = self.win.winfo_pointerxy()
                    over   = self.win.winfo_containing(px, py)
                    if over is None:
                        _outside[0] += 1
                        if _outside[0] >= 2:
                            _do_close()
                            return
                    else:
                        _outside[0] = 0
            except Exception:
                pass
            try:
                self.win.after(200, _poll_focus)
            except Exception:
                pass

        def _close_on_focus_out(e=None):
            """Chiude il menu quando il focus lascia DAVVERO l'applicazione.

            Mostrare il menu fa perdere il focus alla finestra Timeline,
            perche' il focus passa al menu stesso: senza distinguere i due
            casi, il menu si chiudeva da solo 4-6ms dopo essere apparso —
            il tasto destro sembrava semplicemente non funzionare.
            Si verifica quindi DOVE e' finito il focus, con un attimo di
            ritardo perche' al momento dell'evento non e' ancora assegnato:
            focus_displayof() restituisce il widget se il focus e' rimasto
            dentro l'applicazione (il menu), None se e' andato altrove
            (Alt-Tab, altra finestra) — che e' l'unico caso in cui chiudere.
            """
            if _closed[0]:
                return
            def _check():
                if _closed[0]:
                    return
                # Soglia minima di sicurezza: non e' possibile verificare da
                # qui il comportamento esatto del focus su ogni window
                # manager X11, quindi una chiusura immediatamente successiva
                # all'apertura viene comunque scartata.
                if _time.monotonic() - _open_ts[0] < 0.35:
                    return
                try:
                    if self.win.focus_displayof() is not None:
                        return      # focus ancora dentro l'app: e' il menu
                except Exception:
                    return          # nel dubbio, lascia il menu aperto
                _do_close()
            try:
                self.win.after(150, _check)
            except Exception:
                pass
        def _on_menu_unmap(e=None):
            if _closed[0]:
                return
            _closed[0] = True
            _unbind_all_extra()
        self.win.after(250, _poll_focus)
        _bid[0] = self.win.bind("<ButtonPress>", _close_extra, add="+")
        # Il binding sulla sola finestra Timeline non vedeva i click sulla
        # finestra principale (e' un altro toplevel): il menu restava
        # aperto cliccando li'. Si lega anche alla radice dell'app.
        try:
            if self.sorter and self.sorter.root.winfo_exists():
                _bid_root[0] = self.sorter.root.bind(
                    "<ButtonPress>", _close_extra, add="+")
        except Exception:
            pass
        _bid_focus[0] = self.win.bind("<FocusOut>", _close_on_focus_out, add="+")
        menu.bind("<Unmap>", lambda e: (_cleanup(), _on_menu_unmap()), add="+")
        _post_menu(menu, event.x_root, event.y_root, self.win)
        if _rating_row_idx is not None:
            # on_change aggiorna sia le miniature dei file coinvolti sia,
            # se fra loro c'e' quello mostrato in anteprima, il pannello
            # anteprima stesso — prima restava con le stelle vecchie
            # finche' non si cambiava immagine (segnalato da Carlo).
            attach_rating_overlay(menu, _rating_row_idx, _rt_paths,
                                  on_change=lambda its=list(targets): (
                                      [self._refresh_rating_row(it) for it in its],
                                      self._refresh_preview_rating()))

    def _show_properties(self, filepath):
        """Popup proprieta file — withdraw/deiconify evita scatto visivo."""
        if not os.path.isfile(filepath): return
        try:
            import datetime
            stat = os.stat(filepath)
            size_kb = stat.st_size / 1024
            size_str = (f"{size_kb/1024:.1f} MB"
                        if size_kb > 1024 else f"{size_kb:.1f} KB")
            mtime = datetime.datetime.fromtimestamp(
                stat.st_mtime).strftime("%d/%m/%Y %H:%M")
            ctime = datetime.datetime.fromtimestamp(
                stat.st_ctime).strftime("%d/%m/%Y %H:%M")
            shot = ""; camera = ""; dims = ""
            try:
                with Image.open(filepath) as im:
                    dims = f"{im.width} x {im.height} px"
                    exif = im._getexif() or {} if hasattr(im,"_getexif") else {}
                    for tag,val in exif.items():
                        name = ExifTags.TAGS.get(tag,"")
                        if name=="DateTimeOriginal": shot=str(val)[:16].replace(":","/",2)
                        if name=="Model": camera=str(val).strip()
            except Exception: pass
            fname = os.path.basename(filepath)
            ext   = os.path.splitext(fname)[1].lower()
            rows = [("Nome",fname),
                    ("Cartella",os.path.dirname(filepath)),
                    ("Estensione",ext),
                    ("Dimensione",size_str)]
            if dims:   rows.append(("Risoluzione",dims))
            if shot:   rows.append(("Data scatto",shot))
            if camera: rows.append(("Fotocamera",camera))
            rows.append(("Ultima modifica",mtime))
            rows.append(("Creato",ctime))
            dlg = tk.Toplevel(self.win)
            _hud(dlg)      # mancava il bordo ciano delle altre finestre
            dlg.withdraw()
            dlg.title("Proprieta")
            dlg.configure(bg=BG_COLOR)
            dlg.resizable(False, False)
            dlg.transient(self.win)
            tk.Label(dlg,text=fname,font=("TkFixedFont",10,"bold"),
                     bg=BG_COLOR,fg=HUD_CYAN
                     ).grid(row=0,column=0,columnspan=2,
                            padx=20,pady=(14,6),sticky="w")
            tk.Frame(dlg,bg=ACCENT_COLOR,height=1
                     ).grid(row=1,column=0,columnspan=2,
                            sticky="ew",padx=20,pady=(0,8))
            for ri,(lbl,val) in enumerate(rows,start=2):
                tk.Label(dlg,text=lbl+":",
                         font=("TkFixedFont",8,"bold"),
                         bg=BG_COLOR,fg=MUTED_COLOR,anchor="e"
                         ).grid(row=ri,column=0,padx=(20,8),pady=2,sticky="e")
                e=tk.Entry(dlg,font=("TkFixedFont",8),
                           bg=BG_COLOR,fg=HUD_CYAN,relief="flat",bd=4,
                           width=40,readonlybackground=BG_COLOR)
                e.insert(0,val); e.config(state="readonly")
                e.grid(row=ri,column=1,padx=(0,20),pady=2,sticky="ew")
            ri_btn=len(rows)+2
            tk.Frame(dlg,bg=ACCENT_COLOR,height=1
                     ).grid(row=ri_btn,column=0,columnspan=2,
                            sticky="ew",padx=20,pady=(8,0))
            tk.Button(dlg,text="Chiudi",
                      font=("TkFixedFont",9,"bold"),
                      bg=ACCENT_COLOR,fg=TEXT_COLOR,relief="flat",
                      padx=24,command=dlg.destroy
                      ).grid(row=ri_btn+1,column=0,columnspan=2,
                             pady=(8,14))
            dlg.bind("<Return>",lambda e: dlg.destroy())
            dlg.bind("<Escape>",lambda e: dlg.destroy())
            dlg.update_idletasks()
            px=self.win.winfo_rootx(); py=self.win.winfo_rooty()
            pw=self.win.winfo_width(); ph=self.win.winfo_height()
            dw=dlg.winfo_reqwidth(); dh=dlg.winfo_reqheight()
            dlg.geometry(f"{dw}x{dh}+{px+(pw-dw)//2}+{py+(ph-dh)//2}")
            dlg.deiconify()
            dlg.grab_set()
        except Exception as ex:
            print(f"Proprieta errore: {ex}")

    def _rename_item(self, item):
        """Dialog rinomina file."""
        old_path = item["path"]
        old_name = os.path.basename(old_path)
        base, ext = os.path.splitext(old_name)
        dlg = tk.Toplevel(self.win)
        _hud(dlg)      # mancava il bordo ciano delle altre finestre
        dlg.title("Rinomina")
        dlg.configure(bg=BG_COLOR)
        dlg.resizable(False, False)
        dlg.transient(self.win)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        tk.Label(dlg, text="Nuovo nome:",
                 font=("TkFixedFont",9), bg=BG_COLOR,
                 fg=TEXT_COLOR).pack(padx=16, pady=(14,4))
        var = tk.StringVar(value=base)
        entry = tk.Entry(dlg, textvariable=var, width=36,
                         font=("TkFixedFont",10),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR, relief="flat")
        entry.pack(padx=16, pady=4, ipady=4)
        entry.select_range(0, tk.END)
        entry.focus_set()
        def _save(e=None):
            new_base = var.get().strip()
            if not new_base: return
            new_path = os.path.join(os.path.dirname(old_path), new_base + ext)
            if new_path == old_path: dlg.destroy(); return
            if os.path.exists(new_path):
                self.sorter._hud_alert("Errore rinomina", "Nome già esistente.", parent=dlg) if self.sorter else None
                return
            try:
                os.rename(old_path, new_path)
                if _METADATA_STORE_AVAILABLE:
                    metadata_store.rename_path(old_path, new_path)
                item["path"] = new_path
                # Aggiorna label nella cella
                cell = item.get("_cell")
                if cell and cell.winfo_exists():
                    for w in cell.winfo_children():
                        if isinstance(w, tk.Label):
                            try:
                                w.config(text=tk_safe(
                                    os.path.basename(new_path)[:22]))
                            except Exception: pass
                            break
                dlg.destroy()
            except Exception as ex:
                self.sorter._hud_alert("Errore rinomina", str(ex), parent=dlg) if self.sorter else None
        entry.bind("<Return>",   _save)
        entry.bind("<KP_Enter>", _save)
        tk.Button(dlg, text="Rinomina", font=("TkFixedFont",9,"bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=14,
                  command=_save).pack(side="left", padx=12, pady=12, ipady=3)
        tk.Button(dlg, text="Annulla", font=("TkFixedFont",9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=14,
                  command=dlg.destroy).pack(side="right", padx=12, pady=12, ipady=3)
        dlg.update_idletasks()
        x = self.win.winfo_rootx() + (self.win.winfo_width()-dlg.winfo_reqwidth())//2
        y = self.win.winfo_rooty() + (self.win.winfo_height()-dlg.winfo_reqheight())//2
        dlg.geometry(f"+{x}+{y}")
        dlg.grab_set()

    def _rotate_item(self, item, degrees):
        """Ruota immagine in thread separato e aggiorna la thumbnail."""
        def _do():
            try:
                img = Image.open(item["path"])
                rotated = img.rotate(-degrees, expand=True)
                fmt = img.format or "JPEG"
                kw = {}
                if fmt in ("JPEG","JPG"):
                    kw = {"quality":95,"subsampling":0}
                rotated.save(item["path"], format=fmt, **kw)
                # Invalida cache e ricarica thumbnail
                key = (item["path"], self._tw(), self._th())
                _thumb_cache.pop(key, None)
                cell = item.get("_cell")
                if cell:
                    for w in cell.winfo_children():
                        if isinstance(w, tk.Canvas):
                            new_img = make_thumb(item["path"])
                            if new_img:
                                def _upd(cv=w, i=new_img, it=item):
                                    if cv.winfo_exists():
                                        # delete("all") cancella TUTTO il
                                        # canvas, pallini inclusi: vanno
                                        # ridisegnati dopo l'immagine,
                                        # altrimenti ruotando un PNG
                                        # l'indicatore ambra spariva.
                                        cv.delete("all")
                                        cv.create_image(
                                            self._tw()//2, self._th()//2,
                                            anchor="center", image=i)
                                        cv._img = i
                                        self._draw_item_dots(it, cv)
                                self.win.after(0, _upd)
                            break
            except Exception as ex:
                self.win.after(0, lambda e=ex: self.sorter._hud_alert(
                    "Errore rotazione", str(e), parent=self.win) if self.sorter else None)
        threading.Thread(target=_do, daemon=True).start()

    def _convert_item(self, item, fmt):
        """Converte immagine in JPG o GIF."""
        old_path = item["path"]
        new_path = os.path.splitext(old_path)[0] + f".{fmt}"
        if os.path.exists(new_path):
            if not (self.sorter._hud_yesno("File esistente",
                    f"Sovrascrivere {os.path.basename(new_path)}?",
                    yes_label="Sovrascrivi", no_label="Annulla",
                    parent=self.win) if self.sorter else False): return
        def _do():
            try:
                img = Image.open(old_path)
                if fmt == "jpg":
                    if img.mode in ("RGBA","P","LA"):
                        bg = Image.new("RGB", img.size, (255,255,255))
                        if img.mode == "P": img = img.convert("RGBA")
                        bg.paste(img, mask=img.split()[-1]
                                 if img.mode in ("RGBA","LA") else None)
                        img = bg
                    elif img.mode != "RGB": img = img.convert("RGB")
                    img.save(new_path, "JPEG", quality=95, subsampling=0)
                else:
                    img.convert("RGB").save(new_path, "GIF")
                os.remove(old_path)
                item["path"] = new_path
                _thumb_cache.pop((old_path, self._tw(), self._th()), None)
                cell = item.get("_cell")
                if cell and cell.winfo_exists():
                    # Prima si aggiornava solo il NOME: la miniatura
                    # restava quella del vecchio file e i pallini quelli di
                    # prima, quindi convertendo un PNG in JPG l'indicatore
                    # ambra non spariva.
                    new_img = make_thumb(new_path)
                    for w in cell.winfo_children():
                        if isinstance(w, tk.Label):
                            self.win.after(0, lambda lb=w: lb.config(
                                text=tk_safe(os.path.basename(new_path)[:22])))
                            break
                    for w in cell.winfo_children():
                        if isinstance(w, tk.Canvas):
                            def _upd(cv=w, i=new_img, it=item):
                                if not cv.winfo_exists():
                                    return
                                if i is not None:
                                    cv.delete("all")
                                    cv.create_image(
                                        self._tw()//2, self._th()//2,
                                        anchor="center", image=i)
                                    cv._img = i
                                self._draw_item_dots(it, cv)
                            self.win.after(0, _upd)
                            break
            except Exception as ex:
                self.win.after(0, lambda e=ex: self.sorter._hud_alert(
                    "Errore conversione", str(e), parent=self.win) if self.sorter else None)
        threading.Thread(target=_do, daemon=True).start()

    def _delete_selected(self):
        """Canc da tastiera: cestina i file selezionati (o quello con focus)."""
        if self._selected:
            targets = [i for i in self.filtered if i["path"] in self._selected]
        elif self._focus_item:
            targets = [self._focus_item]
        else:
            return
        self._trash_items(targets)

    def _trash_items(self, items):
        """Cestina una lista di item con conferma se multipli."""
        # Lavora su copia per evitare problemi se la lista viene modificata
        work = list(items)
        n = len(work)
        if n == 0:
            return
        if n > 1:
            if not (self.sorter._hud_yesno(
                    "Cestina", f"Spostare {n} file nel cestino?",
                    yes_label="Cestina", no_label="Annulla",
                    parent=self.win) if self.sorter else False):
                return
        errors = []
        done   = []
        for item in work:
            path = item.get("path","")
            if not path or not os.path.exists(path):
                continue
            try:
                if self.sorter:
                    from image_sorter import move_to_transit as _mtt, append_history as _ah
                    dest = _mtt(path, self.sorter.config)
                    if not dest:
                        raise Exception("spostamento nel cestino di transito fallito")
                    _ah({"action": "trashed_transit", "files": [path],
                        "dest": dest, "note": "da Timeline"})
                else:
                    send_to_trash(path)
                done.append(item)
            except Exception as ex:
                errors.append(f"{os.path.basename(path)}: {ex}")
        # Rimuovi celle dopo il loop (non durante)
        self.win.after(0, lambda d=done: [self._remove_cell(i) for i in d])
        if errors:
            (self.sorter._hud_alert("Errore cestino",
                "\n".join(errors[:5]), parent=self.win) if self.sorter else None)

    def _trash_item(self, item):
        self._trash_items([item])

    def _move_item(self, item, dest_dir, skip_history=False):
        try:
            os.makedirs(dest_dir, exist_ok=True)
            orig_path = item["path"]
            dst = os.path.join(dest_dir, os.path.basename(orig_path))
            if os.path.exists(dst):
                base, ext = os.path.splitext(os.path.basename(orig_path))
                import time
                dst = os.path.join(dest_dir, f"{base}_{int(time.time())}{ext}")
            import shutil
            shutil.move(orig_path, dst)
            if _METADATA_STORE_AVAILABLE:
                metadata_store.rename_path(orig_path, dst)
            # Registra in history solo se non è parte di un batch
            if self.sorter and not skip_history:
                self.sorter.history.append(("moved_timeline", orig_path, dst))
                if len(self.sorter.history) > 30:
                    self.sorter.history.pop(0)
                from image_sorter import append_history as _ah
                _ah({"action": "moved_timeline", "files": [orig_path],
                     "dest": dst, "note": "da Timeline"})
            item["path"] = dst
            dest_name = os.path.basename(dest_dir)
            self._mark_moved(item, dest_name)
        except Exception as ex:
            self.sorter._hud_alert("Errore spostamento", str(ex), parent=self.win) if self.sorter else None

    def _move_selected(self, dest):
        """Sposta tutti i file con cella selezionata (future: selezione multipla)."""
        pass  # spostamento multiplo gestito da _move_selected_to

    def _remove_cell(self, item):
        """Rimuove fisicamente la cella dalla griglia."""
        cell = item.get("_cell")
        if cell and cell.winfo_exists():
            cell.destroy()
        try:
            self.filtered.remove(item)
            self.items.remove(item)
        except ValueError:
            pass
        self._selected.discard(item["path"])
        self._update_sel_bar()

    def _mark_restored(self, item, orig_path):
        """Annulla visivamente il badge 'OK' su un item dopo undo."""
        item["path"]     = orig_path
        item["moved_to"] = None
        cell = item.get("_cell")
        if cell and cell.winfo_exists():
            for w in cell.winfo_children():
                if isinstance(w, tk.Canvas):
                    try:
                        # Ridisegna il canvas senza il badge verde
                        w.delete("all")
                        from PIL import Image as _Img, ImageTk as _ITk
                        img = _Img.open(orig_path)
                        img.thumbnail((self._tw(), self._th()))
                        photo = _ITk.PhotoImage(img)
                        item["_photo"] = photo
                        w.create_image(self._tw()//2, self._th()//2,
                                       anchor="center", image=photo)
                    except Exception:
                        pass
                    break
            for w in cell.winfo_children():
                if isinstance(w, tk.Label):
                    try: w.config(fg=TEXT_COLOR)
                    except Exception: pass

    def _mark_moved(self, item, dest_name):
        item["moved_to"] = dest_name
        cell = item.get("_cell")
        if cell and cell.winfo_exists():
            # Aggiorna overlay sulla thumbnail
            for w in cell.winfo_children():
                if isinstance(w, tk.Canvas):
                    try:
                        w.create_rectangle(0, self._th()-18, self._tw(), self._th(),
                                           fill="#1a4a1a", outline="")
                        w.create_text(self._tw()//2, self._th()-9,
                                      text=f"OK {dest_name[:20]}",
                                      fill=SUCCESS,
                                      font=("TkFixedFont",7,"bold"))
                    except Exception:
                        pass
                    break
            # Desatura etichetta
            for w in cell.winfo_children():
                if isinstance(w, tk.Label):
                    try: w.config(fg=MUTED_COLOR)
                    except Exception: pass

    # ── Mappa ─────────────────────────────────────────────────────────────────
    def _open_map(self):
        items = self.filtered if self.filtered else self.items
        if not items:
            self.sorter._show_toast("Prima esegui una scansione.", duration=2000) if self.sorter else None
            return
        # Controlla GPS nel thread principale prima di lanciare
        gps_items = [i for i in items if i.get("gps")]
        if not gps_items:
            if self.sorter:
                self.sorter._show_toast(
                    "Nessuna immagine con dati GPS trovata.",
                    duration=2500)
            return
        self._status(f"Generazione mappa ({len(gps_items)} punti)...", HUD_CYAN)
        def _run():
            # La generazione delle anteprime apre un file per foto: con
            # qualche centinaio di immagini ci vogliono alcuni secondi,
            # quindi si mostra l'avanzamento invece di lasciare la barra
            # ferma su "Generazione mappa...".
            def _prog(done, tot):
                if done % 10 and done != tot:
                    return          # aggiorna ogni 10, non ad ogni foto
                try:
                    self.win.after(0, lambda d=done, t=tot: self._status(
                        f"Generazione mappa: anteprime {d}/{t}...", HUD_CYAN))
                except Exception:
                    pass
            build_map(gps_items, progress=_prog)
            self.win.after(0, lambda: self._status(
                f"Mappa aperta nel browser ({len(gps_items)} punti GPS).", SUCCESS))
        threading.Thread(target=_run, daemon=True).start()

    # ── Utility ───────────────────────────────────────────────────────────────
    def _status(self, text, color=None):
        self._status_lbl.config(text=tk_safe(text),
                                fg=color or MUTED_COLOR)

    def _close(self):
        # Salva la posizione del divisore anteprima e le dimensioni della
        # finestra anche qui (non solo quando si disattiva esplicitamente
        # il pulsante): altrimenti, trascinando il divisore o
        # ridimensionando la finestra e chiudendo direttamente, le nuove
        # proporzioni andrebbero perse. Ogni lettura in un try/except
        # separato: se una fallisce, le altre — e il salvataggio finale
        # su disco — devono comunque procedere.
        if self.sorter:
            if getattr(self, '_preview_visible', False):
                try:
                    self.sorter.config["timeline_preview_sash"] = self._right_paned.sashpos(0)
                except Exception:
                    pass
            try:
                w, h = self.win.winfo_width(), self.win.winfo_height()
                if w > 100 and h > 100:
                    self.sorter.config["timeline_window_size"] = [w, h]
            except Exception:
                pass
            try:
                save_config(self.sorter.config)
            except Exception:
                pass
        self._stop_flag = True
        self.win.destroy()


# ── Entry point standalone + integrazione con image_sorter ───────────────────
def open_deep_browser(parent, sorter=None, initial_dirs=None, browse_fn=None):
    return DeepBrowser(parent, sorter=sorter, initial_dirs=initial_dirs,
                       browse_fn=browse_fn)


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    dirs = sys.argv[1:] or None
    db   = DeepBrowser(root, initial_dirs=dirs)
    root.mainloop()
