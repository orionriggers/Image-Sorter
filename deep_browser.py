# deep_browser.py — Image Sorter v1.21.0
VERSION = "1.25.0"
# Visualizzazione profonda: scansione ricorsiva, timeline per data/luogo, mappa GPS
# Dipendenze: reverse_geocode, folium (pip install reverse-geocode folium)

import os, sys, threading, datetime, tempfile, webbrowser, subprocess, json
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ExifTags
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
                               send_to_trash, KEYS, KEY_COLORS, get_keypad_cols)
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
    def hud_apply(w): w.configure(bg=BG_COLOR)
    PRIVACY_RED = "#ff2020"
    def tk_safe(s): return ''.join(c for c in str(s) if ord(c) < 0x10000)
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
IMG_EXT  = {".jpg",".jpeg",".png",".gif",".bmp",".tiff",".tif",".webp",".heic",".avif"}
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
def build_map(items, out_path=None):
    """Genera HTML con Folium MarkerCluster e lo salva/apre."""
    try:
        import folium
        from folium.plugins import MarkerCluster
    except ImportError:
        if self.sorter:
            self.sorter._hud_alert("Mappa GPS", "Installa folium:\npip install folium --user")
        else:
            messagebox.showerror("Mappa", "Installa folium:\npip install folium --user", parent=None)
        return

    gps_items = [i for i in items if i.get("gps")]
    if not gps_items:
        if self.sorter:
            self.sorter._show_toast("Nessuna immagine con dati GPS trovata.", duration=2500)
        else:
            messagebox.showinfo("Mappa GPS", "Nessuna immagine con dati GPS trovata.", parent=None)
        return

    lats = [i["gps"][0] for i in gps_items]
    lons = [i["gps"][1] for i in gps_items]
    center = (sum(lats)/len(lats), sum(lons)/len(lons))

    m  = folium.Map(location=center, zoom_start=5)
    mc = MarkerCluster(name="Foto").add_to(m)

    for item in gps_items:
        lat, lon = item["gps"]
        name     = os.path.basename(item["path"])
        dt_str   = item["date"].strftime("%d/%m/%Y %H:%M") if item["date"] else "—"
        loc      = item.get("location","")
        popup_html = (
            f"<b>{name}</b><br>"
            f"📅 {dt_str}<br>"
            f"📍 {loc}<br>"
            f"<small>{item['path']}</small>"
        )
        folium.Marker(
            [lat, lon],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=name,
            icon=folium.Icon(color="blue" if not item.get("moved_to") else "green",
                             icon="camera", prefix="fa"),
        ).add_to(mc)

    folium.LayerControl().add_to(m)

    if out_path is None:
        fd, out_path = tempfile.mkstemp(suffix=".html", prefix="deep_map_")
        os.close(fd)

    m.save(out_path)
    webbrowser.open(f"file://{out_path}", new=2)
    return out_path

# ── Thumbnail cache ───────────────────────────────────────────────────────────
_thumb_cache = {}

