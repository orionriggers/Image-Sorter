# exif_editor.py — Image Sorter v1.21.0
VERSION = "1.25.0"
# Dialog per modifica EXIF: data scatto, GPS, autore, descrizione
# Dipendenze: piexif (pip install piexif)

import os, datetime, threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ExifTags

try:
    import piexif
    _PIEXIF_OK = True
except ImportError:
    _PIEXIF_OK = False

try:
    from image_sorter import (BG_COLOR, PANEL_COLOR, ACCENT_COLOR, HUD_CYAN,
                               TEXT_COLOR, MUTED_COLOR, HIGHLIGHT, SUCCESS,
                               WARNING, hud_apply, tk_safe)
except ImportError:
    BG_COLOR    = "#0a0f1a"; PANEL_COLOR = "#0d1117"
    ACCENT_COLOR= "#1a2a3a"; HUD_CYAN    = "#00c8ff"
    TEXT_COLOR  = "#c8d8e8"; MUTED_COLOR = "#4a6080"
    HIGHLIGHT   = "#2a4a6a"; SUCCESS     = "#2ecc71"; WARNING = "#e67e22"
    def hud_apply(w): w.configure(bg=BG_COLOR)
    def tk_safe(s): return ''.join(c for c in str(s) if ord(c) < 0x10000)

# ── Lettura EXIF ──────────────────────────────────────────────────────────────
def read_exif(path):
    """Legge i campi EXIF rilevanti. Restituisce dict."""
    result = {
        "date":        "",   # DateTimeOriginal  "YYYY:MM:DD HH:MM:SS"
        "gps_lat":     "",   # latitudine decimale
        "gps_lon":     "",   # longitudine decimale
        "artist":      "",
        "copyright":   "",
        "description": "",
        "make":        "",
        "model":       "",
    }
    if not os.path.isfile(path):
        return result
    ext = os.path.splitext(path)[1].lower()
    if ext not in {".jpg",".jpeg",".tiff",".tif",".webp"}:
        return result
    try:
        img  = Image.open(path)
        exif = img.getexif()
        # Date
        raw = exif.get(0x9003) or exif.get(0x0132)
        if raw: result["date"] = str(raw)[:19]
        # GPS
        gps = exif.get_ifd(0x8825)
        if gps:
            def _dms(vals, ref):
                try:
                    d,m,s = (float(x) for x in vals)
                    v = d + m/60 + s/3600
                    return -v if ref in ("S","W") else v
                except Exception: return None
            lat = _dms(gps.get(2,(0,0,0)), gps.get(1,"N"))
            lon = _dms(gps.get(4,(0,0,0)), gps.get(3,"E"))
            if lat is not None: result["gps_lat"] = f"{lat:.6f}"
            if lon is not None: result["gps_lon"] = f"{lon:.6f}"
        # Testo
        for key, tag in [("artist",0x013B),("copyright",0x8298),
                         ("description",0x010E),("make",0x010F),("model",0x0110)]:
            v = exif.get(tag)
            if v: result[key] = str(v).strip('\x00')
    except Exception:
        pass
    return result

# ── Scrittura EXIF ────────────────────────────────────────────────────────────
def _deg_to_dms_rational(deg):
    """Converte gradi decimali in (d,m,s) come IFDRational tuple."""
    deg = abs(deg)
    d = int(deg)
    m = int((deg - d) * 60)
    s = round(((deg - d) * 60 - m) * 60, 4)
    # piexif vuole tuple (numeratore, denominatore)
    return ((d,1),(m,1),(int(s*10000),10000))