def make_thumb(path, w=THUMB_W, h=THUMB_H):
    key = (path, w, h)
    if key in _thumb_cache:
        return _thumb_cache[key]
    try:
        img = Image.open(path)
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
        tk_img = ImageTk.PhotoImage(img)
        _thumb_cache[key] = tk_img
        return tk_img
    except Exception:
        return None

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
                    for path in sel:
                        try:
                            self.sorter._move_to_preset_file(k, preset, path)
                        except Exception:
                            pass
                    # Rimuovi i file spostati dalla vista
                    self._selected.clear()
                    self.items = [i for i in self.items
                                  if i["path"] not in sel]
                    self.filtered = [i for i in self.filtered
                                     if i["path"] not in sel]
                    self._render()
                return _handler
            for _k in list("123456789") + ["0"]:
                win.bind(f"<KeyPress-{_k}>", _make_preset_handler(_k))
        hud_apply(win)
        # Non usiamo grab_set per lasciare accessibile la finestra principale
        self.win = win

        self._build()

        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        ww, wh = 1200, min(780, sh-80)
        wx = (sw - ww) // 2
        wy = (sh - wh) // 2
        win.geometry(f"{ww}x{wh}+{wx}+{wy}")
        win.deiconify()

        if initial_dirs:
            for d in initial_dirs:
                self._add_folder(d)

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
        self._sort_var = tk.StringVar(value="Scatto")
        self._sort_map = {"Scatto": "date_shot", "File": "date_file", "Luogo": "location"}
        sort_om = tk.OptionMenu(tb, self._sort_var,
                                "Scatto", "File", "Luogo",
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
        right = tk.Frame(body, bg=BG_COLOR)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        self._prog_frame=tk.Frame(right,bg=PANEL_COLOR,height=3)
        self._prog_frame.grid(row=0,column=0,columnspan=2,sticky="ew")
        self._prog_bar=tk.Frame(self._prog_frame,bg=HUD_CYAN,height=3)
        self._prog_bar.place(relwidth=0,relheight=1)
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


        # Smistamento (visibile solo se sorter disponibile)
        if self.sorter:
            self._sort_bar = tk.Frame(right, bg=PANEL_COLOR)
            self._sort_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
            self._sort_bar.grid_remove()

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
        self.items = []

        def _run():
            def _prog(done, total):
                if self._stop_flag:
                    raise StopIteration("Scansione interrotta")
                pct = done/total if total else 0
                self.win.after(0, lambda: self._prog_bar.place(relwidth=pct))
                self.win.after(0, lambda: self._status(
                    f"Scansione: {done}/{total} file...", "#e67e22"))
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
        self._status(f"Scansione completata.", SUCCESS)
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

                # Pallino colorato
                dot = tk.Canvas(row, width=10, height=10,
                                bg=PANEL_COLOR, highlightthickness=0)
                dot.create_oval(1, 1, 9, 9, fill=col, outline="")
                dot.pack(side="left", padx=(8,4))

                # Bottone con nome e conteggio
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
            # Header mese
            hdr = tk.Frame(self._inner, bg=BG_COLOR)
            hdr.pack(fill="x", padx=12, pady=(16,4))
            tk.Label(hdr, text=tk_safe(month_lbl),
                     font=("TkFixedFont",14,"bold"),
                     bg=BG_COLOR, fg=TEXT_COLOR).pack(side="left")
            if loc_hint:
                tk.Label(hdr, text=f"  @ {tk_safe(loc_hint)}",
                         font=("TkFixedFont",9),
                         bg=BG_COLOR, fg=MUTED_COLOR).pack(side="left", padx=8)

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

        cell = tk.Frame(parent, bg=PANEL_COLOR,
                        width=self._tw()+4, height=self._th()+36)
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
            except Exception as _e:
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

            self.win.after(0, _show)
        threading.Thread(target=_load, daemon=True).start()

        # Binding GPS sul canvas — apre mappa singola foto
        if item.get("gps"):
            def _open_single_map(e, it=item):
                # Verifica click sul pallino (angolo in alto a destra)
                tw_ = self._tw()
                th_ = self._th()
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

    def _toggle_sel(self, item):
        if item["path"] in self._selected:
            self._desel_item(item)
        else:
            self._sel_item(item)

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

    def _update_sel_bar(self):
        """Aggiorna la barra destinazioni in fondo."""
        if not hasattr(self,"_sort_bar") or not self.sorter: return
        n = len(self._selected)
        for w in self._sort_bar.winfo_children():
            w.destroy()
        if n == 0:
            self._sort_bar.grid_remove()
            return
        self._sort_bar.grid()
        tk.Label(self._sort_bar, text=f"  {n} selezionati  ",
                 font=("TkFixedFont",9,"bold"),
                 bg=PANEL_COLOR, fg=SUCCESS).pack(side="left", padx=4)
        preset_name = self.sorter.config.get("active_preset","")
        slots = self.sorter.config["presets"].get(preset_name, {})
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
                      command=lambda d=dest: self._move_selected_to(d)
                      ).pack(side="left", padx=2, pady=3, ipady=2)

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
        # Registra tutto come un singolo batch annullabile
        if self.sorter and batch:
            self.sorter.history.append(("moved_timeline_batch", batch))
            if len(self.sorter.history) > 30:
                self.sorter.history.pop(0)
            from image_sorter import append_history as _ah
            _ah({"action": "moved_timeline_batch",
                 "files": [o for o, d in batch],
                 "dest": os.path.dirname(batch[0][1]) if batch else "",
                 "note": f"{len(batch)} file da Timeline"})
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
        self._selected.add(item["path"])
        cell = item.get("_cell")
        cv   = item.get("_canvas")
        src_color = item.get("_src_color")
        if cell and cell.winfo_exists():
            try: cell.config(bg=self._SEL_BG)
            except Exception: pass
        if cv and cv.winfo_exists():
            try:
                # Bordo selezione: bianco spesso; se c'è colore cartella,
                # mantieni il colore come highlightcolor (inner ring visibile)
                cv.config(highlightthickness=4, highlightbackground="#ffffff")
                if src_color:
                    # Crea un secondo frame colorato attorno al canvas per il colore cartella
                    cell.config(bg=src_color)
            except Exception: pass

    def _desel_item(self, item):
        self._selected.discard(item["path"])
        cell = item.get("_cell")
        cv   = item.get("_canvas")
        src_color = item.get("_src_color")
        if cell and cell.winfo_exists():
            try: cell.config(bg=self._UNSEL_BG)
            except Exception: pass
        if cv and cv.winfo_exists():
            try:
                if src_color:
                    cv.config(highlightthickness=3, highlightbackground=src_color)
                    cell.config(bg=src_color)
                else:
                    cv.config(highlightthickness=0)
                    cell.config(bg=self._UNSEL_BG)
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
        """Naviga al file nel sorter principale, o apre col sistema."""
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
        exif_targets = [i for i in targets
                        if os.path.splitext(i["path"])[1].lower()
                        in {".jpg",".jpeg",".tiff",".tif",".webp"}]
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
        menu.tk_popup(event.x_root, event.y_root)

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
                                def _upd(cv=w, i=new_img):
                                    if cv.winfo_exists():
                                        cv.delete("all")
                                        cv.create_image(
                                            self._tw()//2, self._th()//2,
                                            anchor="center", image=i)
                                        cv._img = i
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
                    for w in cell.winfo_children():
                        if isinstance(w, tk.Label):
                            self.win.after(0, lambda lb=w: lb.config(
                                text=tk_safe(os.path.basename(new_path)[:22])))
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
            build_map(gps_items)
            self.win.after(0, lambda: self._status(
                f"Mappa aperta nel browser ({len(gps_items)} punti GPS).", SUCCESS))
        threading.Thread(target=_run, daemon=True).start()

    # ── Utility ───────────────────────────────────────────────────────────────
    def _status(self, text, color=None):
        self._status_lbl.config(text=tk_safe(text),
                                fg=color or MUTED_COLOR)

    def _close(self):
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