def write_exif(path, data):
    """
    Scrive i campi EXIF nel file.
    data = dict con chiavi: date, gps_lat, gps_lon, artist, copyright, description
    Restituisce (True, "") o (False, messaggio_errore)
    """
    if not _PIEXIF_OK:
        return False, "piexif non installato.\nEsegui: pip install piexif"
    ext = os.path.splitext(path)[1].lower()
    if ext not in {".jpg",".jpeg",".tiff",".tif",".webp"}:
        return False, f"Formato non supportato per scrittura EXIF: {ext}"
    try:
        # Leggi EXIF esistente o crea nuovo
        try:
            exif_dict = piexif.load(path)
        except Exception:
            exif_dict = {"0th":{}, "Exif":{}, "GPS":{}, "1st":{}}

        # Data scatto
        d = data.get("date","").strip()
        if d:
            # Normalizza in "YYYY:MM:DD HH:MM:SS"
            try:
                for fmt in ("%Y:%m:%d %H:%M:%S","%Y-%m-%d %H:%M:%S",
                            "%Y/%m/%d %H:%M:%S","%d/%m/%Y %H:%M:%S",
                            "%Y:%m:%d","%Y-%m-%d"):
                    try:
                        dt = datetime.datetime.strptime(d, fmt)
                        d  = dt.strftime("%Y:%m:%d %H:%M:%S")
                        break
                    except ValueError:
                        pass
            except Exception:
                pass
            d_bytes = d.encode()
            exif_dict["0th"][piexif.ImageIFD.DateTime]        = d_bytes
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = d_bytes
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized]= d_bytes

        # GPS
        lat_s = data.get("gps_lat","").strip()
        lon_s = data.get("gps_lon","").strip()
        if lat_s and lon_s:
            try:
                lat = float(lat_s); lon = float(lon_s)
                exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef]  = b"N" if lat>=0 else b"S"
                exif_dict["GPS"][piexif.GPSIFD.GPSLatitude]     = _deg_to_dms_rational(lat)
                exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon>=0 else b"W"
                exif_dict["GPS"][piexif.GPSIFD.GPSLongitude]    = _deg_to_dms_rational(lon)
            except ValueError:
                return False, "Coordinate GPS non valide.\nInserisci valori decimali (es. 41.9028)"
        elif not lat_s and not lon_s:
            # Rimuovi GPS se entrambi vuoti
            exif_dict["GPS"] = {}

        # Campi testo
        for key, ifd, tag in [
            ("artist",      "0th",  piexif.ImageIFD.Artist),
            ("copyright",   "0th",  piexif.ImageIFD.Copyright),
            ("description", "0th",  piexif.ImageIFD.ImageDescription),
        ]:
            v = data.get(key,"").strip()
            if v:
                exif_dict[ifd][tag] = v.encode()
            elif tag in exif_dict.get(ifd,{}):
                del exif_dict[ifd][tag]

        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, path)
        return True, ""
    except Exception as ex:
        return False, str(ex)

# ── Dialog EXIF editor ────────────────────────────────────────────────────────
class ExifEditor:
    """Dialog per modifica EXIF di uno o più file."""

    def __init__(self, parent, filepaths, on_done=None):
        """
        filepaths : lista di percorsi file
        on_done   : callback(changed_paths) chiamata dopo il salvataggio
        """
        self.parent    = parent
        self.filepaths = [f for f in filepaths
                          if os.path.splitext(f)[1].lower()
                          in {".jpg",".jpeg",".tiff",".tif",".webp"}]
        self.on_done   = on_done
        self._idx      = 0  # file corrente nella lista
        self._changed  = []

        if not self.filepaths:
            messagebox.showinfo("Nessun file compatibile",
                "Sono supportati: JPG, TIFF, WebP\n"
                "(non PNG, GIF, BMP)",
                parent=parent)
            return

        win = tk.Toplevel(parent)
        win.withdraw()
        win.title(f"Modifica EXIF  v{VERSION}")
        win.configure(bg=BG_COLOR)
        win.resizable(False, False)
        win.transient(parent)
        win.bind("<Escape>", lambda e: win.destroy())
        hud_apply(win)
        self.win = win

        self._build()
        self._load(0)

        win.update_idletasks()
        w = win.winfo_reqwidth()
        h = win.winfo_reqheight()
        x = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.deiconify()
        win.grab_set()

    def _build(self):
        win = self.win
        pad = dict(padx=12, pady=4)

        # ── Intestazione file ─────────────────────────────────────────────────
        top = tk.Frame(win, bg=PANEL_COLOR)
        top.grid(row=0, column=0, sticky="ew", pady=(0,4))
        top.columnconfigure(1, weight=1)

        self._file_lbl = tk.Label(top, text="",
            font=("TkFixedFont",9,"bold"), bg=PANEL_COLOR,
            fg=HUD_CYAN, anchor="w")
        self._file_lbl.grid(row=0, column=0, columnspan=3,
                            sticky="ew", padx=12, pady=(8,2))

        self._nav_lbl = tk.Label(top, text="",
            font=("TkFixedFont",8), bg=PANEL_COLOR,
            fg=MUTED_COLOR, anchor="w")
        self._nav_lbl.grid(row=1, column=0, sticky="w", padx=12, pady=(0,6))

        if len(self.filepaths) > 1:
            tk.Button(top, text="< Prec", font=("TkFixedFont",8),
                      bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=8,
                      command=lambda: self._nav(-1)
                      ).grid(row=1, column=1, sticky="e", padx=2, pady=(0,6))
            tk.Button(top, text="Succ >", font=("TkFixedFont",8),
                      bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=8,
                      command=lambda: self._nav(1)
                      ).grid(row=1, column=2, sticky="e", padx=8, pady=(0,6))

        # ── Campi EXIF ────────────────────────────────────────────────────────
        body = tk.Frame(win, bg=BG_COLOR)
        body.grid(row=1, column=0, sticky="nsew", padx=0)

        def _row(parent, label, row, var=None, width=32, hint=""):
            tk.Label(parent, text=label, font=("TkFixedFont",9),
                     bg=BG_COLOR, fg=TEXT_COLOR, anchor="e", width=16
                     ).grid(row=row, column=0, sticky="e", padx=(12,4), pady=4)
            if var is None: var = tk.StringVar()
            e = tk.Entry(parent, textvariable=var, width=width,
                         font=("TkFixedFont",9), bg=ACCENT_COLOR,
                         fg=TEXT_COLOR, insertbackground=HUD_CYAN,
                         relief="flat")
            e.grid(row=row, column=1, sticky="ew", padx=(0,12), pady=4, ipady=3)
            if hint:
                tk.Label(parent, text=hint, font=("TkFixedFont",7),
                         bg=BG_COLOR, fg=MUTED_COLOR
                         ).grid(row=row, column=2, sticky="w", padx=(0,8))
            return var

        self._v_date  = _row(body, "Data scatto:", 0,
                             hint="YYYY:MM:DD HH:MM:SS")
        self._v_lat   = _row(body, "GPS latitudine:", 1,
                             hint="es. 41.902800  (neg = Sud)")
        self._v_lon   = _row(body, "GPS longitudine:", 2,
                             hint="es. 12.496400  (neg = Ovest)")
        self._v_artist= _row(body, "Autore:", 3)
        self._v_copy  = _row(body, "Copyright:", 4)
        self._v_desc  = _row(body, "Descrizione:", 5)

        body.columnconfigure(1, weight=1)

        # Helper: pulsante "Ora corrente"
        tk.Button(body, text="Ora corrente",
                  font=("TkFixedFont",7), bg=ACCENT_COLOR,
                  fg=MUTED_COLOR, relief="flat", padx=6,
                  command=self._set_now
                  ).grid(row=0, column=2, sticky="w", padx=(0,8), pady=4)

        # ── Info sola lettura ─────────────────────────────────────────────────
        sep = tk.Frame(win, bg=ACCENT_COLOR, height=1)
        sep.grid(row=2, column=0, sticky="ew", padx=12, pady=(8,0))

        self._info_lbl = tk.Label(win, text="",
            font=("TkFixedFont",8), bg=BG_COLOR, fg=MUTED_COLOR,
            justify="left", anchor="w")
        self._info_lbl.grid(row=3, column=0, sticky="ew", padx=16, pady=(4,0))

        # ── Avviso batch ──────────────────────────────────────────────────────
        if len(self.filepaths) > 1:
            self._batch_var = tk.BooleanVar(value=False)
            tk.Checkbutton(win, text="Applica le modifiche a tutti i file selezionati",
                           variable=self._batch_var,
                           font=("TkFixedFont",8), bg=BG_COLOR,
                           fg=WARNING, selectcolor=BG_COLOR,
                           activebackground=BG_COLOR, activeforeground=WARNING
                           ).grid(row=4, column=0, sticky="w", padx=16, pady=(8,0))

        # ── Bottoni ───────────────────────────────────────────────────────────
        btn_row = tk.Frame(win, bg=BG_COLOR)
        btn_row.grid(row=5, column=0, sticky="ew", padx=12, pady=12)

        tk.Button(btn_row, text="Salva", font=("TkFixedFont",9,"bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=16,
                  command=self._save
                  ).pack(side="left", padx=4, ipady=4)

        if len(self.filepaths) > 1:
            tk.Button(btn_row, text="Salva e vai al successivo",
                      font=("TkFixedFont",9), bg=HUD_CYAN, fg=BG_COLOR,
                      relief="flat", padx=12,
                      command=lambda: (self._save(), self._nav(1))
                      ).pack(side="left", padx=4, ipady=4)

        tk.Button(btn_row, text="Annulla", font=("TkFixedFont",9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=12,
                  command=self.win.destroy
                  ).pack(side="right", padx=4, ipady=4)

        win.columnconfigure(0, weight=1)

    def _load(self, idx):
        if idx < 0 or idx >= len(self.filepaths):
            return
        self._idx = idx
        path = self.filepaths[idx]
        self._file_lbl.config(text=tk_safe(os.path.basename(path)))
        n = len(self.filepaths)
        self._nav_lbl.config(text=f"{idx+1} / {n}  —  {tk_safe(path)}")

        data = read_exif(path)
        self._v_date.set(data["date"])
        self._v_lat.set(data["gps_lat"])
        self._v_lon.set(data["gps_lon"])
        self._v_artist.set(data["artist"])
        self._v_copy.set(data["copyright"])
        self._v_desc.set(data["description"])

        # Info sola lettura
        info_parts = []
        if data["make"] or data["model"]:
            info_parts.append(f"Camera: {data['make']} {data['model']}".strip())
        size_kb = os.path.getsize(path) // 1024
        info_parts.append(f"Dimensione: {size_kb} KB")
        try:
            img = Image.open(path)
            info_parts.append(f"Risoluzione: {img.width} x {img.height} px")
        except Exception:
            pass
        self._info_lbl.config(text="   ".join(info_parts))

    def _nav(self, delta):
        new_idx = self._idx + delta
        if 0 <= new_idx < len(self.filepaths):
            self._load(new_idx)

    def _set_now(self):
        self._v_date.set(datetime.datetime.now().strftime("%Y:%m:%d %H:%M:%S"))

    def _save(self):
        data = {
            "date":        self._v_date.get(),
            "gps_lat":     self._v_lat.get(),
            "gps_lon":     self._v_lon.get(),
            "artist":      self._v_artist.get(),
            "copyright":   self._v_copy.get(),
            "description": self._v_desc.get(),
        }
        # Batch o singolo?
        batch = (len(self.filepaths) > 1 and
                 hasattr(self, "_batch_var") and
                 self._batch_var.get())
        targets = self.filepaths if batch else [self.filepaths[self._idx]]

        errors = []
        changed = []
        for path in targets:
            ok, err = write_exif(path, data)
            if ok:
                changed.append(path)
            else:
                errors.append(f"{os.path.basename(path)}: {err}")

        self._changed.extend(changed)

        if errors:
            messagebox.showerror("Errori salvataggio EXIF",
                "\n".join(errors[:5]), parent=self.win)
        elif batch:
            messagebox.showinfo("Salvato",
                f"EXIF aggiornati in {len(changed)} file.", parent=self.win)
            if self.on_done:
                self.on_done(changed)
            self.win.destroy()
        else:
            # Singolo: mostra conferma breve nella status bar se disponibile
            if self.on_done:
                self.on_done(changed)
            if not (len(self.filepaths) > 1):
                self.win.destroy()


def open_exif_editor(parent, filepaths, on_done=None):
    if not _PIEXIF_OK:
        messagebox.showerror("Dipendenza mancante",
            "Modulo piexif non trovato.\n"
            "Installare con:\n  pip install piexif --user",
            parent=parent)
        return
    if isinstance(filepaths, str):
        filepaths = [filepaths]
    return ExifEditor(parent, filepaths, on_done=on_done)
