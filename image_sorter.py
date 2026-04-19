#!/usr/bin/env python3
# Image Sorter v1.12
# Python 3.8+ / tkinter / Linux
#
# Struttura classi:
#   DuplicateFinder     — ricerca doppioni (3 tab: SHA256, rapida, A vs B)
#   FolderBrowser       — browser cartelle con albero, anteprime, selezione
#   KeypadPopup         — tastierino flottante preset
#   SidebarPopup        — sidebar smistamento come finestra separata
#   CropOverlay         — ritaglio interattivo sul canvas
#   StreamDeckManager   — gestione deck fisico (idle pages + preset mode)
#   SettingsDialog      — impostazioni (7 tab)
#   ImageSorter         — applicazione principale
"""
image_sorter.py v1.12 — Visualizzatore e smistatore di immagini, video e PDF
Uso: python3 image_sorter.py [/percorso/cartella/o/file]

Navigazione:
  Freccia DESTRA         -> file successivo (con loop)
  Freccia SINISTRA       -> file precedente (con loop)
  Ctrl+Freccia SINISTRA  -> annulla ultimo spostamento e ripristina il file
  Freccia SU             -> pagina precedente (solo PDF multipagina)
  Freccia GIU            -> pagina successiva (solo PDF multipagina)
  PagSu / PagGiu         -> cicla preset precedente / successivo
  Rotella mouse          -> file precedente/successivo (scrolla se zoom > 1)

Smistamento (richiede Sidebar o Deck attivi):
  Tasti 1-9, 0           -> sposta file nel preset attivo
  Ctrl+1-9, 0            -> copia file nel preset attivo (senza spostare)
  Doppio CANC            -> sposta nel cestino di sistema

Zoom e visualizzazione:
  +  /  -                -> zoom in / out
  Z                      -> adatta al canvas (fit)
  X                      -> dimensione originale (1:1 pixel)
  F                      -> schermo intero (solo immagini)
  Invio                  -> schermo intero (immagini) / player esterno (video/PDF)
  H                      -> mostra/nascondi barra superiore
  I                      -> overlay informazioni EXIF

Gestione file (menu tasto destro sull'immagine):
  Rinomina               -> rinomina il file inline
  Ruota 90 orario/antiorario -> ruota e salva (solo immagini)
  Ritaglia               -> overlay di ritaglio interattivo (solo immagini)
  Play video             -> apre nel player di sistema (solo video)
  Apri PDF               -> apre nel visualizzatore (solo PDF)
  Copia percorso         -> copia il percorso negli appunti

Finestre e pannelli:
  O                      -> browser cartelle (albero + anteprime)
  S                      -> sidebar smistamento (inline / popup / off)
  D  oppure  P           -> tastierino/deck (cicla 1/2/3 colonne)
  R                      -> impostazioni (Preset / Destinazioni / Visualizza)
  Q  oppure  Esc         -> esci dal programma

Formati supportati:
  Immagini: JPG, PNG, GIF, BMP, TIFF, WEBP  (+ estensioni aggiuntive conf.)
  Video:    MP4, MOV, AVI, MKV, WEBM, M4V, FLV  (richiede ffmpeg)
  PDF:      PDF, multipagina  (richiede poppler-utils)
  Senza estensione: rilevati automaticamente via magic bytes
"""

import sys
import os
import copy
import string
import shutil
import json
import threading
import subprocess
import time
import io
import datetime
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter.font as tkfont
import tempfile
import glob
import hashlib
from PIL import Image, ImageTk, ImageDraw, ImageFont
from PIL.ExifTags import TAGS

# (L'import di disk_analyzer viene fatto DOPO la definizione di SCRIPT_DIR)

# --- PERCORSI ----------------------------------------------------------------
# SCRIPT_DIR: cartella dell'eseguibile (file scrivibili: config, log...)
SCRIPT_DIR       = os.path.dirname(os.path.abspath(
                       sys.executable if getattr(sys, 'frozen', False)
                       else __file__))
# BUNDLE_DIR: cartella dei file bundled (read-only in PyInstaller)
BUNDLE_DIR       = getattr(sys, '_MEIPASS', SCRIPT_DIR)

# ── Analizzatore disco (modulo opzionale) ─────────────────────────────────
# Aggiungi SCRIPT_DIR al path per trovare disk_analyzer.py quando Image Sorter
# viene lanciato da una cartella diversa da quella dello script.
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
try:
    from disk_analyzer import open_disk_analyzer as _open_disk_analyzer
    _DISK_ANALYZER_AVAILABLE = True
except Exception as _e:
    _DISK_ANALYZER_AVAILABLE = False
    _DISK_ANALYZER_ERR = str(_e)
CONFIG_FILE      = os.path.join(SCRIPT_DIR, "image_sorter_config.json")
BASE_DEST        = os.path.expanduser("~/Immagini/Smistati")
SORTER_ICONS_DIR = os.path.join(BUNDLE_DIR, "sorter_icons")   # icone app + deck
ICON_FILE        = os.path.join(SORTER_ICONS_DIR, "image_sorter_icon.png")


def get_deck_icon(action_type, size=72):
    """Carica icona deck per tipo azione, con fallback None."""
    names = {"folder":"folder.png", "app":"app.png",
             "hotkey":"hotkey.png", "url":"url.png",
             "mute":"mute.png",    "sorter":"sorter.png",
             "page":"page.png",    "preset":"preset.png",
             "nav":"nav.png",      "delete":"delete.png"}
    fn = names.get(action_type)
    if fn:
        fp = os.path.join(SORTER_ICONS_DIR, fn)
        if os.path.isfile(fp):
            try:
                img = Image.open(fp).convert("RGB")
                return img.resize((size,size), Image.Resampling.LANCZOS)
            except Exception:
                pass
    return None



# --- COSTANTI ----------------------------------------------------------------

# =============================================================================
# TRADUZIONI
# =============================================================================

def _load_translations():
    """Carica le traduzioni da translations.py nella stessa cartella dello script."""
    try:
        import importlib.util, sys
        trans_path = os.path.join(SCRIPT_DIR, "translations.py")
        if not os.path.isfile(trans_path):
            return None, None
        spec = importlib.util.spec_from_file_location("translations", trans_path)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "LANG", {}), getattr(mod, "SHORTCUTS", {})
    except Exception:
        return None, None

_LANG_DATA, _SHORTCUTS_DATA = _load_translations()

def T(key, lang=None, **kw):
    """Restituisce la stringa tradotta per key nella lingua corrente."""
    if lang is None:
        try:
            cfg = load_config()
            lang = cfg.get("language", "it")
        except Exception:
            lang = "it"
    data = (_LANG_DATA or {}).get(lang, {})
    if not data:
        data = (_LANG_DATA or {}).get("it", {})
    s = data.get(key, key)   # fallback: mostra la chiave
    if kw:
        try: s = s.format(**kw)
        except Exception: pass
    return s


# =============================================================================
# AUDIO
# =============================================================================

# =============================================================================

import struct, wave, math as _math

def _make_wav(freq, duration, volume=0.4, fade=0.02, sample_rate=22050):
    """Genera un file WAV in memoria come bytes."""
    n_samples = int(sample_rate * duration)
    fade_s    = int(sample_rate * fade)
    buf = bytearray()
    for i in range(n_samples):
        t   = i / sample_rate
        env = 1.0
        if i < fade_s:
            env = i / fade_s
        elif i > n_samples - fade_s:
            env = (n_samples - i) / fade_s
        val = int(32767 * volume * env * _math.sin(2 * _math.pi * freq * t))
        buf += struct.pack("<h", max(-32768, min(32767, val)))
    # Costruisce WAV in memoria
    import io
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(buf))
    return out.getvalue()


def _make_chord_wav(freqs, duration, volume=0.3, fade=0.03, sample_rate=22050):
    """Genera un accordo/sequenza di note."""
    import io
    n_samples = int(sample_rate * duration)
    fade_s    = int(sample_rate * fade)
    buf = bytearray()
    for i in range(n_samples):
        t   = i / sample_rate
        env = 1.0
        if i < fade_s:
            env = i / fade_s
        elif i > n_samples - fade_s:
            env = (n_samples - i) / fade_s
        val = sum(_math.sin(2 * _math.pi * f * t) for f in freqs)
        val = int(32767 * volume * env * val / len(freqs))
        buf += struct.pack("<h", max(-32768, min(32767, val)))
    out = io.BytesIO()
    with wave.open(out, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(buf))
    return out.getvalue()


# Genera i suoni una sola volta all'avvio
_SOUND_MOVE   = None   # breve bip acuto: file spostato
_SOUND_DONE   = None   # accordo conclusivo: scansione completata
_SOUND_READY  = False

def _init_sounds():
    global _SOUND_MOVE, _SOUND_DONE, _SOUND_READY
    if _SOUND_READY:
        return
    try:
        # Suono spostamento: breve bip 880Hz (La5) — 80ms
        _SOUND_MOVE  = _make_wav(880, 0.08, volume=0.35)
        # Suono completamento: accordo Do-Mi-Sol ascendente — 400ms
        import time as _time
        _SOUND_DONE  = _make_chord_wav([523, 659, 784], 0.4, volume=0.3)
        _SOUND_READY = True
    except Exception:
        pass


def play_sound(sound_type="move"):
    """Riproduce un suono in background. sound_type: 'move' o 'done'."""
    global _SOUND_MOVE, _SOUND_DONE
    if not _SOUND_READY:
        _init_sounds()
    data = _SOUND_MOVE if sound_type == "move" else _SOUND_DONE
    if not data:
        return
    def _play():
        try:
            import tempfile, subprocess as _sp
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.write(data)
            tmp.close()
            # Prova aplay (ALSA), poi paplay (PulseAudio)
            for player in ["aplay", "paplay", "sox"]:
                try:
                    _sp.Popen([player, "-q", tmp.name],
                              stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                    break
                except FileNotFoundError:
                    continue
            import time as _t; _t.sleep(0.6)
            import os as _os; _os.unlink(tmp.name)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


# =============================================================================
# ICONE (generate con Pillow, nessun file esterno)
# =============================================================================

_icon_cache    = {}
_thumb_cache   = {}   # {(filepath, mtime, size): PhotoImage}
_THUMB_CACHE_MAX = 200   # max thumbnail in memoria

def make_icon(name, size=18, fg=(0,200,255), bg=(10,15,26)):
    """Genera una PhotoImage tkinter con icona vettoriale semplice."""
    key = (name, size, fg, bg)
    if key in _icon_cache:
        return _icon_cache[key]
    img = Image.new("RGBA", (size, size), (bg[0], bg[1], bg[2], 0))
    d = ImageDraw.Draw(img)
    s = size
    c = s // 2  # centro
    t = max(1, s // 10)  # spessore linea

    if name == "folder":
        # Cartella: rettangolo con tab in cima
        d.rectangle([1, s//3, s-2, s-2], outline=fg, width=t)
        d.rectangle([1, s//4, s//2, s//3+1], outline=fg, fill=fg, width=1)
    elif name == "folder_open":
        d.rectangle([1, s//3, s-2, s-2], outline=fg, width=t)
        d.rectangle([1, s//4, s//2, s//3+1], outline=fg, fill=fg, width=1)
        # Freccia aperta
        d.line([(s//4, s*2//3),(s*3//4, s*2//3)], fill=fg, width=t)
    elif name == "home":
        # Casa: triangolo tetto + rettangolo
        d.polygon([(c, 2),(s-2, s//2),(2, s//2)], outline=fg, fill=bg)
        d.rectangle([s//4, s//2, s*3//4, s-2], outline=fg, width=t)
        # Porta
        d.rectangle([c-2, s*2//3, c+2, s-2], fill=fg)
    elif name == "image":
        # Cornice con montagna stilizzata
        d.rectangle([2, 2, s-3, s-3], outline=fg, width=t)
        d.polygon([(3, s-4),(s//3, s//3),(s*2//3, s*2//3),(s-4,s-4)],
                  outline=fg, fill=(fg[0]//3, fg[1]//3, fg[2]//3, 180))
        d.ellipse([s*2//3-2, 3, s-4, s//3], outline=fg, width=t)
    elif name == "video":
        # Rettangolo con triangolo play
        d.rectangle([2, 2, s-3, s-3], outline=fg, width=t)
        d.polygon([(s//3, s//4),(s//3, s*3//4),(s*3//4, c)], fill=fg)
    elif name == "document":
        # Foglio con angolo piegato
        d.polygon([(2,2),(s-s//4,2),(s-2,s//4),(s-2,s-2),(2,s-2)],
                  outline=fg, width=t)
        d.line([(s-s//4, 2),(s-s//4, s//4),(s-2, s//4)], fill=fg, width=t)
        # Righe testo
        for y in [s//3, s//2, s*2//3]:
            d.line([(s//5, y),(s*4//5, y)], fill=fg, width=max(1,t-1))
    elif name == "disk":
        # Cerchio con etichetta
        d.ellipse([2,2,s-3,s-3], outline=fg, width=t)
        d.ellipse([s//3,s//3,s*2//3,s*2//3], outline=fg, width=t)
    elif name == "root":
        # Slash /
        d.line([(s*2//3, 2),(s//3, s-3)], fill=fg, width=t+1)
    elif name == "up":
        # Freccia su
        d.polygon([(c,2),(s-3,c),(3,c)], fill=fg)
        d.rectangle([c-t, c, c+t, s-3], fill=fg)
    elif name == "down":
        # Freccia giù
        d.polygon([(c,s-3),(s-3,c),(3,c)], fill=fg)
        d.rectangle([c-t, 3, c+t, c], fill=fg)
    elif name == "close":
        # X
        d.line([(3,3),(s-4,s-4)], fill=fg, width=t+1)
        d.line([(s-4,3),(3,s-4)], fill=fg, width=t+1)
    elif name == "check":
        # Spunta
        d.line([(3,c),(c-1,s-4),(s-3,3)], fill=fg, width=t+1)
    elif name == "new_folder":
        # Cartella con +
        d.rectangle([1, s//3, s-2, s-2], outline=fg, width=t)
        d.rectangle([1, s//4, s//2, s//3+1], fill=fg, width=1)
        d.line([(c, s//2),(c, s-3)], fill=(0,255,128), width=t+1)
        d.line([(s//3+1, s*3//4),(s*2//3, s*3//4)], fill=(0,255,128), width=t+1)
    elif name == "back":
        # Freccia sinistra
        d.polygon([(3,c),(c,2),(c,s-3)], fill=fg)
        d.rectangle([c, c-t, s-3, c+t], fill=fg)
    elif name == "play":
        # Triangolo play
        d.polygon([(3,2),(3,s-3),(s-3,c)], fill=fg)

    photo = ImageTk.PhotoImage(img)
    _icon_cache[key] = photo
    return photo


def icon_btn(parent, icon_name, text="", cmd=None, bg=None, fg=None,
             size=16, **kwargs):
    """Crea un Button con icona Pillow + testo opzionale."""
    _bg = bg or PANEL_COLOR
    _fg = fg or (0, 200, 255)
    ico  = make_icon(icon_name, size=size, fg=_fg, bg=tuple(
        int(_bg.lstrip("#")[i:i+2], 16) for i in (0,2,4))
        if isinstance(_bg, str) else _bg)
    b = tk.Button(parent, image=ico, text=text,
                  compound="left" if text else "none",
                  bg=_bg, relief="flat", bd=0,
                  activebackground=HIGHLIGHT,
                  command=cmd, **kwargs)
    b._icon_ref = ico   # impedisce garbage collection
    return b


def detect_media_type(filepath):
    """Rileva il tipo di file anche senza estensione, leggendo i magic bytes."""
    # Prima prova con estensione normale
    ext = os.path.splitext(filepath)[1].lower()
    if ext in MEDIA_EXTENSIONS:
        return ext

    # Nessuna estensione o estensione sconosciuta: leggi magic bytes
    try:
        with open(filepath, "rb") as f:
            header = f.read(16)
        # Immagini
        if header[:3] == b"\xff\xd8\xff":          return ".jpg"
        if header[:8] == b"\x89PNG\r\n\x1a\n":    return ".png"
        if header[:6] in (b"GIF87a", b"GIF89a"):     return ".gif"
        if header[:4] == b"RIFF" and header[8:12] == b"WEBP": return ".webp"
        if header[:2] in (b"BM",):                   return ".bmp"
        if header[:4] in (b"II*\x00", b"MM\x00*"): return ".tiff"
        # Video
        if header[4:8] in (b"ftyp", b"moov"):        return ".mp4"
        if header[:4] == b"RIFF" and header[8:12] == b"AVI ": return ".avi"
        if header[:4] == b"\x1a\x45\xdf\xa3":     return ".mkv"
        # PDF
        if header[:4] == b"%PDF":                    return ".pdf"
    except (OSError, IOError):
        pass
    return ""


def is_media_file(filepath):
    """Controlla se il file è un media supportato, anche senza estensione."""
    return detect_media_type(filepath) in MEDIA_EXTENSIONS


def tk_safe(text, maxlen=None):
    """Rimuove caratteri che causano RenderAddGlyphs crash in tkinter/X11.
    Sostituisce caratteri fuori dal piano base Unicode (BMP) con '?'.
    """
    if not isinstance(text, str):
        text = str(text)
    # Rimuovi caratteri oltre BMP (emoji, CJK estesi, ecc.) che crashano X11
    result = "".join(c if ord(c) < 0x10000 else "?" for c in text)
    if maxlen and len(result) > maxlen:
        result = result[:maxlen-1] + "…"
    return result


def load_thumbnail(filepath, size):
    """Carica thumbnail con cache, draft mode per JPEG, timeout per video/PDF."""
    try:
        mtime = os.path.getmtime(filepath)
        key   = (filepath, mtime, size)
        if key in _thumb_cache:
            return _thumb_cache[key]

        ext = detect_media_type(filepath)
        if ext in VIDEO_EXTENSIONS:
            img = get_video_frame(filepath)
            if img is None:
                img = Image.new("RGB", (size, size), (20,20,40))
                d = ImageDraw.Draw(img)
                s = size
                d.polygon([(s//4,s//4),(s//4,3*s//4),(3*s//4,s//2)], fill=(0,200,255))
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            img = add_play_overlay(img, corner=(size > 60))
        elif ext in PDF_EXTENSIONS:
            img = get_pdf_preview(filepath, size=(size*2, size*2))
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            img = add_pdf_overlay(img)
        else:
            img = Image.open(filepath)
            # Draft mode: molto più veloce per JPEG grandi
            if hasattr(img, "draft") and ext in (".jpg", ".jpeg"):
                img.draft("RGB", (size * 2, size * 2))
            # Sicurezza memoria: se l'immagine è enorme, ridimensiona prima di caricare
            if img.width * img.height > 4000 * 4000:
                img.thumbnail((2000, 2000), Image.Resampling.NEAREST)
            img.thumbnail((size, size), Image.Resampling.LANCZOS)

        # Salva in cache (con pulizia LRU se troppo grande)
        if len(_thumb_cache) >= _THUMB_CACHE_MAX:
            # Rimuovi il 20% più vecchio
            old_keys = list(_thumb_cache.keys())[:_THUMB_CACHE_MAX // 5]
            for k in old_keys:
                del _thumb_cache[k]
        _thumb_cache[key] = img
        return img
    except Exception:
        return None


def is_video(filepath):
    t = detect_media_type(filepath)
    return t in VIDEO_EXTENSIONS

def is_pdf(filepath):
    t = detect_media_type(filepath)
    return t in PDF_EXTENSIONS

def _pymupdf_available():
    """Controlla se PyMuPDF (fitz) è installato."""
    try:
        import fitz  # noqa
        return True
    except ImportError:
        return False


def get_pdf_page_count(filepath):
    """Ritorna il numero di pagine del PDF."""
    # PyMuPDF — veloce, nessun processo esterno
    try:
        import fitz
        doc = fitz.open(filepath)
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        pass
    # Fallback: pdfinfo
    try:
        result = subprocess.run(["pdfinfo", filepath],
                                capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":")[1].strip())
    except Exception:
        pass
    return 1


def get_pdf_preview(filepath, size=(640, 480), page=1):
    """Estrae una pagina del PDF come immagine PIL.
    Usa PyMuPDF se disponibile (più veloce, nessun file temp),
    altrimenti pdftoppm come fallback."""

    # ── PyMuPDF ────────────────────────────────────────────────────────────────
    try:
        import fitz
        doc  = fitz.open(filepath)
        pg   = doc[page - 1]          # 0-indexed
        # Risoluzione: 72dpi per anteprime, 120dpi per visualizzazione grande
        zoom = 1.0 if max(size) <= 200 else 1.5
        mat  = fitz.Matrix(zoom, zoom)
        pix  = pg.get_pixmap(matrix=mat, alpha=False)
        doc.close()
        img  = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return img
    except Exception:
        pass

    # ── Fallback: pdftoppm ────────────────────────────────────────────────────
    try:
        tmp = tempfile.mkdtemp()
        out_base = os.path.join(tmp, "page")
        subprocess.run(
            ["pdftoppm", "-r", "72", "-f", str(page), "-l", str(page),
             "-png", filepath, out_base],
            capture_output=True, timeout=8)
        files = sorted(glob.glob(out_base + "*.png"))
        if files and os.path.getsize(files[0]) > 0:
            img = Image.open(files[0]).copy()
            shutil.rmtree(tmp, ignore_errors=True)
            return img
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass

    # ── Icona generica ────────────────────────────────────────────────────────
    img = Image.new("RGB", (size[0], size[1]), (240, 240, 248))
    d = ImageDraw.Draw(img)
    d.rectangle([80, 40, 360, 440], fill=(255,255,255), outline=(200,60,60), width=3)
    d.rectangle([80, 40, 360, 110], fill=(200,60,60))
    d.text((110, 55), "PDF", fill=(255,255,255))
    d.text((110, 140), os.path.basename(filepath)[:24], fill=(80,80,100))
    return img


def add_pdf_overlay(img, page=1, total_pages=1):
    """Sovrappone badge PDF con numero pagina nell'angolo in basso a sinistra."""
    img = img.convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    pad  = max(4, min(w, h) // 30)
    fh   = max(10, min(w, h) // 12)
    text = f"PDF {page}/{total_pages}" if total_pages > 1 else "PDF"
    char_w = max(6, fh * 6 // 10)
    bw = len(text) * char_w + pad * 3
    bh = fh + pad * 2
    x0, y0 = pad, h - bh - pad
    d.rounded_rectangle([x0, y0, x0+bw, y0+bh], radius=3,
                         fill=(180, 40, 40, 210))
    d.text((x0 + pad, y0 + pad), text, fill=(255, 255, 255, 240))
    result = Image.alpha_composite(img, overlay)
    return result.convert("RGB")



def add_play_overlay(img, alpha=180, corner=True):
    """Sovrappone un badge play nell'angolo in basso a sinistra dell'immagine."""
    img = img.convert("RGBA")
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    if corner:
        # Badge piccolo nell'angolo in basso a sinistra
        r  = max(10, min(w, h) // 8)   # raggio proporzionale ma piccolo
        pad = max(4, r // 3)
        cx = pad + r
        cy = h - pad - r
    else:
        # Centro (usato per le thumbnail senza frame)
        r  = min(w, h) // 4
        cx, cy = w // 2, h // 2
    # Cerchio scuro
    d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(0, 0, 0, alpha))
    # Triangolo play
    m = r // 4
    pts = [
        (cx - r//2 + m, cy - int(r*0.55)),
        (cx - r//2 + m, cy + int(r*0.55)),
        (cx + int(r*0.65), cy),
    ]
    d.polygon(pts, fill=(255, 255, 255, 220))
    result = Image.alpha_composite(img, overlay)
    return result.convert("RGB")


def get_video_frame(filepath, size=(640, 480)):
    """Estrae un frame del video come PIL Image. Richiede ffmpeg.
    Tenta a 1s per evitare il nero iniziale, fallback a 0s."""
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()

    def _run(seek):
        return subprocess.run(
            ["ffmpeg", "-y", "-ss", str(seek), "-i", filepath,
             "-vframes", "1", "-q:v", "2", "-vf", "scale=640:-1",
             tmp.name],
            capture_output=True, timeout=8)

    try:
        result = _run(1)   # prova a 1 secondo
        # Se il video è più corto di 1s o ffmpeg fallisce, usa 0
        if result.returncode != 0 or not os.path.exists(tmp.name)                 or os.path.getsize(tmp.name) < 500:
            result = _run(0)
        if result.returncode == 0 and os.path.exists(tmp.name)                 and os.path.getsize(tmp.name) > 0:
            img = Image.open(tmp.name).copy()
            os.unlink(tmp.name)
            return img
    except Exception:
        pass
    try:
        os.unlink(tmp.name)
    except Exception:
        pass
    return None

def send_to_trash(filepath):
    """Sposta il file nel cestino di sistema (freedesktop.org)."""
    try:
        import send2trash
        send2trash.send2trash(filepath)
        return True
    except ImportError:
        pass
    try:
        trash_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "Trash")
        files_dir = os.path.join(trash_dir, "files")
        info_dir  = os.path.join(trash_dir, "info")
        os.makedirs(files_dir, exist_ok=True)
        os.makedirs(info_dir,  exist_ok=True)
        fname = os.path.basename(filepath)
        dest  = os.path.join(files_dir, fname)
        base, ext = os.path.splitext(fname)
        i = 1
        while os.path.exists(dest):
            dest = os.path.join(files_dir, f"{base}_{i}{ext}")
            i += 1
        dest_name = os.path.basename(dest)
        info_path = os.path.join(info_dir, dest_name + ".trashinfo")
        with open(info_path, "w") as f:
            f.write("[Trash Info]\n")
            f.write(f"Path={filepath}\n")
            f.write(f"DeletionDate={datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}\n")
        shutil.move(filepath, dest)
        return True
    except Exception:
        return False

KEYS             = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0"]
ROWS_LAYOUT      = [["7","8","9"], ["4","5","6"], ["1","2","3"], ["0"]]
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv"}
PDF_EXTENSIONS   = {".pdf"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | PDF_EXTENSIONS
DEFAULT_PRESET   = "Default"

# --- COLORI ------------------------------------------------------------------
BG_COLOR     = "#1a1a2e"
PANEL_COLOR  = "#16213e"
ACCENT_COLOR = "#0f3460"
HIGHLIGHT    = "#e94560"
TEXT_COLOR   = "#eaeaea"
MUTED_COLOR  = "#888888"
SUCCESS      = "#2ecc71"
WARNING      = "#f5a623"
KEY_COLORS   = [
    "#e94560", "#f5a623", "#7ed321",
    "#4a90e2", "#9b59b6", "#1abc9c",
    "#e67e22", "#2ecc71", "#3498db",
    "#e74c3c",
]
HUD_CYAN     = "#00c8ff"
PRESET_COLORS = ["#e74c3c", "#27ae60", "#2980b9"]  # Rosso, Verde, Blu per i primi 3 preset

def preset_color(config, preset_name, fallback=None):
    """Ritorna il colore RGB per il preset (rosso/verde/blu per i primi 3)."""
    names = list(config.get("presets", {}).keys())
    idx = names.index(preset_name) if preset_name in names else -1
    if 0 <= idx < len(PRESET_COLORS):
        return PRESET_COLORS[idx]
    return fallback or HUD_CYAN

HUD_DIM      = "#1a3a5a"

def _tooltip(widget, text):
    """Mostra un tooltip al passaggio del mouse."""
    tip = [None]
    def _show(e):
        if tip[0] and tip[0].winfo_exists():
            return
        t = tk.Toplevel(widget)
        t.wm_overrideredirect(True)
        t.configure(bg=PANEL_COLOR)
        tk.Label(t, text=text, font=("TkFixedFont", 7),
                 bg=PANEL_COLOR, fg=TEXT_COLOR,
                 padx=6, pady=3).pack()
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 2
        t.wm_geometry(f"+{x}+{y}")
        tip[0] = t
    def _hide(e):
        if tip[0] and tip[0].winfo_exists():
            tip[0].destroy()
        tip[0] = None
    widget.bind("<Enter>", _show, add=True)
    widget.bind("<Leave>", _hide, add=True)


def hud_apply(win, color=None):
    """Aggiunge bordo HUD ciano alla finestra usando un frame bordo."""
    c = color or HUD_CYAN
    # Applica un bordo colorato alla finestra tramite highlightbackground
    try:
        win.config(highlightbackground=c, highlightthickness=2,
                   highlightcolor=c)
    except Exception:
        pass

def default_slot(key):
    return {"label": "", "path": ""}

def default_preset():
    return {k: default_slot(k) for k in KEYS}

def migrate_old_preset(old):
    """Converte il vecchio formato {key: "nome"} nel nuovo {key: {label, path}}."""
    new = {}
    for k in KEYS:
        v = old.get(k, f"Cartella_{k}")
        if isinstance(v, dict):
            new[k] = {"label": v.get("label", ""),
                      "path":  v.get("path", "")}
        else:
            new[k] = {"label": str(v), "path": ""}
    return new

def normalize_config_paths(config):
    """Adatta i percorsi salvati nel config all'utente corrente."""
    current_home = os.path.expanduser("~")
    current_user = os.path.basename(current_home)
    def fix(val):
        if not isinstance(val, str):
            return val
        # Sostituisce /home/altro_utente/ con /home/utente_corrente/
        if val.startswith("/home/"):
            parts = val.split("/", 3)
            if len(parts) >= 3 and parts[2] != current_user:
                parts[2] = current_user
                return "/".join(parts)
        return val
    for slots in config.get("presets", {}).values():
        for slot in slots.values():
            if isinstance(slot, dict) and "path" in slot:
                slot["path"] = fix(slot["path"])
    if "last_source" in config:
        config["last_source"] = fix(config["last_source"])
    return config

def load_config():
    default = {
        "active_preset":   DEFAULT_PRESET,
        "presets":         {DEFAULT_PRESET: default_preset()},
        "sidebar_mode":    "inline",
        "sidebar_presets": 3,
        "keypad_cols":     3,
        "crop_remember":   False,
        "show_images":     True,
        "show_videos":     True,
        "show_pdfs":       True,
        "show_no_ext":     True,
    }
    if not os.path.isfile(CONFIG_FILE):
        return default
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        if "presets" not in data:
            # Vecchio formato piatto
            old = {k: data.get(k, f"Cartella_{k}") for k in KEYS}
            data = {"active_preset": DEFAULT_PRESET,
                    "presets": {DEFAULT_PRESET: migrate_old_preset(old)}}
        else:
            for pname in list(data["presets"].keys()):
                data["presets"][pname] = migrate_old_preset(data["presets"][pname])
        if data.get("active_preset") not in data["presets"]:
            data["active_preset"] = next(iter(data["presets"]))
        return normalize_config_paths(data)
    except Exception:
        return default

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_keypad_cols(config):
    """Numero di colonne preset nel tastierino (1, 2 o 3)."""
    return max(1, min(3, int(config.get("keypad_cols", 3))))

def get_sidebar_mode(config):
    """Modalita sidebar: hidden / inline / popup."""
    return config.get("sidebar_mode", "inline")

def get_sidebar_presets(config):
    """Numero di preset visibili nella sidebar (1, 2 o 3)."""
    return max(1, min(3, int(config.get("sidebar_presets", 3))))

def fmt_size(n):
    """Formatta dimensione file in B/KB/MB."""
    if n < 1024:      return f"{n} B"
    if n < 1024 ** 2: return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


def sanitize_name(name):
    for ch in '/\\:*?"<>|':
        name = name.replace(ch, "")
    return name.strip()

def resolve_path(slot):
    """Restituisce il percorso assoluto della cartella per uno slot."""
    p = slot.get("path", "").strip()
    if p and os.path.isabs(p):
        return p
    label = slot.get("label", "Cartella") or "Cartella"
    return os.path.join(BASE_DEST, label)

# =============================================================================
# SELEZIONE PRESET
# =============================================================================

# =============================================================================
# DIALOGO CONFIGURAZIONE CARTELLE (rinomina + percorso libero)
# =============================================================================

def open_in_filemanager(filepath):
    """Apre il file manager nella cartella del file, evidenziando il file se possibile."""
    if not filepath:
        return
    filepath = os.path.abspath(filepath)
    folder   = os.path.dirname(filepath) if os.path.isfile(filepath) else filepath

    # 1. dbus — più affidabile su GNOME/KDE/Cinnamon
    try:
        uri = "file://" + filepath
        subprocess.Popen([
            "dbus-send", "--session", "--dest=org.freedesktop.FileManager1",
            "--type=method_call", "/org/freedesktop/FileManager1",
            "org.freedesktop.FileManager1.ShowItems",
            f"array:string:{uri}", "string:"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    except FileNotFoundError:
        pass

    # 2. File manager specifici su varie distro
    for fm in ["nautilus", "nemo", "thunar", "dolphin", "pcmanfm",
               "caja", "spacefm", "xdg-open"]:
        if subprocess.run(["which", fm], capture_output=True).returncode == 0:
            try:
                # nautilus/nemo/dolphin accettano il file direttamente
                target = filepath if fm in ("nautilus","nemo","dolphin") else folder
                subprocess.Popen([fm, target],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                continue

    # 2. File manager specifici con supporto --select
    folder_uri = "file://" + folder
    for cmd in [
        ["nemo",    filepath],
        ["nautilus","--select", filepath],
        ["dolphin", "--select", filepath],
        ["caja",    "--select", filepath],
        ["thunar",  folder],
        ["pcmanfm", folder],
        ["xdg-open",folder],
    ]:
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue


def _guess_ext_from_image(img):
    """Indovina l'estensione corretta dal formato Pillow dell'immagine."""
    fmt = (img.format or "").upper()
    return {
        "JPEG": ".jpg", "JPG": ".jpg",
        "PNG":  ".png", "GIF": ".gif",
        "BMP":  ".bmp", "TIFF": ".tiff",
        "WEBP": ".webp",
    }.get(fmt)


def _copy_score(file_info):
    """Punteggio per ordinare i file: 0=originale (prima), 1=probabile copia (dopo)."""
    import re as _re
    name = os.path.basename(file_info["path"]).lower()
    base = os.path.splitext(name)[0]
    # Pattern tipici delle copie
    patterns = [
        r'\bcop[yi]\b', r'\bcopia\b', r'\bcopy\b',
        r'\bduplicate\b', r'\bdoppione\b',
        r'\(\d+\)$',          # es. "foto (1)", "foto (2)"
        r'_\d+$',               # es. "foto_1", "foto_2"
        r'-copy$', r'-copia$',
        r' copy$', r' copia$',
    ]
    for p in patterns:
        if _re.search(p, base):
            return 1
    return 0


def browse_folder_hud(parent, title="Scegli cartella",
                      initial_dir=None, config=None):
    """
    Browser cartelle in stile HUD — alternativa a filedialog.askdirectory.
    Mostra accesso rapido (home, Immagini, Video, Scrivania, dischi),
    un campo percorso digitabile e una lista cartelle navigabile.
    Ritorna il percorso scelto o None se annullato.
    """
    result = [None]
    initial = initial_dir or (
        (config.get("last_browse_dir") or os.path.expanduser("~"))
        if config else os.path.expanduser("~"))
    if not os.path.isdir(initial):
        initial = os.path.expanduser("~")

    win = tk.Toplevel(parent)
    win.withdraw()
    win.title(title)
    win.configure(bg=BG_COLOR)
    win.geometry("560x420")
    win.minsize(400, 300)
    win.resizable(True, True)
    win.transient(parent)
    hud_apply(win)

    win.columnconfigure(0, weight=1)
    win.rowconfigure(1, weight=0)
    win.rowconfigure(2, weight=1)
    win.rowconfigure(3, weight=0)

    # ── Accesso rapido ────────────────────────────────────────────────────────
    quick = tk.Frame(win, bg=BG_COLOR)
    quick.grid(row=0, column=0, sticky="ew", padx=6, pady=(6,2))

    def _add_q(lbl, path, color=None):
        if not os.path.isdir(path):
            return
        tk.Button(quick, text=lbl,
                  font=("TkFixedFont", 8),
                  bg=color or ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=6,
                  activebackground=HIGHLIGHT,
                  command=lambda p=path: _navigate(p)
                  ).pack(side="left", padx=2, ipady=2)

    pics = os.path.expanduser("~/Immagini")
    if not os.path.isdir(pics): pics = os.path.expanduser("~/Pictures")
    vids = os.path.expanduser("~/Video")
    if not os.path.isdir(vids): vids = os.path.expanduser("~/Videos")
    desk = os.path.expanduser("~/Scrivania")
    if not os.path.isdir(desk): desk = os.path.expanduser("~/Desktop")

    _add_q("~",        os.path.expanduser("~"))
    _add_q("Immagini", pics)
    _add_q("Video",    vids)
    _add_q("Scrivania",desk)
    _add_q("/",        "/")

    try:
        with open("/proc/mounts") as mf:
            for ln in mf:
                parts = ln.split()
                if len(parts) >= 2:
                    mp = parts[1]
                    if mp.startswith("/media/") or mp.startswith("/mnt/"):
                        if os.path.isdir(mp):
                            _add_q(f"[{os.path.basename(mp) or mp}]",
                                   mp, color="#1a3a5a")
    except Exception:
        pass

    # ── Barra percorso ────────────────────────────────────────────────────────
    nav = tk.Frame(win, bg=PANEL_COLOR)
    nav.grid(row=1, column=0, sticky="ew")
    nav.columnconfigure(1, weight=1)

    tk.Label(nav, text="Cartella:", font=("TkFixedFont", 8),
             bg=PANEL_COLOR, fg=MUTED_COLOR
             ).grid(row=0, column=0, padx=(8,4), pady=6)
    path_var = tk.StringVar(value=initial)
    path_entry = tk.Entry(nav, textvariable=path_var,
                          font=("TkFixedFont", 9),
                          bg=ACCENT_COLOR, fg=HUD_CYAN,
                          insertbackground=HUD_CYAN,
                          relief="flat", bd=3)
    path_entry.grid(row=0, column=1, sticky="ew", padx=4, ipady=3)
    path_entry.bind("<Return>", lambda e: _navigate(path_var.get()))

    tk.Button(nav, text="->", font=("TkFixedFont", 8),
              bg=SUCCESS, fg="white", relief="flat",
              command=lambda: _navigate(path_var.get())
              ).grid(row=0, column=2, padx=(0,6), pady=6)

    # ── Lista cartelle ────────────────────────────────────────────────────────
    list_fr = tk.Frame(win, bg=BG_COLOR)
    list_fr.grid(row=2, column=0, sticky="nsew", padx=6, pady=2)
    list_fr.rowconfigure(0, weight=1)
    list_fr.columnconfigure(0, weight=1)

    lb = tk.Listbox(list_fr,
                    font=("TkFixedFont", 10),
                    bg=BG_COLOR, fg=TEXT_COLOR,
                    selectbackground=HIGHLIGHT,
                    selectforeground="white",
                    activestyle="none",
                    relief="flat", bd=0)
    vsb = tk.Scrollbar(list_fr, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=vsb.set)
    lb.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    lb.bind("<Button-4>", lambda e: lb.yview_scroll(-1, "units"))
    lb.bind("<Button-5>", lambda e: lb.yview_scroll(1, "units"))
    lb.bind("<MouseWheel>", lambda e: lb.yview_scroll(-1 if e.delta > 0 else 1, "units"))

    _current = [initial]

    def _navigate(path):
        path = os.path.expanduser(path.strip())
        if not os.path.isdir(path):
            return
        _current[0] = path
        path_var.set(path)
        lb.delete(0, tk.END)
        try:
            entries = sorted(
                [e for e in os.listdir(path)
                 if os.path.isdir(os.path.join(path, e)) and not e.startswith(".")],
                key=str.lower)
            for e in entries:
                lb.insert(tk.END, f"  {e}")
            # Aggiungi ".." se non siamo alla root
            if path != "/":
                lb.insert(0, "  ..")
        except PermissionError:
            lb.insert(tk.END, "  (accesso negato)")

    def _on_dbl(event):
        sel = lb.curselection()
        if not sel:
            return
        name = lb.get(sel[0]).strip()
        if name == "..":
            _navigate(os.path.dirname(_current[0]))
        else:
            _navigate(os.path.join(_current[0], name))

    lb.bind("<Double-Button-1>", _on_dbl)
    lb.bind("<Return>", _on_dbl)
    lb.bind("<KP_Enter>", _on_dbl)

    # ── Bottoni ───────────────────────────────────────────────────────────────
    bot = tk.Frame(win, bg=PANEL_COLOR)
    bot.grid(row=3, column=0, sticky="ew")

    cur_lbl = tk.Label(bot, text="",
                       font=("TkFixedFont", 8),
                       bg=PANEL_COLOR, fg=MUTED_COLOR)
    cur_lbl.pack(side="left", padx=10, pady=6)

    def _update_cur_lbl(*_):
        p = _current[0]
        short = p if len(p) <= 40 else "..." + p[-37:]
        cur_lbl.config(text=short)
    path_var.trace_add("write", _update_cur_lbl)

    def _confirm():
        sel = lb.curselection()
        if sel:
            name = lb.get(sel[0]).strip()
            if name != "..":
                chosen = os.path.join(_current[0], name)
                if os.path.isdir(chosen):
                    _current[0] = chosen
        result[0] = _current[0]
        if config is not None:
            config["last_browse_dir"] = result[0]
        win.destroy()

    tk.Button(bot, text="Scegli questa cartella",
              font=("TkFixedFont", 9, "bold"),
              bg=SUCCESS, fg="white", relief="flat", padx=12,
              command=_confirm).pack(side="right", padx=6, pady=6, ipady=4)
    tk.Button(bot, text="Annulla",
              font=("TkFixedFont", 9),
              bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=8,
              command=win.destroy).pack(side="right", padx=(0,2), pady=6, ipady=4)

    win.bind("<Escape>", lambda e: win.destroy())

    _navigate(initial)

    win.update_idletasks()
    pw, ph = win.winfo_reqwidth(), win.winfo_reqheight()
    px = parent.winfo_rootx() + (parent.winfo_width()  - pw) // 2
    py = parent.winfo_rooty() + (parent.winfo_height() - ph) // 2
    win.geometry(f"+{max(0,px)}+{max(0,py)}")
    win.deiconify()
    win.grab_set()
    win.wait_window()

    return result[0]


class DuplicateFinder:
    """
    Finestra ricerca doppioni — 3 modalità:
      Tab 1 — Contenuto  : SHA256 su una o più cartelle
      Tab 2 — Rapida     : nome + dimensione, nessuna lettura file
      Tab 3 — A vs B     : confronta due cartelle, mostra file in comune
    """

    def __init__(self, parent, sorter, initial_dir=None):
        self.sorter   = sorter
        self._stop    = False
        self._thread  = None

        win = tk.Toplevel(parent)
        win.title("Cerca doppioni")
        win.configure(bg=BG_COLOR)
        win.geometry("900x620")
        win.minsize(700, 450)
        hud_apply(win)
        self.win = win
        win.bind("<Escape>", lambda e: self._on_close())
        win.protocol("WM_DELETE_WINDOW", self._on_close)

        self._initial_dir = initial_dir or os.path.expanduser("~")
        self._build()

    # ── Layout principale ─────────────────────────────────────────────────────

    def _build(self):
        w = self.win
        w.columnconfigure(0, weight=1)
        w.rowconfigure(1, weight=1)
        w.rowconfigure(2, weight=0)

        # Tab bar
        tab_bar = tk.Frame(w, bg=PANEL_COLOR)
        tab_bar.grid(row=0, column=0, sticky="ew")
        self._tab_btns = {}
        self._current_tab = "sha"
        tabs = [("sha",   "  Contenuto (SHA256)  "),
                ("quick", "  Rapida (nome+dim)   "),
                ("ab",    "  Confronta A vs B    ")]
        for key, label in tabs:
            b = tk.Button(tab_bar, text=label,
                          font=("TkFixedFont", 9),
                          relief="flat", bd=0, padx=4, pady=4,
                          activebackground=BG_COLOR, activeforeground=HIGHLIGHT,
                          command=lambda k=key: self._switch_tab(k))
            b.pack(side="left")
            self._tab_btns[key] = b

        # Area contenuto tab
        self._content = tk.Frame(w, bg=BG_COLOR)
        self._content.grid(row=1, column=0, sticky="nsew")
        self._content.columnconfigure(0, weight=1)
        self._content.rowconfigure(0, weight=0)

        self._switch_tab("sha")

    def _switch_tab(self, key):
        self._stop = True   # ferma eventuale scan in corso
        self._current_tab = key
        for k, b in self._tab_btns.items():
            b.config(bg=BG_COLOR if k == key else PANEL_COLOR,
                     fg=HIGHLIGHT if k == key else MUTED_COLOR,
                     font=("TkFixedFont", 9, "bold") if k == key
                          else ("TkFixedFont", 9))
        for child in self._content.winfo_children():
            child.destroy()
        # Reset rowconfigure per evitare che row=0 si espanda
        self._content.rowconfigure(0, weight=0)
        self._content.rowconfigure(1, weight=1)
        if key == "sha":
            self._build_sha_tab()
        elif key == "quick":
            self._build_quick_tab()
        else:
            self._build_ab_tab()

    # ── Componenti riutilizzabili ─────────────────────────────────────────────

    def _make_folder_list(self, parent, multi=True):
        """
        Pannello lista cartelle con bottoni Aggiungi/Rimuovi.
        Ritorna (frame, getter) dove getter() → lista di (path, recursive).
        """
        fr = tk.Frame(parent, bg=BG_COLOR)

        # Lista
        lst_fr = tk.Frame(fr, bg=ACCENT_COLOR)
        lst_fr.pack(fill="x", padx=0, pady=(0,2))
        lst_fr.columnconfigure(0, weight=1)

        entries = []   # lista di (path_var, rec_var, row_frame)

        def _add(path=""):
            row = tk.Frame(lst_fr, bg=ACCENT_COLOR)
            row.pack(fill="x", padx=4, pady=2)
            row.columnconfigure(1, weight=1)

            rec_var  = tk.BooleanVar(value=True)
            path_var = tk.StringVar(value=path)

            tk.Checkbutton(row, text="Sub",
                           variable=rec_var,
                           font=("TkFixedFont", 7),
                           bg=ACCENT_COLOR, fg=MUTED_COLOR,
                           selectcolor=BG_COLOR,
                           activebackground=ACCENT_COLOR
                           ).grid(row=0, column=0, padx=(4,2))

            tk.Entry(row, textvariable=path_var,
                     font=("TkFixedFont", 8),
                     bg=BG_COLOR, fg=HUD_CYAN,
                     insertbackground=HUD_CYAN,
                     relief="flat", bd=2
                     ).grid(row=0, column=1, sticky="ew", padx=2, ipady=2)

            def _browse_this():
                d = filedialog.askdirectory(
                    parent=self.win,
                    initialdir=path_var.get() or self._initial_dir)
                if d:
                    path_var.set(d)
            tk.Button(row, text="...",
                      font=("TkFixedFont", 7), bg=PANEL_COLOR, fg=TEXT_COLOR,
                      relief="flat", padx=4,
                      command=_browse_this
                      ).grid(row=0, column=2, padx=2, ipady=2)

            def _remove():
                entries.remove((path_var, rec_var, row))
                row.destroy()
            tk.Button(row, text="x",
                      font=("TkFixedFont", 7), bg=PANEL_COLOR, fg="#c0392b",
                      relief="flat", padx=4,
                      command=_remove
                      ).grid(row=0, column=3, padx=(0,4), ipady=2)

            entries.append((path_var, rec_var, row))

        _add(self._initial_dir)

        # Barra aggiungi (solo se multi)
        if multi:
            add_btn = tk.Button(fr, text="+ Aggiungi cartella",
                                font=("TkFixedFont", 8),
                                bg=PANEL_COLOR, fg=HUD_CYAN,
                                relief="flat", padx=8,
                                command=lambda: _add())
            add_btn.pack(anchor="w", pady=(2,0))

        def _get():
            result = []
            for pv, rv, _ in entries:
                p = pv.get().strip()
                if p and os.path.isdir(p):
                    result.append((p, rv.get()))
            return result

        return fr, _get

    def _make_results_area(self, parent, row_paths=None):
        """Lista risultati + barra stato + bottoni azione."""
        fr = tk.Frame(parent, bg=BG_COLOR)
        fr.columnconfigure(0, weight=1)
        fr.rowconfigure(0, weight=1)
        if row_paths is None:
            row_paths = {}

        # Progresso
        prog_fr = tk.Frame(fr, bg=BG_COLOR)
        prog_fr.grid(row=1, column=0, sticky="ew", padx=8, pady=(0,2))
        prog_fr.columnconfigure(0, weight=1)

        status_lbl = tk.Label(prog_fr, text="",
                              font=("TkFixedFont", 8),
                              bg=BG_COLOR, fg=MUTED_COLOR, anchor="w")
        status_lbl.grid(row=0, column=0, sticky="ew")

        prog_canvas = tk.Canvas(prog_fr, bg=ACCENT_COLOR,
                                height=3, highlightthickness=0)
        prog_canvas.grid(row=1, column=0, sticky="ew")
        prog_bar = prog_canvas.create_rectangle(0, 0, 0, 3,
                                                fill=HUD_CYAN, width=0)

        # Listbox
        list_fr = tk.Frame(fr, bg=BG_COLOR)
        list_fr.grid(row=0, column=0, sticky="nsew")
        list_fr.rowconfigure(0, weight=1)
        list_fr.columnconfigure(0, weight=1)

        lb = tk.Listbox(list_fr, font=("TkFixedFont", 9),
                        bg=BG_COLOR, fg=TEXT_COLOR,
                        selectbackground=HIGHLIGHT,
                        selectforeground="white",
                        activestyle="none",
                        relief="flat", bd=0,
                        selectmode=tk.EXTENDED)
        vsb = tk.Scrollbar(list_fr, orient="vertical",   command=lb.yview)
        hsb = tk.Scrollbar(list_fr, orient="horizontal", command=lb.xview)
        lb.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        lb.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        lb.bind("<Button-4>", lambda e: (lb.yview_scroll(-1, "units"), "break")[1])
        lb.bind("<Button-5>", lambda e: (lb.yview_scroll( 1, "units"), "break")[1])
        lb.bind("<MouseWheel>", lambda e: (lb.yview_scroll(-1 if e.delta > 0 else 1, "units"), "break")[1])

        # Barra azioni in fondo
        bot = tk.Frame(fr, bg=PANEL_COLOR)
        bot.grid(row=2, column=0, sticky="ew")

        result_lbl = tk.Label(bot, text="",
                              font=("TkFixedFont", 9),
                              bg=PANEL_COLOR, fg=MUTED_COLOR)
        result_lbl.pack(side="left", padx=10, pady=5)

        # Chiudi per primo → appare più a destra
        tk.Button(bot, text="Chiudi",
                  font=("TkFixedFont", 8), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=8,
                  command=self._on_close
                  ).pack(side="right", padx=(0,6), pady=5, ipady=3)

        stop_btn = tk.Button(bot, text="Stop",
                             font=("TkFixedFont", 8, "bold"),
                             bg=HIGHLIGHT, fg="white",
                             relief="flat", padx=8,
                             state="disabled",
                             command=lambda: setattr(self, '_stop', True))
        stop_btn.pack(side="right", padx=6, pady=5, ipady=3)

        clean_btn = tk.Button(bot,
                              text="Cestina tutti i duplicati (mantieni 1)",
                              font=("TkFixedFont", 8, "bold"),
                              bg="#c0392b", fg="white",
                              relief="flat", padx=10,
                              state="disabled")
        clean_btn.pack(side="right", padx=6, pady=5, ipady=3)

        # Bottone "Cestina selezionati" — visibile solo con selezione attiva
        sel_btn = tk.Button(bot, text="Cestina selezionati (0)",
                            font=("TkFixedFont", 8, "bold"),
                            bg="#8e44ad", fg="white",
                            relief="flat", padx=10,
                            state="disabled")
        sel_btn.pack(side="right", padx=6, pady=5, ipady=3)

        # Aggiorna il bottone quando cambia la selezione
        def _on_select(e=None):
            sel = lb.curselection()
            # Considera solo le righe che corrispondono a file reali
            files = [row_paths.get(i) for i in sel if row_paths.get(i)]
            n = len(files)
            if n > 0:
                sel_btn.config(state="normal",
                               text=f"Cestina selezionati ({n})")
            else:
                sel_btn.config(state="disabled",
                               text="Cestina selezionati (0)")

        lb.bind("<<ListboxSelect>>", _on_select)

        def _trash_selected():
            sel = lb.curselection()
            files = [(i, row_paths.get(i)) for i in sel if row_paths.get(i)]
            if not files:
                return
            n = len(files)
            if not messagebox.askyesno(
                    "Conferma",
                    f"Spostare nel cestino {n} file selezionati?",
                    parent=self.win):
                return
            trashed = 0
            for idx, fpath in files:
                if os.path.isfile(fpath) and send_to_trash(fpath):
                    lb.delete(idx)
                    lb.insert(idx, tk_safe(f"  [CESTINATO]  {fpath}"))
                    lb.itemconfig(idx, fg=MUTED_COLOR)
                    row_paths[idx] = None
                    trashed += 1
            result_lbl.config(text=f"Cestinati {trashed} file.")
            sel_btn.config(state="disabled", text="Cestina selezionati (0)")

        sel_btn.config(command=_trash_selected)

        return fr, lb, status_lbl, prog_canvas, prog_bar, result_lbl, clean_btn, stop_btn, bot

    # ── TAB 1: SHA256 ─────────────────────────────────────────────────────────

    def _build_sha_tab(self):
        f = self._content
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)

        # Pannello cartelle
        top = tk.Frame(f, bg=BG_COLOR)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(4,0))
        top.columnconfigure(0, weight=1)

        tk.Label(top, text="Cartelle da analizzare (confronto esatto SHA256):",
                 font=("TkFixedFont", 8), bg=BG_COLOR,
                 fg=MUTED_COLOR).grid(row=0, column=0, sticky="w", pady=(0,3))

        folder_fr, get_folders = self._make_folder_list(top, multi=True)
        folder_fr.grid(row=1, column=0, sticky="ew", pady=(2,4))

        # Area risultati — creata prima così stop_btn è disponibile
        row_paths = {}
        res_fr, lb, status_lbl, prog_canvas, prog_bar, result_lbl, clean_btn, stop_btn, bot_sha = \
            self._make_results_area(f, row_paths)
        res_fr.grid(row=1, column=0, sticky="nsew", pady=(0,0))

        lb.bind("<Button-3>", lambda e: self._ctx(e, lb, row_paths))
        lb.bind("<Double-Button-1>", lambda e: self._open_lb(lb, row_paths))
        clean_btn.config(command=lambda: self._bulk_trash_lb(
            lb, row_paths, result_lbl))

        scan_btn = tk.Button(bot_sha, text="Avvia scansione SHA256",
                             font=("TkFixedFont", 9, "bold"),
                             bg=SUCCESS, fg="white",
                             relief="flat", padx=12,
                             command=lambda: self._run_sha(
                                 get_folders, scan_btn,
                                 result_lbl, status_lbl,
                                 prog_canvas, prog_bar,
                                 lb, clean_btn, row_paths, stop_btn))
        scan_btn.pack(side="left", padx=(6,4), pady=5, ipady=3)

        # Ordinamento risultati
        tk.Label(bot_sha, text="Ordina:",
                 font=("TkFixedFont", 7), bg=BG_COLOR, fg=MUTED_COLOR
                 ).pack(side="left", padx=(10,2))
        self._sha_sort_var = tk.StringVar(value="size")
        for sval, stxt in [("size","Dimensione"),("folder","Cartella"),("name","Nome file")]:
            tk.Radiobutton(bot_sha, text=stxt, variable=self._sha_sort_var,
                           value=sval,
                           font=("TkFixedFont", 7), bg=BG_COLOR, fg=TEXT_COLOR,
                           selectcolor=BG_COLOR, activebackground=BG_COLOR,
                           activeforeground=HUD_CYAN,
                           command=lambda lb=lb, rp=row_paths: self._resort_dups(lb, rp)
                           ).pack(side="left", padx=2)

    def _resort_dups(self, lb, row_paths):
        """Riordina i risultati già in listbox per dimensione/cartella/nome."""
        sort_mode = getattr(self, '_sha_sort_var', None)
        if not sort_mode: return
        mode = sort_mode.get()
        # Raccoglie gruppi dalla listbox tramite row_paths
        groups = {}  # header_idx: [file_idx, ...]
        cur_header = None
        for i in range(lb.size()):
            fp = row_paths.get(i)
            if fp is None:
                cur_header = i
                groups[cur_header] = []
            elif cur_header is not None:
                groups[cur_header].append(i)
        if not groups: return
        # Leggi testo e path attuali
        items = [(lb.get(i), row_paths.get(i)) for i in range(lb.size())]
        colors = [lb.itemcget(i, 'fg') for i in range(lb.size())]
        bgs    = [lb.itemcget(i, 'background') for i in range(lb.size())]
        # Costruisci lista gruppi
        group_list = []
        for hidx, fidxs in groups.items():
            hdr = items[hidx]
            files = [(items[i], colors[i], bgs[i]) for i in fidxs]
            # key per ordinamento
            if mode == 'size':
                key = -max((os.path.getsize(f[0][1]) for f in files
                            if f[0][1] and os.path.isfile(f[0][1])), default=0)
            elif mode == 'folder':
                key = os.path.dirname(files[0][0][1] or '') if files else ''
            else:  # name
                key = os.path.basename(files[0][0][1] or '') if files else ''
            group_list.append((key, hdr, files))
        group_list.sort(key=lambda x: x[0])
        # Ricostruisci listbox
        lb.delete(0, tk.END)
        row_paths.clear()
        idx = 0
        for _, hdr, files in group_list:
            lb.insert(tk.END, tk_safe(hdr[0]))
            lb.itemconfig(idx, fg='#ff88cc', background=PANEL_COLOR)
            row_paths[idx] = None; idx += 1
            for (txt, fp), fc, bg in files:
                lb.insert(tk.END, tk_safe(txt))
                lb.itemconfig(idx, fg=fc)
                row_paths[idx] = fp; idx += 1
            lb.insert(tk.END, '')
            row_paths[idx] = None; idx += 1

    def _run_sha(self, get_folders, scan_btn, result_lbl, status_lbl,
                 prog_canvas, prog_bar, lb, clean_btn, row_paths, stop_btn=None):
        folders = get_folders()
        if not folders:
            messagebox.showwarning("Cartelle", "Aggiungi almeno una cartella.",
                                   parent=self.win)
            return
        lb.delete(0, tk.END)
        row_paths.clear()
        result_lbl.config(text="")
        clean_btn.config(state="disabled")
        scan_btn.config(state="disabled", text="Scansione...")
        if stop_btn and stop_btn.winfo_exists(): stop_btn.config(state="normal")
        self._stop = False

        threading.Thread(
            target=self._worker_sha,
            args=(folders, lb, status_lbl, prog_canvas, prog_bar,
                  result_lbl, clean_btn, scan_btn, row_paths, stop_btn),
            daemon=True).start()

    def _worker_sha(self, folders, lb, status_lbl, prog_canvas, prog_bar,
                    result_lbl, clean_btn, scan_btn, row_paths, stop_btn=None):
        hashes, duplicates, all_files = {}, {}, []

        for folder, recursive in folders:
            self._set_st(status_lbl, f"Raccolta file: {folder}")
            try:
                if recursive:
                    for root, _, files in os.walk(folder):
                        for f in files:
                            all_files.append(os.path.join(root, f))
                else:
                    all_files += [os.path.join(folder, f)
                                  for f in os.listdir(folder)
                                  if os.path.isfile(os.path.join(folder, f))]
            except OSError:
                pass

        media = [f for f in all_files
                 if detect_media_type(f) in MEDIA_EXTENSIONS
                 or os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS]
        total = len(media)
        self._set_st(status_lbl, f"Analisi {total} file...")

        for idx, fpath in enumerate(media):
            if self._stop:
                def _rst():
                    if scan_btn.winfo_exists(): scan_btn.config(state="normal", text="Avvia scansione SHA256")
                    if stop_btn and stop_btn.winfo_exists(): stop_btn.config(state="disabled")
                self.win.after(0, _rst)
                return
            # Aggiorna UI ogni 10 file per non intasare X11
            if idx % 10 == 0:
                self._set_st(status_lbl,
                             tk_safe(f"{idx+1}/{total}  {os.path.basename(fpath)[:50]}"))
                self._set_prog(prog_canvas, prog_bar, idx+1, total)
            try:
                size = os.path.getsize(fpath)
                if size == 0:
                    continue
                h = self._hash_file(fpath)
                info = {"path": fpath, "size": size,
                        "ext": os.path.splitext(fpath)[1].upper() or "?"}
                if h in hashes:
                    if h not in duplicates:
                        duplicates[h] = [hashes[h]]
                    duplicates[h].append(info)
                else:
                    hashes[h] = info
            except Exception:
                continue

        self.win.after(0, lambda: self._show_dup_results(
            duplicates, total, lb, status_lbl, prog_canvas, prog_bar,
            result_lbl, clean_btn, scan_btn,
            row_paths, "Avvia scansione SHA256", stop_btn))

    # ── TAB 2: Rapida ─────────────────────────────────────────────────────────

    def _build_quick_tab(self):
        f = self._content
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)

        top = tk.Frame(f, bg=BG_COLOR)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(4,0))
        top.columnconfigure(0, weight=1)

        tk.Label(top, text="Cartelle da analizzare (confronto nome + dimensione):",
                 font=("TkFixedFont", 8), bg=BG_COLOR,
                 fg=MUTED_COLOR).grid(row=0, column=0, sticky="w", pady=(0,3))

        folder_fr, get_folders = self._make_folder_list(top, multi=True)
        folder_fr.grid(row=1, column=0, sticky="ew", pady=(2,4))

        # Opzioni modalità
        opt_fr = tk.Frame(top, bg=BG_COLOR)
        opt_fr.grid(row=2, column=0, sticky="w", pady=(0,4))

        mode_var = tk.StringVar(value="name_size")
        tk.Label(opt_fr, text="Criteri:",
                 font=("TkFixedFont", 8), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left", padx=(0,6))
        for val, txt in [("name_size", "Nome + Dimensione"),
                         ("name",      "Solo Nome"),
                         ("size",      "Solo Dimensione")]:
            tk.Radiobutton(opt_fr, text=txt, variable=mode_var, value=val,
                           font=("TkFixedFont", 8), bg=BG_COLOR,
                           fg=TEXT_COLOR, selectcolor=BG_COLOR,
                           activebackground=BG_COLOR,
                           activeforeground=HUD_CYAN
                           ).pack(side="left", padx=4)

        row_paths = {}
        res_fr, lb, status_lbl, prog_canvas, prog_bar, result_lbl, clean_btn, stop_btn, bot_q = \
            self._make_results_area(f, row_paths)
        res_fr.grid(row=1, column=0, sticky="nsew", pady=(0,0))

        lb.bind("<Button-3>", lambda e: self._ctx(e, lb, row_paths))
        lb.bind("<Double-Button-1>", lambda e: self._open_lb(lb, row_paths))
        clean_btn.config(command=lambda: self._bulk_trash_lb(
            lb, row_paths, result_lbl))

        scan_btn = tk.Button(bot_q, text="Avvia scansione rapida",
                             font=("TkFixedFont", 9, "bold"),
                             bg=SUCCESS, fg="white",
                             relief="flat", padx=12,
                             command=lambda: self._run_quick(
                                 get_folders, mode_var.get(), scan_btn,
                                 result_lbl, status_lbl,
                                 prog_canvas, prog_bar,
                                 lb, clean_btn, row_paths, stop_btn))
        scan_btn.pack(side="left", padx=(6,4), pady=5, ipady=3)

    def _run_quick(self, get_folders, mode, scan_btn, result_lbl, status_lbl,
                   prog_canvas, prog_bar, lb, clean_btn, row_paths, stop_btn=None):
        folders = get_folders()
        if not folders:
            messagebox.showwarning("Cartelle", "Aggiungi almeno una cartella.",
                                   parent=self.win)
            return
        lb.delete(0, tk.END)
        row_paths.clear()
        result_lbl.config(text="")
        clean_btn.config(state="disabled")
        scan_btn.config(state="disabled", text="Scansione...")
        if stop_btn and stop_btn.winfo_exists(): stop_btn.config(state="normal")
        self._stop = False

        threading.Thread(
            target=self._worker_quick,
            args=(folders, mode, lb, status_lbl, prog_canvas, prog_bar,
                  result_lbl, clean_btn, scan_btn, row_paths, stop_btn),
            daemon=True).start()

    def _worker_quick(self, folders, mode, lb, status_lbl, prog_canvas,
                      prog_bar, result_lbl, clean_btn, scan_btn, row_paths, stop_btn=None):
        all_files = []
        for folder, recursive in folders:
            self._set_st(status_lbl, f"Raccolta: {folder}")
            try:
                if recursive:
                    for root, _, files in os.walk(folder):
                        for fn in files:
                            all_files.append(os.path.join(root, fn))
                else:
                    all_files += [os.path.join(folder, fn)
                                  for fn in os.listdir(folder)
                                  if os.path.isfile(os.path.join(folder, fn))]
            except OSError:
                pass

        media = [f for f in all_files
                 if detect_media_type(f) in MEDIA_EXTENSIONS
                 or os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS]
        total = len(media)
        self._set_st(status_lbl, f"Indicizzazione {total} file...")

        groups = {}
        for idx, fpath in enumerate(media):
            if self._stop:
                def _rst():
                    if scan_btn.winfo_exists(): scan_btn.config(state="normal", text="Avvia scansione rapida")
                    if stop_btn and stop_btn.winfo_exists(): stop_btn.config(state="disabled")
                self.win.after(0, _rst)
                return
            self._set_prog(prog_canvas, prog_bar, idx+1, total)
            try:
                size = os.path.getsize(fpath)
                name = os.path.basename(fpath).lower()
                if mode == "name_size":
                    key = (name, size)
                elif mode == "name":
                    key = name
                else:
                    key = size
                info = {"path": fpath, "size": size,
                        "ext": os.path.splitext(fpath)[1].upper() or "?"}
                groups.setdefault(key, []).append(info)
            except Exception:
                continue

        duplicates = {k: v for k, v in groups.items() if len(v) > 1}
        self.win.after(0, lambda: self._show_dup_results(
            duplicates, total, lb, status_lbl, prog_canvas, prog_bar,
            result_lbl, clean_btn, scan_btn,
            row_paths, "Avvia scansione rapida", stop_btn,
            label_hash=False))

    # ── TAB 3: A vs B ─────────────────────────────────────────────────────────

    def _build_ab_tab(self):
        """Tab confronto A vs B — layout a colonne, barra in fondo coerente."""
        f = self._content
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)

        # ── Pannello superiore ────────────────────────────────────────────────
        top = tk.Frame(f, bg=BG_COLOR)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(4,0))
        top.columnconfigure(1, weight=1)

        tk.Label(top, text="Confronta A vs B — mostra i file presenti in entrambe le cartelle:",
                 font=("TkFixedFont", 8), bg=BG_COLOR,
                 fg=MUTED_COLOR).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0,4))

        self._ab_vars = {}
        for row_i, (lbl, color) in enumerate([("A", HUD_CYAN), ("B", "#ffaa44")]):
            tk.Label(top, text=f"Cartella {lbl}:",
                     font=("TkFixedFont", 9, "bold"),
                     bg=BG_COLOR, fg=color).grid(
                     row=row_i+1, column=0, sticky="w", padx=(0,6), pady=2)
            pvar = tk.StringVar(value=self._initial_dir if lbl == "A" else "")
            tk.Entry(top, textvariable=pvar,
                     font=("TkFixedFont", 9), bg=ACCENT_COLOR, fg=color,
                     insertbackground=color, relief="flat", bd=3
                     ).grid(row=row_i+1, column=1, sticky="ew", padx=4, ipady=3, pady=2)
            def _browse(v=pvar):
                d = browse_folder_hud(self.win, title="Scegli cartella",
                    initial_dir=v.get() or self._initial_dir)
                if d: v.set(d)
            tk.Button(top, text="...",
                      font=("TkFixedFont", 8), bg=PANEL_COLOR, fg=TEXT_COLOR,
                      relief="flat", padx=6, command=_browse
                      ).grid(row=row_i+1, column=2, padx=(0,4), pady=2, ipady=3)
            rec_var = tk.BooleanVar(value=True)
            tk.Checkbutton(top, text="Sottocartelle", variable=rec_var,
                           font=("TkFixedFont", 8), bg=BG_COLOR, fg=MUTED_COLOR,
                           selectcolor=BG_COLOR, activebackground=BG_COLOR
                           ).grid(row=row_i+1, column=3, padx=6)
            self._ab_vars[lbl] = (pvar, rec_var)

        opt_fr = tk.Frame(top, bg=BG_COLOR)
        opt_fr.grid(row=3, column=0, columnspan=4, sticky="w", pady=(2,0))
        tk.Label(opt_fr, text="Metodo:",
                 font=("TkFixedFont", 8), bg=BG_COLOR, fg=MUTED_COLOR
                 ).pack(side="left", padx=(0,6))
        ab_mode_var = tk.StringVar(value="sha")
        for val, txt in [("sha",       "SHA256 (esatto)"),
                         ("name_size", "Nome + Dimensione"),
                         ("size",      "Solo Dimensione"),
                         ("name",      "Solo Nome")]:
            tk.Radiobutton(opt_fr, text=txt, variable=ab_mode_var, value=val,
                           font=("TkFixedFont", 8), bg=BG_COLOR,
                           fg=TEXT_COLOR, selectcolor=BG_COLOR,
                           activebackground=BG_COLOR, activeforeground=HUD_CYAN
                           ).pack(side="left", padx=4)

        # ── Area risultati a colonne ──────────────────────────────────────────
        res_outer = tk.Frame(f, bg=BG_COLOR)
        res_outer.grid(row=1, column=0, sticky="nsew")
        res_outer.columnconfigure(0, weight=1)
        res_outer.columnconfigure(1, weight=1)
        res_outer.rowconfigure(1, weight=1)

        for ci, (lbl, color) in enumerate([("A", HUD_CYAN), ("B", "#ffaa44")]):
            hdr = tk.Frame(res_outer, bg=ACCENT_COLOR)
            hdr.grid(row=0, column=ci, sticky="ew",
                     padx=(4 if ci == 0 else 1, 1 if ci == 0 else 4))
            tk.Label(hdr, text=f"  Cartella {lbl}",
                     font=("TkFixedFont", 9, "bold"),
                     bg=ACCENT_COLOR, fg=color).pack(side="left", pady=2)

        self._lb_a = tk.Listbox(res_outer, font=("TkFixedFont", 8),
                                bg=BG_COLOR, fg=HUD_CYAN,
                                selectbackground=HIGHLIGHT, selectforeground="white",
                                activestyle="none", relief="flat", bd=0,
                                exportselection=False)
        self._lb_b = tk.Listbox(res_outer, font=("TkFixedFont", 8),
                                bg=BG_COLOR, fg="#ffaa44",
                                selectbackground="#5a3a00", selectforeground="white",
                                activestyle="none", relief="flat", bd=0,
                                exportselection=False)

        vsb = ttk.Scrollbar(res_outer, orient="vertical")
        vsb.grid(row=1, column=2, sticky="ns")

        def _scroll_both(*args):
            self._lb_a.yview(*args)
            self._lb_b.yview(*args)
        vsb.config(command=_scroll_both)
        self._lb_a.config(yscrollcommand=lambda *a: (vsb.set(*a), self._lb_b.yview_moveto(a[0])))
        self._lb_b.config(yscrollcommand=lambda *a: (vsb.set(*a), self._lb_a.yview_moveto(a[0])))
        self._lb_a.grid(row=1, column=0, sticky="nsew", padx=(4,1))
        self._lb_b.grid(row=1, column=1, sticky="nsew", padx=(1,0))

        for lb in (self._lb_a, self._lb_b):
            lb.bind("<Button-4>", lambda e: _scroll_both("scroll", -1, "units"))
            lb.bind("<Button-5>", lambda e: _scroll_both("scroll",  1, "units"))
            lb.bind("<MouseWheel>",
                    lambda e: _scroll_both("scroll", -1 if e.delta>0 else 1, "units"))

        self._ab_row_a = {}
        self._ab_row_b = {}

        def _sync_sel(lb_src, lb_dst):
            sel = lb_src.curselection()
            if sel:
                lb_dst.selection_clear(0, tk.END)
                lb_dst.selection_set(sel[0])
                lb_dst.see(sel[0])
        self._lb_a.bind("<<ListboxSelect>>", lambda e: _sync_sel(self._lb_a, self._lb_b))
        self._lb_b.bind("<<ListboxSelect>>", lambda e: _sync_sel(self._lb_b, self._lb_a))

        def _open_ab(lb, row_map, e=None):
            sel = lb.curselection()
            if not sel: return
            fp = row_map.get(sel[0])
            if fp and os.path.isfile(fp):
                subprocess.Popen(["xdg-open", fp],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._lb_a.bind("<Double-Button-1>", lambda e: _open_ab(self._lb_a, self._ab_row_a))
        self._lb_b.bind("<Double-Button-1>", lambda e: _open_ab(self._lb_b, self._ab_row_b))

        def _ctx_ab(lb, row_map, e):
            idx = lb.nearest(e.y)
            fp  = row_map.get(idx)
            if not fp: return
            lb.selection_clear(0, tk.END); lb.selection_set(idx)
            menu = tk.Menu(self.win, tearoff=0,
                           bg=PANEL_COLOR, fg=TEXT_COLOR,
                           activebackground=HIGHLIGHT, activeforeground="white",
                           relief="flat")
            menu.add_command(label="Apri file",
                             command=lambda: subprocess.Popen(
                                 ["xdg-open", fp],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            menu.add_command(label="Mostra in file manager",
                             command=lambda: open_in_filemanager(fp))
            menu.add_separator()
            menu.add_command(label="Cestina questo file",
                             command=lambda: self._trash_ab(idx, fp, lb, row_map))
            # <Unmap> rimosso: distruggeva il menu prima del click
            menu.tk_popup(e.x_root, e.y_root)
        self._lb_a.bind("<Button-3>", lambda e: _ctx_ab(self._lb_a, self._ab_row_a, e))
        self._lb_b.bind("<Button-3>", lambda e: _ctx_ab(self._lb_b, self._ab_row_b, e))

        # ── Barra progresso (sopra barra bottoni) ────────────────────────────
        prog_fr = tk.Frame(f, bg=BG_COLOR)
        prog_fr.grid(row=2, column=0, sticky="ew", padx=8, pady=(0,2))
        prog_fr.columnconfigure(0, weight=1)
        self._ab_status_lbl = tk.Label(prog_fr, text="",
                                       font=("TkFixedFont", 8),
                                       bg=BG_COLOR, fg=MUTED_COLOR, anchor="w")
        self._ab_status_lbl.grid(row=0, column=0, sticky="ew")
        self._ab_prog_canvas = tk.Canvas(prog_fr, bg=ACCENT_COLOR,
                                         height=3, highlightthickness=0)
        self._ab_prog_canvas.grid(row=1, column=0, sticky="ew")
        self._ab_prog_bar = self._ab_prog_canvas.create_rectangle(
            0, 0, 0, 3, fill=HUD_CYAN, width=0)

        # ── Barra bottoni in fondo (coerente con SHA/Rapida) ─────────────────
        bot = tk.Frame(f, bg=PANEL_COLOR)
        bot.grid(row=3, column=0, sticky="ew")

        self._ab_result_lbl = tk.Label(bot, text="",
                                       font=("TkFixedFont", 9),
                                       bg=PANEL_COLOR, fg=MUTED_COLOR)
        self._ab_result_lbl.pack(side="left", padx=10, pady=5)

        # Chiudi per primo → appare più a destra
        tk.Button(bot, text="Chiudi",
                  font=("TkFixedFont", 8), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=8,
                  command=self._on_close
                  ).pack(side="right", padx=(0,6), pady=5, ipady=3)

        stop_btn = tk.Button(bot, text="Stop",
                             font=("TkFixedFont", 8, "bold"),
                             bg=HIGHLIGHT, fg="white",
                             relief="flat", padx=8, state="disabled",
                             command=lambda: setattr(self, "_stop", True))
        stop_btn.pack(side="right", padx=6, pady=5, ipady=3)

        self._ab_clean_btn = tk.Button(bot,
                             text="Cestina tutti i duplicati di B (mantieni A)",
                             font=("TkFixedFont", 8, "bold"),
                             bg="#c0392b", fg="white",
                             relief="flat", padx=10, state="disabled",
                             command=lambda: self._bulk_trash_ab())
        self._ab_clean_btn.pack(side="right", padx=6, pady=5, ipady=3)

        # ── Bottone avvia nella barra in fondo (a sinistra) ─────────────────
        scan_btn = tk.Button(bot, text="Confronta A vs B",
                             font=("TkFixedFont", 9, "bold"),
                             bg=SUCCESS, fg="white",
                             relief="flat", padx=12,
                             command=lambda: self._run_ab_col(
                                 ab_mode_var.get(), scan_btn, stop_btn))
        scan_btn.pack(side="left", padx=(6,4), pady=5, ipady=3)

    def _trash_ab(self, idx, fpath, lb, row_map):
        """Cestina un file dalla vista colonne A vs B."""
        if not os.path.isfile(fpath):
            return
        if not messagebox.askyesno("Cestina",
                f"Spostare nel cestino?\n{os.path.basename(fpath)}",
                parent=self.win):
            return
        if send_to_trash(fpath):
            lb.delete(idx)
            lb.insert(idx, tk_safe(f"  [cestinato]  {os.path.basename(fpath)}"))
            lb.itemconfig(idx, fg=MUTED_COLOR)
            row_map[idx] = None

    def _bulk_trash_ab(self):
        """Cestina tutti i file di B (mantieni A)."""
        to_del = [(i, p) for i,p in self._ab_row_b.items()
                  if p and os.path.isfile(p)]
        if not to_del:
            return
        if not messagebox.askyesno("Cestina duplicati B",
                f"Cestinare {len(to_del)} file dalla cartella B?",
                parent=self.win):
            return
        done = 0
        for idx, fp in to_del:
            if send_to_trash(fp):
                self._lb_b.delete(idx)
                self._lb_b.insert(idx, f"  [cestinato]")
                self._lb_b.itemconfig(idx, fg=MUTED_COLOR)
                self._ab_row_b[idx] = None
                done += 1
        self._ab_result_lbl.config(text=f"{done} file cestinati")

    def _run_ab_col(self, mode, scan_btn, stop_btn):
        """Avvia la scansione A vs B per la vista a colonne."""
        pa, ra = self._ab_vars["A"]
        pb, rb = self._ab_vars["B"]
        dir_a, dir_b = pa.get().strip(), pb.get().strip()
        if not os.path.isdir(dir_a) or not os.path.isdir(dir_b):
            messagebox.showwarning("Cartelle",
                "Specifica due cartelle valide.", parent=self.win)
            return
        self._lb_a.delete(0, tk.END)
        self._lb_b.delete(0, tk.END)
        self._ab_row_a.clear()
        self._ab_row_b.clear()
        self._ab_result_lbl.config(text="")
        self._ab_clean_btn.config(state="disabled")
        scan_btn.config(state="disabled", text="Confronto...")
        stop_btn.config(state="normal")
        self._stop = False

        threading.Thread(
            target=self._worker_ab_col,
            args=(dir_a, ra.get(), dir_b, rb.get(), mode,
                  scan_btn, stop_btn),
            daemon=True).start()

    def _worker_ab_col(self, dir_a, rec_a, dir_b, rec_b, mode,
                       scan_btn, stop_btn):
        """Thread worker per confronto A vs B con vista a colonne."""

        def collect(folder, recursive):
            files = []
            try:
                if recursive:
                    for root, _, fns in os.walk(folder):
                        for fn in fns:
                            files.append(os.path.join(root, fn))
                else:
                    files = [os.path.join(folder, fn)
                             for fn in os.listdir(folder)
                             if os.path.isfile(os.path.join(folder, fn))]
            except OSError:
                pass
            return [f for f in files
                    if detect_media_type(f) in MEDIA_EXTENSIONS
                    or os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS]

        def key_of(fpath):
            try:
                size = os.path.getsize(fpath)
                name = os.path.basename(fpath).lower()
                if mode == "sha":      return self._hash_file(fpath)
                elif mode == "name_size": return (name, size)
                elif mode == "size":   return size
                else:                  return name
            except Exception:
                return None

        def upd_status(msg):
            self.win.after(0, lambda: self._ab_status_lbl.config(text=msg)
                           if self.win.winfo_exists() else None)
        def upd_prog(cur, tot):
            self.win.after(0, lambda: self._set_prog(
                self._ab_prog_canvas, self._ab_prog_bar, cur, tot)
                if self.win.winfo_exists() else None)

        upd_status("Raccolta file cartella A...")
        files_a = collect(dir_a, rec_a)
        upd_status("Raccolta file cartella B...")
        files_b = collect(dir_b, rec_b)
        total = len(files_a) + len(files_b)

        upd_status(f"Indicizzazione {len(files_a)} + {len(files_b)} file...")

        # Indice A: key → lista file
        index_a = {}
        for i, fp in enumerate(files_a):
            if self._stop: break
            upd_prog(i+1, total)
            k = key_of(fp)
            if k is not None:
                try: size = os.path.getsize(fp)
                except: size = 0
                ext  = os.path.splitext(fp)[1].upper() or "?"
                rel  = os.path.relpath(fp, dir_a)
                index_a.setdefault(k, []).append(
                    {"path": fp, "size": size, "ext": ext, "rel": rel})

        # Scansiona B e trova corrispondenze
        matches = []  # [(key, file_a, file_b)]
        for i, fp in enumerate(files_b):
            if self._stop: break
            upd_prog(len(files_a)+i+1, total)
            k = key_of(fp)
            if k is not None and k in index_a:
                try: size = os.path.getsize(fp)
                except: size = 0
                ext  = os.path.splitext(fp)[1].upper() or "?"
                rel  = os.path.relpath(fp, dir_b)
                b_info = {"path": fp, "size": size, "ext": ext, "rel": rel}
                for a_info in index_a[k]:
                    matches.append((a_info, b_info))

        self.win.after(0, lambda: self._show_ab_col_results(
            matches, len(files_a)+len(files_b), dir_a, dir_b,
            scan_btn, stop_btn))

    def _show_ab_col_results(self, matches, total, dir_a, dir_b,
                              scan_btn, stop_btn):
        """Mostra i risultati nella vista a colonne."""
        if not self.win.winfo_exists():
            return
        scan_btn.config(state="normal", text="Confronta A vs B")
        stop_btn.config(state="disabled")
        self._set_prog(self._ab_prog_canvas, self._ab_prog_bar, 1, 1)

        if not matches:
            self._ab_status_lbl.config(
                text=f"Nessun duplicato trovato ({total} file scansionati).")
            self._ab_result_lbl.config(text="Nessun duplicato.")
            play_sound("done")
            return

        # Ordina per dimensione decrescente
        matches.sort(key=lambda m: -m[0]["size"])

        self._ab_result_lbl.config(text=f"{len(matches)} coppie trovate")
        self._ab_status_lbl.config(
            text=f"{len(matches)} coppie duplicate su {total} file scansionati.")
        self._ab_clean_btn.config(state="normal")
        play_sound("done")

        row = 0
        for a_info, b_info in matches:
            # Intestazione riga: dimensione + nome file
            size_str = self._fmt(a_info["size"])
            name_a   = os.path.basename(a_info["path"])
            name_b   = os.path.basename(b_info["path"])
            same_name = name_a.lower() == name_b.lower()

            # Colonna A
            line_a = tk_safe(f"  {a_info['ext']:<6} {size_str:>9}  {a_info['rel']}")
            self._lb_a.insert(tk.END, line_a)
            col_a = HUD_CYAN if same_name else "#88ffcc"
            self._lb_a.itemconfig(row, fg=col_a)
            self._ab_row_a[row] = a_info["path"]

            # Colonna B
            size_b_str = self._fmt(b_info["size"])
            line_b = tk_safe(f"  {b_info['ext']:<6} {size_b_str:>9}  {b_info['rel']}")
            self._lb_b.insert(tk.END, line_b)
            col_b = "#ffaa44" if same_name else "#ffdd88"
            self._lb_b.itemconfig(row, fg=col_b)
            self._ab_row_b[row] = b_info["path"]
            row += 1

        # Aggiorna label intestazioni con percorsi
        # (non possiamo accedere agli header label facilmente, usiamo status)
        self._ab_status_lbl.config(
            text=tk_safe(f"A: {dir_a}   |   B: {dir_b}   |   {len(matches)} coppie"))

    def _run_ab(self, mode, scan_btn, result_lbl, status_lbl,
                prog_canvas, prog_bar, lb, clean_btn, row_paths, stop_btn=None):
        pa, ra = self._ab_vars["A"]
        pb, rb = self._ab_vars["B"]
        dir_a, dir_b = pa.get().strip(), pb.get().strip()
        if not os.path.isdir(dir_a) or not os.path.isdir(dir_b):
            messagebox.showwarning("Cartelle",
                "Specifica due cartelle valide.", parent=self.win)
            return
        lb.delete(0, tk.END)
        row_paths.clear()
        result_lbl.config(text="")
        clean_btn.config(state="disabled")
        scan_btn.config(state="disabled", text="Confronto...")
        if stop_btn and stop_btn.winfo_exists(): stop_btn.config(state="normal")
        self._stop = False

        threading.Thread(
            target=self._worker_ab,
            args=(dir_a, ra.get(), dir_b, rb.get(), mode,
                  lb, status_lbl, prog_canvas, prog_bar,
                  result_lbl, clean_btn, scan_btn, row_paths, stop_btn),
            daemon=True).start()

    def _worker_ab(self, dir_a, rec_a, dir_b, rec_b, mode,
                   lb, status_lbl, prog_canvas, prog_bar,
                   result_lbl, clean_btn, scan_btn, row_paths, stop_btn=None):

        def collect(folder, recursive):
            files = []
            try:
                if recursive:
                    for root, _, fns in os.walk(folder):
                        for fn in fns:
                            files.append(os.path.join(root, fn))
                else:
                    files = [os.path.join(folder, fn)
                             for fn in os.listdir(folder)
                             if os.path.isfile(os.path.join(folder, fn))]
            except OSError:
                pass
            return [f for f in files
                    if detect_media_type(f) in MEDIA_EXTENSIONS
                    or os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS]

        def key_of(fpath, mode):
            try:
                size = os.path.getsize(fpath)
                name = os.path.basename(fpath).lower()
                if mode == "sha":
                    return self._hash_file(fpath)
                elif mode == "name_size":
                    return (name, size)
                elif mode == "size":
                    return size
                else:
                    return name
            except Exception:
                return None

        self._set_st(status_lbl, "Raccolta file cartella A...")
        files_a = collect(dir_a, rec_a)
        self._set_st(status_lbl, "Raccolta file cartella B...")
        files_b = collect(dir_b, rec_b)

        total = len(files_a) + len(files_b)
        self._set_st(status_lbl,
                     f"Indicizzazione {len(files_a)} + {len(files_b)} file...")

        # Indice A
        index_a = {}
        for idx, fpath in enumerate(files_a):
            if self._stop:
                self.win.after(0, lambda: (scan_btn.config(state="normal", text="Confronta A vs B") if scan_btn.winfo_exists() else None, stop_btn.config(state="disabled") if stop_btn and stop_btn.winfo_exists() else None))
                return
            self._set_prog(prog_canvas, prog_bar, idx+1, total)
            k = key_of(fpath, mode)
            if k:
                size = os.path.getsize(fpath)
                index_a.setdefault(k, []).append(
                    {"path": fpath, "size": size,
                     "ext": os.path.splitext(fpath)[1].upper() or "?"})

        # Scansiona B, trova corrispondenze in A
        duplicates = {}
        for idx, fpath in enumerate(files_b):
            if self._stop:
                self.win.after(0, lambda: (scan_btn.config(state="normal", text="Confronta A vs B") if scan_btn.winfo_exists() else None, stop_btn.config(state="disabled") if stop_btn and stop_btn.winfo_exists() else None))
                return
            self._set_prog(prog_canvas, prog_bar,
                           len(files_a)+idx+1, total)
            k = key_of(fpath, mode)
            if k and k in index_a:
                size = os.path.getsize(fpath)
                b_info = {"path": fpath, "size": size,
                          "ext": os.path.splitext(fpath)[1].upper() or "?"}
                # Gruppo: [file A, file B]
                group_key = k
                if group_key not in duplicates:
                    duplicates[group_key] = list(index_a[k])
                duplicates[group_key].append(b_info)

        self.win.after(0, lambda: self._show_dup_results(
            duplicates, total, lb, status_lbl, prog_canvas, prog_bar,
            result_lbl, clean_btn, scan_btn,
            row_paths, "Confronta A vs B", stop_btn,
            label_hash=False,
            origin_a=dir_a))

    # ── Visualizzazione risultati ─────────────────────────────────────────────

    def _show_dup_results(self, duplicates, total_scanned,
                          lb, status_lbl, prog_canvas, prog_bar,
                          result_lbl, clean_btn, scan_btn,
                          row_paths, btn_label, stop_btn=None,
                          label_hash=True, origin_a=None):
        if not self.win.winfo_exists():
            return
        def _scan_done():
            if scan_btn.winfo_exists():
                scan_btn.config(state="normal", text=btn_label)
            if stop_btn and stop_btn.winfo_exists():
                stop_btn.config(state="disabled")
        self.win.after(0, _scan_done)
        self._set_prog(prog_canvas, prog_bar, 1, 1)

        if not duplicates:
            self._set_st(status_lbl,
                         f"Nessun duplicato trovato ({total_scanned} file).")
            result_lbl.config(text="Nessun duplicato.")
            play_sound("done")
            return

        n_groups = len(duplicates)
        n_dupes  = sum(len(v)-1 for v in duplicates.values())
        result_lbl.config(
            text=f"{n_groups} gruppi  —  {n_dupes} file duplicati")
        self._set_st(status_lbl,
                     f"{n_groups} gruppi, {n_dupes} duplicati su {total_scanned} file.")
        clean_btn.config(state="normal")
        play_sound("done")

        # Prepara tutte le righe in anticipo (no rendering)
        all_rows = []  # lista di (testo, bg, fg, fpath)
        for h, files in sorted(duplicates.items(),
                                key=lambda x: -x[1][0]["size"]):
            files = sorted(files, key=_copy_score)
            total_sz = sum(fi["size"] for fi in files)
            suffix   = f"hash {str(h)[:10]}" if label_hash else ""
            header   = tk_safe(f"  --- {len(files)} file identici | "
                               f"{self._fmt(total_sz)} | {suffix} ---")
            all_rows.append((header, PANEL_COLOR, "#ff88cc", None))
            for i, fi in enumerate(files):
                if origin_a:
                    tag = "  [A]  " if fi["path"].startswith(origin_a) else "  [B]  "
                    col = TEXT_COLOR if fi["path"].startswith(origin_a) else "#ffaa44"
                else:
                    tag = "  [ORIG]  " if i == 0 else "  [COPIA] "
                    col = TEXT_COLOR if i == 0 else "#ffaa88"
                line = tk_safe(f"{tag}{fi['ext']:<6} {self._fmt(fi['size']):>10}  {fi['path']}")
                all_rows.append((line, None, col, fi["path"]))
            all_rows.append(("", None, None, None))

        # Inserisce in batch da 50 righe con after() per non bloccare X11
        BATCH = 50
        def _insert_batch(start_idx):
            end_idx = min(start_idx + BATCH, len(all_rows))
            for i in range(start_idx, end_idx):
                text, bg, fg, fpath = all_rows[i]
                row_idx = i
                lb.insert(tk.END, text)
                if bg: lb.itemconfig(row_idx, bg=bg)
                if fg: lb.itemconfig(row_idx, fg=fg)
                row_paths[row_idx] = fpath
            if end_idx < len(all_rows):
                self.win.after(10, lambda: _insert_batch(end_idx))

        _insert_batch(0)

    # ── Azioni lista ──────────────────────────────────────────────────────────

    def _ctx(self, event, lb, row_paths):
        idx = lb.nearest(event.y)
        fpath = row_paths.get(idx)
        lb.selection_clear(0, tk.END)
        lb.selection_set(idx)
        menu = tk.Menu(self.win, tearoff=0,
                       bg=PANEL_COLOR, fg=TEXT_COLOR,
                       activebackground=HIGHLIGHT,
                       activeforeground="white", relief="flat")

        if fpath:
            # Riga file
            menu.add_command(label="Apri file",
                             command=lambda: subprocess.Popen(
                                 ["xdg-open", fpath],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL))
            menu.add_command(label="Mostra in file manager",
                             command=lambda p=fpath: open_in_filemanager(p))
            menu.add_separator()
            menu.add_command(label="Sposta nel cestino",
                             command=lambda: self._trash_row(idx, fpath, lb, row_paths))
        else:
            # Riga header gruppo — raccogli tutti i file del gruppo
            # Un gruppo inizia dalla riga header (None) e prosegue fino alla prossima None
            group_files = []
            i = idx + 1
            while i in row_paths:
                p = row_paths.get(i)
                if p is None:
                    break
                if p:
                    group_files.append(p)
                i += 1
            # Cartelle uniche del gruppo
            folders = list(dict.fromkeys(os.path.dirname(p) for p in group_files))
            if folders:
                def _open_all_folders(fds=folders):
                    for fd in fds:
                        open_in_filemanager(fd)
                menu.add_command(
                    label=f"Apri {len(folders)} cartel{'la' if len(folders)==1 else 'le'} in file manager",
                    command=_open_all_folders)
            else:
                menu.add_command(label="Nessun file nel gruppo", state="disabled")

        menu.tk_popup(event.x_root, event.y_root)
        try:
            menu.grab_release()
        except Exception:
            pass

    def _open_lb(self, lb, row_paths, event=None):
        sel = lb.curselection()
        if not sel:
            return
        fpath = row_paths.get(sel[0])
        if fpath and os.path.isfile(fpath):
            subprocess.Popen(["xdg-open", fpath],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    def _trash_row(self, idx, fpath, lb, row_paths):
        if not os.path.isfile(fpath):
            return
        fname = os.path.basename(fpath)
        if not messagebox.askyesno("Cestina", f"Spostare nel cestino?\n{fname}",
                                   parent=self.win):
            return
        if send_to_trash(fpath):
            lb.delete(idx)
            lb.insert(idx, tk_safe(f"  [CESTINATO]  {fpath}"))
            lb.itemconfig(idx, fg=MUTED_COLOR)
            row_paths[idx] = None

    def _bulk_trash_lb(self, lb, row_paths, result_lbl):
        to_trash = [(idx, path) for idx, path in row_paths.items()
                    if path and os.path.isfile(path)]
        # Mantieni solo il primo file di ogni gruppo (idx più basso)
        # I gruppi sono separati da righe header (None)
        # Logica: salta il primo file valido di ogni gruppo
        keep = set()
        in_group = False
        for idx in sorted(row_paths.keys()):
            p = row_paths.get(idx)
            if p is None:
                in_group = False
                continue
            if not in_group:
                keep.add(idx)
                in_group = True

        to_delete = [(idx, p) for idx, p in to_trash if idx not in keep]
        count = len(to_delete)
        if not messagebox.askyesno(
                "Conferma",
                f"Spostare nel cestino {count} duplicati?\n"
                f"Verrà conservato il primo file di ogni gruppo.",
                parent=self.win):
            return
        trashed = 0
        for idx, fpath in to_delete:
            if send_to_trash(fpath):
                trashed += 1
                row_paths[idx] = None
        result_lbl.config(text=f"Cestinati {trashed} file.")

    # ── Utility ──────────────────────────────────────────────────────────────

    def _hash_file(self, path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def _fmt(self, b):
        for u in ["B","KB","MB","GB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} TB"

    def _set_st(self, lbl, msg):
        msg = tk_safe(str(msg))
        self.win.after(0, lambda: lbl.config(text=msg)
                       if self.win.winfo_exists() else None)

    def _set_prog(self, canvas, bar, val, total):
        def _up():
            if not self.win.winfo_exists(): return
            w = canvas.winfo_width() or 1
            canvas.coords(bar, 0, 0, int(w * val / total) if total else 0, 3)
        self.win.after(0, _up)

    def _on_close(self):
        # Avvisa solo se c'è davvero un thread di scansione attivo
        thread = getattr(self, '_thread', None)
        scanning = thread is not None and thread.is_alive()
        if scanning:
            if not messagebox.askyesno(
                    "Scansione in corso",
                    "Interrompere la scansione e chiudere?",
                    parent=self.win):
                return
        self._stop = True
        self.win.destroy()

class FolderBrowser:
    """
    Finestra ad albero per navigare le cartelle e caricare immagini.
    Doppio click su una cartella -> carica la prima immagine in ImageSorter.
    """
    def __init__(self, parent, sorter):
        self.sorter          = sorter
        self._thumb_size     = 200
        self._current_folder = None
        self._size_btns      = {}
        self._action_frame   = None
        self._sort_mode      = "name"
        self._sort_btns      = {}
        self._view_mode      = "grid"   # "grid" | "list"
        self._view_btn       = None
        self._show_assign    = False    # mostra/nasconde pannello assegnazione
        self._show_hidden    = False    # mostra cartelle nascoste (punto iniziale)
        self._selected_files = set()   # file selezionati per operazioni multiple
        self._clipboard_files = []    # file copiati/tagliati
        self._clipboard_mode  = None  # "copy" | "cut" 
        self._cell_refs      = {}      # {fpath: cell_frame} per aggiornare stile
        self.win = tk.Toplevel(parent)
        self.win.title("Browser cartelle")
        self.win.configure(bg=BG_COLOR)
        self.win.geometry("1100x700")
        self.win.minsize(400, 340)
        self.win.resizable(True, True)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self.win.bind("<Escape>", lambda e: self._on_close())
        hud_apply(self.win)
        self._build()
        # Mostra la finestra subito, poi popola l'albero in background
        self.win.update_idletasks()
        self.win.after(10, self._deferred_init)

    def _deferred_init(self):
        """Popola l'albero dopo che la finestra è già visibile."""
        sorter = self.sorter
        start = (sorter.config.get("last_source", "")
                 or os.path.expanduser("~/Immagini")
                 or os.path.expanduser("~"))
        if not os.path.isdir(start):
            start = os.path.expanduser("~")
        self._populate_root()
        current = sorter._current_file()
        if current and os.path.isfile(current):
            start = os.path.dirname(current)
            self._start_file = current
        else:
            self._start_file = None
        self._expand_to(start)

    def _build(self):
        w = self.win
        w.columnconfigure(0, weight=1)
        w.rowconfigure(0, weight=0)   # nav
        w.rowconfigure(1, weight=0)   # qf_top
        w.rowconfigure(2, weight=0)   # qf (S/M/L, ordina, vista)
        w.rowconfigure(3, weight=1)   # paned
        w.rowconfigure(4, weight=0)   # sel_bar
        w.rowconfigure(5, weight=0)   # action bar


        # Barra percorso (spanning entrambe le colonne)
        nav = tk.Frame(w, bg=PANEL_COLOR)
        nav.grid(row=0, column=0, columnspan=2, sticky="ew")
        nav.columnconfigure(1, weight=1)
        tk.Label(nav, text="Vai a:", font=("TkFixedFont", 8),
                 bg=PANEL_COLOR, fg=MUTED_COLOR).grid(
                 row=0, column=0, padx=(8,4), pady=6)
        self._path_var = tk.StringVar()
        e = tk.Entry(nav, textvariable=self._path_var,
                     font=("TkFixedFont", 8),
                     bg=ACCENT_COLOR, fg=TEXT_COLOR,
                     insertbackground=TEXT_COLOR, relief="flat", bd=4)
        e.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        e.bind("<Return>", lambda ev=None: self._go_to_path())
        tk.Button(nav, text="Vai →", font=("TkFixedFont", 8),
                  bg=SUCCESS, fg="white", relief="flat",
                  activebackground=HIGHLIGHT,
                  command=self._go_to_path).grid(
                  row=0, column=2, padx=(0,6), pady=6)

        # Riga 1: preferiti + accesso rapido
        qf_top = tk.Frame(w, bg=BG_COLOR)
        qf_top.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(4,0))
        self._qf_top_frame = qf_top

        # Riga 2: controlli vista
        qf = tk.Frame(w, bg=BG_COLOR)
        qf.grid(row=2, column=0, columnspan=2, sticky="ew", padx=6, pady=(0,2))

        def _add_quick(parent, label, fpath, color=None):
            c = color or ACCENT_COLOR
            b = tk.Button(parent, text=label, font=("TkFixedFont", 8),
                          bg=c, fg=TEXT_COLOR, relief="flat", padx=6,
                          activebackground=HIGHLIGHT, activeforeground="white",
                          command=lambda p=fpath: self._expand_to(p))
            b.pack(side="left", padx=2, pady=2, ipady=2)
            return b

        # Posti fissi
        pics = os.path.expanduser("~/Immagini")
        if not os.path.isdir(pics): pics = os.path.expanduser("~/Pictures")
        vids = os.path.expanduser("~/Video")
        if not os.path.isdir(vids): vids = os.path.expanduser("~/Videos")
        desk = os.path.expanduser("~/Scrivania")
        if not os.path.isdir(desk): desk = os.path.expanduser("~/Desktop")
        docs = os.path.expanduser("~/Documenti")
        if not os.path.isdir(docs): docs = os.path.expanduser("~/Documents")

        for lbl, fp in [("Home", os.path.expanduser("~")),
                        ("Immagini", pics), ("Video", vids),
                        ("Scrivania", desk), ("Documenti", docs), ("Root /", "/")]:
            if os.path.isdir(fp):
                _add_quick(qf_top, lbl, fp)

        # Dischi montati — aggiunge i bottoni in after() per non bloccare
        def _add_mounts():
            try:
                with open("/proc/mounts") as _mf:
                    mounts = []
                    for _line in _mf:
                        _parts = _line.split()
                        if len(_parts) >= 2:
                            _mp = _parts[1]
                            if _mp.startswith("/media/") or _mp.startswith("/mnt/"):
                                if os.path.isdir(_mp):
                                    mounts.append(_mp)
                def _add_to_ui():
                    for _mp in mounts:
                        _name = os.path.basename(_mp) or _mp
                        _add_quick(qf_top, f"[{_name}]", _mp, color="#1a3a5a")
                self.win.after(0, _add_to_ui)
            except Exception:
                pass
        threading.Thread(target=_add_mounts, daemon=True).start()

        # Separatore | Ultima usata
        tk.Label(qf_top, text=" | ",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left")
        self._last_used_btn = None
        self._qf_top = qf_top
        self._refresh_last_used_btn()

        # Bottone Cerca doppioni — a destra nella riga destinazioni
        tk.Label(qf_top, text=" | ",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="right")
        tk.Button(qf_top, text="  Cerca doppioni  ",
                  font=("TkFixedFont", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=3,
                  bg="#3a1a2a", fg="#ff88cc",
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=self._open_duplicate_finder
                  ).pack(side="right", padx=4, pady=2, ipady=2)
        tk.Button(qf_top, text="  Analisi cartelle  ",
                  font=("TkFixedFont", 9, "bold"),
                  relief="flat", bd=0, padx=12, pady=3,
                  bg="#1a2a3a", fg=HUD_CYAN,
                  activebackground="#2a4a6a", activeforeground="white",
                  command=self._open_disk_analyzer
                  ).pack(side="right", padx=4, pady=2, ipady=2)

        # Bottoni dimensione thumbnail
        tk.Label(qf, text="Anteprime:",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left", padx=(8,2))
        self._size_btns = {}
        for _lbl, _sz in [("S", 90), ("M", 130), ("L", 200)]:
            _b = tk.Button(qf, text=_lbl,
                           font=("TkFixedFont", 7, "bold"),
                           relief="flat", bd=0, padx=6, pady=1,
                           activebackground=HIGHLIGHT, activeforeground="white",
                           command=lambda s=_sz: self._set_thumb_size(s))
            _b.pack(side="left", padx=1)
            self._size_btns[_sz] = _b
        self._refresh_size_btns()

        tk.Label(qf, text=" | Ordina:",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left", padx=(8,2))
        for _lbl, _mode in [("A-Z", "name"), ("Dim", "size"), ("Data", "date")]:
            _sb = tk.Button(qf, text=_lbl,
                            font=("TkFixedFont", 7, "bold"),
                            relief="flat", bd=0, padx=5, pady=1,
                            activebackground=HIGHLIGHT, activeforeground="white",
                            command=lambda m=_mode: self._set_sort_mode(m))
            _sb.pack(side="left", padx=1)
            self._sort_btns[_mode] = _sb
        self._refresh_sort_btns()

        tk.Label(qf, text=" | ",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left")
        self._view_btn = tk.Button(qf, text="Lista",
                                   font=("TkFixedFont", 7, "bold"),
                                   relief="flat", bd=0, padx=6, pady=1,
                                   bg=ACCENT_COLOR, fg=TEXT_COLOR,
                                   activebackground=HIGHLIGHT, activeforeground="white",
                                   command=self._toggle_view_mode)
        self._view_btn.pack(side="left", padx=1)

        # Bottone Assegna toggle
        tk.Label(qf, text=" | ",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left")
        self._assign_btn = tk.Button(qf, text="Assegna",
                                     font=("TkFixedFont", 7, "bold"),
                                     relief="flat", bd=0, padx=6, pady=1,
                                     bg=HUD_CYAN, fg="#0a1a2e",
                                     activebackground=HIGHLIGHT, activeforeground="white",
                                     command=self._toggle_assign_panel)
        self._assign_btn.pack(side="left", padx=1)


        # Checkbox cartelle nascoste
        tk.Label(qf, text=" | ",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left")
        self._show_hidden_var = tk.BooleanVar(value=self._show_hidden)
        tk.Checkbutton(qf, text="Nascoste", variable=self._show_hidden_var,
                       font=("TkFixedFont", 7), bg=BG_COLOR,
                       fg=MUTED_COLOR, selectcolor=ACCENT_COLOR,
                       activebackground=BG_COLOR, activeforeground=HUD_CYAN,
                       command=lambda: self._toggle_tree_filter(
                           "_show_hidden", self._show_hidden_var)
                       ).pack(side="left", padx=3)


        # Hint doppio click (a destra di tutto)
        tk.Label(qf, text="  clic=seleziona | dbl-clic=apri | Ctrl+A=tutti",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="right", padx=8)



        # PanedWindow orizzontale: divisore trascinabile tra albero e thumbnail
        paned = ttk.PanedWindow(w, orient="horizontal")
        paned.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=6, pady=4)

        # --- Pannello sinistro: albero ---
        tf = tk.Frame(paned, bg=BG_COLOR)
        tf.rowconfigure(0, weight=1)
        tf.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(tf, selectmode="browse", show="tree")
        self.tree.column("#0", width=300, minwidth=200, stretch=True)
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<Button-4>", lambda e: self.tree.yview_scroll(-1, "units"))
        self.tree.bind("<Button-5>", lambda e: self.tree.yview_scroll(1, "units"))
        self.tree.bind("<MouseWheel>", lambda e: self.tree.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.tree.bind("<<TreeviewOpen>>",  self._on_open)
        self.tree.bind("<ButtonRelease-1>", self._on_click)
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-3>",        self._on_tree_right_click)
        self.win.bind("<Control-a>", lambda e: self._sel_all())
        self.win.bind("<Control-A>", lambda e: self._sel_all())
        self.win.bind("<Control-c>", lambda e:
            self._clipboard_set(sorted(self._selected_files), "copy")
            if self._selected_files else None)
        self.win.bind("<Control-x>", lambda e:
            self._clipboard_set(sorted(self._selected_files), "cut")
            if self._selected_files else None)
        self.win.bind("<Control-v>", lambda e:
            self._clipboard_paste(self._current_folder)
            if self._clipboard_files and self._current_folder else None)
        self.win.bind("<Delete>", lambda e:
            self._trash_selection(sorted(self._selected_files))
            if self._selected_files else None)
        paned.add(tf, weight=2)

        # --- Pannello destro: barra dimensioni + thumbnail + assegnazione ---
        right = tk.Frame(paned, bg=PANEL_COLOR)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        paned.add(right, weight=3)
        self._right_panel = right

        # Sash a metà finestra
        def _set_sash():
            try:
                paned.update_idletasks()
                half = paned.winfo_width() // 2
                if half > 50:
                    paned.sashpos(0, half)
            except Exception:
                pass
        self.win.after(150,  _set_sash)
        self.win.after(500,  _set_sash)
        self.win.after(1000, _set_sash)

        # Canvas thumbnail
        self._thumb_canvas = tk.Canvas(right, bg=PANEL_COLOR, highlightthickness=0)
        thumb_vsb = tk.Scrollbar(right, orient="vertical",
                                 command=self._thumb_canvas.yview)
        self._thumb_canvas.configure(yscrollcommand=thumb_vsb.set)
        self._thumb_canvas.grid(row=0, column=0, sticky="nsew")
        thumb_vsb.grid(row=0, column=1, sticky="ns")
        self._thumb_inner = tk.Frame(self._thumb_canvas, bg=PANEL_COLOR)
        self._thumb_win_id = self._thumb_canvas.create_window(
            (0, 0), window=self._thumb_inner, anchor="nw")
        self._thumb_inner.bind("<Configure>", self._on_thumb_frame_configure)
        self._thumb_canvas.bind("<Configure>", self._on_thumb_canvas_configure)
        self._thumb_canvas.bind("<MouseWheel>",
            lambda e: self._thumb_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        self._thumb_canvas.bind("<Button-4>",
            lambda e: self._thumb_canvas.yview_scroll(-1, "units"))
        self._thumb_canvas.bind("<Button-5>",
            lambda e: self._thumb_canvas.yview_scroll(1, "units"))
        # Trackpad a due dita: propaga scroll da widget figli al canvas
        def _scroll_up(e):
            if self._thumb_canvas.winfo_exists():
                self._thumb_canvas.yview_scroll(-1, "units")
        def _scroll_dn(e):
            if self._thumb_canvas.winfo_exists():
                self._thumb_canvas.yview_scroll(1, "units")
        self._thumb_inner.bind_all("<Button-4>", _scroll_up)
        self._thumb_inner.bind_all("<Button-5>", _scroll_dn)

        self._thumb_images = []
        self._thumb_job    = None
        self._cell_refs    = {}
        self._dir_cell_refs = {}   # {dpath: (widget, orig_bg)}
        self._selected_files = set()

        # Barra selezione multipla (visibile solo con file selezionati)
        self._sel_bar = tk.Frame(w, bg="#152515")
        self._sel_bar.grid(row=4, column=0, columnspan=2,
                           sticky="ew", padx=0, pady=0)
        self._sel_bar.grid_remove()

        # Barra assegnazione destinazione (tutta larghezza)
        self._assign_panel = tk.Frame(w, bg=PANEL_COLOR)
        self._assign_panel.grid(row=5, column=0, columnspan=2,
                                sticky="ew", padx=0, pady=0)
        self._build_assign_panel()
        if not self._show_assign:
            self._assign_panel.grid_remove()

        # Status bar (per messaggi dinamici)
        self._status = tk.Label(w, text="",
                                font=("TkFixedFont", 7), bg=BG_COLOR,
                                fg=MUTED_COLOR, anchor="w")
        self._status.grid(row=6, column=0, columnspan=2,
                          sticky="ew", padx=8, pady=(2,4))

    # --- albero -------------------------------------------------------

    def _has_images(self, path):
        try:
            for e in os.scandir(path):
                if e.is_file(follow_symlinks=False):
                    if os.path.splitext(e.name)[1].lower() in MEDIA_EXTENSIONS:
                        return True
        except OSError:
            pass
        return False

    def _has_subdirs(self, path):
        try:
            for e in os.scandir(path):
                if e.is_dir(follow_symlinks=False):
                    return True
        except OSError:
            pass
        return False

    def _img_stats(self, path):
        """Ritorna (n_img, n_vid, n_pdf, size_bytes) per la cartella."""
        n_img, n_vid, n_pdf, size = 0, 0, 0, 0
        try:
            for e in os.scandir(path):
                if e.is_file(follow_symlinks=False):
                    ext = os.path.splitext(e.name)[1].lower()
                    try: sz = e.stat().st_size
                    except OSError: sz = 0
                    if ext in IMAGE_EXTENSIONS:
                        n_img += 1; size += sz
                    elif ext in VIDEO_EXTENSIONS:
                        n_vid += 1; size += sz
                    elif ext in PDF_EXTENSIONS:
                        n_pdf += 1; size += sz
        except OSError:
            pass
        return n_img, n_vid, n_pdf, size

    @staticmethod
    def _fmt_size(b):
        """Formatta bytes in KB/MB/GB leggibili."""
        if b < 1024:
            return f"{b} B"
        elif b < 1024 ** 2:
            return f"{b/1024:.0f} KB"
        elif b < 1024 ** 3:
            return f"{b/1024**2:.1f} MB"
        else:
            return f"{b/1024**3:.2f} GB"

    # --- thumbnail panel --------------------------------------------------

    def _on_thumb_frame_configure(self, event):
        self._thumb_canvas.configure(
            scrollregion=self._thumb_canvas.bbox("all"))

    def _on_thumb_canvas_configure(self, event):
        self._thumb_canvas.itemconfig(
            self._thumb_win_id, width=event.width)
        # Ricalcola colonne se la vista è griglia e la larghezza è cambiata
        if (getattr(self, '_view_mode', 'grid') == 'grid' and
                self._current_folder and
                abs(event.width - getattr(self, '_last_panel_w', 0)) > 20):
            self._last_panel_w = event.width
            self._load_thumbnails(self._current_folder)

    def _set_thumb_size(self, size):
        self._thumb_size = size
        self._refresh_size_btns()
        if self._current_folder:
            self._load_thumbnails(self._current_folder)

    def _refresh_size_btns(self):
        for size, btn in self._size_btns.items():
            btn.config(bg=HIGHLIGHT if size == self._thumb_size else ACCENT_COLOR,
                       fg="white")

    def _build_assign_panel(self):
        for w in self._assign_panel.winfo_children():
            w.destroy()
        self._assign_panel.config(bg=PANEL_COLOR)
        preset_names = list(self.sorter.config["presets"].keys())
        active = self.sorter.config["active_preset"]
        # Mostra i primi 3 preset, uno per riga
        self._assign_rows = []
        for i, pname in enumerate(preset_names[:3]):
            row = tk.Frame(self._assign_panel, bg=PANEL_COLOR)
            row.pack(fill="x", padx=4, pady=1)
            var = tk.StringVar(value=pname)
            om = tk.OptionMenu(row, var, *preset_names)
            om.config(font=("TkFixedFont", 7), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                      activebackground=HIGHLIGHT, activeforeground="white",
                      highlightthickness=0, relief="flat", bd=0, width=10)
            om["menu"].config(font=("TkFixedFont", 7), bg=ACCENT_COLOR,
                              fg=TEXT_COLOR, activebackground=HIGHLIGHT,
                              activeforeground="white")
            om.pack(side="left", padx=(0,4))
            keys_frame = tk.Frame(row, bg=PANEL_COLOR)
            keys_frame.pack(side="left", fill="x", expand=True)
            self._assign_rows.append((var, keys_frame))
            var.trace_add("write", lambda *a, v=var, kf=keys_frame: self._refresh_row_keys(v, kf))
            self._refresh_row_keys(var, keys_frame)
    def _refresh_row_keys(self, var, keys_frame):
        """Aggiorna i bottoni tasto per una riga preset."""
        for w in keys_frame.winfo_children():
            w.destroy()
        pname  = var.get()
        slots  = self.sorter.config["presets"].get(pname, {})
        folder = getattr(self, "_current_folder", None)
        for k in sorted(KEYS, key=int):
            color = KEY_COLORS[KEYS.index(k)]
            lbl   = slots[k].get("label", k) if k in slots else k
            short = lbl if len(lbl) <= 6 else lbl[:5]+"."
            btn = tk.Button(
                keys_frame,
                text=f"{k} {short}",
                font=("TkFixedFont", 8),
                bg=color, fg="white", relief="flat",
                width=8,   # larghezza fissa uguale per tutti
                activebackground=HIGHLIGHT, activeforeground="white",
                disabledforeground="#aaaaaa",
                state="normal" if folder else "disabled",
                command=lambda key=k, p=pname: self._assign_folder(key, p))
            btn.pack(side="left", padx=1, ipady=3)
            btn.bind("<Button-3>",
                     lambda e, key=k, p=pname, b=btn: self._rename_key_label(e, key, p, b))

    def _refresh_assign_keys(self):
        """Aggiorna tutte le righe preset."""
        if hasattr(self, "_assign_rows"):
            for var, kf in self._assign_rows:
                self._refresh_row_keys(var, kf)

    def _refresh_assign_panel(self):
        """Aggiorna stato bottoni quando cambia la cartella selezionata."""
        self._refresh_assign_keys()

    def _toggle_assign_panel(self):
        self._show_assign = not self._show_assign
        if self._show_assign:
            self._assign_panel.grid()
            self._assign_btn.config(bg=HUD_CYAN, fg="#0a1a2e")
        else:
            self._assign_panel.grid_remove()
            self._assign_btn.config(bg=ACCENT_COLOR, fg=TEXT_COLOR)

    def _toggle_tree_filter(self, attr, var):
        setattr(self, attr, var.get())
        # Aggiorna solo i nodi già espansi senza ricostruire l'albero
        self._refresh_expanded_nodes()

    def _refresh_expanded_nodes(self):
        """Ricarica i figli di tutti i nodi già espansi mantenendo la struttura."""
        def refresh_node(iid):
            children = self.tree.get_children(iid)
            # Se ha figli reali (non placeholder), ricarica
            if children:
                first_vals = self.tree.item(children[0], "values")
                if not (first_vals and first_vals[0] == "__ph__"):
                    path_vals = self.tree.item(iid, "values")
                    node_path = path_vals[0] if path_vals else None
                    if node_path:
                        # Salva i figli espansi prima di cancellare
                        expanded = [self.tree.item(c, "values")[0]
                                    for c in children
                                    if self.tree.item(c, "open")
                                    and self.tree.item(c, "values")]
                        self.tree.delete(*children)
                        self._populate_children(iid, node_path)
                        # Riespandi i figli che erano aperti
                        for child in self.tree.get_children(iid):
                            cv = self.tree.item(child, "values")
                            if cv and cv[0] in expanded:
                                self.tree.item(child, open=True)
                                refresh_node(child)
        refresh_node("")
        for top in self.tree.get_children(""):
            if self.tree.item(top, "open"):
                refresh_node(top)

    def _rename_key_label(self, event, key, preset_name, btn):
        """Popup per rinominare l'etichetta di un tasto (tasto destro sul bottone)."""
        win = tk.Toplevel(self.win)
        win.withdraw()   # nasconde subito per evitare flash
        win.title("Rinomina etichetta")
        win.configure(bg=BG_COLOR)
        win.resizable(False, False)
        hud_apply(win)

        slots = self.sorter.config["presets"].get(preset_name, {})
        cur_label = slots.get(key, {}).get("label", key) if key in slots else key

        tk.Label(win, text=f"Tasto {key} — nuovo nome:",
                 font=("TkFixedFont", 9), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(padx=16, pady=(12,4))

        var = tk.StringVar(value=cur_label)
        entry = tk.Entry(win, textvariable=var,
                         font=("TkFixedFont", 10),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=4, width=22)
        entry.pack(padx=16, pady=4, ipady=4)
        entry.selection_range(0, tk.END)
        entry.focus_set()

        def _save():
            new_lbl = var.get().strip()
            if not new_lbl:
                return
            if key not in slots:
                slots[key] = {}
            slots[key]["label"] = new_lbl
            self.sorter.config["presets"][preset_name][key] = slots[key]
            save_config(self.sorter.config)
            # Aggiorna bottone e sidebar/stream deck
            short = new_lbl if len(new_lbl) <= 6 else new_lbl[:5]+"."
            btn.config(text=f"{key}  {short}")
            self.sorter._build_sidebar()
            if getattr(self.sorter, '_stream_deck', None):
                self.sorter._stream_deck.refresh_all()
            win.destroy()

        bf = tk.Frame(win, bg=BG_COLOR)
        bf.pack(padx=16, pady=(4,12), fill="x")
        tk.Button(bf, text="Salva", font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=10,
                  command=_save).pack(side="left", padx=(0,6), ipady=4)
        tk.Button(bf, text="Annulla", font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=10,
                  command=win.destroy).pack(side="left", ipady=4)
        entry.bind("<Return>",   lambda e: _save())
        entry.bind("<KP_Enter>", lambda e: _save())
        entry.bind("<Escape>", lambda e: win.destroy())

        # Centra sulla finestra browser
        win.update_idletasks()
        pw = win.winfo_reqwidth()
        ph = win.winfo_reqheight()
        px = self.win.winfo_rootx() + (self.win.winfo_width()  - pw) // 2
        py = self.win.winfo_rooty() + (self.win.winfo_height() - ph) // 2
        win.geometry(f"+{px}+{py}")
        win.deiconify()
        # win.grab_set()  # rimosso: bloccava altri programmi

        # Chiudi cliccando fuori senza modifiche
        original = var.get()
        def _click_outside(e):
            if not win.winfo_exists():
                return
            wx, wy = win.winfo_rootx(), win.winfo_rooty()
            ww, wh = win.winfo_width(), win.winfo_height()
            if not (wx <= e.x_root <= wx+ww and wy <= e.y_root <= wy+wh):
                if var.get().strip() == original:
                    win.destroy()
        self.win.bind("<ButtonPress>", _click_outside, add=True)
        win.bind("<Destroy>", lambda e: self.win.unbind("<ButtonPress>"))

    def _assign_folder(self, key, preset_name):
        """Assegna _current_folder come percorso del tasto key nel preset."""
        folder = getattr(self, "_current_folder", None)
        if not folder or not os.path.isdir(folder):
            return
        if preset_name not in self.sorter.config["presets"]:
            return

        slots = self.sorter.config["presets"][preset_name]
        old_label = slots[key].get("label", "") if key in slots else ""
        fname = os.path.basename(folder)
        # Auto-etichetta: se label vuota o default usa nome cartella
        if not old_label.strip() or old_label == key or old_label.startswith("Cartella_"):
            slots[key] = slots.get(key, {})
            slots[key]["label"] = fname
        slots[key]["path"] = folder
        save_config(self.sorter.config)

        # Se è il preset attivo aggiorna la sidebar live
        if preset_name == self.sorter.config["active_preset"]:
            self.sorter.labels = self.sorter.config["presets"][preset_name]
            self.sorter._build_sidebar()
            if self.sorter.keypad_popup:
                self.sorter.keypad_popup.refresh_labels()

        self._status.config(
            text=f"Tasto {key} -> {fname}  [preset: {preset_name}]",
            fg=SUCCESS)

    def _refresh_last_used_btn(self):
        """Aggiorna il bottone ultima cartella usata nella barra rapida."""
        if not hasattr(self, '_qf_top') or not self._qf_top.winfo_exists():
            return
        if self._last_used_btn and self._last_used_btn.winfo_exists():
            self._last_used_btn.destroy()
        last = (self.sorter.config.get("last_source") or
                self.sorter.config.get("last_browse_dir") or "")
        if last and os.path.isdir(last):
            name = os.path.basename(last) or last
            short = name if len(name) <= 16 else name[:14] + ".."
            self._last_used_btn = tk.Button(
                self._qf_top,
                text=f"< {short}",
                font=("TkFixedFont", 8),
                bg="#2a1a3a", fg=HUD_CYAN,
                relief="flat", padx=6,
                activebackground=HIGHLIGHT, activeforeground="white",
                command=lambda p=last: self._expand_to(p))
            self._last_used_btn.pack(side="left", padx=2, pady=2, ipady=2)

    def _open_disk_analyzer(self):
        """Apre l'analizzatore utilizzo disco sulla cartella corrente."""
        initial = (self._current_folder
                   or self.sorter.source_folder
                   or os.path.expanduser("~"))
        if _DISK_ANALYZER_AVAILABLE:
            # Usa root come parent: così chiudere il Browser non chiude DiskAnalyzer
            _open_disk_analyzer(self.sorter.root, sorter=self.sorter,
                                initial_dir=initial)
        else:
            err = globals().get("_DISK_ANALYZER_ERR", "File non trovato")
            messagebox.showwarning(
                "Modulo disk_analyzer non caricato",
                f"Motivo: {err}\n\n"
                f"Cercato in: {SCRIPT_DIR}\n"
                "Assicurati che disk_analyzer.py sia nella stessa cartella "
                "di image_sorter.py",
                parent=self.win)

    def _open_duplicate_finder(self):
        """Apre la finestra di ricerca doppioni per la cartella corrente."""""
        initial = self._current_folder or self.sorter.source_folder or os.path.expanduser("~")
        DuplicateFinder(self.win, self.sorter, initial_dir=initial)

    def _toggle_view_mode(self):
        cycle = {"grid": "list", "list": "tree", "tree": "grid"}
        self._view_mode = cycle.get(self._view_mode, "grid")
        labels = {"grid": "Lista", "list": "Elenco", "tree": "Griglia"}
        colors = {"grid": ACCENT_COLOR, "list": HUD_CYAN, "tree": WARNING}
        fgs    = {"grid": TEXT_COLOR,   "list": "#0a1a2e", "tree": "#0a1a2e"}
        if self._view_btn:
            self._view_btn.config(
                text=labels.get(self._view_mode, "Lista"),
                bg=colors.get(self._view_mode, ACCENT_COLOR),
                fg=fgs.get(self._view_mode, TEXT_COLOR))
        if self._current_folder:
            self._load_thumbnails(self._current_folder)

    def _navigate_to(self, path):
        self._current_folder = path
        self._load_thumbnails(path)
        self._status.config(text=path, fg=MUTED_COLOR)
        self._expand_to(path)
        # Dopo il caricamento, evidenzia il file corrente se è in questa cartella
        current = self.sorter._current_file()
        if current and os.path.dirname(current) == path:
            self.win.after(200, lambda: self._highlight_file(current))

    def _highlight_file(self, filepath):
        """Evidenzia la cella corrispondente al file nella vista corrente."""
        fname = os.path.basename(filepath)
        for cell in self._thumb_inner.winfo_children():
            try:
                # Cerca label con testo uguale al nome del file
                for w in cell.winfo_children():
                    if isinstance(w, tk.Label) and w.cget("text") == fname:
                        cell.config(highlightbackground=HUD_CYAN,
                                    highlightthickness=2)
                        # Scrolla verso la cella
                        self._thumb_inner.update_idletasks()
                        y = cell.winfo_y()
                        ch = self._thumb_canvas.winfo_height()
                        fh = self._thumb_inner.winfo_height()
                        if fh > ch:
                            self._thumb_canvas.yview_moveto(
                                max(0.0, (y - ch//2) / fh))
                        return
            except Exception:
                pass

    def _load_dirs_grid(self, folder, dirs):
        THUMB_SIZE = self._thumb_size
        panel_w = self._thumb_canvas.winfo_width()
        if panel_w < 10:
            panel_w = self._thumb_canvas.winfo_reqwidth()
        COLS = max(1, panel_w // (THUMB_SIZE + 12))
        parent = os.path.dirname(folder)
        # Aggiungi ".." se non siamo alla radice
        nav_dirs  = []
        nav_paths = []
        if parent and parent != folder:
            nav_dirs.append("..")
            nav_paths.append(parent)
        all_names  = nav_dirs  + dirs
        all_paths  = nav_paths + [os.path.join(folder, d) for d in dirs]
        if not all_names:
            self._grid_dir_rows = 1
            return
        # Separatore
        sep = tk.Frame(self._thumb_inner, bg=ACCENT_COLOR, height=1)
        sep.grid(row=0, column=0, columnspan=COLS, sticky="ew", pady=(2,4))
        for i, dname in enumerate(all_names):
            dpath  = all_paths[i]
            row_i  = 1 + i // COLS
            col_i  = i % COLS
            is_parent = (dname == "..")
            cell_sz   = (THUMB_SIZE // 2 + 6) if is_parent else (THUMB_SIZE + 6)
            cell_h    = (THUMB_SIZE // 2 + 16) if is_parent else (THUMB_SIZE + 22)
            cell = tk.Frame(self._thumb_inner, bg=BG_COLOR,
                            width=cell_sz, height=cell_h)
            cell.grid(row=row_i, column=col_i, padx=3, pady=3, sticky="nsew")
            cell.grid_propagate(False)
            icon_size = min((THUMB_SIZE // 2 - 6) if is_parent else (THUMB_SIZE - 10), 80)
            cv = tk.Canvas(cell, width=icon_size, height=icon_size,
                           bg=BG_COLOR, highlightthickness=0)
            cv.pack(pady=(4,0))
            s = icon_size
            cv.create_rectangle(2, s//4, s-2, s-2,
                                fill=HUD_DIM, outline=HUD_CYAN, width=1)
            cv.create_rectangle(2, s//4, s//3, s//4+s//8,
                                fill=HUD_CYAN, outline="", width=0)
            if is_parent:
                # Freccia su
                cv.create_line(s//2, s//3, s//2, s*2//3, fill=HUD_CYAN, width=2)
                cv.create_line(s//3, s//2, s//2, s//3, s*2//3, s//2,
                               fill=HUD_CYAN, width=2)
            short = dname if len(dname) <= 12 else dname[:11] + "."
            tk.Label(cell, text=short, font=("TkFixedFont", 6),
                     bg=BG_COLOR, fg=HUD_CYAN).pack()
            if is_parent:
                for w in (cell, cv):
                    w.bind("<Button-1>",
                           lambda e, p=dpath: self._navigate_to(p))
                    w.bind("<Double-Button-1>",
                           lambda e, p=dpath: self._navigate_to(p))
            else:
                self._dir_cell_refs[dpath] = (cell, BG_COLOR)
                for w in (cell, cv):
                    w.bind("<Double-Button-1>",
                           lambda e, p=dpath: self._navigate_to(p))
                    w.bind("<Button-1>",
                           lambda e, p=dpath: self._show_tree_actions(p))
                    w.bind("<Button-3>",
                           lambda e, p=dpath: self._show_tree_actions(p))
        self._grid_dir_rows = 1 + (len(dirs) + COLS - 1) // COLS + 1

    def _load_list_view(self, folder, dirs, files):
        """Visualizzazione a lista: thumbnail piccola + info dettagliate per ogni file."""
        inner = self._thumb_inner
        inner.columnconfigure(0, weight=0)  # thumbnail
        inner.columnconfigure(1, weight=1)  # info

        # Header
        hdr = tk.Frame(inner, bg=ACCENT_COLOR)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0,2))
        hdr.columnconfigure(1, weight=1)
        tk.Label(hdr, text="  Anteprima", font=("TkFixedFont", 7),
                 bg=ACCENT_COLOR, fg=MUTED_COLOR, width=10).grid(row=0, column=0, padx=4, pady=2)
        tk.Label(hdr, text="Nome file  |  Dimensione  |  Data modifica  |  Risoluzione",
                 font=("TkFixedFont", 7), bg=ACCENT_COLOR,
                 fg=MUTED_COLOR, anchor="w").grid(row=0, column=1, sticky="ew", padx=4)

        THUMB = 56

        # Cartelle in cima: prima ".." poi le sottocartelle
        parent = os.path.dirname(folder)
        nav_dirs  = [".."]  + list(dirs)  if parent and parent != folder else list(dirs)
        nav_paths = [parent] + [os.path.join(folder, d) for d in dirs] if parent and parent != folder else [os.path.join(folder, d) for d in dirs]
        for i, dname in enumerate(nav_dirs):
            dpath = nav_paths[i]
            bg    = PANEL_COLOR if i % 2 == 0 else BG_COLOR
            cv = tk.Canvas(inner, width=THUMB, height=THUMB,
                           bg=bg, highlightthickness=0)
            cv.grid(row=i+1, column=0, padx=(4,2), pady=1, sticky="w")
            s = THUMB
            cv.create_rectangle(4, s//4, s-4, s-4,
                                fill=HUD_DIM, outline=HUD_CYAN, width=1)
            cv.create_rectangle(4, s//4, s//3, s//4+s//8,
                                fill=HUD_CYAN, outline="")
            info = tk.Frame(inner, bg=bg)
            info.grid(row=i+1, column=1, sticky="ew", padx=(2,4), pady=1)
            info.columnconfigure(0, weight=1)
            try:
                nf = sum(1 for f in os.listdir(dpath)
                         if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS)
                sub = f"{nf} immagini"
            except OSError:
                sub = ""
            tk.Label(info, text=dname, font=("TkFixedFont", 8, "bold"),
                     bg=bg, fg=HUD_CYAN, anchor="w").grid(row=0, column=0, sticky="w")
            tk.Label(info, text=sub, font=("TkFixedFont", 7),
                     bg=bg, fg=MUTED_COLOR, anchor="w").grid(row=1, column=0, sticky="w")
            is_parent_dir = (dname == "..")
            if is_parent_dir:
                for w in (cv, info):
                    w.bind("<Button-1>",
                           lambda e, p=dpath: self._navigate_to(p))
                    w.bind("<Double-Button-1>",
                           lambda e, p=dpath: self._navigate_to(p))
            else:
                self._dir_cell_refs[dpath] = (info, bg)
                for w in (cv, info):
                    w.bind("<Double-Button-1>",
                           lambda e, p=dpath: self._navigate_to(p))
                    w.bind("<Button-1>",
                           lambda e, p=dpath: self._show_tree_actions(p))
                    w.bind("<Button-3>",
                           lambda e, p=dpath: self._show_tree_actions(p))

        dir_offset = len(nav_dirs) + 1

        def load_batch(idx):
            for _ in range(8):
                if idx >= len(files):
                    return
                fname = files[idx]
                fpath = os.path.join(folder, fname)
                row_i = idx + dir_offset
                bg = PANEL_COLOR if idx % 2 == 0 else BG_COLOR
                try:
                    img = load_thumbnail(fpath, THUMB)
                    if img is None:
                        continue
                    iw, ih = img.size
                    photo = ImageTk.PhotoImage(img)
                    self._thumb_images.append(photo)

                    # Cella contenitore: thumbnail + info nella stessa riga
                    cell_frame = tk.Frame(inner, bg=bg)
                    cell_frame.grid(row=row_i, column=0, columnspan=2,
                                    sticky="ew", padx=2, pady=1)
                    cell_frame.columnconfigure(1, weight=1)
                    self._cell_refs[fpath] = cell_frame

                    # Miniatura dentro la cella
                    lbl = tk.Label(cell_frame, image=photo, bg=bg, cursor="hand2")
                    lbl.grid(row=0, column=0, padx=(4,2), sticky="w")

                    # Info dentro la cella
                    try:
                        fsize = os.path.getsize(fpath)
                        fdate = os.path.getmtime(fpath)
                        date_str = datetime.datetime.fromtimestamp(fdate).strftime("%d/%m/%Y %H:%M")
                        if fsize < 1024:
                            size_str = f"{fsize} B"
                        elif fsize < 1024**2:
                            size_str = f"{fsize/1024:.1f} KB"
                        else:
                            size_str = f"{fsize/1024**2:.1f} MB"
                    except OSError:
                        size_str, date_str = "?", "?"
                        iw, ih = 0, 0

                    info_frame = tk.Frame(cell_frame, bg=bg)
                    info_frame.grid(row=0, column=1, sticky="ew", padx=(2,4))
                    info_frame.columnconfigure(0, weight=1)
                    tk.Label(info_frame, text=fname,
                             font=("TkFixedFont", 8, "bold"),
                             bg=bg, fg=TEXT_COLOR, anchor="w"
                             ).grid(row=0, column=0, sticky="w")
                    tk.Label(info_frame,
                             text=f"{size_str}   {date_str}   {iw}x{ih}px",
                             font=("TkFixedFont", 7),
                             bg=bg, fg=MUTED_COLOR, anchor="w"
                             ).grid(row=1, column=0, sticky="w")

                    def _make_list_click(p, cf):
                        def _click(e):
                            if e.state & 0x0004:
                                self._toggle_select(p, cf)
                            else:
                                self._sel_clear()
                                self._toggle_select(p, cf)
                        return _click

                    clk = _make_list_click(fpath, cell_frame)
                    for w in [cell_frame, lbl, info_frame] + list(info_frame.winfo_children()):
                        w.bind("<Button-1>",        clk)
                        w.bind("<Double-Button-1>", lambda e, p=fpath: self._open_image(p))
                        w.bind("<Button-3>",        lambda e, p=fpath: self._thumb_context_menu(e, p))
                except Exception:
                    pass
                idx += 1
            inner.update_idletasks()
            if idx < len(files):
                self._thumb_job = self.win.after(20, lambda: load_batch(idx))

        self._thumb_job = self.win.after(50, lambda: load_batch(0))



    def _load_tree_view(self, folder, dirs, files):
        """Vista elenco: Treeview con colonne nome/data/dimensione/tipo, ordinabile."""
        # Rimuovi eventuale Treeview precedente
        if getattr(self, '_tv_widget', None):
            try: self._tv_widget.master.destroy()
            except Exception: pass
            self._tv_widget = None

        # Nascondi canvas e mostra il Treeview direttamente nel pannello destro
        self._thumb_canvas.grid_remove()
        # Rimuovi scrollbar laterale del canvas
        for w in list(self._right_panel.grid_slaves()):
            if w is not self._thumb_canvas:
                try: w.grid_remove()
                except Exception: pass

        tv_frame = tk.Frame(self._right_panel, bg=PANEL_COLOR)
        tv_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

        inner = tv_frame   # alias per compatibilità

        style = ttk.Style()
        style.configure("Browser.Treeview",
                        background=PANEL_COLOR, foreground=TEXT_COLOR,
                        fieldbackground=PANEL_COLOR,
                        rowheight=22, font=("TkFixedFont", 8))
        style.configure("Browser.Treeview.Heading",
                        background=ACCENT_COLOR, foreground=HUD_CYAN,
                        font=("TkFixedFont", 8, "bold"), relief="flat")
        style.map("Browser.Treeview",
                  background=[("selected", HIGHLIGHT)],
                  foreground=[("selected", "white")])

        cols = ("name", "size", "date", "type")
        tv = ttk.Treeview(tv_frame, columns=cols, show="headings",
                          style="Browser.Treeview",
                          selectmode="extended")
        tv.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(tv_frame, orient="vertical", command=tv.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(tv_frame, orient="horizontal", command=tv.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tv_frame.rowconfigure(0, weight=1)
        tv_frame.columnconfigure(0, weight=1)

        tv.bind("<Button-4>", lambda e: tv.yview_scroll(-1, "units"))
        tv.bind("<Button-5>", lambda e: tv.yview_scroll( 1, "units"))

        # Intestazioni con ordinamento
        _sort_col  = ["name"]
        _sort_rev  = [False]

        def _sort_by(col):
            if _sort_col[0] == col:
                _sort_rev[0] = not _sort_rev[0]
            else:
                _sort_col[0] = col
                _sort_rev[0] = False
            _rebuild_tree()

        col_cfg = [
            ("name", "Nome",           320, "w"),
            ("size", "Dimensione",     90,  "e"),
            ("date", "Data modifica",  130, "w"),
            ("type", "Tipo",           70,  "w"),
        ]
        for cid, label, width, anchor in col_cfg:
            tv.heading(cid, text=label,
                       command=lambda c=cid: _sort_by(c))
            tv.column(cid, width=width, anchor=anchor, stretch=(cid=="name"))

        # Dati
        _data = []   # [(sort_key, iid, display_values, fpath)]



        # Cartelle
        parent_d = os.path.dirname(folder)
        if parent_d and parent_d != folder:
            tv.insert("", "end", iid="__parent__",
                      values=("[..]", "", "", "cartella"),
                      tags=("dir",))
        for d in sorted(dirs):
            dpath = os.path.join(folder, d)
            try:
                mtime = os.path.getmtime(dpath)
                ds = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
            except OSError:
                ds = ""
            tv.insert("", "end", iid=dpath,
                      values=(f"[{d}]", "", ds, "cartella"),
                      tags=("dir",))

        tv.tag_configure("dir", foreground=HUD_CYAN)

        # File — raccolta dati
        file_rows = []
        for fname in files:
            fpath = os.path.join(folder, fname)
            try:
                st    = os.stat(fpath)
                size  = st.st_size
                mtime = st.st_mtime
                ds    = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
                ext   = os.path.splitext(fname)[1].lower().lstrip(".")
                file_rows.append((fname, size, mtime, ds, ext, fpath))
            except OSError:
                file_rows.append((fname, 0, 0, "", "", fpath))

        def _rebuild_tree():
            # Rimuovi solo le righe file (non cartelle)
            for iid in tv.get_children():
                if iid not in ("__parent__",) and not iid.startswith(folder + "/") or True:
                    try:
                        tags = tv.item(iid, "tags")
                        if "dir" not in tags:
                            tv.delete(iid)
                    except Exception:
                        pass
            # Riordina
            col = _sort_col[0]
            rev = _sort_rev[0]
            if col == "name":
                key = lambda r: r[0].lower()
            elif col == "size":
                key = lambda r: r[1]
            elif col == "date":
                key = lambda r: r[2]
            else:  # type
                key = lambda r: r[4]
            for row in sorted(file_rows, key=key, reverse=rev):
                fname, size, mtime, ds, ext, fpath = row
                tv.insert("", "end", iid=fpath,
                          values=(fname, fmt_size(size), ds, ext or "—"))  # noqa: F821

        _rebuild_tree()

        # Click: selezione
        def _on_tv_click(e):
            iid = tv.identify_row(e.y)
            if not iid:
                return
            tags = tv.item(iid, "tags")
            if "dir" in tags:
                return   # cartelle: non selezionare
            fpath = iid
            if not os.path.isfile(fpath):
                return
            # Aggiorna _selected_files
            sel = set(tv.selection())
            self._selected_files = {s for s in sel
                                    if os.path.isfile(s)}
            if not (e.state & 0x0004):   # senza Ctrl: selezione singola
                self._selected_files = {fpath} if fpath in self._selected_files else {fpath}
            self._update_sel_bar()

        def _on_tv_double(e):
            iid = tv.identify_row(e.y)
            if not iid:
                return
            tags = tv.item(iid, "tags")
            if "dir" in tags:
                if iid == "__parent__":
                    self._navigate_to(os.path.dirname(folder))
                else:
                    self._navigate_to(iid)
            elif os.path.isfile(iid):
                self._open_image(iid)

        def _on_tv_select(e):
            sel = set(tv.selection())
            self._selected_files = {s for s in sel if os.path.isfile(s)}
            self._update_sel_bar()

        def _on_tv_right(e):
            iid = tv.identify_row(e.y)
            if iid and os.path.isfile(iid):
                self._thumb_context_menu(e, iid)

        tv.bind("<ButtonRelease-1>", _on_tv_select)
        tv.bind("<Double-Button-1>", _on_tv_double)
        tv.bind("<Button-3>",        _on_tv_right)
        tv.bind("<Control-a>",       lambda e: (
            tv.selection_set(tv.get_children()),
            _on_tv_select(e)))
        tv.bind("<Delete>", lambda e:
            self._trash_selection(list(self._selected_files))
            if self._selected_files else None)

        self._tv_widget = tv   # riferimento per operazioni esterne

    def _set_sort_mode(self, mode):
        self._sort_mode = mode
        self._refresh_sort_btns()
        if self._current_folder:
            self._load_thumbnails(self._current_folder)

    def _refresh_sort_btns(self):
        for mode, btn in self._sort_btns.items():
            btn.config(bg=HUD_CYAN if mode == self._sort_mode else ACCENT_COLOR,
                       fg="#0a1a2e" if mode == self._sort_mode else TEXT_COLOR)

    def _load_thumbnails(self, folder):
        """Carica le thumbnail della cartella nel pannello, in modo lazy."""
        # Cancella job precedente se ancora in coda
        if self._thumb_job:
            self.win.after_cancel(self._thumb_job)
            self._thumb_job = None

        # Svuota pannello, selezione e riferimenti
        self._selected_files.clear()
        self._cell_refs.clear()
        self._dir_cell_refs.clear()
        if hasattr(self, '_sel_bar') and self._sel_bar.winfo_exists():
            self._sel_bar.grid_remove()
        for w in self._thumb_inner.winfo_children():
            w.destroy()
        self._thumb_images.clear()

        # Raccogli cartelle e immagini
        try:
            entries  = os.listdir(folder)
            dirs     = sorted([f for f in entries if os.path.isdir(os.path.join(folder, f))],
                               key=lambda f: f.lower())
            mode     = getattr(self, '_sort_mode', 'name')
            all_imgs = [f for f in entries
                        if os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS]
            if mode == "size":
                all_imgs.sort(key=lambda f: os.path.getsize(os.path.join(folder, f)),
                              reverse=True)
            elif mode == "date":
                all_imgs.sort(key=lambda f: os.path.getmtime(os.path.join(folder, f)),
                              reverse=True)
            else:
                all_imgs.sort(key=lambda f: f.lower())
            files = all_imgs
        except OSError:
            return

        if not dirs and not files:
            tk.Label(self._thumb_inner, text="Cartella vuota",
                     font=("TkFixedFont", 8), bg=PANEL_COLOR,
                     fg=MUTED_COLOR).pack(pady=20)
            return

        view = getattr(self, '_view_mode', 'grid')

        # Ripristina canvas se stavamo nella vista elenco
        if view != "tree":
            if getattr(self, '_tv_widget', None):
                try: self._tv_widget.master.destroy()
                except Exception: pass
                self._tv_widget = None
            # Ripristina canvas e scrollbar
            for w in list(self._right_panel.grid_slaves()):
                try: w.grid()
                except Exception: pass
            self._thumb_canvas.grid(row=0, column=0, sticky="nsew")

        if view == "list":
            self._load_list_view(folder, dirs, files)
            return
        if view == "tree":
            self._load_tree_view(folder, dirs, files)
            return

        # Modalita griglia: prima le cartelle, poi le immagini
        self._load_dirs_grid(folder, dirs)

        THUMB_SIZE = self._thumb_size
        # Colonne dinamiche: quante ne entrano nella larghezza del pannello
        panel_w = self._thumb_canvas.winfo_width()
        if panel_w < 10:  # finestra non ancora renderizzata
            panel_w = self._thumb_canvas.winfo_reqwidth()
        cell_w = THUMB_SIZE + 12  # thumbnail + padding
        COLS = max(1, panel_w // cell_w)

        # Resetta colonne precedenti e riconfigura
        for ci in range(12):
            self._thumb_inner.columnconfigure(ci, weight=0)
        for ci in range(COLS):
            self._thumb_inner.columnconfigure(ci, weight=1)

        # Carica in batch con after() per non bloccare la UI
        def load_batch(idx):
            for _ in range(8):   # 8 thumbnail per batch
                if idx >= len(files):
                    return
                fname = files[idx]
                fpath = os.path.join(folder, fname)
                dir_rows = getattr(self, '_grid_dir_rows', 1)
                row_i = dir_rows + idx // COLS
                col_i = idx % COLS
                try:
                    img = load_thumbnail(fpath, THUMB_SIZE)
                    if img is None:
                        continue
                    photo = ImageTk.PhotoImage(img)
                    self._thumb_images.append(photo)

                    cell = tk.Frame(self._thumb_inner, bg=PANEL_COLOR,
                                    width=THUMB_SIZE+6, height=THUMB_SIZE+22)
                    cell.grid(row=row_i, column=col_i,
                              padx=3, pady=3, sticky="nsew")
                    cell.grid_propagate(False)

                    btn = tk.Label(cell, image=photo, bg=PANEL_COLOR,
                                   cursor="hand2")
                    btn.pack()
                    # Nome file troncato
                    short = tk_safe((fname[:12] + "...") if len(fname) > 14 else fname)
                    tk.Label(cell, text=short,
                             font=("TkFixedFont", 6), bg=PANEL_COLOR,
                             fg=MUTED_COLOR).pack()

                    # Registra riferimento cella per highlight selezione
                    self._cell_refs[fpath] = cell

                    # Click singolo -> apre immagine (se nessuna selezione attiva)
                    #   o deseleziona tutto e apre
                    # Ctrl+Click -> toggle selezione multipla
                    # Doppio click -> apre sempre
                    def _make_click(p, c):
                        def on_click(e):
                            if e.state & 0x0004:   # Ctrl tenuto: toggle aggiunta
                                self._toggle_select(p, c)
                            else:
                                # Click senza Ctrl: seleziona solo questa
                                self._sel_clear()
                                self._toggle_select(p, c)
                        def on_double(e):
                            self._open_image(p)
                        return on_click, on_double
                    _oc, _od = _make_click(fpath, cell)
                    btn.bind("<Button-1>",       _oc)
                    btn.bind("<Double-Button-1>", _od)
                    btn.bind("<Button-3>",
                             lambda e, p=fpath: self._thumb_context_menu(e, p))
                except Exception:
                    pass
                idx += 1
            self._thumb_inner.update_idletasks()
            if idx < len(files):
                self._thumb_job = self.win.after(20, lambda: load_batch(idx))

        self._thumb_job = self.win.after(50, lambda: load_batch(0))

    def _sel_all(self):
        """Seleziona tutti i file della vista corrente (Ctrl+A)."""
        for fpath, cell in self._cell_refs.items():
            if fpath not in self._selected_files:
                self._selected_files.add(fpath)
                try:
                    cell.config(bg="#1a4a1a")
                    for w in cell.winfo_children():
                        w.config(bg="#1a4a1a")
                except Exception:
                    pass
        self._update_sel_bar()

    def _toggle_select(self, fpath, cell):
        """Toggle selezione di un file nel browser."""
        # Deseleziona cartella se presente
        if getattr(self.sorter, '_selected_browser_folder', None):
            self._deselect_folder_cell()
            self.sorter._selected_browser_folder = None
            self._clear_action_btns()
        if fpath in self._selected_files:
            self._selected_files.discard(fpath)
            try:
                cell.config(bg=PANEL_COLOR)
                for w in cell.winfo_children():
                    w.config(bg=PANEL_COLOR)
            except Exception:
                pass
        else:
            self._selected_files.add(fpath)
            try:
                cell.config(bg="#1a4a1a")
                for w in cell.winfo_children():
                    w.config(bg="#1a4a1a")
            except Exception:
                pass
        self._update_sel_bar()

    def _update_sel_bar(self):
        """Mostra/aggiorna la barra azioni selezione multipla."""
        n = len(self._selected_files)
        if n == 0:
            self._sel_bar.grid_remove()
            return
        # Ricostruisce la barra
        for w in self._sel_bar.winfo_children():
            w.destroy()
        self._sel_bar.grid()

        tk.Label(self._sel_bar,
                 text=f"  {n} file selezionati  ",
                 font=("TkFixedFont", 9, "bold"),
                 bg="#152515", fg="#00ff88").pack(side="left", padx=(8,4), pady=6)

        # Bottoni preset del sorter
        preset_name = self.sorter.config.get("active_preset", "")
        slots = self.sorter.config["presets"].get(preset_name, {})
        for k in sorted(KEYS, key=int):
            slot = slots.get(k, {})
            dest = slot.get("path", "").strip()
            if not dest:
                continue
            lbl   = slot.get("label", k) or k
            short = lbl[:7] + "." if len(lbl) > 7 else lbl
            color = KEY_COLORS[KEYS.index(k)]
            tk.Button(self._sel_bar,
                      text=f"{k} {short}",
                      font=("TkFixedFont", 8, "bold"),
                      bg=color, fg="white", relief="flat", padx=5,
                      activebackground=HIGHLIGHT,
                      command=lambda d=dest: self._sel_move(d)
                      ).pack(side="left", padx=2, pady=4, ipady=3)

        # Tasti azione a destra
        tk.Button(self._sel_bar, text="Cestina selezionati",
                  font=("TkFixedFont", 8), bg="#c0392b", fg="white",
                  relief="flat", padx=8,
                  command=self._sel_trash
                  ).pack(side="right", padx=2, pady=4, ipady=3)

        tk.Button(self._sel_bar, text="Deseleziona tutto",
                  font=("TkFixedFont", 8), bg="#2a1a1a", fg=MUTED_COLOR,
                  relief="flat", padx=8,
                  command=self._sel_clear
                  ).pack(side="right", padx=8, pady=4, ipady=3)

        tk.Button(self._sel_bar, text="Copia",
                  font=("TkFixedFont", 8), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=8,
                  command=self._sel_copy_ask
                  ).pack(side="right", padx=2, pady=4, ipady=3)

        tk.Button(self._sel_bar, text="Rinomina serie",
                  font=("TkFixedFont", 8), bg=WARNING, fg="white",
                  relief="flat", padx=8,
                  command=self._sel_rename_batch
                  ).pack(side="right", padx=(8,2), pady=4, ipady=3)

        # Separatore visivo
        tk.Frame(self._sel_bar, bg=ACCENT_COLOR, width=1
                 ).pack(side="right", fill="y", pady=6, padx=4)

    def _sel_trash(self):
        """Cestina tutti i file selezionati."""
        files = sorted(self._selected_files)
        n = len(files)
        if not n:
            return
        if not messagebox.askyesno(
                "Cestina file selezionati",
                f"Spostare nel cestino {n} file selezionati?",
                parent=self.win):
            return
        trashed, errors = 0, []
        for fp in files:
            if os.path.isfile(fp):
                if send_to_trash(fp):
                    trashed += 1
                else:
                    errors.append(os.path.basename(fp))
        self._sel_clear()
        if self._current_folder:
            self._load_thumbnails(self._current_folder)
        msg = f"{trashed} file cestinati"
        if errors:
            msg += f" ({len(errors)} errori)"
        self._status.config(text=msg, fg=SUCCESS if not errors else WARNING)

    def _clipboard_set(self, files, mode):
        """Imposta la clipboard interna con i file da copiare/tagliare."""
        self._clipboard_files = list(files)
        self._clipboard_mode  = mode
        verb = "Copiati" if mode == "copy" else "Tagliati"
        self._status.config(
            text=f"{verb} {len(files)} file — incolla con tasto destro",
            fg=HUD_CYAN if mode == "copy" else WARNING)

    def _clipboard_paste(self, dest_folder):
        """Incolla i file della clipboard nella cartella di destinazione."""
        if not self._clipboard_files or not dest_folder:
            return
        if not os.path.isdir(dest_folder):
            return
        done, errors = 0, []
        for src_path in self._clipboard_files:
            if not os.path.isfile(src_path):
                continue
            fname    = os.path.basename(src_path)
            dst_path = os.path.join(dest_folder, fname)
            # Rinomina se esiste già
            if os.path.exists(dst_path) and dst_path != src_path:
                base, ext = os.path.splitext(fname)
                i = 1
                while os.path.exists(dst_path):
                    dst_path = os.path.join(dest_folder, f"{base}_{i}{ext}")
                    i += 1
            try:
                if self._clipboard_mode == "cut":
                    shutil.move(src_path, dst_path)
                else:
                    shutil.copy2(src_path, dst_path)
                done += 1
            except Exception as ex:
                errors.append(str(ex))
        if self._clipboard_mode == "cut":
            self._clipboard_files.clear()
            self._clipboard_mode = None
        if self._current_folder:
            self._load_thumbnails(self._current_folder)
        verb = "spostati" if self._clipboard_mode is None else "copiati"
        msg  = f"{done} file {verb}"
        if errors: msg += f" — {len(errors)} errori"
        self._status.config(text=msg,
                            fg=SUCCESS if not errors else HIGHLIGHT)

    def _trash_selection(self, targets):
        """Cestina una lista di file con conferma."""
        if not targets:
            return
        n = len(targets)
        if not messagebox.askyesno(
                "Cestina file",
                f"Spostare nel cestino {n} file?",
                parent=self.win):
            return
        trashed, errors = 0, []
        for fp in targets:
            if os.path.isfile(fp):
                if send_to_trash(fp):
                    trashed += 1
                    self._selected_files.discard(fp)
                else:
                    errors.append(os.path.basename(fp))
        if self._current_folder:
            self._load_thumbnails(self._current_folder)
        self._update_sel_bar()
        msg = f"{trashed} file cestinati"
        if errors: msg += f" ({len(errors)} errori)"
        self._status.config(text=msg,
                            fg=SUCCESS if not errors else WARNING)

    def _sel_clear(self):
        """Deseleziona tutti i file."""
        for fpath in list(self._selected_files):
            cell = self._cell_refs.get(fpath)
            if cell and cell.winfo_exists():
                try:
                    cell.config(bg=PANEL_COLOR)
                    for w in cell.winfo_children():
                        w.config(bg=PANEL_COLOR)
                except Exception:
                    pass
        self._selected_files.clear()
        self._update_sel_bar()

    def _sel_move(self, dest_dir):
        """Sposta i file selezionati nella cartella dest_dir."""
        if not dest_dir or not os.path.isdir(dest_dir):
            try:
                os.makedirs(dest_dir, exist_ok=True)
            except Exception as ex:
                messagebox.showerror("Errore", f"Cartella non valida:\n{ex}",
                                     parent=self.win)
                return
        moved, errors = 0, []
        for fpath in list(self._selected_files):
            if not os.path.isfile(fpath):
                continue
            dest_path = os.path.join(dest_dir, os.path.basename(fpath))
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(os.path.basename(fpath))
                i = 1
                while os.path.exists(dest_path):
                    dest_path = os.path.join(dest_dir, f"{base}_{i}{ext}")
                    i += 1
            try:
                shutil.move(fpath, dest_path)
                moved += 1
            except Exception as ex:
                errors.append(f"{os.path.basename(fpath)}: {ex}")
        self._sel_clear()
        # Ricarica le thumbnail della cartella corrente
        if self._current_folder:
            self._load_thumbnails(self._current_folder)
        msg = f"{moved} file spostati in {os.path.basename(dest_dir)}"
        if errors:
            msg += f"\n{len(errors)} errori"
        self._status.config(text=msg, fg=SUCCESS if not errors else WARNING)

    def _sel_copy_ask(self):
        """Chiede la destinazione e copia i file selezionati."""
        dest = browse_folder_hud(self.win,
            title="Scegli cartella di destinazione",
            initial_dir=self.sorter.config.get("last_browse_dir"),
            config=self.sorter.config)
        if not dest:
            return
        self.sorter.config["last_browse_dir"] = dest
        save_config(self.sorter.config)
        copied, errors = 0, []
        for fpath in list(self._selected_files):
            if not os.path.isfile(fpath):
                continue
            dest_path = os.path.join(dest, os.path.basename(fpath))
            if os.path.exists(dest_path):
                base, ext = os.path.splitext(os.path.basename(fpath))
                i = 1
                while os.path.exists(dest_path):
                    dest_path = os.path.join(dest, f"{base}_{i}{ext}")
                    i += 1
            try:
                shutil.copy2(fpath, dest_path)
                copied += 1
            except Exception as ex:
                errors.append(str(ex))
        self._sel_clear()
        msg = f"{copied} file copiati in {os.path.basename(dest)}"
        if errors:
            msg += f" ({len(errors)} errori)"
        self._status.config(text=msg, fg=SUCCESS if not errors else WARNING)

    def _sel_rename_batch(self):
        """Rinomina in serie i file selezionati."""
        files = sorted(self._selected_files)
        if not files:
            return
        # Prova tool di sistema
        for tool, args in [
            ("thunar",       ["--bulk-rename"] + files),
            ("krename",      files),
            ("gprename",     [os.path.dirname(files[0])]),
            ("metamorphose2",files),
        ]:
            try:
                subprocess.Popen([tool] + args,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return
            except FileNotFoundError:
                continue
        # Nessun tool esterno: dialogo interno
        self._sel_rename_internal(files)

    def _sel_rename_internal(self, files):
        """Rinomina in serie con: nuovo nome, testo aggiuntivo, data EXIF."""
        win = tk.Toplevel(self.win)
        win.withdraw()
        win.title(f"Rinomina in serie — {len(files)} file")
        win.configure(bg=BG_COLOR)
        win.resizable(True, False)
        hud_apply(win)

        tk.Label(win, text=f"Rinomina {len(files)} file selezionati",
                 font=("TkFixedFont", 11, "bold"),
                 bg=BG_COLOR, fg=HUD_CYAN).pack(padx=20, pady=(14,4))

        # Modalità
        mode_fr = tk.Frame(win, bg=BG_COLOR)
        mode_fr.pack(padx=20, pady=(0,6), fill="x")
        mode_var = tk.StringVar(value="new")
        modes = [
            ("new",    "Nuovo nome completo"),
            ("prepend","Aggiungi PRIMA del nome"),
            ("append", "Aggiungi DOPO il nome"),
        ]
        for val, lbl in modes:
            tk.Radiobutton(mode_fr, text=lbl, variable=mode_var, value=val,
                           font=("TkFixedFont", 8),
                           bg=BG_COLOR, fg=TEXT_COLOR,
                           selectcolor=BG_COLOR,
                           activebackground=BG_COLOR, activeforeground=HUD_CYAN,
                           command=lambda: update_preview()
                           ).pack(side="left", padx=(0,12))

        # Campi
        frm = tk.Frame(win, bg=BG_COLOR)
        frm.pack(padx=20, pady=4, fill="x")
        frm.columnconfigure(1, weight=1)

        def _field(r, label, default, vname, hint=None):
            tk.Label(frm, text=label, font=("TkFixedFont", 8),
                     bg=BG_COLOR, fg=MUTED_COLOR,
                     anchor="w").grid(row=r, column=0, sticky="w", pady=3, padx=(0,8))
            v = tk.StringVar(value=default)
            vars_[vname] = v
            e = tk.Entry(frm, textvariable=v, font=("TkFixedFont", 9),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=3, width=26)
            e.grid(row=r, column=1, sticky="ew", ipady=3)
            if hint:
                tk.Label(frm, text=hint, font=("TkFixedFont", 7),
                         bg=BG_COLOR, fg=MUTED_COLOR
                         ).grid(row=r, column=2, sticky="w", padx=6)
            return v

        vars_ = {}
        _field(0, "Prefisso / testo:",  "foto_",  "prefix_var")
        _field(1, "Numero iniziale:",   "1",      "start_var",   "0 = no numero")
        _field(2, "Cifre (es. 3=001):", "3",      "digits_var")
        _field(3, "Suffisso:",          "",       "suffix_var")

        # Opzione data EXIF
        date_fr = tk.Frame(win, bg=BG_COLOR)
        date_fr.pack(padx=20, pady=(4,0), fill="x")
        date_var = tk.BooleanVar(value=False)
        date_fmt_var = tk.StringVar(value="%Y%m%d")
        tk.Checkbutton(date_fr, text="Inserisci data EXIF",
                       variable=date_var,
                       font=("TkFixedFont", 8),
                       bg=BG_COLOR, fg=TEXT_COLOR,
                       selectcolor=BG_COLOR,
                       activebackground=BG_COLOR, activeforeground=HUD_CYAN,
                       command=lambda: update_preview()
                       ).pack(side="left")
        tk.Label(date_fr, text="  Formato:",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left")
        fmt_combo = ttk.Combobox(date_fr, textvariable=date_fmt_var,
                                 values=["%Y%m%d", "%Y-%m-%d", "%d%m%Y", "%Y%m%d_%H%M%S"],
                                 width=16, state="readonly",
                                 font=("TkFixedFont", 8))
        fmt_combo.pack(side="left", padx=4)
        fmt_combo.bind("<<ComboboxSelected>>", lambda e: update_preview())
        tk.Label(date_fr, text="  (fallback: data modifica file)",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left")

        # Cache date EXIF
        _date_cache = {}
        def _get_date(fpath):
            if fpath in _date_cache:
                return _date_cache[fpath]
            date_str = None
            try:
                from PIL import Image as _Img
                from PIL.ExifTags import TAGS as _TAGS
                img = _Img.open(fpath)
                raw = img._getexif()
                if raw:
                    orient_tag = next((k for k,v in _TAGS.items()
                                       if v == "DateTimeOriginal"), None)
                    if not orient_tag:
                        orient_tag = next((k for k,v in _TAGS.items()
                                           if v == "DateTime"), None)
                    if orient_tag and orient_tag in raw:
                        dt_str = raw[orient_tag]
                        import datetime as _dt
                        dt = _dt.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                        date_str = dt.strftime(date_fmt_var.get())
            except Exception:
                pass
            if not date_str:
                # Fallback: data modifica file
                try:
                    import datetime as _dt
                    mtime = os.path.getmtime(fpath)
                    date_str = _dt.datetime.fromtimestamp(mtime).strftime(
                        date_fmt_var.get())
                except Exception:
                    date_str = ""
            _date_cache[fpath] = date_str
            return date_str

        # Anteprima
        tk.Label(win, text="Anteprima (primi 5 file):",
                 font=("TkFixedFont", 8, "bold"),
                 bg=BG_COLOR, fg=MUTED_COLOR).pack(padx=20, pady=(10,2), anchor="w")
        preview_frame = tk.Frame(win, bg=ACCENT_COLOR)
        preview_frame.pack(fill="x", padx=20, pady=(0,8))
        preview_labels = []
        for _ in range(min(5, len(files))):
            lbl = tk.Label(preview_frame, text="",
                           font=("TkFixedFont", 8),
                           bg=ACCENT_COLOR, fg=HUD_CYAN, anchor="w")
            lbl.pack(fill="x", padx=8, pady=1)
            preview_labels.append(lbl)

        def _build_newname(fpath, i):
            ext     = os.path.splitext(fpath)[1]
            oldbase = os.path.splitext(os.path.basename(fpath))[0]
            try:
                n = int(vars_["start_var"].get())
                d = max(1, int(vars_["digits_var"].get()))
            except ValueError:
                n, d = 1, 3
            p  = vars_["prefix_var"].get()
            sx = vars_["suffix_var"].get()
            num_str = str(n+i).zfill(d) if n >= 0 else ""
            date_str = _get_date(fpath) if date_var.get() else ""
            if date_str:
                date_str = "_" + date_str
            mode = mode_var.get()
            if mode == "new":
                return f"{p}{num_str}{date_str}{sx}{ext}"
            elif mode == "prepend":
                return f"{p}{num_str}{date_str}{sx}_{oldbase}{ext}"
            else:  # append
                return f"{oldbase}_{p}{num_str}{date_str}{sx}{ext}"

        def update_preview(*_):
            _date_cache.clear()
            for i, (f, lbl) in enumerate(zip(files, preview_labels)):
                oldname = os.path.basename(f)
                newname = _build_newname(f, i)
                col = HIGHLIGHT if newname == oldname else HUD_CYAN
                lbl.config(text=f"  {oldname}  ->  {newname}", fg=col)

        for v in vars_.values():
            v.trace_add("write", lambda *_: update_preview())
        date_var.trace_add("write", lambda *_: update_preview())
        update_preview()

        msg = tk.Label(win, text="", font=("TkFixedFont", 8),
                       bg=BG_COLOR, fg=HIGHLIGHT)
        msg.pack(padx=20)

        def _apply():
            errors, renamed = [], 0
            for i, fpath in enumerate(files):
                folder  = os.path.dirname(fpath)
                newname = _build_newname(fpath, i)
                newpath = os.path.join(folder, newname)
                if os.path.exists(newpath) and newpath != fpath:
                    errors.append(f"{newname}: gia esistente")
                    continue
                try:
                    os.rename(fpath, newpath)
                    renamed += 1
                except Exception as ex:
                    errors.append(str(ex))
            win.destroy()
            self._sel_clear()
            if self._current_folder:
                self._load_thumbnails(self._current_folder)
            status = f"{renamed} file rinominati"
            if errors:
                status += f" — {len(errors)} errori"
            self._status.config(text=status,
                                fg=SUCCESS if not errors else WARNING)

        bf = tk.Frame(win, bg=BG_COLOR)
        bf.pack(padx=20, pady=(4,16), fill="x")
        tk.Button(bf, text="Rinomina",
                  font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=14,
                  command=_apply).pack(side="left", padx=(0,8), ipady=5)
        tk.Button(bf, text="Annulla",
                  font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=10,
                  command=win.destroy).pack(side="left", ipady=5)

        win.bind("<Return>", lambda e: _apply())
        win.bind("<Escape>", lambda e: win.destroy())

        win.update_idletasks()
        pw = win.winfo_reqwidth()
        ph = win.winfo_reqheight()
        px = self.win.winfo_rootx() + (self.win.winfo_width()  - pw) // 2
        py = self.win.winfo_rooty() + (self.win.winfo_height() - ph) // 2
        win.geometry(f"+{max(0,px)}+{max(0,py)}")
        win.deiconify()
        # win.grab_set()  # rimosso: bloccava altri programmi

    def _open_image(self, filepath):
        """Apre il file nella finestra principale posizionandosi su di esso."""
        folder = os.path.dirname(filepath)
        if folder != self.sorter.source_folder:
            self.sorter._load_source(folder)
        if filepath in self.sorter.images:
            self.sorter.current_index = self.sorter.images.index(filepath)
        else:
            self.sorter.images = self.sorter._load_images()
            if filepath in self.sorter.images:
                self.sorter.current_index = self.sorter.images.index(filepath)
            else:
                self.sorter.current_index = 0
        self.sorter._show_image()
        self.sorter.root.lift()
        self.sorter.root.focus_set()

    def _node_text(self, name, path):
        n_img, n_vid, n_pdf, size = self._img_stats(path)
        parts = []
        indicators = []
        if n_img:  indicators.append("+"); parts.append(f"{n_img} img")
        if n_vid:  indicators.append("v"); parts.append(f"{n_vid} vid")
        if n_pdf:  indicators.append("p"); parts.append(f"{n_pdf} pdf")
        if indicators:
            tag = "[" + "".join(indicators) + "]"
            return f"{tag} {name}  ({', '.join(parts)}, {self._fmt_size(size)})"
        return f"[ ] {name}"

    def _insert_node(self, parent, path, label):
        text = self._node_text(label, path)
        iid  = self.tree.insert(parent, "end", text=text,
                                values=[path], open=False)
        if self._has_subdirs(path):
            self.tree.insert(iid, "end", text="...", values=["__ph__"])
        return iid

    def _populate_root(self):
        self.tree.delete(*self.tree.get_children())
        if os.name == "nt":
            for d in string.ascii_uppercase:
                p = f"{d}:\\"
                if os.path.exists(p):
                    self._insert_node("", p, p)
        else:
            self._insert_node("", "/", "/")

    def _expand_node(self, iid):
        """Sostituisce il placeholder con i figli reali."""
        children = self.tree.get_children(iid)
        if len(children) == 1:
            ph_vals = self.tree.item(children[0], "values")
            if ph_vals and ph_vals[0] == "__ph__":
                self.tree.delete(children[0])
                path = self.tree.item(iid, "values")
                if path:
                    self._populate_children(iid, path[0])

    def _populate_children(self, parent_iid, path):
        try:
            entries = sorted(
                (e for e in os.scandir(path)
                 if e.is_dir(follow_symlinks=False)
                 and (getattr(self, "_show_hidden", False) or not e.name.startswith("."))),
                key=lambda e: e.name.lower())
        except OSError:
            return
        for e in entries:
            # Filtra cartelle senza immagini se richiesto
            # (non filtrare cartelle di sistema di primo livello come /home, /media)
            self._insert_node(parent_iid, e.path, e.name)

    def _has_images_recursive(self, path, depth=1):
        """Controlla se path contiene immagini (depth=1 = solo cartella diretta, veloce)."""
        if depth == 0:
            return False
        try:
            for e in os.scandir(path):
                if e.is_file(follow_symlinks=False):
                    if os.path.splitext(e.name)[1].lower() in MEDIA_EXTENSIONS:
                        return True
                elif e.is_dir(follow_symlinks=False) and depth > 1:
                    if self._has_images_recursive(e.path, depth-1):
                        return True
        except OSError:
            pass
        return False

    def _expand_to(self, target):
        """Espande l'albero fino a target e seleziona il nodo."""
        if not os.path.isdir(target):
            return
        target = os.path.normpath(os.path.realpath(target))

        # Costruisci lista di path dalla root a target
        parts = []
        p = target
        while True:
            parts.insert(0, p)
            parent = os.path.dirname(p)
            if parent == p:
                break
            p = parent

        cur = ""   # nodo corrente nell'albero (stringa vuota = root)
        for part in parts:
            # Espandi il nodo corrente se necessario
            if cur:
                self._expand_node(cur)
                self.tree.item(cur, open=True)
            # Cerca il figlio corrispondente a part
            found = None
            for child in self.tree.get_children(cur):
                vals = self.tree.item(child, "values")
                if vals and os.path.normpath(vals[0]) == part:
                    found = child
                    break
            if found is None:
                break
            cur = found

        if cur:
            self.tree.selection_set(cur)
            self.tree.see(cur)
            self._path_var.set(target)
            # Carica subito le anteprime della cartella selezionata
            self._current_folder = target
            self._load_thumbnails(target)

    def _go_to_path(self):
        p = self._path_var.get().strip()
        if p and os.path.isdir(p):
            self._expand_to(p)
        else:
            self._status.config(text=f"Percorso non trovato: {p}", fg=HIGHLIGHT)

    # --- eventi -------------------------------------------------------

    def _on_open(self, event):
        iid = self.tree.focus()
        if iid:
            self._expand_node(iid)

    def _on_click(self, event):
        iid = self.tree.focus()
        if not iid:
            return
        vals = self.tree.item(iid, "values")
        if not vals or vals[0] == "__ph__":
            return
        path = vals[0]
        if not os.path.isdir(path):
            return
        self._path_var.set(path)
        self.sorter.config["last_browse_dir"] = path
        self._refresh_last_used_btn()
        try:
            entries = os.listdir(path)
            imgs = sum(1 for f in entries if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS)
            vids = sum(1 for f in entries if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS)
            pdfs = sum(1 for f in entries if os.path.splitext(f)[1].lower() in PDF_EXTENSIONS)
            col  = SUCCESS if (imgs+vids+pdfs) > 0 else MUTED_COLOR
            name = os.path.basename(path) or path
            parts = []
            if imgs: parts.append(f"{imgs} img")
            if vids: parts.append(f"{vids} vid")
            if pdfs: parts.append(f"{pdfs} pdf")
            info = ", ".join(parts) if parts else "vuota"
            self._status.config(text=f"{info}  —  {name}", fg=col)
        except OSError:
            pass
        # Carica thumbnail nel pannello a destra
        self._current_folder = path
        self._load_thumbnails(path)
        self._refresh_assign_panel()

    def _on_double_click(self, event):
        iid = self.tree.focus()
        if not iid:
            return
        vals = self.tree.item(iid, "values")
        if not vals or vals[0] == "__ph__":
            return
        path = vals[0]
        if os.path.isdir(path):
            self._load_folder(path)

    def _load_folder(self, path):
        self.sorter._load_source(path)
        self.sorter.root.lift()
        self.sorter.root.focus_set()
        imgs = len(self.sorter.images)
        self._status.config(
            text=tk_safe(f"Aperta: {os.path.basename(path)}  ({imgs} immagini)"),
            fg=SUCCESS if imgs > 0 else WARNING)
        self._current_folder = path
        self._load_thumbnails(path)
        self._refresh_assign_panel()

    def _on_tree_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        self.tree.selection_set(iid)
        vals = self.tree.item(iid, "values")
        if not vals or vals[0] == "__ph__":
            return
        path = vals[0]
        if not os.path.isdir(path):
            return
        name  = os.path.basename(path) or path
        short = name if len(name) <= 30 else name[:28] + ".."
        # Mostra info nella barra di stato invece di un menu popup
        self._status.config(
            text=f"{short}  |  [doppio click = apri]  [copia: {path}]",
            fg=TEXT_COLOR)
        # Piccolo menu inline sulla barra di stato tramite bottoni temporanei
        self._show_tree_actions(path)

    def _thumb_context_menu(self, event, filepath):
        """Menu contestuale per il tasto destro sull'anteprima.
        Se ci sono file selezionati, opera sulla selezione.
        Il secondo tasto destro chiude il menu."""
        # Se il file cliccato non è nella selezione, aggiungi
        multi = len(self._selected_files) > 1
        if filepath not in self._selected_files and not multi:
            # Selezione singola: opera solo su questo file
            targets = [filepath]
        else:
            targets = sorted(self._selected_files) if self._selected_files else [filepath]

        multi = len(targets) > 1
        fname = os.path.basename(filepath)
        short = fname if len(fname) <= 32 else fname[:30] + ".."
        label = f"{len(targets)} file selezionati" if multi else short

        menu = tk.Menu(self.win, tearoff=0,
                       bg=PANEL_COLOR, fg=TEXT_COLOR,
                       activebackground=HIGHLIGHT,
                       activeforeground="white",
                       relief="flat", bd=0,
                       font=("TkFixedFont", 9))
        menu.add_command(label=label, state="disabled",
                         font=("TkFixedFont", 8, "bold" if multi else ""))
        menu.add_separator()

        if not multi:
            menu.add_command(label="Apri",
                             command=lambda: self._open_image(filepath))
        if not multi:
            menu.add_command(label="Rinomina...",
                             command=lambda: self._rename_file_popup(filepath))
        else:
            menu.add_command(label="Rinomina serie...",
                             command=lambda: self._sel_rename_batch())
        if not multi:
            menu.add_command(label="Copia percorso",
                             command=lambda: self._copy_path(filepath))

        menu.add_separator()
        menu.add_command(label="Copia",
                         command=lambda: self._clipboard_set(targets, "copy"))
        menu.add_command(label="Taglia",
                         command=lambda: self._clipboard_set(targets, "cut"))
        if self._clipboard_files:
            mode_lbl = "Copia" if self._clipboard_mode == "copy" else "Sposta"
            n_clip   = len(self._clipboard_files)
            menu.add_command(
                label=f"Incolla qui ({mode_lbl} {n_clip} file)",
                command=lambda: self._clipboard_paste(
                    os.path.dirname(filepath)))
        menu.add_separator()
        menu.add_command(label="Sposta nel cestino",
                         command=lambda: self._trash_selection(targets))

        # Chiudi cliccando fuori o col tasto destro
        _unbound = [False]
        _bid = [None]
        def _close_on_outside(e):
            if _unbound[0]: return
            _unbound[0] = True
            try: self.win.unbind("<ButtonPress>", _bid[0])
            except Exception: pass
            try: menu.unpost()
            except Exception: pass
        def _on_unmap(e=None):
            if _unbound[0]: return
            _unbound[0] = True
            try: self.win.unbind("<ButtonPress>", _bid[0])
            except Exception: pass
        menu.bind("<Unmap>", _on_unmap)
        menu.bind("<Button-3>", lambda e: (menu.unpost(), None))

        # <Unmap> rimosso: distruggeva il menu prima del click
        menu.tk_popup(event.x_root, event.y_root)
        # Registra il bind DOPO tk_popup per non interferire
        _bid[0] = self.win.bind("<ButtonPress>", _close_on_outside, add=True)

    def _highlight_folder_cell(self, dpath):
        """Colora in verde la cella della cartella selezionata."""
        info = self._dir_cell_refs.get(dpath)
        if info:
            widget, orig_bg = info
            try:
                widget.config(bg="#1a4a1a")
                for w in widget.winfo_children():
                    try: w.config(bg="#1a4a1a")
                    except Exception: pass
            except Exception:
                pass

    def _deselect_folder_cell(self):
        """Ripristina il colore originale di tutte le celle cartella."""
        for dpath, (widget, orig_bg) in list(self._dir_cell_refs.items()):
            try:
                widget.config(bg=orig_bg)
                for w in widget.winfo_children():
                    try: w.config(bg=orig_bg)
                    except Exception: pass
            except Exception:
                pass

    def _show_tree_actions(self, path):
        """Mostra bottoni azione su 2 righe per una cartella."""
        self._clear_action_btns()
        # Deseleziona la cartella precedente
        self._deselect_folder_cell()
        # Deseleziona i file se presenti
        if self._selected_files:
            self._sel_clear()
        # Imposta la cartella come "selezionata" per i comandi preset/deck
        self.sorter._selected_browser_folder = path
        # Colora in verde la cella della cartella selezionata
        self._highlight_folder_cell(path)
        name = os.path.basename(path) or path

        af = tk.Frame(self.win, bg="#152515")
        af.grid(row=4, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        af.columnconfigure(0, weight=1)

        # Riga 1: nome + azioni base + x
        row1 = tk.Frame(af, bg="#152515")
        row1.grid(row=0, column=0, sticky="ew", pady=(2,1))

        tk.Label(row1, text=name,
                 font=("TkFixedFont", 8, "bold"),
                 bg="#152515", fg=HUD_CYAN).pack(side="left", padx=(8,8))
        tk.Button(row1, text="Apri come sorgente",
                  font=("TkFixedFont", 8), bg=SUCCESS, fg="white",
                  relief="flat", padx=6, activebackground=HIGHLIGHT,
                  command=lambda: (self._load_folder(path),
                                   self._clear_action_btns())
                  ).pack(side="left", padx=(0,4), ipady=2)
        tk.Button(row1, text="Rinomina",
                  font=("TkFixedFont", 8), bg=WARNING, fg="white",
                  relief="flat", padx=6, activebackground=HIGHLIGHT,
                  command=lambda: (self._clear_action_btns(),
                                   self._rename_folder(path))
                  ).pack(side="left", padx=(0,4), ipady=2)
        tk.Button(row1, text="Copia percorso",
                  font=("TkFixedFont", 8), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=6, activebackground=HIGHLIGHT,
                  command=lambda: (self._copy_path(path),
                                   self._clear_action_btns())
                  ).pack(side="left", padx=(0,4), ipady=2)
        tk.Button(row1, text="Cestina",
                  font=("TkFixedFont", 8), bg="#c0392b", fg="white",
                  relief="flat", padx=6, activebackground=HIGHLIGHT,
                  command=lambda: self._trash_folder(path)
                  ).pack(side="left", padx=(0,4), ipady=2)
        tk.Button(row1, text="x",
                  font=("TkFixedFont", 8), bg=PANEL_COLOR, fg=MUTED_COLOR,
                  relief="flat",
                  command=self._clear_action_btns
                  ).pack(side="right", padx=4, ipady=2)

        # Riga 2: istruzione uso preset
        row2 = tk.Frame(af, bg="#152515")
        row2.grid(row=1, column=0, sticky="ew", pady=(0,2))
        tk.Label(row2,
                 text="Cartella selezionata per spostamento — usa i tasti 1-9 o il deck per spostarla",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left", padx=2)

        self._action_frame = af

    def _move_folder_to(self, folder_path, dest_dir, dest_label):
        """Sposta una cartella in una destinazione preset."""
        if not os.path.isdir(folder_path):
            self._status.config(text="Cartella non trovata.", fg=HIGHLIGHT)
            return
        folder_name = os.path.basename(folder_path)
        dest = os.path.join(dest_dir, folder_name)
        if os.path.normpath(folder_path) == os.path.normpath(dest_dir):
            self._status.config(
                text="Destinazione uguale alla posizione attuale.", fg=HIGHLIGHT)
            return
        if os.path.exists(dest):
            answer = messagebox.askyesno(
                "Cartella esistente",
                "Esiste gia una cartella con lo stesso nome.\nSovrascrivere?",
                parent=self.win)
            if not answer:
                return
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(folder_path, dest)
            self._status.config(
                text=folder_name + "  ->  " + dest_label + "  (" + dest_dir + ")",
                fg=SUCCESS)
            parent = os.path.dirname(folder_path)
            self._load_thumbnails(parent)
            self._expand_to(parent)
        except Exception as ex:
            self._status.config(text="Errore: " + str(ex)[:60], fg=HIGHLIGHT)

    def _trash_folder(self, folder_path):
        """Cestina una cartella con conferma."""
        name = os.path.basename(folder_path)
        answer = messagebox.askyesno(
            "Cestina cartella",
            "Spostare nel cestino la cartella:\n" + name + "\n\nContenuto incluso.",
            parent=self.win)
        if not answer:
            return
        try:
            if send_to_trash(folder_path):
                self._status.config(
                    text="Cartella '" + name + "' cestinata.", fg=SUCCESS)
                parent = os.path.dirname(folder_path)
                self._load_thumbnails(parent)
                self._expand_to(parent)
                self._clear_action_btns()
            else:
                self._status.config(text="Impossibile cestinare.", fg=HIGHLIGHT)
        except Exception as ex:
            self._status.config(text="Errore: " + str(ex)[:60], fg=HIGHLIGHT)

    def _rename_folder(self, folder_path):
        """Popup per rinominare una cartella."""
        parent = os.path.dirname(folder_path)
        old_name = os.path.basename(folder_path)

        win = tk.Toplevel(self.win)
        win.withdraw()
        win.title("Rinomina cartella")
        win.configure(bg=BG_COLOR)
        win.resizable(False, False)
        win.transient(self.win)
        hud_apply(win)

        tk.Label(win, text="Nuovo nome cartella:",
                 font=("TkFixedFont", 9), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(padx=16, pady=(12,4))
        var = tk.StringVar(value=old_name)
        entry = tk.Entry(win, textvariable=var,
                         font=("TkFixedFont", 10),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=4, width=28)
        entry.pack(padx=16, pady=4, ipady=4)
        entry.selection_range(0, tk.END)
        entry.focus_set()
        msg = tk.Label(win, text="", font=("TkFixedFont", 8),
                       bg=BG_COLOR, fg=HIGHLIGHT)
        msg.pack(padx=16)

        def _save():
            new_name = var.get().strip()
            if not new_name or new_name == old_name:
                win.destroy()
                return
            new_path = os.path.join(parent, new_name)
            if os.path.exists(new_path):
                msg.config(text="Nome già esistente.")
                return
            try:
                os.rename(folder_path, new_path)
                win.destroy()
                # Aggiorna la cartella corrente se necessario
                if self._current_folder and self._current_folder.startswith(folder_path):
                    self._current_folder = self._current_folder.replace(
                        folder_path, new_path, 1)
                # Ricostruisce l'albero e naviga al nuovo path
                self._populate_root()
                self._expand_to(new_path)
                # Ricarica thumbnail se stavamo guardando la cartella rinominata
                if self._current_folder and self._current_folder.startswith(new_path):
                    self._load_thumbnails(self._current_folder)
            except Exception as ex:
                msg.config(text=f"Errore: {str(ex)[:40]}")

        bf = tk.Frame(win, bg=BG_COLOR)
        bf.pack(padx=16, pady=(4,12), fill="x")
        tk.Button(bf, text="Rinomina", font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=10,
                  command=_save).pack(side="left", padx=(0,6), ipady=4)
        tk.Button(bf, text="Annulla", font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=10,
                  command=win.destroy).pack(side="left", ipady=4)
        entry.bind("<Return>",   lambda e: _save())
        entry.bind("<KP_Enter>", lambda e: _save())
        entry.bind("<Escape>", lambda e: win.destroy())

        win.update_idletasks()
        pw = win.winfo_reqwidth()
        ph = win.winfo_reqheight()
        px = self.win.winfo_rootx() + (self.win.winfo_width()  - pw) // 2
        py = self.win.winfo_rooty() + (self.win.winfo_height() - ph) // 2
        win.geometry(f"+{px}+{py}")
        win.deiconify()
        # win.grab_set()  # rimosso: bloccava altri programmi

    def _trash_thumb(self, filepath):
        """Sposta il file nel cestino dall'anteprima del browser."""
        fname = os.path.basename(filepath)
        if not messagebox.askyesno("Cestina file",
                                   f"Spostare nel cestino?\n{fname}",
                                   parent=self.win):
            return
        if send_to_trash(filepath):
            self._status.config(text=f"Cestinato: {fname}", fg=SUCCESS)
            if self._current_folder:
                self._load_thumbnails(self._current_folder)
        else:
            messagebox.showerror("Errore",
                f"Impossibile spostare nel cestino:\n{fname}",
                parent=self.win)

    def _rename_file_popup(self, filepath):
        """Popup per rinominare un file dall'anteprima del browser."""
        folder = os.path.dirname(filepath)
        old_name = os.path.basename(filepath)
        base, ext = os.path.splitext(old_name)

        win = tk.Toplevel(self.win)
        win.withdraw()
        win.title("Rinomina file")
        win.configure(bg=BG_COLOR)
        win.resizable(False, False)
        win.transient(self.win)
        hud_apply(win)

        tk.Label(win, text=f"Rinomina  {ext}",
                 font=("TkFixedFont", 9, "bold"), bg=BG_COLOR,
                 fg=HUD_CYAN).pack(padx=16, pady=(12,2))
        var = tk.StringVar(value=base)
        entry = tk.Entry(win, textvariable=var,
                         font=("TkFixedFont", 10),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=4, width=28)
        entry.pack(padx=16, pady=4, ipady=4)
        entry.selection_range(0, tk.END)
        entry.focus_set()
        msg = tk.Label(win, text="", font=("TkFixedFont", 8),
                       bg=BG_COLOR, fg=HIGHLIGHT)
        msg.pack(padx=16)

        def _save():
            new_base = var.get().strip()
            if not new_base:
                msg.config(text="Nome non valido.")
                return
            new_path = os.path.join(folder, new_base + ext)
            if os.path.exists(new_path) and new_path != filepath:
                msg.config(text="Nome già esistente.")
                return
            try:
                os.rename(filepath, new_path)
                win.destroy()
                if self._current_folder:
                    self._load_thumbnails(self._current_folder)
            except Exception as ex:
                msg.config(text=str(ex)[:40])

        bf = tk.Frame(win, bg=BG_COLOR)
        bf.pack(padx=16, pady=(4,12), fill="x")
        tk.Button(bf, text="Rinomina", font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=10,
                  command=_save).pack(side="left", padx=(0,6), ipady=4)
        tk.Button(bf, text="Annulla", font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=10,
                  command=win.destroy).pack(side="left", ipady=4)
        entry.bind("<Return>", lambda e: (_save(), "break")[1])
        win.bind("<Escape>", lambda e: win.destroy())

        win.update_idletasks()
        pw, ph = win.winfo_reqwidth(), win.winfo_reqheight()
        px = self.win.winfo_rootx() + (self.win.winfo_width()  - pw) // 2
        py = self.win.winfo_rooty() + (self.win.winfo_height() - ph) // 2
        win.geometry(f"+{px}+{py}")
        win.deiconify()
        # win.grab_set()  # rimosso: bloccava altri programmi

    def _show_thumb_actions(self, filepath):
        """Barra azioni inline per una thumbnail: bottoni + campo rinomina."""
        self._clear_action_btns()
        af = tk.Frame(self.win, bg=PANEL_COLOR)
        af.grid(row=3, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        self._action_frame = af
        self._build_action_btns(af, filepath)

    def _build_action_btns(self, af, filepath):
        """Costruisce i bottoni azione nella barra."""
        for w in af.winfo_children():
            w.destroy()
        fname = os.path.basename(filepath)
        short = fname if len(fname) <= 30 else fname[:28] + ".."
        tk.Label(af, text=short, font=("TkFixedFont", 7),
                 bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="left", padx=(8,4))
        tk.Button(af, text="Apri",
                  font=("TkFixedFont", 8), bg=SUCCESS, fg="white",
                  relief="flat", padx=6,
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=lambda: (self._open_image(filepath),
                                   self._clear_action_btns())
                  ).pack(side="left", padx=2, ipady=2)
        tk.Button(af, text="Rinomina",
                  font=("TkFixedFont", 8), bg=WARNING, fg="white",
                  relief="flat", padx=6,
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=lambda: self._show_rename_inline_browser(af, filepath)
                  ).pack(side="left", padx=2, ipady=2)
        tk.Button(af, text="Copia percorso",
                  font=("TkFixedFont", 8), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=6,
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=lambda: (self._copy_path(filepath),
                                   self._clear_action_btns())
                  ).pack(side="left", padx=2, ipady=2)
        tk.Button(af, text="x",
                  font=("TkFixedFont", 9), bg=PANEL_COLOR, fg=MUTED_COLOR,
                  relief="flat",
                  command=self._clear_action_btns
                  ).pack(side="right", padx=6, ipady=2)

    def _show_rename_inline_browser(self, af, filepath):
        """Sostituisce i bottoni con campo testo per rinomina, inline nella barra."""
        for w in af.winfo_children():
            w.destroy()
        folder    = os.path.dirname(filepath)
        base, ext = os.path.splitext(os.path.basename(filepath))

        tk.Label(af, text=f"{ext}  |",
                 font=("TkFixedFont", 8), bg=PANEL_COLOR,
                 fg=WARNING).pack(side="left", padx=(8,4))

        var   = tk.StringVar(value=base)
        entry = tk.Entry(af, textvariable=var,
                         font=("TkFixedFont", 9),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=4)
        entry.pack(side="left", fill="x", expand=True, padx=4, ipady=3)
        entry.selection_range(0, tk.END)
        entry.focus_set()

        msg = tk.Label(af, text="", font=("TkFixedFont", 8),
                       bg=PANEL_COLOR, fg=HIGHLIGHT)
        msg.pack(side="left", padx=4)

        def do_rename(event=None):
            new_base = sanitize_name(var.get().strip())
            if not new_base:
                msg.config(text="Nome non valido.")
                return
            new_path = os.path.join(folder, new_base + ext)
            if new_path == filepath:
                self._clear_action_btns()
                return
            if os.path.exists(new_path):
                msg.config(text="Già esistente.")
                return
            try:
                os.rename(filepath, new_path)
                # Aggiorna sorter e thumbnail
                if self.sorter.source_folder == folder:
                    self.sorter._refresh_after_rename(filepath, new_path)
                self._load_thumbnails(folder)
                self._refresh_node(folder)
                self._clear_action_btns()
            except Exception as ex:
                msg.config(text=str(ex)[:35])

        tk.Button(af, text="OK",
                  font=("TkFixedFont", 8), bg=SUCCESS, fg="white",
                  relief="flat", padx=6,
                  activebackground=HIGHLIGHT,
                  command=do_rename).pack(side="left", padx=2, ipady=3)
        tk.Button(af, text="Annulla",
                  font=("TkFixedFont", 8), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=6,
                  activebackground=HIGHLIGHT,
                  command=lambda: self._build_action_btns(af, filepath)
                  ).pack(side="left", padx=2, ipady=3)

        entry.bind("<Return>",   do_rename)
        entry.bind("<KP_Enter>", do_rename)
        entry.bind("<Escape>",
                   lambda e: self._build_action_btns(af, filepath))

    def _clear_action_btns(self):
        self.sorter._selected_browser_folder = None
        self._deselect_folder_cell()
        af = getattr(self, "_action_frame", None)
        if af and af.winfo_exists():
            af.destroy()
        self._action_frame = None

    def _refresh_node(self, folder):
        """Aggiorna il testo del nodo dell'albero per la cartella data."""
        for iid in self.tree.get_children(""):
            self._refresh_node_recursive(iid, folder)

    def _refresh_node_recursive(self, iid, target_folder):
        vals = self.tree.item(iid, "values")
        if vals and os.path.normpath(vals[0]) == os.path.normpath(target_folder):
            name = os.path.basename(target_folder) or target_folder
            self.tree.item(iid, text=self._node_text(name, target_folder))
            return
        for child in self.tree.get_children(iid):
            self._refresh_node_recursive(child, target_folder)

    def _copy_path(self, path):
        self.win.clipboard_clear()
        self.win.clipboard_append(path)

    def _on_close(self):
        self.sorter.folder_browser = None
        self.win.destroy()

class KeypadPopup:
    """
    Tastierino flottante, trascinabile, sempre in primo piano.
    Mostra sempre i primi 3 preset (come la sidebar principale).
    - Una colonna per ciascuno dei 3 preset
    - Bottoni di attivazione (quale risponde alla tastiera) sotto le griglie
    - Tasto INDIETRO / SALTA / CANC in fondo
    """
    BTN_IPAD = 7

    def __init__(self, parent, sorter):
        self.sorter     = sorter
        self.badge_btns = {}   # {key: btn} del preset attivo (per flash)

        self.win = tk.Toplevel(parent)
        self.win.withdraw()
        self.win.title("Tastierino")
        self.win.configure(bg=BG_COLOR)
        self.win.resizable(True, True)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self.win.bind("<Escape>", lambda e: self._on_close())
        hud_apply(self.win)
        self._build()
        self.win.deiconify()

    # ------------------------------------------------------------------
    def _build(self):
        w = self.win
        w.rowconfigure(0, weight=0)   # header preset selector
        w.rowconfigure(1, weight=1)   # griglie preset
        w.rowconfigure(2, weight=0)   # bottoni attivazione
        w.rowconfigure(3, weight=0)   # nav

        ncols = get_keypad_cols(self.sorter.config)
        for ci in range(3):
            w.columnconfigure(ci, weight=1 if ci < ncols else 0)

        self._build_header()
        self._build_columns()

        self.win.bind("<KP_Decimal>", lambda e: self._delete_current())
        self.win.bind("<Delete>",     lambda e: self._delete_current())
        w_px = 220 * ncols
        self.win.geometry(f"{w_px}x500")
        # Centra rispetto alla finestra principale
        self.win.update_idletasks()
        px = self.sorter.root.winfo_x() + (self.sorter.root.winfo_width()  - w_px) // 2
        py = self.sorter.root.winfo_y() + (self.sorter.root.winfo_height() - 500)  // 2
        self.win.geometry(f"+{px}+{py}")
        self.win.minsize(200, 340)

    def _build_header(self):
        """Una riga con un menu a tendina per colonna — assegna quale preset mostrare."""
        w = self.win
        preset_names = list(self.sorter.config["presets"].keys())
        ncols = get_keypad_cols(self.sorter.config)
        # Inizializza _col_presets se non esiste o se ncols è cambiato
        if not hasattr(self, "_col_presets") or len(self._col_presets) != ncols:
            self._col_presets = [preset_names[i] if i < len(preset_names) else
                                  (preset_names[0] if preset_names else "")
                                  for i in range(ncols)]
        self._col_vars = []
        for ci in range(ncols):
            var = tk.StringVar(value=self._col_presets[ci])
            self._col_vars.append(var)
            om = tk.OptionMenu(w, var, *preset_names,
                               command=lambda name, col=ci: self._assign_col_preset(col, name))
            om.config(font=("TkFixedFont", 8, "bold"),
                      bg=ACCENT_COLOR, fg=HUD_CYAN,
                      activebackground=HIGHLIGHT, activeforeground="white",
                      highlightthickness=0, relief="flat", bd=0, padx=4)
            om["menu"].config(font=("TkFixedFont", 9),
                              bg=PANEL_COLOR, fg=TEXT_COLOR,
                              activebackground=HIGHLIGHT, activeforeground="white")
            om.grid(row=0, column=ci, sticky="ew",
                    padx=(4 if ci==0 else 2, 4 if ci==ncols-1 else 2),
                    pady=(3,2), ipady=1)

    def _assign_col_preset(self, col, name):
        """Assegna il preset `name` alla colonna `col` del tastierino."""
        if name not in self.sorter.config["presets"]:
            return
        self._col_presets[col] = name
        # Se la colonna scelta è quella attiva, aggiorna labels e deck
        active = self.sorter.config["active_preset"]
        if self._col_presets[col] == name:
            # Controlla se questa colonna era quella attiva
            pass
        # Ridisegna il tastierino mantenendo la posizione
        self.refresh_labels()

    def _build_columns(self):
        """Costruisce le colonne preset + bottoni attivazione + nav."""
        w            = self.win
        active       = self.sorter.config["active_preset"]
        preset_names = list(self.sorter.config["presets"].keys())
        ncols        = get_keypad_cols(self.sorter.config)
        self.badge_btns = {}

        # Aggiorna sempre i pesi delle 3 colonne (ncols puo' cambiare da PresetSelector)
        for ci in range(3):
            w.columnconfigure(ci, weight=1 if ci < ncols else 0)

        PAD_OUT = 4
        PAD_IN  = 2

        # ---- Riga 1: griglie tasti (ncols colonne) ----
        for ci in range(ncols):
            # Usa il preset assegnato alla colonna (da _col_presets)
            col_presets = getattr(self, "_col_presets", preset_names)
            pname = col_presets[ci] if ci < len(col_presets) else (
                    preset_names[ci] if ci < len(preset_names) else None)
            is_active = (pname == active) if pname else False
            border    = (preset_color(self.sorter.config, pname, HIGHLIGHT)
                         if is_active else ACCENT_COLOR)

            col_wrap = tk.Frame(w, bg=border)
            col_wrap.grid(row=1, column=ci, sticky="nsew",
                          padx=(PAD_OUT if ci == 0 else PAD_IN,
                                PAD_OUT if ci == ncols-1 else PAD_IN),
                          pady=(PAD_IN, PAD_IN))
            col_wrap.columnconfigure(0, weight=1)
            col_wrap.rowconfigure(0, weight=1)

            if not pname:
                continue

            slots = self.sorter.config["presets"][pname]
            grid  = tk.Frame(col_wrap, bg=BG_COLOR)
            grid.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
            for gi in range(3):
                grid.columnconfigure(gi, weight=1)

            ri = 0
            for row_keys in ROWS_LAYOUT:
                for gi, k in enumerate(row_keys):
                    color   = KEY_COLORS[KEYS.index(k)]
                    colspan = 3 if k == "0" else 1
                    has_dest = bool(slots[k].get('path', '').strip())
                    lbl     = slots[k].get('label', '') if has_dest else ''
                    short_l = (lbl[:10] + ".") if len(lbl) > 10 else lbl
                    btn = tk.Button(
                        grid,
                        text=f"{k}\n{short_l}",
                        font=("TkFixedFont", 9, "bold"),
                        bg=color, fg="white", justify="center",
                        activebackground=HIGHLIGHT, activeforeground="white",
                        relief="flat", bd=0,
                        width=6,    # larghezza fissa uniforme
                        wraplength=60,
                        command=lambda key=k, p=pname:
                            self.sorter._move_to_preset(key, p))
                    btn.grid(row=ri, column=gi, columnspan=colspan,
                             sticky="nsew", padx=2, pady=2,
                             ipady=self.BTN_IPAD)
                    btn.bind("<Button-3>",
                             lambda e, key=k, p=pname: self.sorter._quick_set_dest(key, p, e))
                    if is_active:
                        self.badge_btns[k] = btn
                grid.rowconfigure(ri, weight=1)
                ri += 1

        # ---- Riga 2: bottoni attivazione preset ----
        for ci in range(ncols):
            # Usa il preset assegnato alla colonna (da _col_presets)
            col_presets = getattr(self, "_col_presets", preset_names)
            pname = col_presets[ci] if ci < len(col_presets) else (
                    preset_names[ci] if ci < len(preset_names) else None)
            if not pname:
                continue
            is_active = (pname == active)
            short     = (pname[:12] + ".") if len(pname) > 12 else pname
            tk.Button(
                w,
                text=(">> " if is_active else "   ") + short,
                font=("TkFixedFont", 8, "bold" if is_active else "normal"),
                bg=(preset_color(self.sorter.config, pname, HIGHLIGHT)
                    if is_active else ACCENT_COLOR),
                fg="white", relief="flat", bd=0,
                activebackground=HIGHLIGHT, activeforeground="white",
                command=lambda p=pname: self._switch_preset(p)
            ).grid(row=2, column=ci, sticky="ew",
                   padx=(PAD_OUT if ci == 0 else PAD_IN,
                         PAD_OUT if ci == ncols-1 else PAD_IN),
                   pady=(PAD_IN, PAD_IN), ipady=6)

        # ---- Righe 4+: INDIETRO / SALTA / CANC ----
        if ncols >= 3:
            # 3 bottoni su 3 colonne, stessa riga
            tk.Button(w, text="< INDIETRO", font=("TkFixedFont", 9, "bold"),
                      bg="#4a90e2", fg="white", relief="flat",
                      activebackground=HIGHLIGHT,
                      command=self.sorter._go_back).grid(
                      row=3, column=0, sticky="ew",
                      padx=(PAD_OUT, PAD_IN), pady=(PAD_IN, PAD_OUT),
                      ipady=self.BTN_IPAD)
            tk.Button(w, text="SALTA >", font=("TkFixedFont", 9, "bold"),
                      bg=WARNING, fg="white", relief="flat",
                      activebackground=HIGHLIGHT,
                      command=self.sorter._skip).grid(
                      row=3, column=1, sticky="ew",
                      padx=(PAD_IN, PAD_IN), pady=(PAD_IN, PAD_OUT),
                      ipady=self.BTN_IPAD)
            tk.Button(w, text="CANC", font=("TkFixedFont", 9, "bold"),
                      bg="#c0392b", fg="white", relief="flat",
                      activebackground=HIGHLIGHT,
                      command=self._delete_current).grid(
                      row=3, column=2, sticky="ew",
                      padx=(PAD_IN, PAD_OUT), pady=(PAD_IN, PAD_OUT),
                      ipady=self.BTN_IPAD)
        elif ncols == 2:
            tk.Button(w, text="< INDIETRO", font=("TkFixedFont", 9, "bold"),
                      bg="#4a90e2", fg="white", relief="flat",
                      activebackground=HIGHLIGHT,
                      command=self.sorter._go_back).grid(
                      row=3, column=0, sticky="ew",
                      padx=(PAD_OUT, PAD_IN), pady=(PAD_IN, PAD_IN),
                      ipady=self.BTN_IPAD)
            tk.Button(w, text="SALTA >", font=("TkFixedFont", 9, "bold"),
                      bg=WARNING, fg="white", relief="flat",
                      activebackground=HIGHLIGHT,
                      command=self.sorter._skip).grid(
                      row=3, column=1, sticky="ew",
                      padx=(PAD_IN, PAD_OUT), pady=(PAD_IN, PAD_IN),
                      ipady=self.BTN_IPAD)
            tk.Button(w, text="CANC", font=("TkFixedFont", 9, "bold"),
                      bg="#c0392b", fg="white", relief="flat",
                      activebackground=HIGHLIGHT,
                      command=self._delete_current).grid(
                      row=4, column=0, columnspan=2, sticky="ew",
                      padx=PAD_OUT, pady=(PAD_IN, PAD_OUT),
                      ipady=self.BTN_IPAD)
            w.rowconfigure(4, weight=0)
        else:  # ncols == 1
            for ri, (txt, bg_c, cmd) in enumerate([
                    ("< INDIETRO", "#4a90e2", self.sorter._go_back),
                    ("SALTA >",    WARNING,   self.sorter._skip),
                    ("CANC",       "#c0392b", self._delete_current)]):
                tk.Button(w, text=txt, font=("TkFixedFont", 9, "bold"),
                          bg=bg_c, fg="white", relief="flat",
                          activebackground=HIGHLIGHT,
                          command=cmd).grid(
                          row=3+ri, column=0, sticky="ew",
                          padx=PAD_OUT,
                          pady=(PAD_IN, PAD_OUT if ri == 2 else PAD_IN),
                          ipady=self.BTN_IPAD)
                w.rowconfigure(3+ri, weight=0)

    # ------------------------------------------------------------------
    def _switch_preset(self, preset_name):
        if not preset_name or preset_name not in self.sorter.config["presets"]:
            return
        self.sorter.config["active_preset"] = preset_name
        save_config(self.sorter.config)
        self.sorter.labels = self.sorter.config["presets"][preset_name]
        for k in KEYS:
            os.makedirs(self.sorter._dest_path(k), exist_ok=True)
        self.sorter._update_preset_label()
        self.sorter._build_sidebar()
        self.refresh_labels()

    def refresh_labels(self):
        """Aggiorna le etichette del tastierino senza spostare la finestra."""
        # Cattura geometria PRIMA di qualsiasi operazione
        # Usa wm_geometry() per posizione reale inclusi i decoratori WM
        self.win.update_idletasks()
        geo = self.win.wm_geometry()  # "WxH+X+Y"
        import re as _re
        _m = _re.match(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", geo)
        if _m:
            cur_w, cur_h = int(_m.group(1)), int(_m.group(2))
            cur_x, cur_y = int(_m.group(3)), int(_m.group(4))
        else:
            cur_w = self.win.winfo_width()  or 220
            cur_h = self.win.winfo_height() or 500
            cur_x = self.win.winfo_x()
            cur_y = self.win.winfo_y()
        ncols = get_keypad_cols(self.sorter.config)
        new_w = 220 * ncols

        # Fissa posizione e dimensioni prima di distruggere i widget
        self.win.geometry(f"{cur_w}x{cur_h}+{cur_x}+{cur_y}")
        self.win.update_idletasks()

        for child in list(self.win.winfo_children()):
            try: child.destroy()
            except Exception: pass

        w = self.win
        w.rowconfigure(0, weight=0)   # header preset
        w.rowconfigure(1, weight=1)   # griglie
        w.rowconfigure(2, weight=0)   # attivazione
        w.rowconfigure(3, weight=0)   # nav
        for ci in range(4):  # 3 col + 1 per frecce header
            w.columnconfigure(ci, weight=1 if ci < ncols else 0)
        self._build_header()
        self._build_columns()

        # Ripristina geometria esatta — usa after() per applicarla dopo il layout
        self.win.minsize(200 * ncols, 340)
        self.win.after(0, lambda x=cur_x, y=cur_y, w=new_w, h=cur_h:
                       self.win.geometry(f"{w}x{h}+{x}+{y}")
                       if self.win.winfo_exists() else None)

    def flash(self, key):
        btn = self.badge_btns.get(key)
        if not btn:
            return
        orig = btn.cget("bg")
        btn.config(bg=HIGHLIGHT)
        self.win.after(250, lambda: btn.config(bg=orig))

    def _do_trash(self, filepath):
        """Esegue effettivamente il cestino del file corrente."""
        self._delete_pending = False
        if getattr(self, '_delete_timer', None):
            self.root.after_cancel(self._delete_timer)
            self._delete_timer = None
        # Ripristina Return
        if getattr(self, '_delete_return_bind', None):
            self.root.bind_all("<Return>", self._hk_guard(self._toggle_fullscreen))
            self._delete_return_bind = None
        try:
            if not send_to_trash(filepath): raise Exception("Errore cestino")
        except Exception as ex:
            messagebox.showerror("Errore", f"Impossibile spostare nel cestino:\n{ex}",
                                 parent=self.root)
            return
        if self.current_index < len(self.images):
            self.images.pop(self.current_index)
        if self.images and self.current_index >= len(self.images):
            self.current_index = 0
        if not self.images and self.source_folder:
            self.images = [f for f in self._load_images() if f != filepath]
            self.current_index = 0
        self._show_image()

    def _delete_current(self):
        filepath = self.sorter._current_file()
        if not filepath or not os.path.isfile(filepath):
            return
        fname = os.path.basename(filepath)
        if not messagebox.askyesno(
                "Elimina file",
                f"Spostare nel cestino:\n{fname}",
                parent=self.win):
            return
        try:
            if not send_to_trash(filepath): raise Exception("Errore cestino")
        except Exception as ex:
            messagebox.showerror("Errore", f"Impossibile spostare nel cestino:\n{ex}",
                                 parent=self.win)
            return
        if self.sorter.current_index < len(self.sorter.images):
            self.sorter.images.pop(self.sorter.current_index)
        elif self.sorter.skipped:
            self.sorter.skipped.pop(0)
        self.sorter._show_image()

    def _on_close(self):
        self.sorter.keypad_popup = None
        self.sorter._update_keypad_btn(0)
        self.sorter._update_preset_label()
        self.win.destroy()
        # Deck fisico torna a idle quando si chiude il softdeck
        sdk = getattr(self.sorter, '_stream_deck', None)
        if sdk and sdk.is_active():
            sdk.set_mode("idle")

# =============================================================================
# SIDEBAR POPUP (finestra separata a colonna, stesso formato della sidebar inline)
# =============================================================================

class SidebarPopup:
    """Finestra separata che replica la sidebar inline come colonna verticale."""

    def __init__(self, parent, sorter):
        self.sorter = sorter
        self.win = tk.Toplevel(parent)
        self.win.title("SideBar")
        self.win.configure(bg=PANEL_COLOR)
        # Nasconde subito per evitare flash al centro
        self.win.withdraw()
        self.win.minsize(220, 400)
        self.win.resizable(True, True)
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        hud_apply(self.win)
        self.win.transient(parent)
        self._build()
        # Posiziona sul lato destro evitando la barra header (circa 80px)
        # e lasciando un piccolo margine dal bordo
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        ww = 260
        header_h = 80    # altezza approssimativa della barra header + toolbar
        wh = sh - header_h - 50
        x  = sw - ww - 8
        y  = header_h    # inizia sotto la barra, non sopra
        self.win.geometry(f"{ww}x{wh}+{x}+{y}")
        self.win.deiconify()

    def _build(self):
        self.win.rowconfigure(0, weight=1)
        self.win.columnconfigure(0, weight=1)
        self.frame = tk.Frame(self.win, bg=PANEL_COLOR)
        self.frame.grid(row=0, column=0, sticky="nsew")
        self.frame.columnconfigure(0, weight=1)
        self.refresh()

    def refresh(self):
        for w in self.frame.winfo_children():
            w.destroy()
        sorter = self.sorter
        config = sorter.config
        active = config["active_preset"]
        preset_names = list(config["presets"].keys())
        n_presets = get_sidebar_presets(config)

        sorter.badge_labels       = {}
        sorter.folder_name_labels = {}

        cols_frame = tk.Frame(self.frame, bg=PANEL_COLOR)
        cols_frame.pack(fill="x", padx=4, pady=(8,0))
        cols_frame.columnconfigure(0, weight=1)

        for ci in range(n_presets):
            # Usa il preset assegnato alla colonna (da _col_presets)
            col_presets = getattr(self, "_col_presets", preset_names)
            pname = col_presets[ci] if ci < len(col_presets) else (
                    preset_names[ci] if ci < len(preset_names) else None)
            is_active = (pname == active) if pname else False
            border    = HUD_CYAN if is_active else ACCENT_COLOR

            col_frame = tk.Frame(cols_frame, bg=border)
            col_frame.grid(row=ci, column=0, sticky="ew", padx=2, pady=2)
            col_frame.columnconfigure(0, weight=1)
            if not pname:
                continue

            slots = config["presets"][pname]
            short = pname if len(pname) <= 8 else pname[:7] + "."
            tk.Button(col_frame, text=short,
                      font=("TkFixedFont", 7, "bold" if is_active else "normal"),
                      bg=HUD_CYAN if is_active else ACCENT_COLOR,
                      fg="#0a1a2e" if is_active else TEXT_COLOR,
                      relief="flat", bd=0,
                      activebackground=HUD_CYAN, activeforeground="#0a1a2e",
                      command=lambda p=pname: sorter._switch_preset_sidebar(p)
                      ).pack(fill="x", ipady=4, padx=1, pady=(1,2))

            grid = tk.Frame(col_frame, bg=PANEL_COLOR)
            grid.pack(fill="x", padx=1, pady=(0,1))
            for gi in range(3):
                grid.columnconfigure(gi, weight=1)

            row_idx = 0
            for row_keys in ROWS_LAYOUT:
                for col_idx, k in enumerate(row_keys):
                    color   = KEY_COLORS[KEYS.index(k)]
                    colspan = 3 if k == "0" else 1
                    has_dest = bool(slots[k].get('path', '').strip())
                    lbl     = slots[k].get('label', '') if has_dest else ''
                    short_l = lbl if len(lbl) <= 11 else lbl[:10] + "."
                    cell = tk.Frame(grid, bg=PANEL_COLOR)
                    cell.grid(row=row_idx, column=col_idx, columnspan=colspan,
                              sticky="nsew", padx=1, pady=1)
                    badge = tk.Button(cell, text=k,
                                      font=("TkFixedFont", 9, "bold"),
                                      bg=color, fg="white",
                                      activebackground=HUD_CYAN, activeforeground="white",
                                      relief="flat", bd=0,
                                      command=lambda key=k, p=pname: sorter._move_to_preset(key, p))
                    badge.pack(fill="x")
                    name_btn = tk.Button(cell, text=short_l,
                                         font=("TkFixedFont", 7), bg=PANEL_COLOR,
                                         fg=SUCCESS if slots[k].get("path","").strip() else TEXT_COLOR,
                                         activebackground=PANEL_COLOR, activeforeground=HUD_CYAN,
                                         relief="flat", bd=0,
                                         command=lambda key=k, p=pname: sorter._move_to_preset(key, p))
                    name_btn.pack(fill="x", pady=(0,1))
                    if is_active:
                        sorter.badge_labels[k]       = badge
                        sorter.folder_name_labels[k] = name_btn
                row_idx += 1

        tk.Frame(self.frame, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=4, pady=(6,4))

        nav = tk.Frame(self.frame, bg=PANEL_COLOR)
        nav.pack(fill="x", padx=4, pady=(0,4))
        for ci in range(3):
            nav.columnconfigure(ci, weight=1)
        tk.Button(nav, text="< Indietro", font=("TkFixedFont", 8, "bold"),
                  bg="#4a90e2", fg="white", relief="flat", bd=0,
                  activebackground=HUD_CYAN, activeforeground="white",
                  command=sorter._go_back).grid(row=0, column=0, sticky="ew", padx=(0,2), ipady=5)
        tk.Button(nav, text="Salta >", font=("TkFixedFont", 8, "bold"),
                  bg=WARNING, fg="white", relief="flat", bd=0,
                  activebackground=HUD_CYAN, activeforeground="white",
                  command=sorter._skip).grid(row=0, column=1, sticky="ew", padx=2, ipady=5)
        tk.Button(nav, text="CANC", font=("TkFixedFont", 8, "bold"),
                  bg="#c0392b", fg="white", relief="flat", bd=0,
                  activebackground=HUD_CYAN, activeforeground="white",
                  command=sorter._delete_current).grid(row=0, column=2, sticky="ew", padx=(2,0), ipady=5)

        tk.Frame(self.frame, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=4, pady=(4,6))

        self.stats_label = tk.Label(self.frame, text="",
                                    font=("TkFixedFont", 8),
                                    bg=PANEL_COLOR, fg=MUTED_COLOR, justify="left")
        self.stats_label.pack(padx=14, anchor="w")
        prog_bg = tk.Frame(self.frame, bg=ACCENT_COLOR, height=5)
        prog_bg.pack(fill="x", padx=4, pady=(10,4))
        prog_bg.pack_propagate(False)
        self.progress_bar = tk.Frame(prog_bg, bg=HUD_CYAN, height=5)
        self.progress_bar.place(x=0, y=0, relheight=1, relwidth=0)

        sorter.stats_label  = self.stats_label
        sorter.progress_bar = self.progress_bar

    def _on_close(self):
        self.sorter.sidebar_popup = None
        self.sorter._update_preset_label()
        self.sorter.config["sidebar_mode"] = "inline"
        save_config(self.sorter.config)
        self.sorter._apply_sidebar_mode()   # aggiorna anche il bottone
        self.win.destroy()

# =============================================================================
# CROP OVERLAY (ritaglio direttamente sul canvas principale)
# =============================================================================

class CropOverlay:
    """Selezione di ritaglio sovrapposta al canvas principale di ImageSorter."""

    HANDLE_R = 7

    def __init__(self, sorter):
        self.sorter   = sorter
        self.canvas   = sorter.canvas
        self.filepath = sorter._current_file()
        if not self.filepath or not os.path.isfile(self.filepath):
            return

        self.orig_img = Image.open(self.filepath)
        self.iw, self.ih = self.orig_img.size

        # Disabilita keybind normali
        sorter._disable_keybinds()

        self._drag       = None
        self._drag_start = None
        self._active     = True

        # Barra comandi in basso sull'img_frame
        img_frame = self.canvas.master
        self._bar = tk.Frame(img_frame, bg=PANEL_COLOR)
        self._bar.place(relx=0, rely=0.0, anchor="nw", relwidth=1.0, height=40)

        # Info dimensioni
        self._info = tk.Label(self._bar, text="", font=("TkFixedFont", 8),
                              bg=PANEL_COLOR, fg=HUD_CYAN)
        self._info.pack(side="left", padx=10)

        # Checkbox ricorda
        self._remember_var = tk.BooleanVar(
            value=sorter.config.get("crop_remember", False))
        tk.Checkbutton(self._bar, text="Ricorda dimensioni",
                       variable=self._remember_var,
                       font=("TkFixedFont", 8),
                       bg=PANEL_COLOR, fg=TEXT_COLOR,
                       selectcolor=ACCENT_COLOR,
                       activebackground=PANEL_COLOR,
                       activeforeground=HUD_CYAN
                       ).pack(side="left", padx=6)

        tk.Button(self._bar, text="Ritaglia",
                  font=("TkFixedFont", 8, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=8,
                  activebackground=HUD_CYAN,
                  command=lambda: self._apply(advance=False)
                  ).pack(side="left", padx=4, ipady=3)

        tk.Button(self._bar, text="Ritaglia e avanza",
                  font=("TkFixedFont", 8, "bold"),
                  bg=HUD_CYAN, fg="#0a1a2e", relief="flat", padx=8,
                  activebackground=SUCCESS,
                  command=lambda: self._apply(advance=True)
                  ).pack(side="left", padx=4, ipady=3)

        tk.Button(self._bar, text="Ritaglia prossimo",
                  font=("TkFixedFont", 8, "bold"),
                  bg="#2a6a3a", fg="white", relief="flat", padx=8,
                  activebackground=SUCCESS,
                  command=lambda: self._apply(advance=True, open_next=True)
                  ).pack(side="left", padx=4, ipady=3)

        tk.Button(self._bar, text="Annulla",
                  font=("TkFixedFont", 8),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=8,
                  activebackground=HIGHLIGHT,
                  command=self._cancel
                  ).pack(side="left", padx=4, ipady=3)

        # Inizializza selezione
        self._init_selection()

        # Bind mouse sul canvas
        self._bind_ids = []
        self._bind_ids.append(
            (self.canvas, "<ButtonPress-1>",
             self.canvas.bind("<ButtonPress-1>", self._on_press, add=True)))
        self._bind_ids.append(
            (self.canvas, "<B1-Motion>",
             self.canvas.bind("<B1-Motion>", self._on_drag, add=True)))
        self._bind_ids.append(
            (self.canvas, "<ButtonRelease-1>",
             self.canvas.bind("<ButtonRelease-1>", self._on_release, add=True)))
        self._bind_ids.append(
            (self.canvas, "<Motion>",
             self.canvas.bind("<Motion>", self._on_motion, add=True)))
        # Escape per annullare
        sorter.root.bind("<Escape>", lambda e: self._cancel(), add=True)

        self._draw()

    def _init_selection(self):
        remember = self.sorter.config.get("crop_remember", False)
        crop_pos  = self.sorter.config.get("crop_pos")
        if remember and crop_pos and len(crop_pos) == 4:
            # Ripristina posizione e dimensioni relative
            x0r, y0r, x1r, y1r = crop_pos
            x0 = max(0, min(self.iw-2, int(x0r * self.iw)))
            y0 = max(0, min(self.ih-2, int(y0r * self.ih)))
            x1 = max(x0+2, min(self.iw, int(x1r * self.iw)))
            y1 = max(y0+2, min(self.ih, int(y1r * self.ih)))
            self.sel = [x0, y0, x1, y1]
        else:
            self.sel = [0, 0, self.iw, self.ih]

    def _get_offset(self):
        """Ritorna (ox, oy, scale) dell'immagine sul canvas.
        Replica esattamente thumbnail(): non ingrandisce mai (scale <= 1).
        """
        cw = max(self.canvas.winfo_width(),  100)
        ch = max(self.canvas.winfo_height(), 100)
        # thumbnail non ingrandisce: scale massima = 1.0
        scale = min(1.0, (cw - 16) / self.iw, (ch - 16) / self.ih)
        dw = int(self.iw * scale)
        dh = int(self.ih * scale)
        ox = cw // 2 - dw // 2
        oy = ch // 2 - dh // 2
        return ox, oy, scale

    def _i2c(self, x, y):
        ox, oy, s = self._get_offset()
        return ox + x*s, oy + y*s

    def _c2i(self, cx, cy):
        ox, oy, s = self._get_offset()
        return (cx-ox)/s, (cy-oy)/s

    def _draw(self):
        if not self._active or not self._bar.winfo_exists():
            return
        c = self.canvas
        c.delete("crop")
        ox, oy, scale = self._get_offset()
        dw, dh = int(self.iw*scale), int(self.ih*scale)

        x1, y1, x2, y2 = self.sel
        cx1, cy1 = self._i2c(x1, y1)
        cx2, cy2 = self._i2c(x2, y2)

        # Zone scure
        for coords in [
            (ox, oy, ox+dw, cy1),
            (ox, cy2, ox+dw, oy+dh),
            (ox, cy1, cx1, cy2),
            (cx2, cy1, ox+dw, cy2),
        ]:
            c.create_rectangle(*coords, fill="#000000",
                                stipple="gray50", outline="", tags="crop")

        # Bordo selezione
        c.create_rectangle(cx1, cy1, cx2, cy2,
                           outline=HUD_CYAN, width=2, tags="crop")

        # Griglia terzi
        tx, ty = (cx2-cx1)/3, (cy2-cy1)/3
        for i in (1, 2):
            c.create_line(cx1+tx*i, cy1, cx1+tx*i, cy2,
                         fill=HUD_CYAN, width=1, dash=(4,4), tags="crop")
            c.create_line(cx1, cy1+ty*i, cx2, cy1+ty*i,
                         fill=HUD_CYAN, width=1, dash=(4,4), tags="crop")

        # Handle
        r = self.HANDLE_R
        mx, my = (cx1+cx2)/2, (cy1+cy2)/2
        for hx, hy in [(cx1,cy1),(cx2,cy1),(cx1,cy2),(cx2,cy2),
                        (mx,cy1),(mx,cy2),(cx1,my),(cx2,my)]:
            c.create_rectangle(hx-r, hy-r, hx+r, hy+r,
                               fill=BG_COLOR, outline=HUD_CYAN,
                               width=2, tags="crop")

        # Aggiorna info
        sw, sh = int(x2-x1), int(y2-y1)
        if self._info.winfo_exists():
            self._info.config(text=f"{sw} x {sh} px")

    def _hit(self, cx, cy):
        x1, y1, x2, y2 = self.sel
        cx1, cy1c = self._i2c(x1, y1)
        cx2, cy2c = self._i2c(x2, y2)
        r = self.HANDLE_R + 4
        mx, my = (cx1+cx2)/2, (cy1c+cy2c)/2
        for name, hx, hy in [
            ("tl",cx1,cy1c),("tr",cx2,cy1c),
            ("bl",cx1,cy2c),("br",cx2,cy2c),
            ("t",mx,cy1c),("b",mx,cy2c),
            ("l",cx1,my),("r",cx2,my)
        ]:
            if abs(cx-hx)<=r and abs(cy-hy)<=r:
                return name
        if cx1+r<cx<cx2-r and cy1c+r<cy<cy2c-r:
            return "move"
        return None

    def _on_motion(self, e):
        cursors = {
            "tl":"top_left_corner","tr":"top_right_corner",
            "bl":"bottom_left_corner","br":"bottom_right_corner",
            "t":"top_side","b":"bottom_side",
            "l":"left_side","r":"right_side","move":"fleur"
        }
        self.canvas.config(cursor=cursors.get(self._hit(e.x,e.y),"crosshair"))

    def _on_press(self, e):
        hit = self._hit(e.x, e.y)
        if hit:
            self._drag = hit
            ix, iy = self._c2i(e.x, e.y)
            self._drag_start = (ix, iy, list(self.sel))

    def _on_drag(self, e):
        if not self._drag or not self._drag_start:
            return
        sx, sy, orig = self._drag_start
        ix, iy = self._c2i(e.x, e.y)
        dx, dy = ix-sx, iy-sy
        x1, y1, x2, y2 = orig
        M = 20
        d = self._drag
        if d == "move":
            w, h = x2-x1, y2-y1
            nx1 = max(0, min(self.iw-w, x1+dx))
            ny1 = max(0, min(self.ih-h, y1+dy))
            self.sel = [nx1, ny1, nx1+w, ny1+h]
        else:
            nx1,ny1,nx2,ny2 = x1,y1,x2,y2
            if "l" in d: nx1 = max(0, min(x1+dx, x2-M))
            if "r" in d: nx2 = min(self.iw, max(x2+dx, x1+M))
            if "t" in d: ny1 = max(0, min(y1+dy, y2-M))
            if "b" in d: ny2 = min(self.ih, max(y2+dy, y1+M))
            self.sel = [nx1, ny1, nx2, ny2]
        self._draw()

    def _on_release(self, e):
        self._drag = None

    def _cleanup(self):
        self._active = False
        # Rimuovi bind mouse
        for widget, event, bid in getattr(self, '_bind_ids', []):
            try: widget.unbind(event, bid)
            except Exception: pass
        self._bind_ids = []
        self.canvas.delete("crop")
        self.canvas.config(cursor="")
        if self._bar.winfo_exists():
            self._bar.destroy()
        self.sorter._restore_keybinds()
        self.sorter.root.bind("<Escape>", lambda e: (
            self.sorter._toggle_fullscreen() if self.sorter._fullscreen
            else self.sorter.root.destroy()))
        self.sorter._crop_overlay = None

    def _cancel(self):
        self._cleanup()
        self.sorter._show_image()

    def _apply(self, advance=False, open_next=False):
        x1,y1,x2,y2 = [int(v) for v in self.sel]
        x1,x2 = max(0,min(x1,self.iw)), max(0,min(x2,self.iw))
        y1,y2 = max(0,min(y1,self.ih)), max(0,min(y2,self.ih))
        if x2-x1 < 4 or y2-y1 < 4:
            messagebox.showwarning("Selezione troppo piccola",
                "Seleziona un'area più grande.", parent=self.sorter.root)
            return
        try:
            cropped = self.orig_img.crop((x1,y1,x2,y2))
        except Exception as ex:
            messagebox.showerror("Errore ritaglio",
                f"Impossibile ritagliare:\n{ex}", parent=self.sorter.root)
            return

        if open_next:
            # Ritaglia prossimo: sovrascrive, salva posizione, apre crop sul prossimo
            self._save_crop(cropped, dest=self.filepath,
                            advance=True, open_next=True)
        elif advance:
            # Ritaglia e avanza: sovrascrive direttamente senza chiedere
            self._save_crop(cropped, dest=self.filepath, advance=True)
        else:
            # Ritaglia: mostra dialogo sovrascrivere/nuovo nome
            self._ask_save(cropped, advance=False)

    def _save_crop(self, cropped, dest, advance, open_next=False):
        """Salva il crop su dest e gestisce la storia e l'avanzamento."""
        fmt = self.orig_img.format or "JPEG"
        kw  = {"quality":95,"subsampling":0} if fmt in ("JPEG","JPG") else {}
        try:
            # Backup originale per undo
            backup = dest + "._crop_backup"
            shutil.copy2(dest, backup)
            cropped.save(dest, format=fmt, **kw)
            remember = self._remember_var.get()
            self.sorter.config["crop_remember"] = remember
            if remember:
                cx1,cy1,cx2,cy2 = [int(v) for v in self.sel]
                self.sorter.config["crop_size"] = [cx2-cx1, cy2-cy1]
                self.sorter.config["crop_pos"]  = [cx1/self.iw, cy1/self.ih,
                                                    cx2/self.iw, cy2/self.ih]
            else:
                self.sorter.config.pop("crop_size", None)
                self.sorter.config.pop("crop_pos",  None)
            save_config(self.sorter.config)
            self.sorter.history.append(("cropped", self.filepath, backup))
            self._cleanup()
            if open_next:
                # Avanza al prossimo file e riapre subito il crop
                self.sorter._skip()
                # Piccolo delay per permettere il caricamento del file
                self.sorter.root.after(150, self._open_crop_on_current)
            else:
                self.sorter._show_image()
                if advance:
                    self.sorter._skip()
        except Exception as ex:
            messagebox.showerror("Errore ritaglio",
                f"Impossibile salvare:\n{ex}", parent=self.sorter.root)

    def _open_crop_on_current(self):
        """Riapre il crop overlay sul file corrente (usato da open_next)."""
        fp = self.sorter._current_file()
        if fp and os.path.isfile(fp) and not is_video(fp) and not is_pdf(fp):
            self.sorter._open_crop(fp)

    def _ask_save(self, cropped, advance):
        """Chiede se sovrascrivere o salvare con nuovo nome."""
        folder   = os.path.dirname(self.filepath)
        base, ext = os.path.splitext(os.path.basename(self.filepath))
        dlg = tk.Toplevel(self.sorter.root)
        dlg.title("Salva ritaglio")
        dlg.configure(bg=BG_COLOR)
        dlg.resizable(False, False)
        # dlg.grab_set()  # rimosso: bloccava altri programmi
        dlg.attributes("-topmost", True)
        hud_apply(dlg)
        # Disabilita Return per fullscreen mentre il dialog è aperto
        self.sorter.root.unbind_all("<Return>")
        dlg.bind("<Destroy>", lambda e: self.sorter.root.bind_all(
            "<Return>", lambda ev=None: (
                self.sorter._toggle_fullscreen()
                if not any(isinstance(w, tk.Toplevel) and w.winfo_viewable()
                           and w.grab_status() == "global"
                           for w in self.sorter.root.winfo_children())
                else None)))

        # Info dimensioni
        w, h = cropped.size
        tk.Label(dlg, text=f"Ritaglio: {w} x {h} px",
                 font=("TkFixedFont", 9, "bold"),
                 bg=BG_COLOR, fg=HUD_CYAN).pack(padx=20, pady=(14,2))
        tk.Label(dlg, text="Come vuoi salvare l'immagine ritagliata?",
                 font=("TkFixedFont", 8), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(padx=20, pady=(0,10))

        tk.Frame(dlg, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=12)

        # Campo nome file (per "salva con nuovo nome")
        name_frame = tk.Frame(dlg, bg=BG_COLOR)
        name_frame.pack(fill="x", padx=20, pady=(10,4))
        tk.Label(name_frame, text="Nome file:",
                 font=("TkFixedFont", 8), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(side="left", padx=(0,6))
        name_var = tk.StringVar(value=f"{base}_crop{ext}")
        entry = tk.Entry(name_frame, textvariable=name_var,
                         font=("TkFixedFont", 9),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=4, width=32)
        entry.pack(side="left", fill="x", expand=True, ipady=3)
        entry.selection_range(0, tk.END)
        entry.focus_set()

        msg = tk.Label(dlg, text="", font=("TkFixedFont", 8),
                       bg=BG_COLOR, fg=HIGHLIGHT)
        msg.pack(padx=20)

        def _save(overwrite):
            if overwrite:
                dest = self.filepath
            else:
                new_name = sanitize_name(name_var.get().strip())
                if not new_name:
                    msg.config(text="Nome non valido.")
                    return
                # Assicura estensione corretta
                if not new_name.lower().endswith(ext.lower()):
                    new_name += ext
                dest = os.path.join(folder, new_name)
                if os.path.exists(dest) and dest != self.filepath:
                    msg.config(text="File già esistente.")
                    return
            try:
                if not overwrite:
                    idx = self.sorter.current_index
                    if idx < len(self.sorter.images):
                        self.sorter.images.insert(idx+1, dest)
                dlg.destroy()
                self._save_crop(cropped, dest=dest, advance=False)
            except Exception as ex:
                msg.config(text=f"Errore: {str(ex)[:40]}")

        bf = tk.Frame(dlg, bg=BG_COLOR)
        bf.pack(fill="x", padx=20, pady=(8,16))
        tk.Button(bf, text="Sovrascrivi originale",
                  font=("TkFixedFont", 9, "bold"),
                  bg=HIGHLIGHT, fg="white", relief="flat", padx=8,
                  activebackground="#c73652",
                  command=lambda: _save(True)
                  ).pack(side="left", padx=(0,6), ipady=5, fill="x", expand=True)
        tk.Button(bf, text="Salva con nuovo nome",
                  font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=8,
                  activebackground=HUD_CYAN,
                  command=lambda: _save(False)
                  ).pack(side="left", padx=(0,6), ipady=5, fill="x", expand=True)
        tk.Button(bf, text="Annulla",
                  font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=8,
                  command=dlg.destroy
                  ).pack(side="left", ipady=5, fill="x", expand=True)

        entry.bind("<Return>", lambda e: _save(False))
        entry.bind("<Escape>", lambda e: dlg.destroy())

# =============================================================================
# STREAM DECK INTEGRATION
# =============================================================================


# =============================================================================
# STREAM DECK — IDLE PAGE MANAGER
# =============================================================================

# Schema config pagine idle (salvato in image_sorter_config.json):
# "deck_idle_pages": [
#   [  # pagina 0 — lista di 15 slot (Standard), None = vuoto
#     {"label": "Documenti", "color": [20,60,120],
#      "action": "folder", "param": "/home/carlo/Documenti", "image": null},
#     {"label": "Copia", "color": [80,40,0],
#      "action": "hotkey", "param": "ctrl+c", "image": null},
#     ...
#   ],
#   [ ... ],  # pagina 1
# ]
#
# Tipi di azione:
#   "folder"   param = percorso cartella  -> apre in file manager
#   "app"      param = comando            -> subprocess.Popen
#   "hotkey"   param = "ctrl+c" ecc.     -> xdotool key
#   "url"      param = https://...       -> xdg-open
#   "mute"     param = ""               -> pactl set-sink-mute @DEFAULT_SINK@ toggle
#   "sorter"   param = percorso          -> apre Image Sorter su quella cartella
#   "page"     param = "next"/"prev"     -> cambia pagina idle

IDLE_ACTION_TYPES = [
    ("folder",  "Apri cartella"),
    ("app",     "Apri applicazione"),
    ("hotkey",  "Scorciatoia tastiera"),
    ("url",     "Apri URL"),
    ("mute",    "Muto / smuto audio"),
    ("sorter",  "Image Sorter su cartella"),
    ("page",    "Cambia pagina"),
    ("text",    "Scrivi testo (xdotool)"),
]

IDLE_ACTION_LABELS = {k: v for k, v in IDLE_ACTION_TYPES}


def _deck_execute_action(action_dict, sorter=None):
    """Esegue l'azione di un tasto idle. Chiamata nel thread principale."""
    if not action_dict:
        return
    kind  = action_dict.get("action", "")
    param = action_dict.get("param", "")
    try:
        if kind == "folder":
            open_in_filemanager(param)
        elif kind == "app":
            subprocess.Popen(param.split(),
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif kind == "hotkey":
            # xdotool key ctrl+c ecc.
            subprocess.Popen(["xdotool", "key", param],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif kind == "url":
            subprocess.Popen(["xdg-open", param],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif kind == "mute":
            subprocess.Popen(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif kind == "sorter" and sorter:
            sorter.root.after(0, lambda: sorter._load_source(param))
        elif kind == "page":
            pass   # gestita da DeckIdleManager
        elif kind == "text":
            # Scrivi testo tramite xdotool type
            try:
                subprocess.Popen(["xdotool", "type", "--clearmodifiers", param],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except Exception:
                pass
    except Exception:
        pass



class StreamDeckManager:
    """
    Gestisce lo Stream Deck Standard (15 tasti, 3x5).
    Layout tasti:
      [ 0][ 1][ 2][ 3][ 4]     tasto SD index
      [ 5][ 6][ 7][ 8][ 9]
      [10][11][12][13][14]

    Mappa sul tastierino image_sorter:
      [7 ][8 ][9 ][ ← ][ → ]
      [4 ][5 ][6 ][ ⌫ ][PRST]
      [1 ][2 ][3 ][0  ][    ]
    """

    # Layout:
    # Riga 1: [1][2][3][0=preset attivo][Canc    ]
    # Riga 2: [4][5][6][^preset prev   ][vpreset ]
    # Riga 3: [7][8][9][<<             ][>>      ]
    LAYOUT = {
        0:  ("key", "1"),
        1:  ("key", "2"),
        2:  ("key", "3"),
        3:  ("key", "0"),
        4:  ("delete",),
        5:  ("key", "4"),
        6:  ("key", "5"),
        7:  ("key", "6"),
        8:  ("preset_prev",),
        9:  ("preset_next",),
        10: ("key", "7"),
        11: ("key", "8"),
        12: ("key", "9"),
        13: ("nav", "left"),
        14: ("nav", "right"),
    }

    # Colori azioni speciali (R, G, B) 0-255
    COLOR_FLASH   = (255, 255, 255)

    def __init__(self, sorter):
        self.sorter       = sorter
        self.deck         = None
        self._active      = False
        self._mode        = "idle"     # "preset" | "idle" — default idle
        self._idle_page   = 0          # pagina corrente in idle
        self._deck_info   = {}         # info modello: key_count, rows, cols
        self._connect()

    # ------------------------------------------------------------------
    def _connect(self):
        try:
            from StreamDeck.DeviceManager import DeviceManager
            decks = DeviceManager().enumerate()
            if not decks:
                return
            # Scegli il deck configurato o il primo disponibile
            preferred = self.sorter.config.get("deck_device_index", 0)
            idx = preferred if preferred < len(decks) else 0
            self.deck = decks[idx]
            self.deck.open()
            self.deck.reset()
            self.deck.set_brightness(
                self.sorter.config.get("deck_brightness", 70))
            self._active = True
            # Rileva modello
            self._deck_info = {
                "key_count": self.deck.key_count(),
                "rows":      self.deck.key_layout()[0],
                "cols":      self.deck.key_layout()[1],
                "type":      self.deck.deck_type(),
            }
            self.sorter.config.setdefault("deck_model", self._deck_info["type"])
            self.deck.set_key_callback(self._on_key)
            self.refresh_all()
            print(f"[StreamDeck] Connesso: {self._deck_info['type']} "
                  f"({self._deck_info['key_count']} tasti)")
        except Exception as ex:
            print(f"[StreamDeck] Non disponibile: {ex}")
            self.deck = None

    def is_active(self):
        return self._active and self.deck is not None

    def key_count(self):
        return self._deck_info.get("key_count", 15)

    # ------------------------------------------------------------------
    # Modalità idle / preset
    # ------------------------------------------------------------------

    def set_mode(self, mode):
        """Cambia modalità: 'preset' (smistamento) o 'idle' (pagine custom)."""
        self._mode = mode
        self._idle_page = 0
        self.refresh_all()

    def _idle_pages(self):
        return self.sorter.config.get("deck_idle_pages", [])

    def _idle_page_data(self):
        pages = self._idle_pages()
        if not pages:
            return []
        return pages[self._idle_page % len(pages)]

    def idle_next_page(self):
        pages = self._idle_pages()
        if len(pages) > 1:
            self._idle_page = (self._idle_page + 1) % len(pages)
            self.refresh_all()

    def idle_prev_page(self):
        pages = self._idle_pages()
        if len(pages) > 1:
            self._idle_page = (self._idle_page - 1) % len(pages)
            self.refresh_all()

    # ------------------------------------------------------------------
    def refresh_all(self):
        if not self.is_active():
            return
        n = self.key_count()
        for idx in range(n):
            self.sorter.root.after(idx * 30, lambda i=idx: self._render_key(i))

    def _render_key(self, idx):
        if not self.is_active():
            return
        if self._mode == "idle":
            self._render_key_idle(idx)
            return
        action = self.LAYOUT.get(idx)
        try:
            img = self._make_key_image(idx, action)
            fmt  = self.deck.key_image_format()
            w, h = fmt["size"]
            img = img.convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
            # Applica flip richiesto dal deck
            if fmt.get("flip"):
                fh, fv = fmt["flip"]
                if fh: img = img.transpose(Image.FLIP_LEFT_RIGHT)
                if fv: img = img.transpose(Image.FLIP_TOP_BOTTOM)
            if fmt.get("rotation"):
                img = img.rotate(fmt["rotation"])
            # Converti in JPEG bytes
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            self.deck.set_key_image(idx, buf.getvalue())
        except Exception as ex:
            print(f"[StreamDeck] render key {idx}: {ex}")
            traceback.print_exc()

    def _make_key_image(self, idx, action):
        key_w, key_h = self.deck.key_image_format()["size"]
        BG = (10, 15, 26)
        img  = Image.new("RGB", (key_w, key_h), BG)
        draw = ImageDraw.Draw(img)

        # Font
        try:
            font_lg = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)
            font_xs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9)
        except Exception:
            font_lg = font_sm = font_xs = ImageFont.load_default()

        def ctext(text, font, y, color):
            try:
                bb  = draw.textbbox((0,0), text, font=font)
                tw  = bb[2] - bb[0]
            except Exception:
                tw = len(text) * 7
            draw.text(((key_w - tw) // 2, y), text, font=font, fill=color)

        if action is None:
            return img

        kind = action[0]

        if kind == "key":
            k  = action[1]
            ki = KEYS.index(k) if k in KEYS else 0
            hex_c = KEY_COLORS[ki].lstrip("#")
            r, g, b = int(hex_c[0:2],16), int(hex_c[2:4],16), int(hex_c[4:6],16)
            if k == "0":
                # Tasto 0: etichetta cartella in alto + nome preset in basso
                draw.rectangle([1, 1, key_w-1, key_h-1], outline=(r, g, b), width=2)
                preset = self.sorter.labels.get("0", {})
                label  = preset.get("label", "") if isinstance(preset, dict) else str(preset)
                active = self.sorter.config.get("active_preset", "")
                # Etichetta cartella in alto (ciano)
                for i, line in enumerate(self._wrap(label, 8)):
                    ctext(line, font_sm, 5 + i*13, (r, g, b))
                # Separatore
                draw.line([(6, key_h//2), (key_w-6, key_h//2)],
                          fill=(r//2, g//2, b//2), width=1)
                # Nome preset in basso (bianco)
                for i, line in enumerate(self._wrap(active, 8)):
                    ctext(line, font_xs, key_h//2 + 4 + i*11, (200, 200, 200))
            else:
                # Tasti 1-9: sfondo colorato, etichetta cartella
                draw.rectangle([0, 0, key_w, key_h], fill=(r//4, g//4, b//4))
                draw.rectangle([2, 2, key_w-2, key_h-2], fill=(r//3, g//3, b//3))
                draw.rectangle([1, 1, key_w-1, key_h-1], outline=(r, g, b), width=1)
                draw.text((4, 3), k, font=font_xs, fill=(r, g, b))
                preset = self.sorter.labels.get(k, {})
                label  = preset.get("label", k) if isinstance(preset, dict) else str(preset)
                lines  = self._wrap(label, 8)
                y = (key_h - len(lines)*15)//2 + 4
                for line in lines:
                    ctext(line, font_sm, y, (220, 220, 220))
                    y += 15

        elif kind == "nav":
            draw.rectangle([1, 1, key_w-1, key_h-1], outline=(0, 100, 180), width=2)
            cy = key_h // 2 - 6
            cx = key_w // 2
            if action[1] == "left":
                # Freccia sinistra
                draw.polygon([(6, cy), (20, cy-10), (20, cy+10)],
                             fill=(0, 180, 255))
                draw.rectangle([20, cy-4, 34, cy+4], fill=(0, 180, 255))
                ctext("Indietro", font_xs, key_h//2 + 10, (80, 140, 180))
            else:
                # Freccia destra
                draw.rectangle([key_w-34, cy-4, key_w-20, cy+4], fill=(0, 180, 255))
                draw.polygon([(key_w-6, cy), (key_w-20, cy-10), (key_w-20, cy+10)],
                             fill=(0, 180, 255))
                ctext("Avanti", font_xs, key_h//2 + 10, (80, 140, 180))

        elif kind == "delete":
            draw.rectangle([1, 1, key_w-1, key_h-1], outline=(180, 30, 30), width=2)
            ctext("DEL", font_lg, key_h//2 - 18, (220, 60, 60))
            ctext("Cancella", font_xs, key_h//2 + 8, (160, 80, 80))

        elif kind in ("preset_prev", "preset_next"):
            draw.rectangle([1, 1, key_w-1, key_h-1], outline=(0, 160, 200), width=2)
            presets = list(self.sorter.config["presets"].keys())
            active  = self.sorter.config.get("active_preset", "")
            cur_idx = presets.index(active) if active in presets else 0
            if kind == "preset_prev":
                target = presets[(cur_idx - 1) % len(presets)] if presets else ""
                # Freccia su disegnata
                cx = key_w // 2
                draw.polygon([(cx, 6), (cx-10, 20), (cx+10, 20)],
                             fill=(0, 200, 255))
                draw.rectangle([cx-4, 20, cx+4, 30], fill=(0, 200, 255))
            else:
                target = presets[(cur_idx + 1) % len(presets)] if presets else ""
                # Freccia giu disegnata
                cx = key_w // 2
                draw.rectangle([cx-4, 6, cx+4, 16], fill=(0, 200, 255))
                draw.polygon([(cx, 30), (cx-10, 16), (cx+10, 16)],
                             fill=(0, 200, 255))
            lines = self._wrap(target, 8)
            y = key_h//2 - len(lines)*7
            for line in lines:
                ctext(line, font_sm, y, (180, 230, 240))
                y += 14

        return img

    @staticmethod
    def _wrap(text, max_chars):
        words, lines, cur = text.split(), [], ""
        for w in words:
            if len(cur) + len(w) + 1 <= max_chars:
                cur = (cur + " " + w).strip()
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [text[:max_chars]]

    # ------------------------------------------------------------------
    def _on_key(self, deck, idx, pressed):
        if not pressed:
            return
        self._flash_key_sd(idx)

        if self._mode == "idle":
            self._on_key_idle(idx)
            return

        action = self.LAYOUT.get(idx)
        if action is None:
            return
        kind = action[0]
        # Usa l'istanza con la finestra in primo piano, non necessariamente
        # quella che possiede il deck
        target = ImageSorter._get_focused_instance() or self.sorter
        if kind == "key":
            target.root.after(0, lambda k=action[1], t=target: t._move_to(k))
        elif kind == "nav":
            if action[1] == "left":
                target.root.after(0, target._go_back)
            else:
                target.root.after(0, target._skip)
        elif kind == "delete":
            target.root.after(0, target._delete_current)
        elif kind == "preset_prev":
            target.root.after(0, lambda t=target: t._cycle_preset(-1))
        elif kind == "preset_next":
            target.root.after(0, lambda t=target: t._cycle_preset(1))

    def _on_key_idle(self, idx):
        """Gestisce il click di un tasto in modalità idle."""
        page_data = self._idle_page_data()
        if not isinstance(page_data, list) or idx >= len(page_data):
            return
        slot = page_data[idx]
        if not slot:
            return
        action = slot.get("action", "")
        # Azione "page" gestita localmente
        if action == "page":
            param = slot.get("param", "next")
            if param == "prev":
                self.idle_prev_page()
            elif param == "next":
                self.idle_next_page()
            else:
                # Numero di pagina diretto (0-based internamente)
                try:
                    target = int(param) - 1   # utente inserisce 1-based
                    pages = self._idle_pages()
                    if 0 <= target < len(pages):
                        self._idle_page = target
                        self.refresh_all()
                except ValueError:
                    self.idle_next_page()
            return
        target = ImageSorter._get_focused_instance() or self.sorter
        self.sorter.root.after(0,
            lambda s=slot, t=target: _deck_execute_action(s, t))

    def _render_key_idle(self, idx):
        """Renderizza un tasto in modalità idle."""
        if not self.is_active():
            return
        fmt      = self.deck.key_image_format()
        w, h     = fmt["size"]
        n        = self.key_count()
        page_data = self._idle_page_data()
        pages    = self._idle_pages()

        # Ogni tasto è libero — leggi semplicemente lo slot configurato
        if isinstance(page_data, list) and idx < len(page_data):
            slot = page_data[idx] or {}
        else:
            slot = {}
        # Se lo slot è un'azione "page", mostra la pagina corrente nel label
        if slot.get("action") == "page":
            cur_p = self._idle_page + 1
            total_p = len(pages)
            param = slot.get("param", "next")
            default_lbl = f"< {cur_p}/{total_p}" if param == "prev" else f"> {cur_p}/{total_p}"
            slot = dict(slot)   # copia per non modificare config
            if not slot.get("label"):
                slot["label"] = default_lbl

        # Costruisce immagine tasto
        label  = slot.get("label", "")
        color  = tuple(slot.get("color", [15, 20, 40]))
        img_path = slot.get("image", None)

        try:
            if img_path and os.path.isfile(img_path):
                base = Image.open(img_path).convert("RGB")
                base = base.resize((w, h), Image.Resampling.LANCZOS)
                overlay = Image.new("RGB", (w, h), (0,0,0))
                base = Image.blend(base, overlay, 0.35)
            else:
                # Prova icona di default per il tipo di azione
                action_type = slot.get("action","") if slot else ""
                icon_base = get_deck_icon(action_type, size=w) if action_type else None
                if icon_base:
                    # Mescola icona con il colore del tasto
                    color_layer = Image.new("RGB", (w, h), color)
                    base = Image.blend(icon_base, color_layer, 0.45)
                else:
                    base = Image.new("RGB", (w, h), color)

            if label:
                draw  = ImageDraw.Draw(base)
                lines = self._wrap(label, 8)
                line_h = h // (len(lines) + 1)
                for li, line in enumerate(lines):
                    bbox = draw.textbbox((0,0), line)
                    tw = bbox[2] - bbox[0]
                    x  = (w - tw) // 2
                    y  = (li + 1) * line_h - (bbox[3] - bbox[1]) // 2
                    draw.text((x, y), line, fill=(220, 220, 220))

            img = base
            if fmt.get("flip"):
                fh, fv = fmt["flip"]
                if fh: img = img.transpose(Image.FLIP_LEFT_RIGHT)
                if fv: img = img.transpose(Image.FLIP_TOP_BOTTOM)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            self.deck.set_key_image(idx, buf.getvalue())
        except Exception as ex:
            print(f"[StreamDeck] render idle key {idx}: {ex}")

    def _flash_key_sd(self, idx):
        """Flash bianco brevissimo sul tasto premuto."""
        if not self.is_active():
            return
        try:
            fmt = self.deck.key_image_format()
            key_w, key_h = fmt["size"]
            img = Image.new("RGB", (key_w, key_h), self.COLOR_FLASH)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            self.deck.set_key_image(idx, buf.getvalue())
            self.sorter.root.after(120, lambda i=idx: self._render_key(i))
        except Exception:
            pass

    def close(self):
        self._active = False
        # Non chiamiamo deck.reset() o deck.close() esplicitamente:
        # il device viene rilasciato dal sistema quando il processo termina.
        # Chiamare close() manteneva il device occupato impedendo
        # a StreamController di riconnettersi.
        self.deck = None


# =============================================================================
# FINESTRA IMPOSTAZIONI (tab Preset + tab Destinazioni)
# =============================================================================

class SettingsDialog:
    """Finestra impostazioni unificata con due tab:
    - Preset: gestione e selezione preset (ex PresetSelector)
    - Destinazioni: configurazione cartelle per tasto (ex FolderConfigDialog)
    """
    def __init__(self, parent, sorter, initial_tab="preset"):
        self.sorter = sorter
        self.config = sorter.config
        self.result = None   # preset selezionato (per compatibilità)

        self.win = tk.Toplevel(parent)
        self.win.title("Impostazioni")
        self.win.configure(bg=BG_COLOR)
        self.win.geometry("780x640")
        self.win.minsize(600, 480)
        self.win.resizable(True, True)
        self.win.transient(parent)   # legata alla finestra principale
        hud_apply(self.win)
        self._build(initial_tab)
        self.win.bind("<Return>", lambda e: self._on_enter())
        self.win.bind("<Escape>", lambda e: self._on_close_request())
        self.win.protocol("WM_DELETE_WINDOW", self._on_close_request)

    def _on_enter(self):
        tab = self._current_tab.get() if hasattr(self, '_current_tab') else "preset"
        if tab == "preset":
            self._confirm_preset()
        elif tab == "dest":
            self._apply_dest()
        else:
            pass   # tab visualizza: le checkbox si applicano in tempo reale

    def _dest_has_unsaved_changes(self):
        """True se il tab Destinazioni ha modifiche non ancora salvate."""
        if self._current_tab.get() != "dest":
            return False
        if not hasattr(self, 'label_vars') or not hasattr(self, 'path_vars'):
            return False
        try:
            preset_name = self._dest_preset_var.get()
            saved = self.config["presets"].get(preset_name, {})
            for k in KEYS:
                saved_slot  = saved.get(k, {})
                cur_label   = self.label_vars[k].get().strip()
                cur_path    = self.path_vars[k].get().strip()
                saved_label = saved_slot.get("label", "").strip()
                saved_path  = saved_slot.get("path",  "").strip()
                if cur_label != saved_label or cur_path != saved_path:
                    return True
        except Exception:
            pass
        return False

    def _on_close_request(self, e=None):
        """Chiude la finestra, chiedendo conferma se ci sono modifiche non salvate."""
        if self._dest_has_unsaved_changes():
            answer = messagebox.askyesnocancel(
                "Modifiche non salvate",
                "Il tab Destinazioni ha modifiche non ancora salvate.\n\n"
                "Salvare prima di chiudere?",
                parent=self.win)
            if answer is None:      # Annulla → rimani
                return
            if answer:              # Sì → salva e chiudi
                self._apply_dest()
        self.win.destroy()

    def _build(self, initial_tab):
        w = self.win
        w.columnconfigure(0, weight=1)
        w.rowconfigure(1, weight=1)
        w.rowconfigure(2, weight=0)

        # --- Tab bar in cima ---
        tab_bar = tk.Frame(w, bg=PANEL_COLOR)
        tab_bar.grid(row=0, column=0, sticky="ew")
        self._tab_btns = {}
        self._current_tab = tk.StringVar(value=initial_tab)

        cfg_lang = self.config.get("language", "it")
        for key, label in [
            ("preset", T("tab_preset", cfg_lang)),
            ("dest",   T("tab_dest",   cfg_lang)),
            ("view",   T("tab_view",   cfg_lang)),
            ("keys",   T("tab_keys",   cfg_lang)),
            ("deck",   "  Stream Deck  "),
            ("info",   "  Info  "),
        ]:
            btn = tk.Button(tab_bar, text=label,
                            font=("TkFixedFont", 10),
                            relief="flat", bd=0, padx=4, pady=8,
                            activebackground=BG_COLOR, activeforeground=HIGHLIGHT,
                            command=lambda k=key: self._switch_tab(k))
            btn.pack(side="left")
            self._tab_btns[key] = btn

        # --- Area contenuto ---
        self._content = tk.Frame(w, bg=BG_COLOR)
        self._content.grid(row=1, column=0, sticky="nsew")
        self._content.columnconfigure(0, weight=1)
        self._content.rowconfigure(0, weight=0)

        # --- Barra fondo: area sinistra contestuale + Chiudi a destra ---
        bot = tk.Frame(w, bg=PANEL_COLOR)
        bot.grid(row=2, column=0, sticky="ew")
        # Frame sinistro per bottoni del tab corrente (aggiornato da _switch_tab)
        self._bot_left = tk.Frame(bot, bg=PANEL_COLOR)
        self._bot_left.pack(side="left", fill="y")
        tk.Button(bot, text="Chiudi",
                  font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=16,
                  command=self._on_close_request
                  ).pack(side="right", padx=10, pady=6, ipady=3)

        self._switch_tab(initial_tab)

    def _switch_tab(self, key):
        # Avvisa se si cambia tab con modifiche Destinazioni non salvate
        if key != "dest" and self._dest_has_unsaved_changes():
            answer = messagebox.askyesno(
                "Modifiche non salvate",
                "Il tab Destinazioni ha modifiche non ancora salvate.\n\n"
                "Salvare prima di cambiare tab?",
                parent=self.win)
            if answer:
                self._apply_dest()
        self._current_tab.set(key)
        # Aggiorna stile bottoni tab
        for k, btn in self._tab_btns.items():
            if k == key:
                btn.config(bg=BG_COLOR, fg=HIGHLIGHT,
                           font=("TkFixedFont", 10, "bold"))
            else:
                btn.config(bg=PANEL_COLOR, fg=MUTED_COLOR,
                           font=("TkFixedFont", 10))
        # Svuota e ricostruisce contenuto — resetta anche i rowconfigure
        for child in self._content.winfo_children():
            child.destroy()
        # Pulisci bottoni contestuali nella barra fondo
        if hasattr(self, '_bot_left'):
            for child in self._bot_left.winfo_children():
                child.destroy()
        # Resetta weight righe per evitare layout residui dai tab precedenti
        for i in range(10):
            self._content.rowconfigure(i, weight=0)
        self._content.rowconfigure(0, weight=0)
        if key == "preset":
            self._build_preset_tab()
        elif key == "dest":
            self._build_dest_tab()
        elif key == "view":
            self._build_view_tab()
        elif key == "keys":
            self._build_keys_tab()
        elif key == "deck":
            self._build_deck_tab()
        elif key == "info":
            self._build_info_tab()

    # ------------------------------------------------------------------
    # TAB PRESET
    # ------------------------------------------------------------------
    def _build_preset_tab(self):
        f = self._content
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)

        tk.Label(f, text="I primi 3 preset (in verde) sono visibili nella sidebar e nel tastierino.\n"
                          "Usa le frecce per riordinare.",
                 font=("TkFixedFont", 8), bg=BG_COLOR, fg=MUTED_COLOR,
                 justify="left").grid(row=0, column=0, sticky="w",
                                      padx=20, pady=(12, 4))

        # Lista + frecce
        list_outer = tk.Frame(f, bg=BG_COLOR)
        list_outer.grid(row=1, column=0, sticky="nsew", padx=20, pady=4)
        list_outer.rowconfigure(0, weight=1)
        list_outer.columnconfigure(0, weight=1)

        lf = tk.Frame(list_outer, bg=ACCENT_COLOR)
        lf.grid(row=0, column=0, sticky="nsew")
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)
        sb = tk.Scrollbar(lf, orient="vertical", bg=ACCENT_COLOR, troughcolor=BG_COLOR)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox = tk.Listbox(lf, font=("TkFixedFont", 11),
                                  bg=PANEL_COLOR, fg=TEXT_COLOR,
                                  selectbackground=HIGHLIGHT, selectforeground="white",
                                  activestyle="none", relief="flat", bd=0,
                                  width=28,
                                  yscrollcommand=sb.set, exportselection=False)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb.config(command=self.listbox.yview)
        self.listbox.bind("<Button-4>", lambda e: self.listbox.yview_scroll(-1, "units"))
        self.listbox.bind("<Button-5>", lambda e: self.listbox.yview_scroll(1, "units"))
        self.listbox.bind("<MouseWheel>", lambda e: self.listbox.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.listbox.bind("<Double-Button-1>", lambda e: self._confirm_preset())
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._update_preview())

        arrows = tk.Frame(list_outer, bg=BG_COLOR)
        arrows.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        _ico_arr_up = make_icon("up", size=16, fg=(0,200,255), bg=(20,28,48))
        _btn_up = tk.Button(arrows, image=_ico_arr_up, text="", compound="none",
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat",
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=self._move_up).pack(fill="x", pady=(0, 3), ipady=4)
        _ico_arr_dn = make_icon("down", size=16, fg=(0,200,255), bg=(20,28,48))
        _btn_dn = tk.Button(arrows, image=_ico_arr_dn, text="", compound="none",
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat",
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=self._move_down).pack(fill="x", ipady=4)

        # Anteprima cartelle
        pf = tk.Frame(f, bg=BG_COLOR)
        pf.grid(row=2, column=0, sticky="ew", padx=20, pady=(4, 2))
        tk.Label(pf, text="Cartelle:", font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR).pack(side="left")
        self.preview_label = tk.Label(pf, text="", font=("TkFixedFont", 8),
                                      bg=BG_COLOR, fg=TEXT_COLOR,
                                      anchor="w", wraplength=440, justify="left")
        self.preview_label.pack(side="left", padx=6, fill="x", expand=True)

        self._refresh_list()

        # Azioni preset
        af = tk.Frame(f, bg=BG_COLOR)
        af.grid(row=3, column=0, sticky="ew", padx=20, pady=4)
        for txt, cmd, col in [
            ("+ Nuovo",  self._new_preset,    SUCCESS),
            ("Copia",    self._copy_preset,   "#4a90e2"),
            ("Rinomina", self._rename_preset, WARNING),
            ("Elimina",  self._delete_preset, "#c0392b"),
        ]:
            tk.Button(af, text=txt, font=("TkFixedFont", 8),
                      bg=col, fg="white", relief="flat", padx=6,
                      activebackground=HIGHLIGHT, activeforeground="white",
                      command=cmd).pack(side="left", padx=3, pady=4,
                                        fill="x", expand=True)

        # --- Separatore ---
        tk.Frame(f, bg=ACCENT_COLOR, height=1).grid(
            row=4, column=0, sticky="ew", padx=20, pady=(8,4))

        # Sezione Tastierino + Sidebar affiancati
        bottom_f = tk.Frame(f, bg=BG_COLOR)
        bottom_f.grid(row=5, column=0, sticky="ew", padx=20, pady=(0,4))
        bottom_f.columnconfigure(0, weight=1)
        bottom_f.columnconfigure(1, weight=0, minsize=8)
        bottom_f.columnconfigure(2, weight=1)

        # --- Tastierino ---
        kf = tk.Frame(bottom_f, bg=PANEL_COLOR,
                      highlightbackground=HUD_DIM, highlightthickness=1)
        kf.grid(row=0, column=0, sticky="nsew", padx=(0,4), pady=2)
        tk.Label(kf, text="Tastierino", font=("TkFixedFont", 9, "bold"),
                 bg=PANEL_COLOR, fg=WARNING).pack(anchor="w", padx=8, pady=(6,2))
        tk.Frame(kf, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=4, pady=(0,4))
        cols_row = tk.Frame(kf, bg=PANEL_COLOR)
        cols_row.pack(fill="x", padx=8, pady=(0,8))
        tk.Label(cols_row, text="Colonne:", font=("TkFixedFont", 8),
                 bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="left", padx=(0,6))
        self._col_btns = {}
        for n in (1, 2, 3):
            b = tk.Button(cols_row, text=str(n),
                          font=("TkFixedFont", 9, "bold"),
                          relief="flat", bd=0, width=3,
                          activebackground=HUD_CYAN, activeforeground="#0a1a2e",
                          command=lambda v=n: self._set_keypad_cols(v))
            b.pack(side="left", padx=2, ipady=3)
            self._col_btns[n] = b
        self._refresh_col_btns()

        # --- Sidebar ---
        sf = tk.Frame(bottom_f, bg=PANEL_COLOR,
                      highlightbackground=HUD_DIM, highlightthickness=1)
        sf.grid(row=0, column=2, sticky="nsew", padx=(4,0), pady=2)
        tk.Label(sf, text="Sidebar", font=("TkFixedFont", 9, "bold"),
                 bg=PANEL_COLOR, fg=WARNING).pack(anchor="w", padx=8, pady=(6,2))
        tk.Frame(sf, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=4, pady=(0,4))

        np_row = tk.Frame(sf, bg=PANEL_COLOR)
        np_row.pack(fill="x", padx=8, pady=(0,4))
        tk.Label(np_row, text="Preset:", font=("TkFixedFont", 8),
                 bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="left", padx=(0,6))
        self._sb_preset_btns = {}
        for n in (1, 2, 3):
            b = tk.Button(np_row, text=str(n),
                          font=("TkFixedFont", 9, "bold"),
                          relief="flat", bd=0, width=3, padx=4,
                          activebackground=HUD_CYAN, activeforeground="#0a1a2e",
                          command=lambda v=n: self._set_sidebar_presets(v))
            b.pack(side="left", padx=2, ipady=3)
            self._sb_preset_btns[n] = b
        self._refresh_sb_preset_btns()

        mode_row = tk.Frame(sf, bg=PANEL_COLOR)
        mode_row.pack(fill="x", padx=8, pady=(0,8))
        tk.Label(mode_row, text="Modalita:", font=("TkFixedFont", 8),
                 bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="left", padx=(0,4))
        self._sidebar_mode_var = tk.StringVar(value=get_sidebar_mode(self.config))
        for val, label in [("inline","Fissa"), ("popup","Finestra"), ("hidden","Off")]:
            tk.Radiobutton(mode_row, text=label,
                           variable=self._sidebar_mode_var, value=val,
                           font=("TkFixedFont", 8),
                           bg=PANEL_COLOR, fg=TEXT_COLOR,
                           selectcolor=ACCENT_COLOR,
                           activebackground=PANEL_COLOR, activeforeground=HUD_CYAN,
                           command=self._apply_sidebar_settings
                           ).pack(side="left", padx=4)

        # Bottone nella barra fondo a sinistra
        tk.Button(self._bot_left, text="  USA QUESTO PRESET  ",
                  font=("TkFixedFont", 9, "bold"),
                  bg=HIGHLIGHT, fg="white", relief="flat",
                  activebackground="#c73652",
                  command=self._confirm_preset
                  ).pack(side="left", padx=10, pady=6, ipady=3)
    # --- helpers tab preset ---
    def _refresh_list(self, select_name=None):
        self.listbox.delete(0, tk.END)
        presets = list(self.config["presets"].keys())
        active  = self.config.get("active_preset", "")
        for i, name in enumerate(presets):
            star = "* " if name == active else "  "
            self.listbox.insert(tk.END, f"  {star}  {name}")
            color = (PRESET_COLORS[i] if i < len(PRESET_COLORS)
                     else TEXT_COLOR)
            self.listbox.itemconfig(i, fg=color)
        target = select_name or active
        idx = presets.index(target) if target in presets else 0
        if presets:
            self.listbox.selection_set(idx)
            self.listbox.see(idx)
        self._update_preview()

    def _selected_name(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        presets = list(self.config["presets"].keys())
        return presets[sel[0]] if sel[0] < len(presets) else None

    def _update_preview(self):
        name = self._selected_name()
        if not name:
            self.preview_label.config(text="")
            return
        slots = self.config["presets"][name]
        parts = [f"{k}:{slots[k].get('label',k)}" for k in KEYS]
        self.preview_label.config(text="  ".join(parts))

    def _confirm_preset(self):
        name = self._selected_name()
        if not name:
            return
        self.config["active_preset"] = name
        save_config(self.config)
        self.sorter.labels = self.config["presets"][name]
        for k in KEYS:
            os.makedirs(self.sorter._dest_path(k), exist_ok=True)
        self.sorter._update_preset_label()
        self.sorter._build_sidebar()
        if self.sorter.keypad_popup:
            self.sorter.keypad_popup.refresh_labels()
        self.win.destroy()

    def _move_up(self):
        name = self._selected_name()
        if not name:
            return
        presets = list(self.config["presets"].keys())
        idx = presets.index(name)
        if idx == 0:
            return
        presets.insert(idx-1, presets.pop(idx))
        self.config["presets"] = {k: self.config["presets"][k] for k in presets}
        save_config(self.config)
        self._refresh_list(select_name=name)
        self.sorter._build_sidebar()
        if self.sorter.keypad_popup:
            self.sorter.keypad_popup.refresh_labels()

    def _move_down(self):
        name = self._selected_name()
        if not name:
            return
        presets = list(self.config["presets"].keys())
        idx = presets.index(name)
        if idx >= len(presets)-1:
            return
        presets.insert(idx+1, presets.pop(idx))
        self.config["presets"] = {k: self.config["presets"][k] for k in presets}
        save_config(self.config)
        self._refresh_list(select_name=name)
        self.sorter._build_sidebar()
        if self.sorter.keypad_popup:
            self.sorter.keypad_popup.refresh_labels()

    def _new_preset(self):
        name = simpledialog.askstring("Nuovo preset", "Nome:", parent=self.win)
        if not name:
            return
        name = sanitize_name(name)
        if not name or name in self.config["presets"]:
            messagebox.showwarning("Nome non valido", f"'{name}' non valido o già esistente.", parent=self.win)
            return
        self.config["presets"][name] = default_preset()
        save_config(self.config)
        self._refresh_list(select_name=name)

    def _copy_preset(self):
        src = self._selected_name()
        if not src:
            return
        name = simpledialog.askstring("Copia preset", f"Nome della copia di '{src}':", parent=self.win)
        if not name:
            return
        name = sanitize_name(name)
        if not name or name in self.config["presets"]:
            messagebox.showwarning("Nome non valido", f"'{name}' non valido.", parent=self.win)
            return
        self.config["presets"][name] = copy.deepcopy(self.config["presets"][src])
        save_config(self.config)
        self._refresh_list(select_name=name)

    def _rename_preset(self):
        old = self._selected_name()
        if not old:
            return
        new = simpledialog.askstring("Rinomina", f"Nuovo nome per '{old}':",
                                     initialvalue=old, parent=self.win)
        if not new or new == old:
            return
        new = sanitize_name(new)
        if not new or new in self.config["presets"]:
            messagebox.showwarning("Nome non valido", f"'{new}' non valido.", parent=self.win)
            return
        self.config["presets"][new] = self.config["presets"].pop(old)
        if self.config.get("active_preset") == old:
            self.config["active_preset"] = new
        save_config(self.config)
        self._refresh_list(select_name=new)

    def _delete_preset(self):
        name = self._selected_name()
        if not name:
            return
        if len(self.config["presets"]) <= 1:
            messagebox.showwarning("Impossibile", "Deve esistere almeno un preset.", parent=self.win)
            return
        if not messagebox.askyesno("Elimina", f"Eliminare il preset '{name}'?\n(Le cartelle su disco NON vengono toccate.)", parent=self.win):
            return
        del self.config["presets"][name]
        if self.config.get("active_preset") == name:
            self.config["active_preset"] = next(iter(self.config["presets"]))
        save_config(self.config)
        self._refresh_list()

    def _set_keypad_cols(self, n):
        self.config["keypad_cols"] = n
        save_config(self.config)
        self._refresh_col_btns()
        if self.sorter.keypad_popup:
            self.sorter.keypad_popup.refresh_labels()

    def _refresh_col_btns(self):
        n = get_keypad_cols(self.config)
        for v, b in self._col_btns.items():
            b.config(bg=HIGHLIGHT if v == n else ACCENT_COLOR, fg="white")

    # ------------------------------------------------------------------
    # TAB DESTINAZIONI (ex FolderConfigDialog)
    # ------------------------------------------------------------------
    def _apply_sidebar_settings(self):
        mode = self._sidebar_mode_var.get()
        self.config["sidebar_mode"] = mode
        save_config(self.config)
        self.sorter._apply_sidebar_mode()

    def _set_sidebar_presets(self, n):
        self.config["sidebar_presets"] = n
        save_config(self.config)
        self._refresh_sb_preset_btns()
        # Aggiorna sidebar attiva
        mode = get_sidebar_mode(self.config)
        if mode == "inline":
            self.sorter._build_sidebar()
        elif mode == "popup" and self.sorter.sidebar_popup:
            self.sorter.sidebar_popup.refresh()

    def _refresh_sb_preset_btns(self):
        n = get_sidebar_presets(self.config)
        for v, b in self._sb_preset_btns.items():
            b.config(bg=HUD_CYAN if v == n else ACCENT_COLOR,
                     fg="#0a1a2e" if v == n else TEXT_COLOR)

    def _build_dest_tab(self):
        self.slots = copy.deepcopy(self.sorter.labels)
        self.label_vars = {}
        self.path_vars  = {}
        self.mode_vars  = {}

        f = self._content
        f.rowconfigure(0, weight=0)   # header preset
        f.rowconfigure(1, weight=1)   # scroll area tasti (si espande)
        f.rowconfigure(2, weight=0)   # bottoni
        f.columnconfigure(0, weight=1)

        # Selettore preset + label descrittiva in un unico header compatto
        hdr = tk.Frame(f, bg=PANEL_COLOR)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        hdr.columnconfigure(1, weight=1)
        tk.Label(hdr, text="  Preset:",
                 font=("TkFixedFont", 9, "bold"),
                 bg=PANEL_COLOR, fg=WARNING).grid(row=0, column=0, padx=(8,6), pady=6)
        self._dest_preset_var = tk.StringVar(value=self.config["active_preset"])
        preset_names = list(self.config["presets"].keys())
        om = tk.OptionMenu(hdr, self._dest_preset_var, *preset_names,
                           command=lambda _: self._reload_dest_preset())
        om.config(font=("TkFixedFont", 12, "bold"), bg=ACCENT_COLOR, fg=HUD_CYAN,
                  activebackground=HIGHLIGHT, activeforeground="white",
                  highlightthickness=0, relief="flat", bd=0, padx=10)
        om["menu"].config(font=("TkFixedFont", 11), bg=PANEL_COLOR, fg=TEXT_COLOR,
                          activebackground=HIGHLIGHT, activeforeground="white")
        om.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=6, ipady=4)
        tk.Label(hdr, text="nome + percorso per tasto  |  AUTO = ~/Immagini/Smistati/  |  ... = percorso libero",
                 font=("TkFixedFont", 7), bg=PANEL_COLOR,
                 fg=MUTED_COLOR).grid(row=1, column=0, columnspan=3,
                                       sticky="w", padx=8, pady=(0, 4))

        # Scroll area tasti (riga 1, si espande)
        canvas = tk.Canvas(f, bg=BG_COLOR, highlightthickness=0)
        canvas.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 2))
        vsb = tk.Scrollbar(f, orient="vertical", command=canvas.yview)
        vsb.grid(row=1, column=1, sticky="ns", pady=(4, 2))
        canvas.configure(yscrollcommand=vsb.set)
        self._dest_canvas = canvas

        inner = tk.Frame(canvas, bg=BG_COLOR)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(inner_id, width=e.width))
        inner.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        inner.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))
        self._dest_inner = inner
        self._dest_inner_id = inner_id

        self._build_dest_keys()

        # Bottone nella barra fondo a sinistra
        tk.Button(self._bot_left, text="  APPLICA  ",
                  font=("TkFixedFont", 9, "bold"),
                  bg=HIGHLIGHT, fg="white", relief="flat",
                  activebackground="#c73652",
                  command=self._apply_dest
                  ).pack(side="left", padx=10, pady=6, ipady=3)
    def _reload_dest_preset(self):
        pname = self._dest_preset_var.get()
        self.slots = copy.deepcopy(self.config["presets"][pname])
        self.label_vars.clear()
        self.path_vars.clear()
        self.mode_vars.clear()
        for w in self._dest_inner.winfo_children():
            w.destroy()
        self.label_vars.clear()
        self.path_vars.clear()
        self.mode_vars.clear()
        self._build_dest_keys()
        self._dest_canvas.yview_moveto(0)

    def _build_dest_keys(self):
        """Layout a griglia compatta: ogni riga = un tasto, colonne = badge | nome | percorso | btn."""
        inner = self._dest_inner
        inner.columnconfigure(0, minsize=28)  # badge
        inner.columnconfigure(1, weight=2)    # nome
        inner.columnconfigure(2, weight=3)    # percorso
        inner.columnconfigure(3, minsize=28)  # btn ...
        inner.columnconfigure(4, minsize=28)  # btn X

        # Intestazione
        for ci, txt in enumerate(["", "Nome etichetta", "Percorso (vuoto = AUTO)", "", ""]):
            if txt:
                tk.Label(inner, text=txt, font=("TkFixedFont", 7),
                         bg=BG_COLOR, fg=MUTED_COLOR).grid(
                         row=0, column=ci, sticky="w", padx=4, pady=(4,2))

        for ri, k in enumerate(KEYS, start=1):
            self._build_key_row(inner, ri, k)

    def _build_key_row(self, inner, ri, k):
        color     = KEY_COLORS[KEYS.index(k)]
        slot      = self.slots[k]
        is_custom = bool(slot.get("path", "").strip())

        # Badge colorato
        tk.Label(inner, text=f" {k} ", font=("TkFixedFont", 10, "bold"),
                 bg=color, fg="white", anchor="center").grid(
                 row=ri, column=0, sticky="ew", padx=(6,2), pady=2, ipady=2)

        # Campo nome
        lv = tk.StringVar(value=slot.get("label", ""))
        self.label_vars[k] = lv
        tk.Entry(inner, textvariable=lv, font=("TkFixedFont", 9),
                 bg=ACCENT_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR,
                 relief="flat", bd=3).grid(
                 row=ri, column=1, sticky="ew", padx=2, pady=2, ipady=3)

        # Campo percorso
        pv = tk.StringVar(value=slot.get("path", ""))
        self.path_vars[k] = pv
        mv = tk.StringVar(value="custom" if is_custom else "auto")
        self.mode_vars[k] = mv

        path_entry = tk.Entry(inner, textvariable=pv,
                              font=("TkFixedFont", 8), bg=BG_COLOR, fg=MUTED_COLOR,
                              insertbackground=TEXT_COLOR, relief="flat", bd=3,
                              state="normal" if is_custom else "disabled")
        path_entry.grid(row=ri, column=2, sticky="ew", padx=2, pady=2, ipady=3)

        def browse(key=k, pvar=pv, entry=path_entry, lvar=lv):
            try:
                initial = (pvar.get().strip()
                           or self.config.get("last_browse_dir", "")
                           or os.path.expanduser("~"))
                if not os.path.isdir(initial):
                    initial = os.path.expanduser("~")
                self._browse_with_mkdir(key, pvar, entry, initial, lvar)
            except Exception as _e:
                import traceback
                traceback.print_exc()
                # Fallback a dialogo nativo
                folder = filedialog.askdirectory(parent=self.win, initialdir=initial)
                if folder:
                    pvar.set(folder)
                    self.mode_vars[key].set("custom")
                    entry.config(state="normal")
                    if lvar is not None:
                        current_label = lvar.get().strip()
                        if not current_label or current_label == key:
                            lvar.set(os.path.basename(folder) or folder)

        def _browse_with_mkdir_impl(key, pvar, entry, initial_dir, lvar=None):
            """Browser cartelle avanzato con accesso rapido a dischi e nuova cartella."""
            # Ricorda ultima cartella
            last_dir = self.config.get("last_browse_dir", initial_dir) or initial_dir
            if not os.path.isdir(last_dir):
                last_dir = os.path.expanduser("~")

            dlg = tk.Toplevel(self.win)
            dlg.withdraw()
            dlg.title(f"Scegli destinazione — tasto {key}")
            dlg.configure(bg=BG_COLOR)
            dlg.resizable(True, True)
            dlg.geometry("680x500")
            hud_apply(dlg)
            dlg.columnconfigure(0, weight=1)
            dlg.rowconfigure(1, weight=1)

            # ── Barra superiore: percorso ──────────────────────────────────
            top = tk.Frame(dlg, bg=PANEL_COLOR)
            top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
            top.columnconfigure(1, weight=1)
            tk.Label(top, text="Percorso:", font=("TkFixedFont", 8),
                     bg=PANEL_COLOR, fg=MUTED_COLOR).grid(
                     row=0, column=0, padx=(10,4), pady=6)
            path_v = tk.StringVar(value=last_dir)
            path_e = tk.Entry(top, textvariable=path_v,
                              font=("TkFixedFont", 9),
                              bg=ACCENT_COLOR, fg=HUD_CYAN,
                              insertbackground=HUD_CYAN,
                              relief="flat", bd=3)
            path_e.grid(row=0, column=1, sticky="ew", padx=4, pady=6, ipady=3)
            tk.Button(top, text="Vai", font=("TkFixedFont", 8),
                      bg=SUCCESS, fg="white", relief="flat", padx=8,
                      command=lambda: go_path()).grid(
                      row=0, column=2, padx=(0,8), pady=6, ipady=3)

            # ── Colonna sinistra: accesso rapido ───────────────────────────
            left = tk.Frame(dlg, bg=PANEL_COLOR, width=140)
            left.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
            left.grid_propagate(False)
            left.columnconfigure(0, weight=1)

            tk.Label(left, text="Accesso rapido",
                     font=("TkFixedFont", 8, "bold"),
                     bg=PANEL_COLOR, fg=MUTED_COLOR,
                     anchor="w").pack(fill="x", padx=8, pady=(8,4))

            # Raccoglie mount points: home, dischi montati
            def get_quick_access():
                places = [
                    ("[~] Home",    os.path.expanduser("~")),
                    ("[i] Immagini", os.path.expanduser("~/Immagini")),
                    ("[v] Video",   os.path.expanduser("~/Video")),
                    ("[d] Documenti", os.path.expanduser("~/Documenti")),
                    ("[s] Scrivania", os.path.expanduser("~/Scrivania")),
                ]
                # Dischi montati
                try:
                    mounts = []
                    with open("/proc/mounts") as f:
                        for line in f:
                            parts = line.split()
                            if len(parts) >= 2:
                                mp = parts[1]
                                if mp.startswith("/media/") or mp.startswith("/mnt/"):
                                    mounts.append(("[D] " + os.path.basename(mp), mp))
                    places += mounts
                except Exception:
                    pass
                places.append(("[/] Root", "/"))
                return [(label, p) for label, p in places if os.path.isdir(p)]

            quick_btns = []
            def build_quick():
                for w in left.winfo_children()[1:]:
                    w.destroy()
                for label, fpath in get_quick_access():
                    b = tk.Button(left, text=label,
                                  font=("TkFixedFont", 8),
                                  bg=PANEL_COLOR, fg=TEXT_COLOR,
                                  activebackground=ACCENT_COLOR,
                                  activeforeground=HUD_CYAN,
                                  relief="flat", anchor="w", padx=10,
                                  command=lambda p=fpath: populate(p))
                    b.pack(fill="x", pady=1, ipady=3)
                    quick_btns.append(b)

            build_quick()

            # Separatore
            tk.Frame(left, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=6, pady=6)

            # Ultima cartella usata
            if self.config.get("last_browse_dir"):
                tk.Label(left, text="Ultima usata:",
                         font=("TkFixedFont", 7), bg=PANEL_COLOR,
                         fg=MUTED_COLOR, anchor="w").pack(fill="x", padx=8)
                last_lbl = tk.Label(left,
                    text=os.path.basename(self.config["last_browse_dir"]) or "/",
                    font=("TkFixedFont", 8), bg=PANEL_COLOR,
                    fg=HUD_CYAN, anchor="w", cursor="hand2", wraplength=120)
                last_lbl.pack(fill="x", padx=8, pady=(0,4))
                last_lbl.bind("<Button-1>",
                    lambda e: populate(self.config["last_browse_dir"]))

            # ── Colonna destra: lista cartelle ────────────────────────────
            right = tk.Frame(dlg, bg=BG_COLOR)
            right.grid(row=1, column=1, sticky="nsew", padx=0, pady=0)
            right.rowconfigure(0, weight=1)
            right.columnconfigure(0, weight=1)
            dlg.columnconfigure(1, weight=1)

            # Canvas + scrollbar per la lista
            canvas = tk.Canvas(right, bg=BG_COLOR, highlightthickness=0)
            vsb = tk.Scrollbar(right, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=vsb.set)
            canvas.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")

            inner = tk.Frame(canvas, bg=BG_COLOR)
            inner_id = canvas.create_window((0,0), window=inner, anchor="nw")
            inner.bind("<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>",
                lambda e: canvas.itemconfig(inner_id, width=e.width))
            canvas.bind("<Button-4>",  lambda e: canvas.yview_scroll(-1,"units"))
            canvas.bind("<Button-5>",  lambda e: canvas.yview_scroll( 1,"units"))
            canvas.bind("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1,"units"))
            inner.bind("<Button-4>",   lambda e: canvas.yview_scroll(-1,"units"))
            inner.bind("<Button-5>",   lambda e: canvas.yview_scroll( 1,"units"))
            # Propaga scroll dai widget figli (righe cartelle)
            def _bind_rows_scroll(e=None):
                for child in inner.winfo_children():
                    child.bind("<Button-4>", lambda e: canvas.yview_scroll(-1,"units"))
                    child.bind("<Button-5>", lambda e: canvas.yview_scroll( 1,"units"))
                    for grandchild in child.winfo_children():
                        grandchild.bind("<Button-4>", lambda e: canvas.yview_scroll(-1,"units"))
                        grandchild.bind("<Button-5>", lambda e: canvas.yview_scroll( 1,"units"))
            inner.bind("<Configure>", _bind_rows_scroll, add=True)

            current_dir = [os.path.normpath(last_dir)]
            selected_dir = [os.path.normpath(last_dir)]

            def populate(d):
                if not os.path.isdir(d):
                    return
                d = os.path.normpath(d)
                current_dir[0] = d
                selected_dir[0] = d
                path_v.set(d)
                for w in inner.winfo_children():
                    w.destroy()

                # Riga ".."
                if d != "/":
                    parent = os.path.dirname(d)
                    row = tk.Frame(inner, bg=BG_COLOR, cursor="hand2")
                    row.pack(fill="x", padx=4, pady=1)
                    tk.Label(row, text="[>]", font=("TkFixedFont", 10),
                             bg=BG_COLOR, fg=MUTED_COLOR).pack(side="left", padx=(6,4))
                    tk.Label(row, text="..", font=("TkFixedFont", 9),
                             bg=BG_COLOR, fg=MUTED_COLOR).pack(side="left")
                    for w in (row,) + tuple(row.winfo_children()):
                        w.bind("<Double-Button-1>", lambda e, p=parent: populate(p))
                        w.bind("<Button-1>", lambda e, p=parent: select_row(p, row))

                # Sottocartelle
                try:
                    entries = sorted(
                        (e for e in os.scandir(d)
                         if e.is_dir() and not e.name.startswith(".")),
                        key=lambda e: e.name.lower())
                except OSError:
                    entries = []

                row_refs = {}
                for e in entries:
                    fpath = e.path
                    # Conta file
                    try:
                        n_files = sum(1 for f in os.scandir(fpath)
                                      if f.is_file())
                    except OSError:
                        n_files = 0

                    bg_row = BG_COLOR
                    row = tk.Frame(inner, bg=bg_row, cursor="hand2")
                    row.pack(fill="x", padx=4, pady=1)

                    tk.Label(row, text="[>]", font=("TkFixedFont", 10),
                             bg=bg_row, fg=HUD_CYAN).pack(side="left", padx=(6,4))
                    tk.Label(row, text=e.name, font=("TkFixedFont", 9, "bold"),
                             bg=bg_row, fg=TEXT_COLOR).pack(side="left")
                    if n_files:
                        tk.Label(row, text=f"  {n_files} file",
                                 font=("TkFixedFont", 7),
                                 bg=bg_row, fg=MUTED_COLOR).pack(side="left")
                    row_refs[fpath] = row

                    def _bind(row=row, fpath=fpath):
                        for w in [row] + list(row.winfo_children()):
                            w.bind("<Button-1>",
                                   lambda e, p=fpath, r=row: select_row(p, r))
                            w.bind("<Double-Button-1>",
                                   lambda e, p=fpath: populate(p))
                    _bind()

                canvas.yview_moveto(0)

            def select_row(fpath, row_widget):
                selected_dir[0] = fpath
                path_v.set(fpath)
                # Evidenzia riga selezionata
                for w in inner.winfo_children():
                    try:
                        w.config(bg=BG_COLOR)
                        for c in w.winfo_children():
                            c.config(bg=BG_COLOR)
                    except Exception:
                        pass
                try:
                    row_widget.config(bg=ACCENT_COLOR)
                    for c in row_widget.winfo_children():
                        c.config(bg=ACCENT_COLOR)
                except Exception:
                    pass

            def go_path(e=None):
                d = path_v.get().strip()
                if os.path.isdir(d):
                    populate(d)

            path_e.bind("<Return>", go_path)
            populate(last_dir)

            # ── Barra inferiore ────────────────────────────────────────────
            bot = tk.Frame(dlg, bg=PANEL_COLOR)
            bot.grid(row=2, column=0, columnspan=2, sticky="ew")
            dlg.rowconfigure(2, weight=0)

            def mkdir_action():
                base = selected_dir[0] or current_dir[0]
                name = simpledialog.askstring("Nuova cartella",
                    f"Nome della nuova cartella in:\n{base}",
                    parent=dlg)
                if not name:
                    return
                new_d = os.path.join(base, name)
                try:
                    os.makedirs(new_d, exist_ok=True)
                    populate(current_dir[0])
                    selected_dir[0] = new_d
                    path_v.set(new_d)
                except Exception as ex:
                    messagebox.showerror("Errore",
                        f"Impossibile creare:\n{ex}", parent=dlg)

            def confirm():
                chosen = selected_dir[0] or path_v.get().strip()
                if not chosen or not os.path.isdir(chosen):
                    chosen = current_dir[0]
                pvar.set(chosen)
                self.mode_vars[key].set("custom")
                entry.config(state="normal")
                # Auto-compila etichetta col nome cartella se è vuota
                if lvar is not None:
                    current_label = lvar.get().strip()
                    if not current_label or current_label == key:
                        lvar.set(os.path.basename(chosen) or chosen)
                self.config["last_browse_dir"] = chosen
                save_config(self.config)
                dlg.destroy()

            _ico_nf  = make_icon("new_folder", size=15, fg=(0,255,128), bg=(10,15,26))
            _ico_sel = make_icon("check",      size=15, fg=(0,200,255), bg=(10,26,42))
            _btn_nf = tk.Button(bot, text="  Nuova cartella", image=_ico_nf,
                      compound="left",
                      font=("TkFixedFont", 9), bg=BG_COLOR, fg=HUD_CYAN,
                      relief="flat", padx=10,
                      command=mkdir_action)
            _btn_nf._ico = _ico_nf
            _btn_nf.pack(side="left", padx=8, pady=8, ipady=4)
            tk.Label(bot, text="", bg=PANEL_COLOR).pack(side="left", expand=True)
            tk.Button(bot, text="Annulla",
                      font=("TkFixedFont", 9), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                      relief="flat", padx=10,
                      command=dlg.destroy).pack(side="right", padx=6, pady=8, ipady=4)
            _btn_sel = tk.Button(bot, text="  Seleziona", image=_ico_sel,
                      compound="left",
                      font=("TkFixedFont", 9, "bold"), bg=HUD_CYAN, fg="#0a1a2e",
                      relief="flat", padx=14,
                      command=confirm)
            _btn_sel._ico = _ico_sel
            _btn_sel.pack(side="right", padx=(0,8), pady=8, ipady=4)
            dlg.bind("<Return>", lambda e: confirm())
            dlg.bind("<Escape>", lambda e: dlg.destroy())

            # Centra sulla finestra impostazioni
            dlg.update_idletasks()
            pw, ph = 680, 500
            px = self.win.winfo_rootx() + (self.win.winfo_width()  - pw) // 2
            py = self.win.winfo_rooty() + (self.win.winfo_height() - ph) // 2
            dlg.geometry(f"{pw}x{ph}+{px}+{py}")
            dlg.deiconify()
            dlg.grab_set()


        self._browse_with_mkdir = _browse_with_mkdir_impl

        def clear(key=k, pvar=pv, entry=path_entry, lvar=lv):
            pvar.set("")
            lvar.set("")
            self.mode_vars[key].set("auto")
            entry.config(state="disabled")

        def update_placeholder(*_):
            if not self.mode_vars[k].get() == "custom" or not self.path_vars[k].get().strip():
                path_entry.config(state="disabled")
                if not pv.get():
                    # mostra hint
                    pass
            else:
                path_entry.config(state="normal")

        mv.trace_add("write", update_placeholder)
        pv.trace_add("write", update_placeholder)

        tk.Button(inner, text="...", font=("TkFixedFont", 8),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat",
                  activebackground=HIGHLIGHT,
                  command=browse).grid(row=ri, column=3, padx=2, pady=2, sticky="ew")
        tk.Button(inner, text="X", font=("TkFixedFont", 8),
                  bg="#c0392b", fg="white", relief="flat",
                  activebackground=HIGHLIGHT,
                  command=clear).grid(row=ri, column=4, padx=(2,6), pady=2, sticky="ew")

    def _build_view_tab(self):
        """Tab Visualizza: scegli quali tipi di file mostrare."""
        f = self._content
        f.columnconfigure(0, weight=1)

        tk.Label(f, text="Tipi di file da visualizzare",
                 font=("TkFixedFont", 11, "bold"),
                 bg=BG_COLOR, fg=HUD_CYAN).pack(padx=24, pady=(20,4), anchor="w")
        tk.Label(f, text="Le impostazioni vengono applicate al prossimo caricamento cartella.",
                 font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR).pack(padx=24, pady=(0,16), anchor="w")

        cfg = self.config
        entries = [
            ("show_images", "Immagini",
             ".jpg  .jpeg  .png  .gif  .bmp  .tiff  .webp"),
            ("show_videos", "Video",
             ".mp4  .mov  .avi  .mkv  .webm  .m4v  .flv  (richiede ffmpeg)"),
            ("show_pdfs",   "PDF",
             ".pdf  (richiede poppler-utils)"),
            ("show_no_ext", "File senza estensione",
             "rilevati automaticamente tramite magic bytes"),
        ]

        self._view_vars = {}

        def _make_toggle(parent, cfg_key, label, desc):
            val = cfg.get(cfg_key, True)
            var = tk.BooleanVar(value=val)
            self._view_vars[cfg_key] = var

            row = tk.Frame(parent, bg=ACCENT_COLOR)
            row.pack(fill="x", padx=20, pady=4)
            row.columnconfigure(2, weight=1)

            # Bottone ON/OFF visuale
            btn_frame = tk.Frame(row, bg=ACCENT_COLOR)
            btn_frame.grid(row=0, column=0, rowspan=2, padx=(10,8), pady=8)

            on_btn  = [None]
            off_btn = [None]

            def _toggle(new_val):
                var.set(new_val)
                _refresh_btns()
                self._apply_view_filter(cfg_key, var)

            def _refresh_btns():
                v = var.get()
                on_btn[0].config(
                    bg=SUCCESS if v else ACCENT_COLOR,
                    fg="white" if v else MUTED_COLOR,
                    relief="flat" if v else "flat")
                off_btn[0].config(
                    bg="#c0392b" if not v else ACCENT_COLOR,
                    fg="white" if not v else MUTED_COLOR)

            on_btn[0]  = tk.Button(btn_frame, text=" ON  ",
                                   font=("TkFixedFont", 8, "bold"),
                                   relief="flat", bd=0, padx=4, pady=2,
                                   command=lambda: _toggle(True))
            on_btn[0].pack(side="left")
            off_btn[0] = tk.Button(btn_frame, text=" OFF ",
                                   font=("TkFixedFont", 8, "bold"),
                                   relief="flat", bd=0, padx=4, pady=2,
                                   command=lambda: _toggle(False))
            off_btn[0].pack(side="left")
            _refresh_btns()

            tk.Label(row, text=label,
                     font=("TkFixedFont", 10, "bold"),
                     bg=ACCENT_COLOR, fg=TEXT_COLOR,
                     anchor="w").grid(row=0, column=2, sticky="w")
            tk.Label(row, text=desc,
                     font=("TkFixedFont", 8),
                     bg=ACCENT_COLOR, fg=MUTED_COLOR,
                     anchor="w").grid(row=1, column=2, sticky="w",
                                      padx=(0,10), pady=(0,8))

        for cfg_key, label, desc in entries:
            _make_toggle(f, cfg_key, label, desc)

        # Sezione estensioni personalizzate
        tk.Frame(f, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=20, pady=(16,8))
        tk.Label(f, text="Estensioni aggiuntive da includere (separate da virgola):",
                 font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR).pack(padx=24, anchor="w")

        extra_frame = tk.Frame(f, bg=BG_COLOR)
        extra_frame.pack(fill="x", padx=20, pady=4)
        extra_frame.columnconfigure(0, weight=1)

        extra_var = tk.StringVar(value=", ".join(sorted(cfg.get("extra_extensions", []))))
        extra_entry = tk.Entry(extra_frame, textvariable=extra_var,
                               font=("TkFixedFont", 9),
                               bg=ACCENT_COLOR, fg=TEXT_COLOR,
                               insertbackground=TEXT_COLOR,
                               relief="flat", bd=4)
        extra_entry.grid(row=0, column=0, sticky="ew", ipady=4)

        def save_extra(e=None):
            raw = extra_var.get()
            exts = [x.strip().lower() for x in raw.split(",") if x.strip()]
            exts = ["." + e if not e.startswith(".") else e for e in exts]
            cfg["extra_extensions"] = exts
            save_config(cfg)
            self._reload_sorter_list()

        tk.Button(extra_frame, text="Salva",
                  font=("TkFixedFont", 8), bg=SUCCESS, fg="white",
                  relief="flat", padx=8,
                  command=save_extra).grid(row=0, column=1, padx=(6,0), ipady=4)
        extra_entry.bind("<Return>", save_extra)

        tk.Label(f, text="Es: .heic, .arw, .cr2, .dng",
                 font=("TkFixedFont", 7),
                 bg=BG_COLOR, fg=MUTED_COLOR).pack(padx=24, pady=(2,0), anchor="w")

    def _apply_view_filter(self, cfg_key, var):
        """Salva la preferenza di visualizzazione e ricarica la lista."""
        self.config[cfg_key] = var.get()
        save_config(self.config)
        self._reload_sorter_list()

    def _reload_sorter_list(self):
        """Ricarica la lista immagini nel sorter applicando i filtri correnti."""
        if self.sorter.source_folder:
            self.sorter.images = self.sorter._load_images()
            self.sorter.current_index = min(
                self.sorter.current_index, max(0, len(self.sorter.images)-1))
            self.sorter._show_image()

    def _build_deck_tab(self):
        """Tab impostazioni Stream Deck: modello, luminosità, pagine idle."""
        lang = self.config.get("language", "it")
        f = self._content
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)

        sdk = getattr(self.sorter, '_stream_deck', None)
        connected = sdk and sdk.is_active()
        n_keys = sdk._deck_info.get("key_count", 15) if connected else 15
        cols   = sdk._deck_info.get("cols", 5)        if connected else 5

        # ── Barra superiore: stato + luminosità ──────────────────────────────
        top = tk.Frame(f, bg=PANEL_COLOR)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(2, weight=1)

        status_text = (f"Connesso: {sdk._deck_info.get('type','?')}  "
                       f"({n_keys} tasti)"
                       if connected else "Stream Deck non connesso")
        tk.Label(top, text=status_text,
                 font=("TkFixedFont", 9, "bold"),
                 bg=PANEL_COLOR,
                 fg=SUCCESS if connected else MUTED_COLOR
                 ).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        tk.Label(top, text="Luminosità:",
                 font=("TkFixedFont", 8), bg=PANEL_COLOR,
                 fg=MUTED_COLOR).grid(row=0, column=1, padx=(16,4))
        bright_var = tk.IntVar(value=self.config.get("deck_brightness", 70))
        tk.Scale(top, from_=10, to=100, orient="horizontal",
                 variable=bright_var, length=120, width=7,
                 bg=PANEL_COLOR, fg=HUD_CYAN, troughcolor=ACCENT_COLOR,
                 highlightthickness=0, bd=0, showvalue=False,
                 command=lambda v: self._apply_deck_brightness(int(float(v)))
                 ).grid(row=0, column=2, padx=4, sticky="w")
        # Checkbox riavvio StreamController alla chiusura
        restart_var = tk.BooleanVar(
            value=self.config.get("deck_restart_sc", True))
        def _save_restart(*_):
            self.config["deck_restart_sc"] = restart_var.get()
            save_config(self.config)
        tk.Checkbutton(top, text="Riavvia StreamController alla chiusura",
                       variable=restart_var,
                       font=("TkFixedFont", 8), bg=PANEL_COLOR,
                       fg=MUTED_COLOR, selectcolor=BG_COLOR,
                       activebackground=PANEL_COLOR, activeforeground=HUD_CYAN,
                       command=_save_restart
                       ).grid(row=0, column=3, padx=(20,12), sticky="e")
        top.columnconfigure(3, weight=1)

        f.rowconfigure(0, weight=0)
        f.rowconfigure(1, weight=1)
        # ── Area principale: griglia + editor ────────────────────────────────
        main = tk.Frame(f, bg=BG_COLOR)
        main.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=0)   # tab pagine
        main.rowconfigure(1, weight=0)   # griglia tasti
        main.rowconfigure(2, weight=1)   # editor

        # ── Tab pagine ────────────────────────────────────────────────────────
        pages = self.config.setdefault("deck_idle_pages", [])
        while len(pages) < 2:
            pages.append([None] * n_keys)

        page_tab_fr = tk.Frame(main, bg=PANEL_COLOR)
        page_tab_fr.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._deck_page_idx  = 0
        self._deck_page_btns = []
        self._deck_sel_key   = [None]   # [page_idx, key_idx] selezionato

        def _switch_page(pi, rebuild=True):
            self._deck_page_idx = pi
            self._deck_sel_key[0] = None
            for i, b in enumerate(self._deck_page_btns):
                b.config(bg=BG_COLOR if i == pi else PANEL_COLOR,
                         fg=HUD_CYAN if i == pi else MUTED_COLOR,
                         font=("TkFixedFont", 9, "bold") if i == pi
                              else ("TkFixedFont", 9))
            if rebuild:
                _rebuild_grid(pi)
                _clear_editor()

        def _add_page():
            pages.append([None] * n_keys)
            _rebuild_tabs()
            _switch_page(len(pages) - 1)

        def _rebuild_tabs():
            for w in page_tab_fr.winfo_children():
                w.destroy()
            self._deck_page_btns.clear()
            for pi in range(len(pages)):
                b = tk.Button(page_tab_fr, text=f"  Pag.{pi+1}  ",
                              font=("TkFixedFont", 9), relief="flat", bd=0,
                              padx=4, pady=6,
                              command=lambda p=pi: _switch_page(p))
                b.pack(side="left")
                self._deck_page_btns.append(b)
            tk.Button(page_tab_fr, text="+ Pag.",
                      font=("TkFixedFont", 8), bg=PANEL_COLOR, fg=MUTED_COLOR,
                      relief="flat", padx=6,
                      command=_add_page).pack(side="left", padx=6)
            tk.Label(page_tab_fr, text="Modalità attuale:",
                     font=("TkFixedFont", 7), bg=PANEL_COLOR,
                     fg=MUTED_COLOR).pack(side="right", padx=4)
            mode_txt = "preset" if (connected and sdk._mode == "preset") else "idle"
            mode_col = SUCCESS if mode_txt == "preset" else HUD_CYAN
            tk.Label(page_tab_fr, text=mode_txt.upper(),
                     font=("TkFixedFont", 8, "bold"), bg=PANEL_COLOR,
                     fg=mode_col).pack(side="right", padx=(0,8))

        # ── Griglia tasti ─────────────────────────────────────────────────────
        grid_outer = tk.Frame(main, bg=BG_COLOR)
        grid_outer.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        grid_outer.columnconfigure(0, weight=1)
        grid_outer.rowconfigure(0, weight=1)
        grid_fr = tk.Frame(grid_outer, bg=BG_COLOR)
        grid_fr.grid(row=0, column=0, sticky="nw")

        def _rebuild_grid(pi):
            for w in grid_fr.winfo_children():
                w.destroy()
            page = pages[pi]
            while len(page) < n_keys:
                page.append(None)
            # Altezza righe uniforme
            rows_count = (n_keys + cols - 1) // cols
            for ri in range(rows_count):
                grid_fr.rowconfigure(ri, weight=1, uniform="deck_row", minsize=74)
            for ci in range(cols):
                grid_fr.columnconfigure(ci, weight=1, uniform="deck_col", minsize=80)
            for ki in range(n_keys):
                r, c = divmod(ki, cols)
                slot = page[ki] or {}
                is_nav = False   # tutti i tasti sono liberamente configurabili
                label  = slot.get("label", "")
                color  = tuple(slot.get("color", [15,20,40]))
                bg_hex = "#{:02x}{:02x}{:02x}".format(*[
                    max(0,min(255,int(x))) for x in color])
                sel = (self._deck_sel_key[0] == ki)
                border_col = HUD_CYAN if sel else (PANEL_COLOR if label else ACCENT_COLOR)

                cell = tk.Frame(grid_fr, bg=border_col,
                                width=76, height=70)
                cell.grid(row=r, column=c, padx=2, pady=2)
                cell.grid_propagate(False)

                inner = tk.Frame(cell, bg=bg_hex)
                inner.place(x=2, y=2, width=72, height=66)

                # Immagine miniatura
                img_path = slot.get("image")
                if img_path and os.path.isfile(img_path) and not is_nav:
                    try:
                        thumb = load_thumbnail(img_path, 46)
                        if thumb:
                            photo = ImageTk.PhotoImage(thumb)
                            self._deck_idle_imgs = getattr(
                                self, "_deck_idle_imgs", [])
                            self._deck_idle_imgs.append(photo)
                            tk.Label(inner, image=photo,
                                     bg=bg_hex).pack(pady=(4,0))
                    except Exception:
                        tk.Frame(inner, bg=bg_hex, height=32).pack(fill="x")
                else:
                    # Icona azione
                    if is_nav:
                        nav_txt = ("< Pag" if ki == n_keys-2
                                   else f"> {pi+1}/{len(pages)}")
                        tk.Label(inner, text=nav_txt,
                                 font=("TkFixedFont", 7), bg=bg_hex,
                                 fg=MUTED_COLOR).pack(expand=True)
                    else:
                        # Prova icona da file, fallback etichetta testo
                        icon_img = get_deck_icon(slot.get("action",""), size=36)
                        if icon_img and not img_path:
                            try:
                                icon_photo = ImageTk.PhotoImage(icon_img)
                                self._deck_idle_imgs = getattr(
                                    self,"_deck_idle_imgs",[])
                                self._deck_idle_imgs.append(icon_photo)
                                tk.Label(inner, image=icon_photo,
                                         bg=bg_hex).pack(pady=(4,0))
                            except Exception:
                                pass

                lbl_txt = (label[:9]+"…") if len(label)>9 else (label or "—")
                lbl_col = TEXT_COLOR if label else MUTED_COLOR
                tk.Label(inner, text=lbl_txt,
                         font=("TkFixedFont", 7, "bold" if label else ""),
                         bg=bg_hex, fg=lbl_col).pack()

                if not is_nav:
                    for w in [cell, inner] + inner.winfo_children():
                        w.bind("<Button-1>",
                               lambda e, p=pi, k=ki: _select_key(p, k))

        def _select_key(pi, ki):
            self._deck_sel_key[0] = ki
            _rebuild_grid(pi)
            _show_editor(pi, ki)

        # ── Editor inline ─────────────────────────────────────────────────────
        editor_fr = tk.Frame(main, bg=BG_COLOR)
        editor_fr.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        editor_fr.columnconfigure(1, weight=1)

        def _clear_editor():
            for w in editor_fr.winfo_children():
                w.destroy()
            tk.Label(editor_fr,
                     text="Clicca un tasto qui sopra per configurarlo",
                     font=("TkFixedFont", 9), bg=BG_COLOR,
                     fg=MUTED_COLOR).pack(pady=20)
            # Rimuovi bottoni deck dalla barra globale
            if hasattr(self, '_bot_left'):
                for w in self._bot_left.winfo_children():
                    w.destroy()

        # Descrizioni chiare per ogni azione

        def _show_editor(pi, ki):
            for w in editor_fr.winfo_children():
                w.destroy()
            page = pages[pi]
            while len(page) <= ki:
                page.append(None)
            slot = page[ki] or {}

            # Titolo
            tk.Label(editor_fr,
                     text=f"Tasto {ki+1}  —  Pagina {pi+1}",
                     font=("TkFixedFont", 9, "bold"),
                     bg=BG_COLOR, fg=HUD_CYAN,
                     anchor="w").grid(row=0, column=0, columnspan=3,
                                      sticky="w", pady=(0,6))

            vars_ = {}
            editor_fr.columnconfigure(1, weight=1)

            def _field_row(r, label, widget_fn):
                tk.Label(editor_fr, text=label,
                         font=("TkFixedFont", 8), bg=BG_COLOR,
                         fg=MUTED_COLOR, anchor="w", width=12
                         ).grid(row=r, column=0, sticky="w", pady=2, padx=(0,4))
                w = widget_fn(r)
                return w

            # ── Label ────────────────────────────────────────────────────────
            label_var = tk.StringVar(value=slot.get("label", ""))
            vars_["label"] = label_var
            def _mk_label(r):
                e = tk.Entry(editor_fr, textvariable=label_var,
                             font=("TkFixedFont", 9),
                             bg=ACCENT_COLOR, fg=TEXT_COLOR,
                             insertbackground=TEXT_COLOR,
                             relief="flat", bd=3)
                e.grid(row=r, column=1, columnspan=2, sticky="ew", ipady=3)
                return e
            _field_row(1, "Label:", _mk_label)

            # ── Image ────────────────────────────────────────────────────────
            img_var = tk.StringVar(value=slot.get("image", "") or "")
            vars_["image"] = img_var
            def _mk_image(r):
                fr = tk.Frame(editor_fr, bg=BG_COLOR)
                fr.grid(row=r, column=1, columnspan=2, sticky="ew")
                fr.columnconfigure(0, weight=1)
                tk.Entry(fr, textvariable=img_var,
                         font=("TkFixedFont", 8),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=3
                         ).grid(row=0, column=0, sticky="ew", ipady=2)
                tk.Button(fr, text="...",
                          font=("TkFixedFont", 8), bg=PANEL_COLOR, fg=TEXT_COLOR,
                          relief="flat", padx=6,
                          command=lambda: img_var.set(
                              filedialog.askopenfilename(
                                  parent=self.win,
                                  initialdir=(os.path.dirname(img_var.get())
                                              if img_var.get() else SORTER_ICONS_DIR),
                                  filetypes=[("Immagini","*.png *.jpg *.jpeg *.gif *.bmp *.webp")])
                              or img_var.get())
                          ).grid(row=0, column=1, padx=(4,0), ipady=2)
                tk.Button(fr, text="x",
                          font=("TkFixedFont", 8), bg=PANEL_COLOR, fg=MUTED_COLOR,
                          relief="flat", command=lambda: img_var.set("")
                          ).grid(row=0, column=2, padx=(2,0), ipady=2)
                return fr
            _field_row(2, "Image:", _mk_image)

            # ── Colore ───────────────────────────────────────────────────────
            color_val = slot.get("color", [15, 20, 40])
            color_var = tk.StringVar(value=",".join(str(x) for x in color_val))
            vars_["color"] = color_var
            def _mk_color(r):
                fr = tk.Frame(editor_fr, bg=BG_COLOR)
                fr.grid(row=r, column=1, columnspan=2, sticky="ew")
                tk.Entry(fr, textvariable=color_var,
                         font=("TkFixedFont", 9), width=12,
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=3
                         ).pack(side="left", ipady=3)
                tk.Label(fr, text="  (0-255 per R,G,B)",
                         font=("TkFixedFont", 7), bg=BG_COLOR,
                         fg=MUTED_COLOR).pack(side="left")
                return fr
            _field_row(3, "Colore R,G,B:", _mk_color)

            # Separatore
            tk.Frame(editor_fr, bg=ACCENT_COLOR, height=1
                     ).grid(row=4, column=0, columnspan=3, sticky="ew", pady=4)

            # ── Azione ───────────────────────────────────────────────────────
            tk.Label(editor_fr, text="Azione:",
                     font=("TkFixedFont", 8), bg=BG_COLOR,
                     fg=MUTED_COLOR, anchor="w", width=12
                     ).grid(row=5, column=0, sticky="w", pady=2, padx=(0,4))

            ACTION_ROWS = [
                # (action_key, label_display, param_label, param_hint, param_type)
                ("folder",  "Apri cartella",           "Percorso:", "/home/user/Documenti", "folder"),
                ("app",     "Apri applicazione",       "Comando:",  "gimp  /  firefox",     "entry"),
                ("hotkey",  "Scorciatoia tastiera",    "Tasto:",    "ctrl+c  ctrl+alt+t",   "entry"),
                ("url",     "Apri URL",                "URL:",      "https://www.esempio.it","entry"),
                ("mute",    "Muto/smuto audio",        "",          "",                      "none"),
                ("sorter",  "Image Sorter su cartella","Cartella:", "/home/user/Foto",       "folder"),
                ("page",    "Cambia pagina",           "N. pagina:","1  (numero pagina)",    "entry"),
                ("text",    "Scrivi testo",            "Testo:",    "testo da digitare",     "text_area"),
            ]
            action_keys  = [a[0] for a in ACTION_ROWS]
            action_names = {a[0]: a[1] for a in ACTION_ROWS}
            action_map   = {a[0]: a for a in ACTION_ROWS}

            cur_action = slot.get("action", "folder")
            action_var = tk.StringVar(value=cur_action)

            # Radio buttons per azione
            radio_fr = tk.Frame(editor_fr, bg=BG_COLOR)
            radio_fr.grid(row=5, column=1, columnspan=2, sticky="ew")
            for ai, (akey, alabel, *_) in enumerate(ACTION_ROWS):
                rb = tk.Radiobutton(radio_fr, text=alabel,
                                    variable=action_var, value=akey,
                                    font=("TkFixedFont", 8),
                                    bg=BG_COLOR, fg=TEXT_COLOR,
                                    selectcolor=BG_COLOR,
                                    activebackground=BG_COLOR,
                                    activeforeground=HUD_CYAN,
                                    command=lambda: _update_param_row())
                rb.grid(row=ai//2, column=ai%2, sticky="w", padx=4, pady=1)

            # ── Parametro dinamico ───────────────────────────────────────────
            param_var  = tk.StringVar(value=slot.get("param", ""))
            param_fr   = tk.Frame(editor_fr, bg=BG_COLOR)
            param_fr.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(4,0))
            param_fr.columnconfigure(1, weight=1)
            vars_["param"] = param_var
            _param_widgets = [None]  # riferimento al widget corrente

            def _update_param_row():
                for w in param_fr.winfo_children():
                    w.destroy()
                akey = action_var.get()
                if akey not in action_map:
                    return
                _, _, plabel, phint, ptype = action_map[akey]
                if ptype == "none":
                    tk.Label(param_fr, text="(nessun parametro richiesto)",
                             font=("TkFixedFont", 7), bg=BG_COLOR,
                             fg=MUTED_COLOR).grid(row=0, column=0,
                                                  columnspan=3, sticky="w")
                    return
                tk.Label(param_fr, text=plabel,
                         font=("TkFixedFont", 8), bg=BG_COLOR,
                         fg=MUTED_COLOR, anchor="w", width=12
                         ).grid(row=0, column=0, sticky="w", padx=(0,4))
                if ptype == "text_area":
                    txt = tk.Text(param_fr, font=("TkFixedFont", 9),
                                  bg=ACCENT_COLOR, fg=TEXT_COLOR,
                                  insertbackground=TEXT_COLOR,
                                  relief="flat", bd=3, height=4, width=28)
                    txt.grid(row=0, column=1, columnspan=2, sticky="ew")
                    txt.insert("1.0", param_var.get())
                    txt.bind("<Button-4>", lambda e: txt.yview_scroll(-1, "units"))
                    txt.bind("<Button-5>", lambda e: txt.yview_scroll(1, "units"))
                    # Aggiorna param_var in tempo reale
                    txt.bind("<KeyRelease>",
                             lambda e: param_var.set(txt.get("1.0", "end-1c")))
                    _param_widgets[0] = txt
                else:
                    pf = tk.Frame(param_fr, bg=BG_COLOR)
                    pf.grid(row=0, column=1, columnspan=2, sticky="ew")
                    pf.columnconfigure(0, weight=1)
                    e = tk.Entry(pf, textvariable=param_var,
                                 font=("TkFixedFont", 9),
                                 bg=ACCENT_COLOR, fg=TEXT_COLOR,
                                 insertbackground=TEXT_COLOR,
                                 relief="flat", bd=3)
                    e.grid(row=0, column=0, sticky="ew", ipady=3)
                    e.bind("<Return>", lambda ev: _save_key())
                    if ptype in ("folder",):
                        def _br():
                            d = browse_folder_hud(self.win,
                                title="Scegli cartella",
                                initial_dir=param_var.get() or os.path.expanduser("~"),
                                config=self.config)
                            if d: param_var.set(d)
                        tk.Button(pf, text="...",
                                  font=("TkFixedFont", 8), bg=PANEL_COLOR,
                                  fg=TEXT_COLOR, relief="flat", padx=6,
                                  command=_br
                                  ).grid(row=0, column=1, padx=(4,0), ipady=3)
                    if phint:
                        tk.Label(param_fr, text="Es: " + phint,
                                 font=("TkFixedFont", 7), bg=BG_COLOR,
                                 fg=MUTED_COLOR
                                 ).grid(row=1, column=1, columnspan=2,
                                        sticky="w", pady=(1,0))
                    _param_widgets[0] = e

            _update_param_row()

            # Separatore
            tk.Frame(editor_fr, bg=ACCENT_COLOR, height=1
                     ).grid(row=7, column=0, columnspan=3, sticky="ew", pady=6)

            # ── Bottoni nella barra globale in basso ─────────────────────
            def _save_key():
                try:
                    raw = [max(0, min(255, int(x.strip())))
                           for x in color_var.get().split(",")]
                    if len(raw) != 3:
                        raise ValueError
                except ValueError:
                    raw = [15, 20, 40]
                page[ki] = {
                    "label":  label_var.get().strip(),
                    "action": action_var.get(),
                    "param":  param_var.get().strip(),
                    "color":  raw,
                    "image":  img_var.get().strip() or None,
                }
                save_config(self.config)
                if connected:
                    sdk.refresh_all()
                _rebuild_grid(pi)

            def _clear_key():
                page[ki] = None
                save_config(self.config)
                if connected:
                    sdk.refresh_all()
                _clear_editor()
                _rebuild_grid(pi)

            # Aggiorna _bot_left con i bottoni contestuali
            for w in self._bot_left.winfo_children():
                w.destroy()
            tk.Button(self._bot_left, text="  Salva tasto  ",
                      font=("TkFixedFont", 9, "bold"),
                      bg=SUCCESS, fg="white", relief="flat", padx=10,
                      command=_save_key).pack(side="left", padx=(10,4),
                                              pady=6, ipady=3)
            tk.Button(self._bot_left, text="Svuota",
                      font=("TkFixedFont", 9),
                      bg=WARNING, fg="white", relief="flat", padx=8,
                      command=_clear_key).pack(side="left", padx=(0,4),
                                               pady=6, ipady=3)
            tk.Button(self._bot_left, text="Annulla",
                      font=("TkFixedFont", 9),
                      bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=8,
                      command=_clear_editor).pack(side="left", pady=6, ipady=3)

        _rebuild_tabs()
        _switch_page(0)
        _clear_editor()

    def _apply_deck_brightness(self, val):
        self.config["deck_brightness"] = val
        save_config(self.config)
        sdk = getattr(self.sorter, '_stream_deck', None)
        if sdk and sdk.is_active():
            try: sdk.deck.set_brightness(val)
            except Exception: pass

    def _edit_idle_key(self, page_idx, key_idx):
        """Apre il popup di configurazione per un tasto idle."""
        pages  = self.config.setdefault("deck_idle_pages", [])
        while len(pages) <= page_idx:
            pages.append([])
        page = pages[page_idx]
        while len(page) <= key_idx:
            page.append(None)

        slot = page[key_idx] or {}

        win = tk.Toplevel(self.win)
        win.withdraw()
        win.title(f"Tasto {key_idx+1} — Pagina {page_idx+1}")
        win.configure(bg=BG_COLOR)
        win.resizable(False, False)
        win.transient(self.win)
        hud_apply(win)

        frm = tk.Frame(win, bg=BG_COLOR)
        frm.pack(padx=16, pady=12, fill="x")
        frm.columnconfigure(1, weight=1)

        # Etichetta
        tk.Label(frm, text="Etichetta:", font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR).grid(row=0, column=0, sticky="w", pady=4)
        label_var = tk.StringVar(value=slot.get("label", ""))
        tk.Entry(frm, textvariable=label_var, font=("TkFixedFont", 9),
                 bg=ACCENT_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR,
                 relief="flat", bd=3).grid(row=0, column=1, sticky="ew", ipady=3)

        # Azione
        tk.Label(frm, text="Azione:", font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR).grid(row=1, column=0, sticky="w", pady=4)
        action_var = tk.StringVar(value=slot.get("action", "folder"))
        action_frame = tk.Frame(frm, bg=BG_COLOR)
        action_frame.grid(row=1, column=1, sticky="ew")
        action_menu = ttk.Combobox(action_frame, textvariable=action_var,
                                   values=[k for k,v in IDLE_ACTION_TYPES],
                                   state="readonly", width=16)
        action_menu.pack(side="left")
        # Mostra nome descrittivo
        desc_lbl = tk.Label(action_frame, text="",
                            font=("TkFixedFont", 7), bg=BG_COLOR, fg=MUTED_COLOR)
        desc_lbl.pack(side="left", padx=6)
        def _upd_desc(*_):
            desc_lbl.config(text=IDLE_ACTION_LABELS.get(action_var.get(), ""))
        action_var.trace_add("write", _upd_desc)
        _upd_desc()

        # Parametro
        tk.Label(frm, text="Parametro:", font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR).grid(row=2, column=0, sticky="w", pady=4)
        param_var = tk.StringVar(value=slot.get("param", ""))
        param_fr = tk.Frame(frm, bg=BG_COLOR)
        param_fr.grid(row=2, column=1, sticky="ew")
        param_fr.columnconfigure(0, weight=1)
        tk.Entry(param_fr, textvariable=param_var, font=("TkFixedFont", 9),
                 bg=ACCENT_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR,
                 relief="flat", bd=3).grid(row=0, column=0, sticky="ew", ipady=3)
        def _browse_param():
            a = action_var.get()
            if a in ("folder", "sorter"):
                d = browse_folder_hud(win, title="Scegli cartella",
                    initial_dir=param_var.get() or os.path.expanduser("~"),
                    config=self.config)
                if d: param_var.set(d)
            elif a in ("app",):
                f = filedialog.askopenfilename(parent=win)
                if f: param_var.set(f)
        tk.Button(param_fr, text="...",
                  font=("TkFixedFont", 8), bg=PANEL_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=6,
                  command=_browse_param).grid(row=0, column=1, padx=(4,0), ipady=3)

        # Immagine sfondo tasto
        tk.Label(frm, text="Immagine tasto:", font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR).grid(row=3, column=0, sticky="w", pady=4)
        img_var = tk.StringVar(value=slot.get("image", "") or "")
        img_fr = tk.Frame(frm, bg=BG_COLOR)
        img_fr.grid(row=3, column=1, sticky="ew")
        img_fr.columnconfigure(0, weight=1)
        tk.Entry(img_fr, textvariable=img_var, font=("TkFixedFont", 8),
                 bg=ACCENT_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR,
                 relief="flat", bd=3).grid(row=0, column=0, sticky="ew", ipady=2)
        def _browse_img():
            f = filedialog.askopenfilename(parent=win,
                filetypes=[("Immagini","*.png *.jpg *.jpeg *.gif *.bmp *.webp")])
            if f: img_var.set(f)
        tk.Button(img_fr, text="...", font=("TkFixedFont", 8),
                  bg=PANEL_COLOR, fg=TEXT_COLOR, relief="flat", padx=6,
                  command=_browse_img).grid(row=0, column=1, padx=(4,0), ipady=2)
        tk.Button(img_fr, text="x", font=("TkFixedFont", 8),
                  bg=PANEL_COLOR, fg=MUTED_COLOR, relief="flat",
                  command=lambda: img_var.set("")
                  ).grid(row=0, column=2, padx=(2,0), ipady=2)

        # Colore sfondo
        tk.Label(frm, text="Colore (R,G,B):", font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR).grid(row=4, column=0, sticky="w", pady=4)
        color_val = slot.get("color", [15,20,40])
        color_var = tk.StringVar(value=",".join(str(x) for x in color_val))
        tk.Entry(frm, textvariable=color_var, font=("TkFixedFont", 9),
                 bg=ACCENT_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR,
                 relief="flat", bd=3, width=14).grid(row=4, column=1, sticky="w", ipady=3)

        msg = tk.Label(win, text="", font=("TkFixedFont", 8), bg=BG_COLOR, fg=HIGHLIGHT)
        msg.pack(padx=16)

        def _save():
            try:
                raw_color = [max(0,min(255,int(x.strip())))
                             for x in color_var.get().split(",")]
                if len(raw_color) != 3:
                    raise ValueError
            except ValueError:
                raw_color = [15,20,40]
            page[key_idx] = {
                "label":  label_var.get().strip(),
                "action": action_var.get(),
                "param":  param_var.get().strip(),
                "color":  raw_color,
                "image":  img_var.get().strip() or None,
            }
            save_config(self.config)
            win.destroy()
            self._build_deck_tab()   # aggiorna la griglia

        def _clear():
            page[key_idx] = None
            save_config(self.config)
            win.destroy()
            self._build_deck_tab()

        bf = tk.Frame(win, bg=BG_COLOR)
        bf.pack(padx=16, pady=(4,14))
        tk.Button(bf, text="Salva", font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=12,
                  command=_save).pack(side="left", padx=(0,8), ipady=4)
        tk.Button(bf, text="Svuota tasto", font=("TkFixedFont", 9),
                  bg=WARNING, fg="white", relief="flat", padx=8,
                  command=_clear).pack(side="left", padx=(0,8), ipady=4)
        tk.Button(bf, text="Annulla", font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=8,
                  command=win.destroy).pack(side="left", ipady=4)
        win.bind("<Return>", lambda e: _save())
        win.bind("<Escape>", lambda e: win.destroy())

        win.update_idletasks()
        pw, ph = win.winfo_reqwidth(), win.winfo_reqheight()
        px = self.win.winfo_rootx() + (self.win.winfo_width()  - pw) // 2
        py = self.win.winfo_rooty() + (self.win.winfo_height() - ph) // 2
        win.geometry(f"+{max(0,px)}+{max(0,py)}")
        win.deiconify()
        win.grab_set()

    def _build_keys_tab(self):
        """Tab scorciatoie da tastiera."""
        lang = self.config.get("language", "it")
        f = self._content
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        outer = tk.Frame(f, bg=BG_COLOR)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=BG_COLOR, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        inner = tk.Frame(canvas, bg=BG_COLOR)
        iid = canvas.create_window((0,0), window=inner, anchor="nw")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(iid, width=e.width))
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        def _scroll_up(e): canvas.yview_scroll(-1, "units")
        def _scroll_dn(e): canvas.yview_scroll( 1, "units")
        # Bind su canvas E su inner (e tutti i figli tramite bind_all temporaneo)
        canvas.bind("<Button-4>", _scroll_up)
        canvas.bind("<Button-5>", _scroll_dn)
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        inner.bind("<Button-4>", _scroll_up)
        inner.bind("<Button-5>", _scroll_dn)
        # Propaga scroll dai widget figli che verranno creati
        def _bind_scroll_to_children(widget):
            widget.bind("<Button-4>", _scroll_up)
            widget.bind("<Button-5>", _scroll_dn)
        # Chiama dopo che i widget sono stati creati
        inner.bind("<Configure>",
                   lambda e: [_bind_scroll_to_children(w)
                               for w in inner.winfo_children()
                               for w in [w] + list(w.winfo_children())],
                   add=True)

        shortcuts = (_SHORTCUTS_DATA or {}).get(lang,
                     (_SHORTCUTS_DATA or {}).get("it", []))

        for section, pairs in shortcuts:
            tk.Label(inner, text=section,
                     font=("TkFixedFont", 10, "bold"),
                     bg=BG_COLOR, fg=HUD_CYAN,
                     anchor="w").pack(fill="x", padx=20, pady=(14,2))
            tk.Frame(inner, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=20)
            for key, desc in pairs:
                row = tk.Frame(inner, bg=BG_COLOR)
                row.pack(fill="x", padx=20, pady=1)
                tk.Label(row, text=key,
                         font=("TkFixedFont", 9, "bold"),
                         bg=BG_COLOR, fg=TEXT_COLOR,
                         width=22, anchor="w").pack(side="left")
                tk.Label(row, text=desc,
                         font=("TkFixedFont", 9),
                         bg=BG_COLOR, fg=MUTED_COLOR,
                         anchor="w").pack(side="left")

    def _apply_lang(self):
        """Salva la lingua scelta nel config."""
        lang = self._lang_var.get()
        self.config["language"] = lang
        save_config(self.config)

    def _build_info_tab(self):
        """Tab Info: lingua + about."""
        lang = self.config.get("language", "it")
        f = self._content
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)

        outer = tk.Frame(f, bg=BG_COLOR)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=BG_COLOR, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        inner = tk.Frame(canvas, bg=BG_COLOR)
        iid = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(iid, width=e.width))
        def _update_scroll(e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Disabilita scroll se il contenuto non supera il canvas
            ch = inner.winfo_reqheight()
            cv = canvas.winfo_height()
            if ch <= cv:
                canvas.yview_moveto(0)
        inner.bind("<Configure>", lambda e: _update_scroll())
        canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>", lambda e: canvas.yview_scroll( 1, "units"))
        inner.bind("<Button-4>",  lambda e: canvas.yview_scroll(-1, "units"))
        inner.bind("<Button-5>",  lambda e: canvas.yview_scroll( 1, "units"))

        try:
            self._build_info_content(inner, lang)
        except Exception as _e:
            import traceback as _tb
            err = _tb.format_exc()
            import datetime
            with open(os.path.join(SCRIPT_DIR, "image_sorter_error.log"), "a") as _f:
                _f.write(f"\n[INFO TAB] {datetime.datetime.now()}\n{err}")
            tk.Label(inner, text=f"Errore: {_e}",
                     font=("TkFixedFont", 9), bg=BG_COLOR, fg=HIGHLIGHT
                     ).pack(padx=20, pady=20)

    def _build_info_content(self, inner, lang):
        """Contenuto del tab Info."""
        # Lingua
        tk.Label(inner, text="Lingua / Language",
                 font=("TkFixedFont", 10, "bold"),
                 bg=BG_COLOR, fg=HUD_CYAN
                 ).pack(padx=24, pady=(16, 4), anchor="w")

        fr_lang = tk.Frame(inner, bg=BG_COLOR)
        fr_lang.pack(padx=32, anchor="w")
        available  = list((_LANG_DATA or {}).keys()) if _LANG_DATA else ["it"]
        lang_names = {"it": "Italiano", "en": "English"}
        self._lang_var = tk.StringVar(value=lang)
        for code in available:
            tk.Radiobutton(fr_lang,
                           text=lang_names.get(code, code.upper()),
                           variable=self._lang_var, value=code,
                           font=("TkFixedFont", 10),
                           bg=BG_COLOR, fg=TEXT_COLOR,
                           selectcolor=BG_COLOR,
                           activebackground=BG_COLOR,
                           activeforeground=HUD_CYAN,
                           command=self._apply_lang
                           ).pack(side="left", padx=8, pady=2)

        tk.Label(inner, text=T("lang_restart", lang),
                 font=("TkFixedFont", 7), bg=BG_COLOR, fg=WARNING
                 ).pack(padx=24, pady=(2, 0), anchor="w")

        tk.Frame(inner, bg=ACCENT_COLOR, height=1
                 ).pack(fill="x", padx=20, pady=(14, 10))

        # Logo
        icon_path = os.path.join(SORTER_ICONS_DIR, "image_sorter_icon.png")
        try:
            from PIL import Image, ImageTk as _ITk
            _img = Image.open(icon_path).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
            _ph  = _ITk.PhotoImage(_img, master=inner)
            lbl  = tk.Label(inner, image=_ph, bg=BG_COLOR)
            lbl.image = _ph
            lbl.pack(pady=(0, 6))
        except Exception:
            pass

        # About
        for text, fnt, col in [
            ("Un programma per gestione immagini e file", ("TkFixedFont", 9),        MUTED_COLOR),
            ("IMAGE SORTER",                              ("TkFixedFont", 16, "bold"), HUD_CYAN),
            ("Ver. 1.12",                                 ("TkFixedFont", 10),        TEXT_COLOR),
            ("Creative Commons By Carlo Porrone — 2026", ("TkFixedFont", 9),   MUTED_COLOR),
            ("greencarlo@gmail.com",                      ("TkFixedFont", 9),        "#4a9eff"),
            ("Questo programma non fornisce nessuna garanzia di utilizzo",
             ("TkFixedFont", 8),                                                     MUTED_COLOR),
        ]:
            tk.Label(inner, text=text, font=fnt, bg=BG_COLOR, fg=col
                     ).pack(pady=2)

        tk.Frame(inner, bg=ACCENT_COLOR, height=1
                 ).pack(fill="x", padx=20, pady=(12, 8))

        # Manuali
        fr_rm = tk.Frame(inner, bg=BG_COLOR)
        fr_rm.pack(padx=24, anchor="w", pady=(0, 16))
        for fname, rpath in [
            ("LEGGIMI.txt",   os.path.join(SCRIPT_DIR, "LEGGIMI.txt")),
            ("README_en.txt", os.path.join(SCRIPT_DIR, "README_en.txt")),
        ]:
            if os.path.isfile(rpath):
                tk.Button(fr_rm, text="Apri " + fname,
                          font=("TkFixedFont", 8),
                          bg=ACCENT_COLOR, fg=TEXT_COLOR,
                          relief="flat", padx=8,
                          command=lambda p=rpath: subprocess.Popen(
                              ["xdg-open", p],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
                          ).pack(side="left", padx=4, ipady=2)

    def _apply_dest(self):
        preset_name = self._dest_preset_var.get()
        old_slots   = self.config["presets"][preset_name]
        new_slots   = {}

        for k in KEYS:
            raw_label = sanitize_name(self.label_vars[k].get())
            raw_path_for_label = self.path_vars[k].get().strip()
            # Auto-etichetta: se vuota usa nome cartella
            if not raw_label and raw_path_for_label:
                raw_label = os.path.basename(raw_path_for_label) or f"Cartella_{k}"
            elif not raw_label:
                raw_label = ""   # etichetta vuota = slot non configurato
            raw_path  = self.path_vars[k].get().strip()
            mode      = self.mode_vars[k].get()
            new_path  = raw_path if (mode == "custom" and raw_path and os.path.isabs(raw_path)) else ""
            new_slots[k] = {"label": raw_label, "path": new_path}

            if preset_name == self.config["active_preset"] and not new_path:
                old_path = resolve_path(old_slots[k])
                new_resolved = os.path.join(BASE_DEST, raw_label)
                if old_path != new_resolved and os.path.isdir(old_path) and old_path.startswith(BASE_DEST):
                    try:
                        os.rename(old_path, new_resolved)
                    except Exception as ex:
                        messagebox.showerror("Errore rinomina",
                                             f"Impossibile rinominare:\n{ex}", parent=self.win)
                        return

        self.config["presets"][preset_name] = new_slots
        save_config(self.config)

        # Aggiorna le variabili tkinter con i valori effettivamente salvati
        # così _dest_has_unsaved_changes() non rileva false differenze
        for k in KEYS:
            if k in self.label_vars:
                self.label_vars[k].set(new_slots[k].get("label", ""))
            if k in self.path_vars:
                self.path_vars[k].set(new_slots[k].get("path", ""))

        if preset_name == self.config["active_preset"]:
            self.sorter.labels = copy.deepcopy(new_slots)
            for k in KEYS:
                rp = resolve_path(new_slots[k])
                try:
                    if rp:
                        os.makedirs(rp, exist_ok=True)
                except Exception as _mk_err:
                    messagebox.showwarning(
                        "Avviso percorso",
                        f"Impossibile creare cartella tasto {k}:\n{_mk_err}",
                        parent=self.win)
            self.sorter._build_sidebar()
            if self.sorter.keypad_popup:
                self.sorter.keypad_popup.refresh_labels()

        messagebox.showinfo("Salvato", "Configurazione salvata.", parent=self.win)

# =============================================================================
# APPLICAZIONE PRINCIPALE
# =============================================================================

class ImageSorter:
    _all_instances = []   # registro globale istanze attive

    def __init__(self, root, source_folder, start_file=None):
        self.root          = root
        self.source_folder = source_folder
        self.config        = load_config()
        self.history       = []
        ImageSorter._all_instances.append(self)
        self.skipped       = []
        self.current_index = 0
        self.moved_count   = 0
        self.keypad_popup       = None
        self.badge_labels       = {}
        self.folder_name_labels = {}
        self._fullscreen        = False
        self._zoom_factor       = 1.0
        self._total_images     = 0
        self._view_pos         = 0
        self._crop_overlay      = None
        self._pdf_page          = {}   # {filepath: current_page}
        self._pdf_panel         = None  # pannello miniature laterale
        self._pdf_thumb_imgs    = []    # PhotoImage delle miniature
        self._pdf_thumbs_fp     = None  # filepath del PDF corrente nel pannello
        self._suppress_ext_popup_for = None  # path del file appena rinominato
        threading.Thread(target=_init_sounds, daemon=True).start()
        self.folder_browser          = None
        self._selected_browser_folder = None  # cartella selezionata nel browser per spostamento con preset


        # Usa il preset attivo salvato (nessun dialogo all'avvio)
        active = self.config.get("active_preset", "")
        if active not in self.config["presets"]:
            active = next(iter(self.config["presets"]))
            self.config["active_preset"] = active
        self.labels = self.config["presets"][active]

        self._start_file   = start_file
        self.images        = []   # inizializza subito, il thread la popolerà
        self.skipped       = []
        self.current_index = 0
        self.stats_label   = None
        self.progress_bar  = None
        self._show_info    = False   # overlay EXIF attivo/disattivo

        # Costruisci la UI
        self._build_ui()
        self._show_welcome()
        self.root.config(cursor="")

        # Imposta _NET_WM_ICON via Xlib/ctypes — necessario su Linux 64-bit
        # perché iconphoto usa solo XSetWMHints, non _NET_WM_ICON
        def _set_net_wm_icon():
            icon_path = os.path.join(SORTER_ICONS_DIR, "image_sorter_icon.png")
            if not os.path.isfile(icon_path):
                return
            try:
                import ctypes, ctypes.util
                from PIL import Image
                xlib    = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11"))
                display = xlib.XOpenDisplay(None)
                if not display:
                    return
                wid     = self.root.winfo_id()
                prop    = xlib.XInternAtom(display, b"_NET_WM_ICON", False)
                cardinal= xlib.XInternAtom(display, b"CARDINAL", False)
                img     = Image.open(icon_path).convert("RGBA")
                chunks  = []
                for sz in (256, 128, 64, 48, 32):
                    im  = img.resize((sz, sz), Image.Resampling.LANCZOS)
                    px  = list(im.getdata())
                    chunks.append(sz)
                    chunks.append(sz)
                    chunks.extend((a<<24)|(r<<16)|(g<<8)|b for r,g,b,a in px)
                # Xlib formato 32 su Linux 64-bit richiede c_long (8 byte)
                data = (ctypes.c_long * len(chunks))(*chunks)
                xlib.XChangeProperty(
                    display, wid, prop, cardinal, 32, 0,
                    ctypes.cast(data, ctypes.POINTER(ctypes.c_ubyte)),
                    len(chunks))
                xlib.XFlush(display)
                xlib.XCloseDisplay(display)
            except Exception:
                pass
        self.root.after(500, _set_net_wm_icon)

        # Stream Deck (opzionale)
        self._stream_deck       = None
        self._configure_job     = None   # debounce canvas Configure
        self._delete_pending    = False
        self._delete_no_confirm = False  # True = elimina senza conferma per questa sessione
        self._delete_overlay_frame = None  # Frame overlay alert CANC
        self._delete_timer      = None
        self._delete_return_bind = None
        self._ext_popup         = None
        self._action_bar        = None
        self._pdf_bar_fp        = None
        self._pdf_bar_was_single = None
        self._pdf_thumbs_visible = False

        threading.Thread(target=self._init_stream_deck, daemon=True).start()

        # Operazioni lente in background
        threading.Thread(target=self._startup_io, daemon=True).start()

    def _startup_io(self):
        """Operazioni filesystem all'avvio eseguite in background."""
        try:
            os.makedirs(BASE_DEST, exist_ok=True)
            for k in KEYS:
                os.makedirs(resolve_path(self.labels[k]), exist_ok=True)
            images = self._load_images() if self.source_folder else []
        except Exception:
            images = []
        # Torna nel thread principale per aggiornare la UI
        self.root.after(0, lambda: self._startup_done(images))

    def _startup_done(self, images):
        """Chiamata dal thread principale dopo il caricamento iniziale."""
        self.images = images
        if self._start_file:
            if self._start_file in self.images:
                self.current_index = self.images.index(self._start_file)
            elif os.path.isfile(self._start_file):
                self.images.insert(0, self._start_file)
                self.current_index = 0
        self._show_image()

    # --- helpers -------------------------------------------------------------

    def _dest_path(self, key):
        return resolve_path(self.labels[key])

    def _cleanup_crop_backups(self, folder):
        """Rimuove i file ._crop_backup lasciati da undo crop non eseguiti."""
        if not folder or not os.path.isdir(folder):
            return
        try:
            for fn in os.listdir(folder):
                if fn.endswith("._crop_backup"):
                    try:
                        os.remove(os.path.join(folder, fn))
                    except Exception:
                        pass
        except Exception:
            pass

    def _load_images(self):
        cfg = self.config
        show_img  = cfg.get("show_images", True)
        show_vid  = cfg.get("show_videos", True)
        show_pdf  = cfg.get("show_pdfs",   True)
        show_noe  = cfg.get("show_no_ext", True)
        extra_ext = set(cfg.get("extra_extensions", []))
        result = []
        for f in sorted(os.listdir(self.source_folder)):
            fp  = os.path.join(self.source_folder, f)
            if not os.path.isfile(fp):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                if show_img: result.append(fp)
            elif ext in VIDEO_EXTENSIONS:
                if show_vid: result.append(fp)
            elif ext in PDF_EXTENSIONS:
                if show_pdf: result.append(fp)
            elif ext in extra_ext:
                result.append(fp)
            elif ext == "" and is_media_file(fp):
                if show_noe: result.append(fp)
            elif ext in {".chk", ".tmp", ".bak", ".dat", ".bin", ".unknown"}:
                # Estensioni generiche che spesso nascondono immagini
                if show_noe and is_media_file(fp):
                    result.append(fp)
        return result

    # --- UI ------------------------------------------------------------------

    def _build_ui(self):
        self.root.title("Image Sorter v1.12")
        self.root.configure(bg=BG_COLOR)
        self.root.geometry("1280x820")
        self.root.minsize(960, 640)
        self.root.state("zoomed") if sys.platform == "win32" else self.root.attributes("-zoomed", True)
        hud_apply(self.root)
        # WM_CLASS: deve corrispondere a StartupWMClass nel .desktop
        # GNOME usa WM_CLASS per abbinare la finestra all'icona XDG installata
        self.root.tk.call("wm", "iconname", self.root, "Image Sorter")
        try:
            # Imposta WM_CLASS = ("image_sorter", "Image_sorter")
            self.root.tk.call("tk", "appname", "image_sorter")
        except Exception:
            pass
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=0)
        self.root.rowconfigure(2, weight=1)

        # Header con Canvas per elementi HUD decorativi
        hdr = tk.Frame(self.root, bg=PANEL_COLOR, height=50)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.grid_propagate(False)
        self._hdr = hdr   # riferimento per fullscreen

        self.progress_label = tk.Label(hdr, text="",
                                       font=("TkFixedFont", 10),
                                       bg=PANEL_COLOR, fg=TEXT_COLOR)
        self.progress_label.pack(side="left", padx=10)

        # Slider navigazione rapida
        self._nav_slider_var = tk.IntVar(value=0)
        self._nav_slider_updating = False
        self._nav_slider = tk.Scale(
            hdr, from_=0, to=1,
            orient="horizontal",
            variable=self._nav_slider_var,
            showvalue=False,
            length=180, width=8,
            bg=PANEL_COLOR, fg=HUD_CYAN,
            troughcolor=ACCENT_COLOR,
            activebackground=HIGHLIGHT,
            highlightthickness=0,
            bd=0, relief="flat",
            command=self._on_slider_change)
        self._nav_slider.pack(side="left", padx=(0,10), pady=8)

        # Separatore visivo
        tk.Frame(hdr, bg=ACCENT_COLOR, width=1).pack(side="left", fill="y", pady=6)

        # Label pagina PDF (visibile solo per PDF multipagina)
        self._pdf_page_label = tk.Label(hdr, text="",
                                        font=("TkFixedFont", 9),
                                        bg=PANEL_COLOR, fg="#ff6666")
        self._pdf_page_label.pack(side="left", padx=(8,2))

        # Slider pagine PDF
        self._pdf_slider_var = tk.IntVar(value=0)
        self._pdf_slider_updating = False
        self._pdf_slider = tk.Scale(
            hdr, from_=1, to=1,
            orient="horizontal",
            variable=self._pdf_slider_var,
            showvalue=False,
            length=120, width=8,
            bg=PANEL_COLOR, fg="#ff6666",
            troughcolor=ACCENT_COLOR,
            activebackground=HIGHLIGHT,
            highlightthickness=0,
            bd=0, relief="flat",
            command=self._on_pdf_slider_change)
        self._pdf_slider.pack(side="left", padx=(0,4), pady=8)

        # Bottoni pagina prev/next PDF
        self._pdf_prev_btn = tk.Button(hdr, text="<",
                                       font=("TkFixedFont", 9, "bold"),
                                       bg=ACCENT_COLOR, fg="#ff6666",
                                       relief="flat", bd=0, padx=4,
                                       activebackground=HIGHLIGHT,
                                       command=self._pdf_prev_page)
        self._pdf_prev_btn.pack(side="left", padx=1, pady=8)
        self._pdf_next_btn = tk.Button(hdr, text=">",
                                       font=("TkFixedFont", 9, "bold"),
                                       bg=ACCENT_COLOR, fg="#ff6666",
                                       relief="flat", bd=0, padx=4,
                                       activebackground=HIGHLIGHT,
                                       command=self._pdf_next_page)
        self._pdf_next_btn.pack(side="left", padx=(1,8), pady=8)

        # Bottone miniature pagine
        self._pdf_thumbs_visible = self.config.get("pdf_thumbs_open", False)
        self._pdf_thumbs_btn = tk.Button(hdr,
            text="Min.",
            font=("TkFixedFont", 7, "bold"),
            bg=HUD_CYAN if self._pdf_thumbs_visible else ACCENT_COLOR,
            fg="#0a1a2e" if self._pdf_thumbs_visible else TEXT_COLOR,
            relief="flat", padx=4,
            activebackground=HIGHLIGHT,
            command=self._toggle_pdf_thumbs)

        # Nasconde barra PDF di default
        self._pdf_bar_visible = False
        self._pdf_bar_widgets = [self._pdf_page_label, self._pdf_slider,
                                 self._pdf_prev_btn, self._pdf_next_btn]
        for w in self._pdf_bar_widgets + [self._pdf_thumbs_btn]:
            w.pack_forget()

        self._info_btn_ref    = None
        self._sidebar_btn_ref = None
        self._keypad_btn_ref  = None
        self._settings_dialog  = None
        self._settings_btn_ref = None
        self._fs_btn_ref       = None
        self._play_btn_ref    = None
        _btn_list = [
            ("Esci",        self._quit,                  ACCENT_COLOR, "Q"),
            ("Deck",        self._toggle_keypad,          ACCENT_COLOR, "P"),
            ("S-Deck",      self._toggle_deck_preset_mode,"#1a3a5a",    "Ctrl+D"),
            ("Sidebar",     self._toggle_sidebar,         ACCENT_COLOR, "S"),
            ("Full Screen", self._toggle_fullscreen,      ACCENT_COLOR, "F / Invio"),
            ("Play",         self._play_video,               SUCCESS,      "Invio (video)"),
            ("+",           lambda: self._zoom(1.25),     ACCENT_COLOR, "+"),
            ("-",           lambda: self._zoom(0.80),     ACCENT_COLOR, "-"),
            ("Estendi",     self._zoom_fit,               ACCENT_COLOR, "Z"),
            ("Originale",   self._zoom_original,          ACCENT_COLOR, "X"),
            ("Info EXIF",   self._toggle_info,            ACCENT_COLOR, "I"),
            ("Impostazioni",     self._open_settings,          HIGHLIGHT,    "R"),
            ("Apri",        self._open_new_source,        SUCCESS,      "O"),
        ]

        def _make_tooltip(widget, text):
            tip = [None]
            def show(e):
                if tip[0] and tip[0].winfo_exists():
                    return
                tip[0] = tk.Toplevel(widget)
                tip[0].withdraw()
                tip[0].overrideredirect(True)
                tk.Label(tip[0], text=text,
                         font=("TkFixedFont", 8),
                         bg="#1a3a5a", fg=HUD_CYAN,
                         relief="flat", padx=6, pady=3).pack()
                tip[0].update_idletasks()
                x = widget.winfo_rootx() + widget.winfo_width()//2 - tip[0].winfo_width()//2
                y = widget.winfo_rooty() + widget.winfo_height() + 2
                tip[0].geometry(f"+{x}+{y}")
                tip[0].deiconify()
            def hide(e):
                if tip[0] and tip[0].winfo_exists():
                    tip[0].destroy()
                tip[0] = None
            widget.bind("<Enter>", show)
            widget.bind("<Leave>", hide)

        for txt, cmd, col, key_hint in _btn_list:
            b = tk.Button(hdr, text=txt, font=("TkFixedFont", 9),
                          bg=col, fg="white" if col != ACCENT_COLOR else TEXT_COLOR,
                          relief="flat", padx=6,
                          activebackground=HIGHLIGHT, activeforeground="white",
                          command=cmd)
            b.pack(side="right", padx=2, pady=10)
            _make_tooltip(b, f"Tasto: {key_hint}")
            if txt == "Info EXIF":
                self._info_btn_ref = b
            if txt == "Sidebar":
                self._sidebar_btn_ref = b
            if txt == "Deck":
                self._keypad_btn_ref = b
            if txt == "Originale":
                self._orig_btn_ref = b
            if txt == "Full Screen":
                self._fs_btn_ref = b
            if txt == "Play":
                self._play_btn_ref = b
            if txt == "Impostazioni":
                self._settings_btn_ref = b
        self.preset_label = tk.Label(hdr, text="",
                                     font=("TkFixedFont", 9, "bold"),
                                     bg=PANEL_COLOR, fg=WARNING)
        self.preset_label.pack(side="right", padx=8)
        self._update_preset_label()

        # Seconda riga header: percorso + file corrente (larghezza piena)
        hdr2 = tk.Frame(self.root, bg=PANEL_COLOR)
        hdr2.grid(row=1, column=0, columnspan=2, sticky="ew", padx=0, pady=0)
        self._hdr2 = hdr2
        self.source_label = tk.Label(hdr2, text="",
                                     font=("TkFixedFont", 10),
                                     bg=PANEL_COLOR, fg=HUD_CYAN,
                                     anchor="w")
        self.source_label.pack(side="left", fill="x", expand=True, padx=8, pady=3)
        self._update_source_label()

        img_frame = tk.Frame(self.root, bg=BG_COLOR)
        img_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        img_frame.rowconfigure(0, weight=1)
        img_frame.columnconfigure(0, weight=0)   # colonna miniature PDF (sinistra)
        img_frame.columnconfigure(1, weight=1)   # canvas principale
        img_frame.columnconfigure(2, weight=0)   # scrollbar verticale
        self._img_frame = img_frame
        self.canvas = tk.Canvas(img_frame, bg=BG_COLOR,
                               highlightthickness=1,
                               highlightbackground=HUD_DIM)
        self._canvas_vsb = tk.Scrollbar(img_frame, orient="vertical",
                                        command=self.canvas.yview)
        self._canvas_hsb = tk.Scrollbar(img_frame, orient="horizontal",
                                        command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self._canvas_vsb.set,
                              xscrollcommand=self._canvas_hsb.set)
        self.canvas.grid(row=0, column=1, sticky="nsew")
        self._canvas_vsb.grid(row=0, column=2, sticky="ns")
        self._canvas_hsb.grid(row=1, column=1, sticky="ew")
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        img_frame.rowconfigure(1, weight=0)
        self._configure_job     = None
        def _on_canvas_configure(e):
            # Debounce: aspetta 80ms che il resize finisca prima di ridisegnare
            if self._configure_job:
                self.root.after_cancel(self._configure_job)
            self._configure_job = self.root.after(80, self._show_image)
        self.canvas.bind("<Configure>", _on_canvas_configure)
        self.canvas.bind("<Button-3>",  lambda e: self._canvas_context_menu(e))
        self.canvas.bind("<Button-1>",  lambda e: self._canvas_click(e))
        # Scroll rotella: naviga se zoom=1, scrolla se ingrandito
        def _wheel_up(e):
            if getattr(self, '_zoom_factor', 1.0) > 1.0:
                self.canvas.yview_scroll(-1, "units")
            else:
                self._go_back()
        def _wheel_dn(e):
            if getattr(self, '_zoom_factor', 1.0) > 1.0:
                self.canvas.yview_scroll(1, "units")
            else:
                self._skip()
        self.canvas.bind("<Button-4>",  lambda e: _wheel_up(e))
        self.canvas.bind("<Button-5>",  lambda e: _wheel_dn(e))
        self.canvas.bind("<MouseWheel>",
            lambda e: _wheel_up(e) if e.delta > 0 else _wheel_dn(e))

        self.sidebar_popup = None   # finestra popup sidebar separata

        self.sidebar = tk.Frame(self.root, bg=PANEL_COLOR, width=240,
                               highlightbackground=HUD_DIM,
                               highlightthickness=1)
        self.sidebar.grid(row=2, column=1, sticky="ns", padx=(0,8), pady=8)
        self.sidebar.grid_propagate(False)
        # Costruisce la sidebar dopo che la finestra è già visibile
        self.root.after(50, self._apply_sidebar_mode)

        self.root.focus_set()
        for k in KEYS:
            self.root.bind(f"<KP_{k}>",          lambda e, key=k: self._move_to(key))
            self.root.bind(f"<KeyPress-{k}>",     lambda e, key=k: self._move_to(key))
            self.root.bind(f"<Control-KeyPress-{k}>",
                           lambda e, key=k: self._copy_to(key))
        self.root.bind("<Right>",  lambda e: self._skip())
        self.root.bind("<Up>",     lambda e: self._pdf_prev_page())
        self.root.bind("<Down>",   lambda e: self._pdf_next_page())
        self.root.bind("<Left>",   lambda e: self._go_back())
        self.root.bind("<Control-Left>", lambda e: self._undo_last())
        self.root.bind("<Control-x>", lambda e: self._undo_last())
        self.root.bind("<Control-X>", lambda e: self._undo_last())
        self.root.bind("<Control-z>", lambda e: self._undo_last())
        self.root.bind("<Control-Z>", lambda e: self._undo_last())
        self.root.bind("<Prior>", lambda e: self._cycle_preset(-1))
        self.root.bind("<Next>",  lambda e: self._cycle_preset(1))
        # bind_all con guard
        _hk = self._hk_guard
        self.root.bind_all("<r>", _hk(self._open_settings))
        self.root.bind_all("<R>", _hk(self._open_settings))
        self.root.bind_all("<p>", _hk(self._toggle_keypad))
        self.root.bind_all("<P>", _hk(self._toggle_keypad))
        self.root.bind_all("<d>", _hk(self._toggle_keypad))
        self.root.bind_all("<D>", _hk(self._toggle_keypad))
        self.root.bind("<Control-d>", lambda e: self._toggle_deck_preset_mode())
        self.root.bind("<Control-D>", lambda e: self._toggle_deck_preset_mode())
        self.root.bind("<Control-r>", lambda e: self._open_rename_current())
        self.root.bind("<Control-R>", lambda e: self._open_rename_current())
        self.root.bind_all("<s>", _hk(self._toggle_sidebar))
        self.root.bind_all("<S>", _hk(self._toggle_sidebar))
        self.root.bind_all("<i>", _hk(self._toggle_info))
        self.root.bind_all("<I>", _hk(self._toggle_info))
        self.root.bind_all("<o>", _hk(self._open_new_source))
        self.root.bind_all("<O>", _hk(self._open_new_source))
        self.root.bind_all("<b>",         _hk(self._toggle_browser))
        self.root.bind_all("<B>",         _hk(self._toggle_browser))
        # C = Clockwise (orario), A = Anticlockwise (antiorario)
        self.root.bind_all("<c>", _hk(lambda: self._rotate_current(90)))
        self.root.bind_all("<C>", _hk(lambda: self._rotate_current(90)))
        self.root.bind_all("<a>", _hk(lambda: self._rotate_current(-90)))
        self.root.bind_all("<A>", _hk(lambda: self._rotate_current(-90)))
        self.root.bind_all("<n>",         _hk(self._next_preset))
        self.root.bind_all("<N>",         _hk(self._next_preset))
        self.root.bind_all("<Tab>",       _hk(self._next_preset))
        self.root.bind_all("<ISO_Left_Tab>", _hk(self._prev_preset))
        self.root.bind_all("<f>", _hk(self._toggle_fullscreen))
        self.root.bind_all("<F>", _hk(self._toggle_fullscreen))
        self.root.bind_all("<Return>",      _hk(self._toggle_fullscreen))
        self.root.bind_all("<KP_Enter>",   _hk(self._toggle_fullscreen))
        self.root.bind_all("<plus>",        _hk(lambda: self._zoom(1.25)))
        self.root.bind_all("<minus>",       _hk(lambda: self._zoom(0.80)))
        self.root.bind_all("<equal>",       _hk(lambda: self._zoom(1.25)))
        self.root.bind_all("<KP_Add>",      _hk(lambda: self._zoom(1.25)))
        self.root.bind_all("<KP_Subtract>", _hk(lambda: self._zoom(0.80)))
        self.root.bind_all("<z>",            _hk(self._zoom_fit))
        self.root.bind_all("<Z>",            _hk(self._zoom_fit))
        self.root.bind_all("<h>",            _hk(self._toggle_header))
        self.root.bind_all("<H>",            _hk(self._toggle_header))
        self.root.bind_all("<x>",            _hk(self._zoom_original))
        self.root.bind_all("<X>",            _hk(self._zoom_original))
        self.root.bind_all("<KP_Decimal>", lambda e: self._delete_current())
        self.root.bind_all("<Delete>",     lambda e: self._delete_current())
        self.root.bind("<Escape>", self._on_escape_key)
        self.root.bind_all("<q>", self._hk_guard(self._quit))
        self.root.bind_all("<Q>", self._hk_guard(self._quit))

    def _cycle_preset(self, direction=1):
        names = list(self.config["presets"].keys())
        if len(names) < 2:
            return
        current = self.config.get("active_preset", names[0])
        idx = names.index(current) if current in names else 0
        new_name = names[(idx + direction) % len(names)]
        self._switch_preset_sidebar(new_name)
        self._build_sidebar()
        self._toast_preset(new_name)
        # Aggiorna keypad senza spostarlo
        if self.keypad_popup:
            self.keypad_popup.refresh_labels()
        if getattr(self, '_stream_deck', None) and self._stream_deck.is_active():
            self._stream_deck.refresh_all()

    def _show_toast(self, msg, color=None, duration=1200, tag="hud_toast"):
        """Mostra un messaggio HUD temporaneo centrato sul canvas."""
        if not hasattr(self, 'canvas') or not self.canvas.winfo_exists():
            return
        col = color or HUD_CYAN
        self.canvas.delete(tag)
        cw = max(self.canvas.winfo_width(),  100)
        ch = max(self.canvas.winfo_height(), 100)
        f = tkfont.Font(family="TkFixedFont", size=13, weight="bold")
        tw = f.measure(msg) + 40
        th = 36
        self.canvas.create_rectangle(
            cw//2 - tw//2, ch//2 - th//2,
            cw//2 + tw//2, ch//2 + th//2,
            fill=PANEL_COLOR, outline=col, width=2, tags=tag)
        self.canvas.create_text(
            cw//2, ch//2, text=msg,
            font=("TkFixedFont", 13, "bold"),
            fill=col, tags=tag)
        self.root.after(duration,
            lambda: self.canvas.delete(tag)
            if self.canvas.winfo_exists() else None)

    def _toast_preset(self, name):
        self._show_toast(f"Preset: {name}", duration=1200)

    def _update_preset_label(self):
        # Mostra solo se sidebar o tastierino sono aperti
        sb_mode    = self.config.get("sidebar_mode", "inline")
        sb_visible = (sb_mode == "inline" or
                      (sb_mode == "popup" and self.sidebar_popup and
                       self.sidebar_popup.win.winfo_exists()))
        kp_visible = bool(self.keypad_popup and
                          self.keypad_popup.win.winfo_exists())
        if not sb_visible and not kp_visible:
            self.preset_label.config(text="")
            return
        name  = self.config["active_preset"]
        color = preset_color(self.config, name, fallback=WARNING)
        self.preset_label.config(
            text=f"Preset: {name}",
            fg=color)

    def _switch_preset_sidebar(self, preset_name):
        """Attiva il preset cliccato (bottone nome in cima alla colonna)."""
        if not preset_name or preset_name not in self.config["presets"]:
            return
        if preset_name == self.config["active_preset"]:
            return   # gia' attivo, niente da fare
        self.config["active_preset"] = preset_name
        save_config(self.config)
        self.labels = self.config["presets"][preset_name]
        for k in KEYS:
            os.makedirs(self._dest_path(k), exist_ok=True)
        self._update_preset_label()
        mode = get_sidebar_mode(self.config)
        if mode == "inline":
            self._build_sidebar()
        elif mode == "popup" and self.sidebar_popup:
            self.sidebar_popup.refresh()
        if self.keypad_popup:
            self.keypad_popup.refresh_labels()

    def _move_to_preset(self, key, preset_name):
        """Clicca un tasto di qualsiasi colonna: attiva quel preset (se non lo e')
        e poi sposta il file nella cartella corrispondente."""
        if preset_name != self.config["active_preset"]:
            self._switch_preset_sidebar(preset_name)
        self._move_to(key)

    def _on_slider_change(self, val):
        if self._nav_slider_updating:
            return
        if not self.images:
            return
        idx = int(val)
        if 0 <= idx < len(self.images) and idx != self.current_index:
            self.current_index = idx
            self._show_image()

    def _update_original_btn(self, img=None):
        """Colora il tasto Originale se l'immagine è rimpicciolita."""
        btn = getattr(self, '_orig_btn_ref', None)
        if not btn or not btn.winfo_exists():
            return
        try:
            filepath = self._current_file()
            if not filepath or not img:
                btn.config(bg=ACCENT_COLOR, fg=TEXT_COLOR)
                return
            # Leggi dimensioni originali
            try:
                orig_img = Image.open(filepath)
                orig_w, orig_h = orig_img.size
                orig_img.close()
            except Exception:
                btn.config(bg=ACCENT_COLOR, fg=TEXT_COLOR)
                return
            # Se l'immagine visualizzata è più piccola dell'originale
            if img.width < orig_w or img.height < orig_h:
                btn.config(bg=WARNING, fg="white")
            else:
                btn.config(bg=ACCENT_COLOR, fg=TEXT_COLOR)
        except Exception:
            pass

    def _update_nav_slider(self):
        if not hasattr(self, "_nav_slider"):
            return
        self._nav_slider_updating = True
        n = max(1, len(self.images))
        self._nav_slider.config(from_=0, to=max(0, n-1))
        self._nav_slider_var.set(self.current_index)
        self._nav_slider_updating = False

    def _on_pdf_slider_change(self, val):
        """Chiamata quando l'utente muove lo slider pagine PDF."""""
        if getattr(self, '_pdf_slider_updating', False):
            return
        fp = self._current_file()
        if not fp or not is_pdf(fp):
            return
        page = int(val)
        if page != self._pdf_page.get(fp, 1):
            self._pdf_page[fp] = page
            self._show_image()

    def _update_pdf_bar(self, filepath=None):
        """Mostra/aggiorna la barra di navigazione PDF."""
        if not hasattr(self, '_pdf_bar_widgets'):
            return
        fp = filepath or self._current_file()
        if not fp or not is_pdf(fp):
            # Nascondi tutto
            for w in self._pdf_bar_widgets:
                w.pack_forget()
            if hasattr(self, '_pdf_thumbs_btn'):
                self._pdf_thumbs_btn.pack_forget()
            self._pdf_bar_visible = False
            self._pdf_bar_fp = None
            self._hide_pdf_panel()
            return

        total = get_pdf_page_count(fp)
        cur   = self._pdf_page.get(fp, 1)
        self._pdf_page_label.config(text=f"Pag. {cur}/{total}")

        # Ricostruisci la barra ogni volta che cambia il file o il tipo (1pg vs multipg)
        fp_changed    = getattr(self, '_pdf_bar_fp', None) != fp
        was_single    = getattr(self, '_pdf_bar_was_single', None)
        is_single_now = (total <= 1)

        if fp_changed or (was_single != is_single_now):
            # Smonta tutto e ricostruisce da zero
            for w in self._pdf_bar_widgets + ([self._pdf_thumbs_btn]
                     if hasattr(self, '_pdf_thumbs_btn') else []):
                w.pack_forget()
            self._pdf_bar_visible   = False
            self._pdf_bar_fp        = fp
            self._pdf_bar_was_single = is_single_now

        if total <= 1:
            if not self._pdf_bar_visible:
                self._pdf_page_label.pack(side="left", padx=8)
                self._pdf_bar_visible = True
            return

        # Multi-pagina
        self._pdf_slider_updating = True
        self._pdf_slider.config(from_=1, to=total,
                                length=max(80, min(200, total * 12)))
        self._pdf_slider_var.set(cur)
        self._pdf_slider_updating = False

        if not self._pdf_bar_visible:
            self._pdf_page_label.pack(side="left", padx=(8,2))
            self._pdf_slider.pack(side="left", padx=(0,4), pady=8)
            self._pdf_prev_btn.pack(side="left", padx=1, pady=8)
            self._pdf_next_btn.pack(side="left", padx=(1,4), pady=8)
            if hasattr(self, '_pdf_thumbs_btn'):
                self._pdf_thumbs_btn.pack(side="left", padx=4, pady=8)
            self._pdf_bar_visible = True

        self._pdf_prev_btn.config(
            state="normal" if cur > 1 else "disabled",
            fg=HUD_CYAN if cur > 1 else MUTED_COLOR)
        self._pdf_next_btn.config(
            state="normal" if cur < total else "disabled",
            fg=HUD_CYAN if cur < total else MUTED_COLOR)

        if getattr(self, '_pdf_thumbs_visible', False):
            self._pdf_thumbs_highlight(cur)

    def _update_source_label(self, filepath=None):

        if not self.source_folder:
            self.source_label.config(text="Nessuna cartella aperta")
            return
        folder = self.source_folder
        if len(folder) > 50:
            folder = "..." + folder[-47:]
        if filepath:
            fname = os.path.basename(filepath)
            text = f"  {folder}  /  {fname}"
        else:
            text = f"  {folder}"
        self.source_label.config(text=text)

    def _apply_sidebar_mode(self):
        """Applica la modalita sidebar dalla config: hidden/inline/popup."""
        mode = get_sidebar_mode(self.config)

        # Chiudi eventuale popup aperto
        if self.sidebar_popup and self.sidebar_popup.win.winfo_exists():
            self.sidebar_popup.win.destroy()
        self.sidebar_popup = None

        if mode == "hidden":
            self.sidebar.grid_remove()
            self._update_sidebar_btn(False)
        elif mode == "popup":
            self.sidebar.grid_remove()
            self.sidebar_popup = SidebarPopup(self.root, self)
            self._update_sidebar_btn(True)
        else:  # inline (default)
            self.sidebar.grid()
            self._build_sidebar()
            self._update_sidebar_btn(True)
        self._update_preset_label()

    def _build_sidebar(self):
        self._update_preset_label()
        for w in self.sidebar.winfo_children():
            w.destroy()
        self.stats_label  = None
        self.progress_bar = None

        active       = self.config["active_preset"]
        preset_names = list(self.config["presets"].keys())

        self.badge_labels       = {}
        self.folder_name_labels = {}

        cols_frame = tk.Frame(self.sidebar, bg=PANEL_COLOR)
        cols_frame.pack(fill="x", padx=4, pady=(8, 0))
        cols_frame.columnconfigure(0, weight=1)
        self.sidebar_preset_frame = cols_frame

        n_presets = get_sidebar_presets(self.config)
        for ci in range(n_presets):
            # Usa il preset assegnato alla colonna (da _col_presets)
            col_presets = getattr(self, "_col_presets", preset_names)
            pname = col_presets[ci] if ci < len(col_presets) else (
                    preset_names[ci] if ci < len(preset_names) else None)
            is_active = (pname == active) if pname else False
            border    = HUD_CYAN if is_active else ACCENT_COLOR

            col_frame = tk.Frame(cols_frame, bg=border)
            col_frame.grid(row=ci, column=0, sticky="ew", padx=2, pady=2)
            col_frame.columnconfigure(0, weight=1)
            if not pname:
                continue

            slots = self.config["presets"][pname]
            short = pname if len(pname) <= 8 else pname[:7] + "."
            tk.Button(col_frame, text=short,
                      font=("TkFixedFont", 7, "bold" if is_active else "normal"),
                      bg=(preset_color(self.config, pname, HIGHLIGHT)
                          if is_active else ACCENT_COLOR),
                      fg="white", relief="flat", bd=0,
                      activebackground=HIGHLIGHT, activeforeground="white",
                      command=lambda p=pname: self._switch_preset_sidebar(p)
                      ).pack(fill="x", ipady=4, padx=1, pady=(1, 2))

            grid = tk.Frame(col_frame, bg=PANEL_COLOR)
            grid.pack(fill="x", padx=1, pady=(0, 1))
            for gi in range(3):
                grid.columnconfigure(gi, weight=1)

            row_idx = 0
            for row_keys in ROWS_LAYOUT:
                for col_idx, k in enumerate(row_keys):
                    color   = KEY_COLORS[KEYS.index(k)]
                    colspan = 3 if k == "0" else 1
                    has_dest = bool(slots[k].get('path', '').strip())
                    lbl     = slots[k].get('label', '') if has_dest else ''
                    short_l = lbl if len(lbl) <= 11 else lbl[:10] + "."
                    cell = tk.Frame(grid, bg=PANEL_COLOR)
                    cell.grid(row=row_idx, column=col_idx, columnspan=colspan,
                              sticky="nsew", padx=1, pady=1)
                    badge = tk.Button(cell, text=k,
                                      font=("TkFixedFont", 9, "bold"),
                                      bg=color, fg="white",
                                      activebackground=HIGHLIGHT, activeforeground="white",
                                      relief="flat", bd=0,
                                      command=lambda key=k, p=pname: self._move_to_preset(key, p))
                    badge.pack(fill="x")
                    name_btn = tk.Button(cell, text=short_l,
                                         font=("TkFixedFont", 7), bg=PANEL_COLOR,
                                         fg=SUCCESS if slots[k].get("path","").strip() else TEXT_COLOR,
                                         activebackground=PANEL_COLOR, activeforeground=HIGHLIGHT,
                                         relief="flat", bd=0,
                                         command=lambda key=k, p=pname: self._move_to_preset(key, p))
                    name_btn.pack(fill="x", pady=(0, 1))
                    # Tasto destro: cambia destinazione del tasto
                    for _w in (badge, name_btn):
                        _w.bind("<Button-3>",
                                lambda e, key=k, p=pname: self._quick_set_dest(key, p, e))
                    if is_active:
                        self.badge_labels[k]       = badge
                        self.folder_name_labels[k] = name_btn
                row_idx += 1

        tk.Frame(self.sidebar, bg=ACCENT_COLOR, height=1).pack(
            fill="x", padx=4, pady=(6, 4))
        nav = tk.Frame(self.sidebar, bg=PANEL_COLOR)
        nav.pack(fill="x", padx=4, pady=(0, 4))
        for ci in range(3):
            nav.columnconfigure(ci, weight=1)
        tk.Button(nav, text="< Indietro", font=("TkFixedFont", 8, "bold"),
                  bg="#4a90e2", fg="white", relief="flat", bd=0,
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=self._go_back).grid(row=0, column=0, sticky="ew",
                                              padx=(0, 2), ipady=5)
        tk.Button(nav, text="Salta >", font=("TkFixedFont", 8, "bold"),
                  bg=WARNING, fg="white", relief="flat", bd=0,
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=self._skip).grid(row=0, column=1, sticky="ew",
                                           padx=2, ipady=5)
        tk.Button(nav, text="CANC", font=("TkFixedFont", 8, "bold"),
                  bg="#c0392b", fg="white", relief="flat", bd=0,
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=self._delete_current).grid(row=0, column=2, sticky="ew",
                                                     padx=(2, 0), ipady=5)
        tk.Frame(self.sidebar, bg=ACCENT_COLOR, height=1).pack(
            fill="x", padx=4, pady=(4, 6))
        self.stats_label = tk.Label(self.sidebar, text="",
                                    font=("TkFixedFont", 8),
                                    bg=PANEL_COLOR, fg=MUTED_COLOR, justify="left")
        self.stats_label.pack(padx=14, anchor="w")
        prog_bg = tk.Frame(self.sidebar, bg=ACCENT_COLOR, height=5)
        prog_bg.pack(fill="x", padx=4, pady=(10, 4))
        prog_bg.pack_propagate(False)
        self.progress_bar = tk.Frame(prog_bg, bg=HIGHLIGHT, height=5)
        self.progress_bar.place(x=0, y=0, relheight=1, relwidth=0)

    # --- mostra immagine -----------------------------------------------------

    def _sync_browser(self):
        """Se il browser è aperto, naviga alla cartella dell'immagine corrente."""
        if not (self.folder_browser and
                self.folder_browser.win.winfo_exists()):
            return
        current = self._current_file()
        if not current or not os.path.isfile(current):
            return
        folder = os.path.dirname(current)
        fb = self.folder_browser
        if fb._current_folder != folder:
            fb._navigate_to(folder)
        else:
            # Stessa cartella: evidenzia solo il file
            self.root.after(100, lambda: fb._highlight_file(current))

    def _zoom(self, factor):
        self._zoom_factor = max(0.1, min(10.0, self._zoom_factor * factor))
        self._show_image()

    def _zoom_fit(self):
        """Adatta l'immagine a tutto lo spazio disponibile (riempie il canvas)."""
        filepath = self._current_file()
        if not filepath or not os.path.isfile(filepath):
            return
        try:
            img = Image.open(filepath)
            iw, ih = img.size
        except Exception:
            return
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        # base_scale = scala normale (fit con cap a 1.0)
        base_scale = min(1.0, (cw-16) / iw, (ch-16) / ih)
        # fill_scale = massima scala che mantiene tutta l'immagine visibile
        # (min = nessun taglio, max = riempie ma taglia)
        fill_scale = min((cw-16) / iw, (ch-16) / ih)
        # zoom_factor = rapporto tra le due scale
        if base_scale > 0:
            self._zoom_factor = fill_scale / base_scale
        self._show_image()

    def _zoom_original(self):
        """Riporta l'immagine alla dimensione originale del file (1:1 pixel)."""
        filepath = self._current_file()
        if not filepath or not os.path.isfile(filepath):
            return
        try:
            img = Image.open(filepath)
            iw, ih = img.size
        except Exception:
            return
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        base_scale = min(1.0, cw / iw, ch / ih)
        # zoom_factor tale che base_scale * zf = 1.0
        if base_scale > 0:
            self._zoom_factor = 1.0 / base_scale
        self._show_image()

    def _show_image(self):
        # Se crop overlay attivo, ridisegna solo il crop (non ricostruire il canvas)
        if self._crop_overlay and self._crop_overlay._active:
            self._crop_overlay._draw()
            return
        # Sincronizza browser se aperto
        self._sync_browser()
        # Aggiorna Stream Deck
        if getattr(self, '_stream_deck', None):
            self.root.after(50, self._stream_deck.refresh_all)
        if not self.source_folder:
            self._show_welcome()
            return
        filepath = self._current_file()
        if not filepath:
            if self.moved_count > 0:
                self._show_done()
            else:
                self._show_welcome()
            return
        if not filepath or not os.path.isfile(filepath):
            self._advance()
            return
        # Carica in thread — mantieni l'immagine corrente finché la nuova è pronta
        self._loading_filepath = filepath
        # Mostra solo un piccolo indicatore nell'angolo, senza cancellare l'immagine
        self.canvas.delete("loading")
        cw2 = max(self.canvas.winfo_width(), 100)
        ch2 = max(self.canvas.winfo_height(), 100)
        self.canvas.create_text(cw2 - 8, ch2 - 8,
                                anchor="se",
                                text="...",
                                font=("TkFixedFont", 10), fill=MUTED_COLOR,
                                tags="loading")

        def _load_in_thread():
            try:
                media_type = detect_media_type(filepath)
                if media_type in VIDEO_EXTENSIONS:
                    img = get_video_frame(filepath)
                    if img is None:
                        img = Image.new("RGB", (640, 360), (20, 20, 40))
                        d = ImageDraw.Draw(img)
                        d.polygon([(220,80),(220,280),(460,180)], fill=(0,200,255))
                        d.text((60, 300), os.path.basename(filepath)[:50],
                               fill=(150,150,180))
                elif media_type in PDF_EXTENSIONS:
                    page = self._pdf_page.get(filepath, 1)
                    img  = get_pdf_preview(filepath, page=page)
                else:
                    try:
                        img = Image.open(filepath)
                        if hasattr(img, "draft"):
                            cw = max(self.canvas.winfo_width(),  640)
                            ch = max(self.canvas.winfo_height(), 480)
                            img.draft("RGB", (cw * 2, ch * 2))
                        img.load()
                        # Rotazione automatica da EXIF Orientation
                        try:
                            from PIL.ExifTags import TAGS
                            exif_raw = img._getexif()
                            if exif_raw:
                                orient_tag = next(
                                    (k for k,v in TAGS.items() if v=="Orientation"),
                                    None)
                                orient = exif_raw.get(orient_tag) if orient_tag else None
                                rotation_map = {
                                    3: 180, 6: 270, 8: 90,
                                    # 2,4,5,7 = flip — rari nelle foto, gestiamo solo rotazione
                                }
                                if orient in rotation_map:
                                    img = img.rotate(rotation_map[orient],
                                                     expand=True)
                        except Exception:
                            pass
                        # Controlla SEMPRE se l'estensione è sbagliata,
                        # anche se Pillow è riuscito ad aprire il file
                        correct_ext = _guess_ext_from_image(img)
                        cur_ext     = os.path.splitext(filepath)[1].lower()
                        if correct_ext and cur_ext != correct_ext:
                            self.root.after(50, lambda fp=filepath, ex=correct_ext:
                                self._suggest_rename_ext(fp, ex))
                    except Exception:
                        self.root.after(0, self._advance)
                        return
            except Exception:
                self.root.after(0, self._advance)
                return
            self.root.after(0, lambda: self._finish_show_image(filepath, img))
        threading.Thread(target=_load_in_thread, daemon=True).start()
        return   # la funzione continua in _finish_show_image



    def _finish_show_image(self, filepath, img):
        if not hasattr(self, '_loading_filepath') or self._loading_filepath != filepath:
            return   # nel frattempo l'utente ha navigato altrove


        # Chiudi popup estensione del file precedente
        ep = getattr(self, '_ext_popup', None)
        if ep:
            try: ep.destroy()
            except Exception: pass
            self._ext_popup = None
        self.canvas.delete("loading")
        self.canvas.update_idletasks()
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        zf = getattr(self, '_zoom_factor', 1.0)
        # base_scale: rimpicciolisce se necessario ma non ingrandisce mai (cap a 1.0)
        base_scale  = min(1.0, (cw - 16) / img.width, (ch - 16) / img.height)
        # zoom_factor permette di superare 1.0 esplicitamente
        final_scale = base_scale * zf
        nw = max(1, int(img.width  * final_scale))
        nh = max(1, int(img.height * final_scale))
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
        # Overlay per video (play) e PDF (badge pagina)
        if is_video(filepath):
            img = add_play_overlay(img, alpha=160)
        elif is_pdf(filepath):
            page  = self._pdf_page.get(filepath, 1)
            total = get_pdf_page_count(filepath)
            img   = add_pdf_overlay(img, page, total)
            # Aggiorna pannello miniature se visibile e PDF cambiato
            if getattr(self, '_pdf_thumbs_visible', False):
                if self._pdf_thumbs_fp != filepath:
                    self.root.after(10, lambda fp=filepath: self._show_pdf_panel(fp))
                else:
                    self._pdf_thumbs_highlight(page)
        self._tk_img = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        iw_disp, ih_disp = img.width, img.height
        # Centra se più piccola del canvas, altrimenti parte dall'angolo
        ix = max(cw // 2, iw_disp // 2)
        iy = max(ch // 2, ih_disp // 2)
        self.canvas.create_image(ix, iy, anchor="center", image=self._tk_img)
        # Scrollregion per permettere lo scroll quando ingrandita
        self.canvas.configure(scrollregion=(0, 0,
                              max(cw, iw_disp), max(ch, ih_disp)))
        # Mostra scrollbar solo quando l'immagine è più grande del canvas
        zf = getattr(self, '_zoom_factor', 1.0)
        if zf > 1.0 and (iw_disp > cw or ih_disp > ch):
            self._canvas_vsb.grid()
            self._canvas_hsb.grid()
        else:
            self._canvas_vsb.grid_remove()
            self._canvas_hsb.grid_remove()
        if self._show_info:
            self._draw_info_overlay(filepath)
        self._update_source_label(filepath)
        self._update_nav_slider()
        self._update_pdf_bar(filepath)
        self._update_original_btn(img)
        # Mostra/nascondi bottone Play in base al tipo di file
        if hasattr(self, '_play_btn_ref') and self._play_btn_ref:
            try:
                if is_video(filepath):
                    self._play_btn_ref.pack(side="right", padx=2, pady=10)
                else:
                    self._play_btn_ref.pack_forget()
            except Exception:
                pass

        total_folder = len(self.images) + self.moved_count + len(self.skipped)
        pos          = self.current_index + 1 if self.images else 0
        moved_str    = f"  OK {self.moved_count}/{total_folder}" if self.moved_count else ""

        self.progress_label.config(
            text=f"  {pos}/{total_folder}{moved_str}")
        try:
            if self.stats_label and self.stats_label.winfo_exists():
                self.stats_label.config(
                    text=f"Spostati:  {self.moved_count}\n"
                         f"Rimanenti: {len(self.images)}")
        except Exception:
            self.stats_label = None
        total_bar = len(self.images) + self.moved_count + len(self.skipped)
        pct = self.moved_count / total_bar if total_bar else 0
        try:
            if self.progress_bar and self.progress_bar.winfo_exists():
                self.progress_bar.place(relwidth=pct)
        except Exception:
            self.progress_bar = None

    def _current_file(self):
        if self.current_index < len(self.images):
            return self.images[self.current_index]
        elif self.skipped:
            return self.skipped[0]
        return None

    # --- azioni --------------------------------------------------------------

    def _prompt_empty_preset(self, key):
        """Avvisa che il preset e' vuoto e offre di configurarlo subito."""
        preset_name = self.config["active_preset"]
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.title("Destinazione non configurata")
        win.configure(bg=BG_COLOR)
        win.resizable(False, False)
        hud_apply(win)

        tk.Label(win,
                 text=f"Tasto {key}  —  preset \"{preset_name}\"",
                 font=("TkFixedFont", 9, "bold"),
                 bg=BG_COLOR, fg=WARNING).pack(padx=20, pady=(14,2))
        tk.Label(win,
                 text="Nessuna destinazione configurata.\nVuoi impostarla ora?",
                 font=("TkFixedFont", 9),
                 bg=BG_COLOR, fg=MUTED_COLOR,
                 justify="center").pack(padx=20, pady=(0,10))

        tk.Label(win, text="Percorso destinazione:",
                 font=("TkFixedFont", 8), bg=BG_COLOR,
                 fg=MUTED_COLOR, anchor="w").pack(fill="x", padx=20)
        path_var = tk.StringVar()
        path_row = tk.Frame(win, bg=BG_COLOR)
        path_row.pack(fill="x", padx=20, pady=(2,0))
        path_row.columnconfigure(0, weight=1)
        entry = tk.Entry(path_row, textvariable=path_var,
                         font=("TkFixedFont", 9),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=4)
        entry.grid(row=0, column=0, sticky="ew", ipady=3)
        def _browse():
            d = browse_folder_hud(win, title="Scegli cartella",
                initial_dir=os.path.expanduser("~"))
            if d: path_var.set(d)
        tk.Button(path_row, text="...", font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=6,
                  command=_browse).grid(row=0, column=1, padx=(4,0), ipady=3)

        msg = tk.Label(win, text="", font=("TkFixedFont", 8),
                       bg=BG_COLOR, fg=HIGHLIGHT)
        msg.pack(padx=20)

        def _save():
            new_path = path_var.get().strip()
            if not new_path:
                msg.config(text="Inserisci un percorso.")
                return
            try:
                os.makedirs(new_path, exist_ok=True)
            except Exception as ex:
                msg.config(text=str(ex)[:40])
                return
            slots = self.config["presets"].setdefault(preset_name, {})
            if key not in slots:
                slots[key] = {}
            slots[key]["path"] = new_path
            save_config(self.config)
            self.labels = self.config["presets"][preset_name]
            self._build_sidebar()
            if getattr(self, "_stream_deck", None):
                self._stream_deck.refresh_all()
            win.destroy()
            # Riprova lo spostamento
            self._move_to(key)

        bf = tk.Frame(win, bg=BG_COLOR)
        bf.pack(padx=20, pady=(8,14), fill="x")
        tk.Button(bf, text="Salva e sposta",
                  font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=10,
                  command=_save).pack(side="left", padx=(0,6), ipady=4)
        tk.Button(bf, text="Annulla",
                  font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=10,
                  command=win.destroy).pack(side="left", ipady=4)
        entry.bind("<Return>",   lambda e: _save())
        entry.bind("<KP_Enter>", lambda e: _save())
        win.bind("<Return>",   lambda e: _save())
        win.bind("<KP_Enter>", lambda e: _save())
        win.bind("<Escape>", lambda e: win.destroy())

        win.update_idletasks()
        pw = win.winfo_reqwidth()
        ph = win.winfo_reqheight()
        px = self.root.winfo_rootx() + (self.root.winfo_width()  - pw) // 2
        py = self.root.winfo_rooty() + (self.root.winfo_height() - ph) // 2
        win.geometry(f"+{px}+{py}")
        win.deiconify()
        win.grab_set()

    def _flash_blocked(self):

        orig = self.canvas.cget("bg")
        self.canvas.config(bg="#3a0010")
        self.root.after(150, lambda: self.canvas.config(bg=orig)
                        if self.canvas.winfo_exists() else None)

    def _copy_to(self, key):
        """Ctrl+tasto: copia il file nella cartella di destinazione senza spostarlo."""
        filepath = self._current_file()
        if not filepath or not os.path.isfile(filepath):
            return
        dest_dir = self._dest_path(key)
        if not dest_dir or not dest_dir.strip():
            self._prompt_empty_preset(key)
            return
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, os.path.basename(filepath))
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(os.path.basename(filepath))
            i = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(dest_dir, f"{base}_{i}{ext}")
                i += 1
        shutil.copy2(filepath, dest_path)
        play_sound("move")
        # Toast feedback
        self._show_toast(f"Copiato → {os.path.basename(dest_dir)}")

    def _move_to(self, key):
        # Protezione: blocca se sidebar e tastierino sono entrambi inattivi
        # (eccetto se chiamato dallo Stream Deck)
        sd_active  = bool(getattr(self, '_stream_deck', None) and
                          self._stream_deck.is_active())
        kp_active  = bool(self.keypad_popup and
                          self.keypad_popup.win.winfo_exists())
        sb_mode    = self.config.get("sidebar_mode", "inline")
        sb_visible = sb_mode == "inline" or (
                     sb_mode == "popup" and bool(
                     self.sidebar_popup and
                     self.sidebar_popup.win.winfo_exists()))
        if not sd_active and not kp_active and not sb_visible:
            self._flash_blocked()
            return
        # Controlla se c'è una cartella selezionata nel browser
        sel_folder = getattr(self, '_selected_browser_folder', None)
        if sel_folder and os.path.isdir(sel_folder):
            dest_dir = self._dest_path(key)
            if not dest_dir or not dest_dir.strip():
                self._prompt_empty_preset(key)
                return
            if self.folder_browser and self.folder_browser.win.winfo_exists():
                self.folder_browser._move_folder_to(sel_folder, dest_dir,
                    self.labels.get(key, {}).get("label", key))
            else:
                dest = os.path.join(dest_dir, os.path.basename(sel_folder))
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(sel_folder, dest)
                self._show_toast(
                    os.path.basename(sel_folder) + "  ->  " + dest_dir,
                    color=SUCCESS, duration=1500)
            self._selected_browser_folder = None
            self._flash_key(key)
            return

        filepath = self._current_file()
        if not filepath or not os.path.isfile(filepath):
            self._advance()
            return
        dest_dir = self._dest_path(key)
        # Verifica che il preset abbia una destinazione configurata
        if not dest_dir or not dest_dir.strip():
            self._prompt_empty_preset(key)
            return
        # Verifica che la destinazione non sia la stessa cartella sorgente
        if os.path.normpath(dest_dir) == os.path.normpath(self.source_folder or ""):
            self._show_toast("Destinazione uguale alla cartella corrente!", color="#e74c3c", duration=1800)
            return
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, os.path.basename(filepath))
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(os.path.basename(filepath))
            i = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(dest_dir, f"{base}_{i}{ext}")
                i += 1
        shutil.move(filepath, dest_path)
        play_sound("move")
        self.history.append(("moved", filepath, dest_path, key))
        if len(self.history) > 30:
            self.history.pop(0)
        self.moved_count += 1
        self._zoom_factor = 1.0
        self._view_pos   += 1
        self._flash_key(key)
        if self.current_index < len(self.images):
            self.images.pop(self.current_index)
        else:
            self.skipped.pop(0)
        self._show_image()

    def _cancel_delete_pending(self):
        """Annulla il pending delete (chiamato da frecce destra/sinistra)."""
        if getattr(self, '_delete_pending', False):
            self._delete_pending = False
            if getattr(self, '_delete_timer', None):
                self.root.after_cancel(self._delete_timer)
                self._delete_timer = None
            if self.canvas.winfo_exists():
                self.canvas.delete("delete_warn")
        if getattr(self, '_delete_return_bind', None):
            self.root.bind_all("<Return>", self._hk_guard(self._toggle_fullscreen))
            self._delete_return_bind = None

    def _pdf_next_page(self):
        """Freccia GIU: pagina successiva del PDF."""
        fp = self._current_file()
        if not fp or not is_pdf(fp):
            self._skip()
            return
        total = get_pdf_page_count(fp)
        cur   = self._pdf_page.get(fp, 1)
        if cur < total:
            self._pdf_page[fp] = cur + 1
            self._show_image()
        else:
            self._skip()

    def _pdf_prev_page(self):
        """Freccia SU: pagina precedente del PDF."""
        fp = self._current_file()
        if not fp or not is_pdf(fp):
            self._go_back()
            return
        cur = self._pdf_page.get(fp, 1)
        if cur > 1:
            self._pdf_page[fp] = cur - 1
            self._show_image()
        else:
            self._go_back()

    def _skip(self):
        """Avanza alla prossima immagine. Se siamo all'ultima, torna alla prima (loop)."""
        self._cancel_delete_pending()
        if not self.images:
            return
        self._view_pos += 1
        self.current_index += 1
        if self.current_index >= len(self.images):
            self.current_index = 0   # loop
        self._zoom_factor = 1.0
        self._show_image()

    def _undo_last(self):
        """Ctrl+Freccia sinistra: annulla ultimo spostamento/azione."""
        self._cancel_delete_pending()
        if not self.history:
            return
        current = self._current_file()

        # Per il crop: cerca nella history il crop del file corrente (non necessariamente l'ultimo)
        if current:
            crop_idx = next((i for i in range(len(self.history)-1, -1, -1)
                             if self.history[i][0] == "cropped"
                             and self.history[i][1] == current), None)
            last_action = self.history[-1][0] if self.history else None
            # Se l'ultima azione NON è un crop del file corrente ma esiste un crop del file corrente
            if (crop_idx is not None and
                    (last_action != "cropped" or self.history[-1][1] != current)):
                action = self.history.pop(crop_idx)
                _, filepath, backup = action
                if os.path.isfile(backup):
                    try:
                        shutil.copy2(backup, filepath)
                        os.remove(backup)
                        keys_to_del = [k for k in _thumb_cache if k[0] == filepath]
                        for k in keys_to_del:
                            del _thumb_cache[k]
                        self._loading_filepath = None
                        self._show_toast("Crop annullato", color=WARNING, duration=1200)
                    except Exception:
                        pass
                self._show_image()
                return

        action = self.history.pop()
        if action[0] == "moved":
            _, orig, dest, key = action
            if os.path.isfile(dest):
                shutil.move(dest, orig)
                self.moved_count -= 1
                idx = self._find_insert_index(orig)
                self.images.insert(idx, orig)
                self.current_index = idx
        elif action[0] == "skipped":
            _, orig = action
            if orig in self.skipped:
                self.skipped.remove(orig)
            idx = self._find_insert_index(orig)
            self.images.insert(idx, orig)
            self.current_index = idx
        elif action[0] == "rotated":
            _, filepath, degrees = action
            if os.path.isfile(filepath):
                try:
                    img = Image.open(filepath)
                    fmt = img.format or "JPEG"
                    kw = {"quality": 95, "subsampling": 0} if fmt in ("JPEG","JPG") else {}
                    img.rotate(degrees, expand=True).save(filepath, format=fmt, **kw)
                except Exception:
                    pass
        elif action[0] == "cropped":
            _, filepath, backup = action
            if self._current_file() != filepath:
                self.history.append(action)
                self._show_toast("Nessun crop da annullare su questo file",
                                 color=MUTED_COLOR, duration=1200)
                return
            if os.path.isfile(backup):
                try:
                    shutil.copy2(backup, filepath)
                    os.remove(backup)
                    keys_to_del = [k for k in _thumb_cache if k[0] == filepath]
                    for k in keys_to_del:
                        del _thumb_cache[k]
                    self._loading_filepath = None
                    self._show_toast("Crop annullato", color=WARNING, duration=1200)
                except Exception:
                    pass
        self._show_image()

    def _go_back(self):
        """Freccia sinistra: naviga indietro (senza annullare)."""
        self._cancel_delete_pending()
        if self.current_index > 0:
            self.current_index -= 1
        elif self.images:
            self.current_index = len(self.images) - 1
        self._show_image()

    def _find_insert_index(self, filepath):
        for i, f in enumerate(self.images):
            if filepath < f:
                return i
        return len(self.images)

    def _advance(self):
        if self.current_index < len(self.images):
            self.images.pop(self.current_index)
        elif self.skipped:
            self.skipped.pop(0)
        self._show_image()

    def _flash_key(self, key):
        badge    = self.badge_labels.get(key)
        name_lbl = self.folder_name_labels.get(key)
        color    = KEY_COLORS[KEYS.index(key)]
        has_custom = bool(self.labels[key].get("path", "").strip())
        name_fg   = SUCCESS if has_custom else TEXT_COLOR
        try:
            if badge and badge.winfo_exists():
                badge.config(bg=HIGHLIGHT, activebackground=HIGHLIGHT)
                self.root.after(250, lambda c=color: badge.winfo_exists() and
                                badge.config(bg=c, activebackground=HIGHLIGHT))
        except Exception:
            pass
        try:
            if name_lbl and name_lbl.winfo_exists():
                name_lbl.config(fg=HIGHLIGHT)
                self.root.after(250, lambda c=name_fg: name_lbl.winfo_exists() and
                                name_lbl.config(fg=c))
        except Exception:
            pass
        if self.keypad_popup and self.keypad_popup.win.winfo_exists():
            self.keypad_popup.flash(key)

    def _show_done(self):
        self.canvas.delete("all")
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        self.canvas.create_text(
            cw // 2, ch // 2,
            text=f"FATTO!\n\n{self.moved_count} immagini spostate.\n\n"
                 f"Premi [O] per aprire una nuova cartella.",
            font=("TkFixedFont", 16, "bold"),
            fill=HIGHLIGHT, justify="center")
        self.progress_label.config(
            text=f"  Completato -- {self.moved_count} file spostati")

    def _show_welcome(self):
        self.canvas.delete("all")
        self.canvas.update_idletasks()
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        self.canvas.create_text(
            cw // 2, ch // 2,
            text="Benvenuto in Image Sorter\n\n"
                 "Premi  [O]  per scegliere una cartella\n"
                 "oppure usa il pulsante 'Apri cartella' in alto.",
            font=("TkFixedFont", 14),
            fill=MUTED_COLOR, justify="center")
        self.progress_label.config(text="  Nessuna cartella aperta")

    # --- elimina file corrente -----------------------------------------------

    def _do_trash(self, filepath):
        """Esegue il cestino del file e avanza all'immagine successiva."""
        self._delete_pending = False
        if getattr(self, '_delete_timer', None):
            self.root.after_cancel(self._delete_timer)
            self._delete_timer = None
        self.canvas.delete("delete_warn")
        if getattr(self, '_delete_return_bind', None):
            self.root.bind_all("<Return>", self._hk_guard(self._toggle_fullscreen))
            self._delete_return_bind = None
        try:
            if not send_to_trash(filepath):
                raise Exception("Errore cestino")
        except Exception as ex:
            messagebox.showerror("Errore",
                                 "Impossibile spostare nel cestino:\n" + str(ex),
                                 parent=self.root)
            return
        if self.current_index < len(self.images):
            self.images.pop(self.current_index)
        if self.images and self.current_index >= len(self.images):
            self.current_index = 0
        if not self.images and self.source_folder:
            self.images = [f for f in self._load_images() if f != filepath]
            self.current_index = 0
        self._show_image()

    def _delete_current(self):
        """Elimina con doppio CANC o CANC+Invio. Le frecce annullano."""
        filepath = self._current_file()
        if not filepath or not os.path.isfile(filepath):
            return

        # Modalità senza conferma attivata per questa sessione
        if getattr(self, '_delete_no_confirm', False):
            self._do_trash(filepath)
            return

        if not getattr(self, '_delete_pending', False):
            # Primo tap: mostra avviso sul canvas
            self._delete_pending = True
            fname = os.path.basename(filepath)
            tag = "delete_warn"
            self.canvas.delete(tag)
            cw = max(self.canvas.winfo_width(), 200)
            ch = max(self.canvas.winfo_height(), 200)
            self.canvas.create_rectangle(
                cw//2-220, ch//2-36, cw//2+220, ch//2+36,
                fill=PANEL_COLOR, outline="#e9455e", width=2, tags=tag)
            self.canvas.create_text(
                cw//2, ch//2-12,
                text="Premi CANC di nuovo  (o Invio)  →  Cestino",
                font=("TkFixedFont", 11, "bold"),
                fill="#e9455e", tags=tag)
            self.canvas.create_text(
                cw//2, ch//2+14,
                text=tk_safe(fname, 52),
                font=("TkFixedFont", 9),
                fill=MUTED_COLOR, tags=tag)
            # Bind Return per conferma
            def _confirm_delete(e=None):
                if getattr(self, '_delete_pending', False):
                    self._do_trash(filepath)
                return "break"
            self.root.bind_all("<Return>", _confirm_delete)
            self._delete_return_bind = True
            # Auto-annulla dopo 3 secondi
            if getattr(self, '_delete_timer', None):
                self.root.after_cancel(self._delete_timer)
            self._delete_timer = self.root.after(3000, self._cancel_delete_pending)
        else:
            # Secondo tap CANC: elimina
            self._do_trash(filepath)

    # --- menu contestuale canvas (tasto destro) ----------------------------

    def _canvas_context_menu(self, event):
        filepath = self._current_file()
        if not filepath or not os.path.isfile(filepath):
            return
        self._show_image_menu(event.x_root, event.y_root, filepath)

    def _show_image_menu(self, mx, my, filepath):
        """Finestra popup con azioni sull'immagine corrente."""
        # Chiudi eventuale menu precedente
        if hasattr(self, "_img_menu") and self._img_menu and                 self._img_menu.winfo_exists():
            self._img_menu.destroy()

        fname = tk_safe(os.path.basename(filepath))
        short = fname if len(fname) <= 36 else fname[:34] + ".."

        win = tk.Toplevel(self.root)
        win.withdraw()
        win.title("")
        win.configure(bg=PANEL_COLOR)
        win.resizable(False, False)
        win.transient(self.root)   # rimane sopra alla finestra principale ma non alle altre app
        hud_apply(win)
        self._img_menu = win

        win.bind("<Escape>", lambda e: win.destroy())
        # Chiudi cliccando fuori: usa ButtonPress sul resto dell'applicazione
        def _close_if_outside(e):
            if not win.winfo_exists():
                return
            wx, wy = win.winfo_rootx(), win.winfo_rooty()
            ww2, wh2 = win.winfo_width(), win.winfo_height()
            if not (wx <= e.x_root <= wx+ww2 and wy <= e.y_root <= wy+wh2):
                win.destroy()
        _bid = [self.root.bind("<ButtonPress>", _close_if_outside, add=True)]
        _unbound = [False]
        def _safe_unbind_menu(e=None):
            if _unbound[0]: return
            _unbound[0] = True
            try: self.root.unbind("<ButtonPress>", _bid[0])
            except Exception: pass
            self.root.after(50, self.root.focus_set)
        win.bind("<Destroy>", _safe_unbind_menu)

        # Titolo
        tk.Label(win, text=short, font=("TkFixedFont", 8),
                 bg=PANEL_COLOR, fg=MUTED_COLOR,
                 anchor="w").pack(fill="x", padx=10, pady=(8,4))
        tk.Frame(win, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=6)

        def btn(text, color, cmd):
            tk.Button(win, text=text,
                      font=("TkFixedFont", 9),
                      bg=PANEL_COLOR, fg=TEXT_COLOR,
                      activebackground=color, activeforeground="white",
                      relief="flat", anchor="w",
                      command=lambda: (win.destroy(), cmd())
                      ).pack(fill="x", padx=6, pady=1, ipady=4)

        if is_video(filepath):
            btn("Play video",         SUCCESS,   lambda: self._play_video())
        elif is_pdf(filepath):
            btn("Apri PDF",           SUCCESS,   lambda: subprocess.Popen(
                ["xdg-open", filepath],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        else:
            btn("Ritaglia...",        SUCCESS,   lambda: self._open_crop(filepath))
        btn("Rinomina...",        WARNING,      lambda: self._open_rename_direct(filepath))
        if not is_video(filepath) and not is_pdf(filepath):
            btn("Ruota 90 orario",    "#4a90e2", lambda: self._rotate_image(filepath,  90))
            btn("Ruota 90 antiorario","#4a90e2", lambda: self._rotate_image(filepath, -90))
        btn("Elimina",            HIGHLIGHT,    lambda: (win.destroy(), self._do_trash(filepath)))

        # Checkbox "non chiedere conferma" — vale per tutta la sessione
        ck_var = tk.BooleanVar(value=getattr(self, '_delete_no_confirm', False))
        tk.Checkbutton(win,
                       text="Elimina direttamente (senza conferma) per questa sessione",
                       variable=ck_var,
                       font=("TkFixedFont", 8),
                       bg=PANEL_COLOR, fg=MUTED_COLOR,
                       selectcolor=PANEL_COLOR,
                       activebackground=PANEL_COLOR, activeforeground=TEXT_COLOR,
                       relief="flat", anchor="w",
                       command=lambda: setattr(self, '_delete_no_confirm', ck_var.get())
                       ).pack(fill="x", padx=10, pady=(2,4))

        tk.Frame(win, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=6, pady=(0,0))
        btn("Apri cartella",      ACCENT_COLOR, lambda: open_in_filemanager(filepath))
        btn("Modifica con...",    "#2a3a5a",    lambda: self._open_edit_with(filepath))
        btn("Copia percorso",     ACCENT_COLOR, lambda: self._copy_to_clipboard(filepath))

        tk.Frame(win, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=6, pady=(4,0))
        tk.Button(win, text="Chiudi",
                  font=("TkFixedFont", 8),
                  bg=PANEL_COLOR, fg=MUTED_COLOR,
                  relief="flat",
                  command=win.destroy).pack(fill="x", padx=6, pady=(2,6), ipady=2)

        # Posiziona vicino al click, aggiusta se esce dallo schermo
        win.update_idletasks()
        ww = win.winfo_reqwidth()
        wh = win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x  = min(mx + 4, sw - ww - 8)
        y  = min(my + 4, sh - wh - 8)
        win.geometry(f"+{x}+{y}")
        win.deiconify()
        win.focus_set()

    def _open_crop(self, filepath):
        if is_video(filepath) or is_pdf(filepath):
            messagebox.showinfo("Ritaglio",
                "Il ritaglio non è disponibile per video e PDF.",
                parent=self.root)
            return
        # Chiudi eventuale overlay precedente
        if hasattr(self, "_crop_overlay") and self._crop_overlay:
            self._crop_overlay._cancel()
        self._crop_overlay = CropOverlay(self)

    def _rotate_current(self, degrees):
        """Ruota l'immagine corrente di `degrees` gradi (da tastiera C/A)."""
        fp = self._current_file()
        if fp and not is_video(fp) and not is_pdf(fp):
            self._rotate_image(fp, degrees)

    def _rotate_image(self, filepath, degrees):
        """Ruota l'immagine in place e aggiorna la visualizzazione."""
        try:
            img = Image.open(filepath)
            # EXIF transpose per non perdere metadati orientamento
            rotated = img.rotate(-degrees, expand=True)
            # Salva preservando il formato e la qualità originale
            fmt = img.format or "JPEG"
            kwargs = {}
            if fmt in ("JPEG", "JPG"):
                kwargs["quality"] = 95
                kwargs["subsampling"] = 0
            rotated.save(filepath, format=fmt, **kwargs)
            # Aggiorna history per permettere undo
            self.history.append(("rotated", filepath, degrees))
            self._show_image()
        except Exception as ex:
            messagebox.showerror("Errore rotazione",
                f"Impossibile ruotare l'immagine:\n{ex}",
                parent=self.root)

    def _open_rename_current(self, e=None):
        """Ctrl+R: apre il rinomina inline sul file corrente."""
        filepath = self._current_file()
        if filepath and os.path.isfile(filepath):
            self._open_rename_direct(filepath)

    def _open_rename_direct(self, filepath):
        """Apre direttamente il campo rinomina inline, saltando la barra bottoni."""
        self._close_action_bar()
        img_frame = self.canvas.master
        bar = tk.Frame(img_frame, bg=PANEL_COLOR)
        bar.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0, height=36)
        self._action_bar = bar
        self._show_rename_inline(bar, filepath)

    def _show_action_bar(self, filepath):
        """Mostra barra azioni in basso sull'area immagine."""
        self._close_action_bar()
        fname = os.path.basename(filepath)
        short = fname if len(fname) <= 40 else fname[:38] + ".."

        # Frame sovrapposto in basso sull'img_frame con place()
        img_frame = self.canvas.master
        bar = tk.Frame(img_frame, bg=PANEL_COLOR)
        bar.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0, height=36)
        self._action_bar = bar

        tk.Label(bar, text=short, font=("TkFixedFont", 8),
                 bg=PANEL_COLOR, fg=MUTED_COLOR).pack(side="left", padx=8)

        tk.Button(bar, text="Rinomina",
                  font=("TkFixedFont", 8), bg=WARNING, fg="white",
                  relief="flat", padx=8,
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=lambda: self._show_rename_inline(bar, filepath)
                  ).pack(side="left", padx=4, ipady=2)

        tk.Button(bar, text="Copia percorso",
                  font=("TkFixedFont", 8), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=8,
                  activebackground=HIGHLIGHT, activeforeground="white",
                  command=lambda: (self._copy_to_clipboard(filepath),
                                   self._close_action_bar())
                  ).pack(side="left", padx=4, ipady=2)

        tk.Button(bar, text="x",
                  font=("TkFixedFont", 9), bg=PANEL_COLOR, fg=MUTED_COLOR,
                  relief="flat",
                  command=self._close_action_bar
                  ).pack(side="right", padx=8, ipady=2)

    def _show_rename_inline(self, bar, filepath):
        """Sostituisce i bottoni nella barra con un campo di testo per rinomina."""
        for w in bar.winfo_children():
            w.destroy()

        folder    = os.path.dirname(filepath)
        old_name  = os.path.basename(filepath)
        base, ext = os.path.splitext(old_name)

        tk.Label(bar, text=f"{ext}  |",
                 font=("TkFixedFont", 8), bg=PANEL_COLOR,
                 fg=WARNING).pack(side="left", padx=(8,4))

        var   = tk.StringVar(value=base)
        entry = tk.Entry(bar, textvariable=var,
                         font=("TkFixedFont", 9),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         selectbackground=HIGHLIGHT,
                         relief="flat", bd=4)
        entry.pack(side="left", fill="x", expand=True, padx=4, ipady=3)

        entry.focus_force()
        # Seleziona tutto per indicare visivamente che è pronto
        entry.after(20, lambda: (
            entry.selection_range(0, tk.END),
            entry.focus_force()
        ) if entry.winfo_exists() else None)

        msg = tk.Label(bar, text="", font=("TkFixedFont", 8),
                       bg=PANEL_COLOR, fg=HIGHLIGHT)
        msg.pack(side="left", padx=4)

        # I bind_all sono già gestiti da _hk_guard che controlla se il focus
        # è su un Entry — non serve disabilitarli esplicitamente.

        def do_rename(event=None):
            new_base = sanitize_name(var.get().strip())
            if not new_base:
                msg.config(text="Nome non valido.")
                return "break"
            new_path = os.path.join(folder, new_base + ext)
            if new_path == filepath:
                self._close_action_bar()
                return "break"
            if os.path.exists(new_path):
                msg.config(text="Nome già esistente.")
                return "break"
            try:
                os.rename(filepath, new_path)
                self._close_action_bar()
                self._refresh_after_rename(filepath, new_path)
            except Exception as ex:
                msg.config(text=str(ex)[:40])
            return "break"   # blocca propagazione Return a bind_all fullscreen

        def cancel(event=None):
            self._close_action_bar()

        tk.Button(bar, text="OK",
                  font=("TkFixedFont", 8), bg=SUCCESS, fg="white",
                  relief="flat", padx=6,
                  activebackground=HIGHLIGHT,
                  command=do_rename).pack(side="left", padx=2, ipady=3)
        tk.Button(bar, text="Annulla",
                  font=("TkFixedFont", 8), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=6,
                  activebackground=HIGHLIGHT,
                  command=cancel).pack(side="left", padx=2, ipady=3)

        entry.bind("<Return>",   do_rename)
        entry.bind("<KP_Enter>", do_rename)
        entry.bind("<Escape>", cancel)
        # Chiudi premendo Esc sulla root (anche se il focus è altrove)
        _esc_bid = [self.root.bind("<Escape>",
                                   lambda e: cancel() if bar.winfo_exists() else None,
                                   add=True)]
        # Chiudi cliccando sul canvas (fuori dalla barra)
        def _click_outside(e):
            if not bar.winfo_exists():
                return
            bx = bar.winfo_rootx()
            by = bar.winfo_rooty()
            bw = bar.winfo_width()
            bh = bar.winfo_height()
            if not (bx <= e.x_root <= bx+bw and by <= e.y_root <= by+bh):
                cancel()
        self.canvas.bind("<ButtonPress>", _click_outside, add=True)
        def _cleanup(e=None):
            self.canvas.unbind("<ButtonPress>")
            try: self.root.unbind("<Escape>", _esc_bid[0])
            except Exception: pass
        bar.bind("<Destroy>", _cleanup)

    def _close_action_bar(self):
        bar = getattr(self, "_action_bar", None)
        if bar and bar.winfo_exists():
            bar.destroy()
        self._action_bar = None
        self._restore_keybinds()
        self.root.focus_set()

    def _disable_keybinds(self):
        """No-op: la guardia _is_rename_active() blocca i bind quando
        la barra di rinomina è attiva. Non servono unbind espliciti."""
        pass

    def _is_rename_active(self):
        """True se la barra di rinomina inline è aperta con un Entry."""
        bar = getattr(self, '_action_bar', None)
        if not bar or not bar.winfo_exists():
            return False
        return any(isinstance(w, tk.Entry) for w in bar.winfo_children())

    def _restore_keybinds(self):
        def _g(fn):
            def _h(e):
                if self._is_rename_active():
                    return
                if isinstance(e.widget, (tk.Entry, tk.Text, tk.Spinbox)):
                    return
                fn()
            return _h
        for k in KEYS:
            self.root.bind(f"<KP_{k}>",
                lambda e, key=k: None if self._is_rename_active() else self._move_to(key))
            self.root.bind(f"<KeyPress-{k}>",
                lambda e, key=k: None if self._is_rename_active() else self._move_to(key))
            self.root.bind(f"<Control-KeyPress-{k}>",
                lambda e, key=k: self._copy_to(key))
        self.root.bind("<Right>",        _g(self._skip))
        self.root.bind("<Up>",           _g(self._pdf_prev_page))
        self.root.bind("<Down>",         _g(self._pdf_next_page))
        self.root.bind("<Left>",         _g(self._go_back))
        self.root.bind("<Control-Left>", lambda e: self._undo_last())
        self.root.bind("<Prior>", lambda e: self._cycle_preset(-1))
        self.root.bind("<Next>",  lambda e: self._cycle_preset(1))
        _hk = self._hk_guard
        self.root.bind_all("<R>", _hk(self._open_settings))
        self.root.bind_all("<p>", _hk(self._toggle_keypad))
        self.root.bind_all("<P>", _hk(self._toggle_keypad))
        self.root.bind_all("<d>", _hk(self._toggle_keypad))
        self.root.bind_all("<D>", _hk(self._toggle_keypad))
        self.root.bind("<Control-d>", lambda e: self._toggle_deck_preset_mode())
        self.root.bind("<Control-D>", lambda e: self._toggle_deck_preset_mode())
        self.root.bind("<Control-r>", lambda e: self._open_rename_current())
        self.root.bind("<Control-R>", lambda e: self._open_rename_current())
        self.root.bind_all("<s>", _hk(self._toggle_sidebar))
        self.root.bind_all("<S>", _hk(self._toggle_sidebar))
        self.root.bind_all("<i>", _hk(self._toggle_info))
        self.root.bind_all("<I>", _hk(self._toggle_info))
        self.root.bind_all("<o>", _hk(self._open_new_source))
        self.root.bind_all("<O>", _hk(self._open_new_source))
        self.root.bind_all("<b>",         _hk(self._toggle_browser))
        self.root.bind_all("<B>",         _hk(self._toggle_browser))
        # C = Clockwise (orario), A = Anticlockwise (antiorario)
        self.root.bind_all("<c>", _hk(lambda: self._rotate_current(90)))
        self.root.bind_all("<C>", _hk(lambda: self._rotate_current(90)))
        self.root.bind_all("<a>", _hk(lambda: self._rotate_current(-90)))
        self.root.bind_all("<A>", _hk(lambda: self._rotate_current(-90)))
        self.root.bind_all("<n>",         _hk(self._next_preset))
        self.root.bind_all("<N>",         _hk(self._next_preset))
        self.root.bind_all("<Tab>",       _hk(self._next_preset))
        self.root.bind_all("<ISO_Left_Tab>", _hk(self._prev_preset))
        self.root.bind_all("<f>", _hk(self._toggle_fullscreen))
        self.root.bind_all("<F>", _hk(self._toggle_fullscreen))
        self.root.bind_all("<Return>",      _hk(self._toggle_fullscreen))
        self.root.bind_all("<plus>",        _hk(lambda: self._zoom(1.25)))
        self.root.bind_all("<minus>",       _hk(lambda: self._zoom(0.80)))
        self.root.bind_all("<equal>",       _hk(lambda: self._zoom(1.25)))
        self.root.bind_all("<KP_Add>",      _hk(lambda: self._zoom(1.25)))
        self.root.bind_all("<KP_Subtract>", _hk(lambda: self._zoom(0.80)))
        self.root.bind_all("<z>",            _hk(self._zoom_fit))
        self.root.bind_all("<Z>",            _hk(self._zoom_fit))
        self.root.bind_all("<h>",            _hk(self._toggle_header))
        self.root.bind_all("<H>",            _hk(self._toggle_header))
        self.root.bind_all("<x>",            _hk(self._zoom_original))
        self.root.bind_all("<X>",            _hk(self._zoom_original))
        self.root.bind_all("<KP_Decimal>", lambda e: self._delete_current())
        self.root.bind_all("<Delete>",     lambda e: self._delete_current())
        self.root.bind("<Escape>", self._on_escape_key)
        self.root.bind_all("<q>", self._hk_guard(self._quit))
        self.root.bind_all("<Q>", self._hk_guard(self._quit))

    def _rename_file(self, filepath, callback=None):
        """Usato dal browser: apre la barra rinomina nella finestra principale."""
        self._show_action_bar(filepath)
        # Sostituisci il callback di _refresh_after_rename con quello del browser
        if callback and callback is not self._refresh_after_rename:
            self._rename_browser_callback = callback

    def _refresh_after_rename(self, old_path, new_path):
        """Aggiorna la lista immagini dopo una rinomina."""
        if old_path in self.images:
            idx = self.images.index(old_path)
            self.images[idx] = new_path
            self.current_index = idx
        if old_path in self.skipped:
            idx = self.skipped.index(old_path)
            self.skipped[idx] = new_path
        self.root.after(50, self._show_image)

    def _copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    # --- overlay info EXIF --------------------------------------------------

    def _toggle_sidebar(self):
        cycle = {"inline": "popup", "popup": "hidden", "hidden": "inline"}
        self.config["sidebar_mode"] = cycle.get(get_sidebar_mode(self.config), "inline")
        save_config(self.config)
        self._apply_sidebar_mode()

    def _update_sidebar_btn(self, active=None):
        if not self._sidebar_btn_ref:
            return
        m = get_sidebar_mode(self.config)
        colors = {"inline": HUD_CYAN, "popup": WARNING, "hidden": ACCENT_COLOR}
        fgs    = {"inline": "#0a1a2e", "popup": "#0a1a2e", "hidden": TEXT_COLOR}
        self._sidebar_btn_ref.config(
            bg=colors.get(m, ACCENT_COLOR),
            fg=fgs.get(m, TEXT_COLOR))

    def _toggle_info(self):
        self._show_info = not self._show_info
        if self._info_btn_ref:
            self._info_btn_ref.config(
                bg=HIGHLIGHT if self._show_info else ACCENT_COLOR)
        # Non ricaricare l'immagine — aggiungi/rimuovi solo l'overlay
        filepath = self._current_file()
        if not filepath:
            return
        if self._show_info:
            self._draw_info_overlay(filepath)
        else:
            self.canvas.delete("exif_overlay")

    def _draw_info_overlay(self, filepath):
        """Disegna un overlay semitrasparente con info file e dati EXIF sul canvas."""
        # Raccoglie informazioni
        lines = []
        try:
            fname = os.path.basename(filepath)
            fsize = os.path.getsize(filepath)
            if fsize < 1024:
                size_str = f"{fsize} B"
            elif fsize < 1024**2:
                size_str = f"{fsize/1024:.1f} KB"
            else:
                size_str = f"{fsize/1024**2:.1f} MB"
            lines.append(f"File:  {fname}")
            lines.append(f"Dim.:  {size_str}")
            try:
                mtime = os.path.getmtime(filepath)
                import datetime as _dt
                date_str = _dt.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y  %H:%M")
                lines.append(f"Modif: {date_str}")
            except Exception:
                pass
        except OSError:
            pass

        try:
            img = Image.open(filepath)
            lines.append(f"Pixel: {img.width} x {img.height}")
            lines.append(f"Modo:  {img.mode}")

            # Dati EXIF
            exif_data = {}
            try:
                raw = img._getexif()
                if raw:
                    for tag_id, val in raw.items():
                        tag = TAGS.get(tag_id, tag_id)
                        exif_data[tag] = val
            except Exception:
                pass

            wanted = [
                ("Data",        ["DateTimeOriginal", "DateTime"]),
                ("Fotocamera",  ["Model"]),
                ("Marca",       ["Make"]),
                ("Obiettivo",   ["LensModel"]),
                ("Focale",      ["FocalLength"]),
                ("Diaframma",   ["FNumber"]),
                ("Esposiz.",    ["ExposureTime"]),
                ("ISO",         ["ISOSpeedRatings", "PhotographicSensitivity"]),
                ("Flash",       ["Flash"]),
                ("GPS",         ["GPSInfo"]),
            ]
            for label, keys in wanted:
                for k in keys:
                    if k in exif_data:
                        val = exif_data[k]
                        # Formattazione valori speciali
                        if k == "FNumber" and hasattr(val, "numerator"):
                            val = f"f/{val.numerator/val.denominator:.1f}"
                        elif k == "ExposureTime" and hasattr(val, "numerator"):
                            n, d = val.numerator, val.denominator
                            val = f"1/{int(d/n)}s" if n < d else f"{n/d:.1f}s"
                        elif k == "FocalLength" and hasattr(val, "numerator"):
                            val = f"{val.numerator/val.denominator:.0f}mm"
                        elif k == "Flash":
                            val = "si" if val & 1 else "no"
                        elif k == "GPSInfo":
                            val = "presente"
                        elif k in ("DateTimeOriginal", "DateTime"):
                            val = str(val).replace(":", "/", 2)
                        val_str = str(val)
                        if len(val_str) > 30:
                            val_str = val_str[:28] + ".."
                        lines.append(f"{label+':':<10} {val_str}")
                        break
        except Exception:
            pass

        if not lines:
            return

        # Disegna l'overlay in basso a sinistra
        pad   = 10
        lh    = 18
        fsize = 11
        font  = ("TkFixedFont", fsize)
        x0    = pad

        # Misura larghezza con tkFont
        try:
            f = tkfont.Font(family="TkFixedFont", size=fsize)
            max_w = max(f.measure(line) for line in lines) if lines else 200
        except Exception:
            max_w = max(len(l) for l in lines) * 8 if lines else 200

        box_w = max_w + pad * 3
        box_h = pad * 2 + len(lines) * lh
        y0    = self.canvas.winfo_height() - box_h - pad

        # Sfondo
        self.canvas.create_rectangle(
            x0, y0, x0 + box_w, y0 + box_h,
            fill="#0a1420", outline="#1a3a5a",
            stipple="gray50", tags="exif_overlay")

        # Testo
        for i, line in enumerate(lines):
            ty = y0 + pad + i * lh
            self.canvas.create_text(
                x0 + pad + 1, ty + 1,
                text=line, anchor="nw",
                font=font, fill="#000000",
                tags="exif_overlay")
            col = WARNING if i == 0 else ("#aaddff" if ":" in line[:12] else TEXT_COLOR)
            self.canvas.create_text(
                x0 + pad, ty,
                text=line, anchor="nw",
                font=font, fill=col,
                tags="exif_overlay")

    # --- navigazione sorgente ------------------------------------------------

    def _open_new_source(self):
        """Toggle browser cartelle: apre se chiuso, chiude se aperto."""
        if self.folder_browser and self.folder_browser.win.winfo_exists():
            self.folder_browser._on_close()
        else:
            try:
                self.folder_browser = FolderBrowser(self.root, self)
            except Exception:
                tb = traceback.format_exc()
                log = os.path.join(SCRIPT_DIR, "image_sorter_error.log")
                with open(log, "w") as _f:
                    _f.write(tb)
                messagebox.showerror("Errore Browser", tb[:600], parent=self.root)

    def _load_source(self, new_source):
        """Carica una nuova cartella sorgente (usato da browser e dialogo)."""
        if not hasattr(self, "canvas"):
            return   # UI non ancora costruita
        # Pulizia backup crop dalla cartella precedente
        if getattr(self, 'source_folder', None):
            self._cleanup_crop_backups(self.source_folder)
        self.config["last_source"] = new_source
        save_config(self.config)
        self.source_folder  = new_source
        self.images         = self._load_images()
        self.skipped        = []
        self.current_index  = 0
        self.moved_count    = 0
        self.history        = []
        self._zoom_factor   = 1.0
        self._total_images  = len(self.images)
        self._view_pos      = 0   # posizione crescente nella sequenza di visualizzazione
        self._update_source_label()
        self.progress_label.config(text="")
        if not self.images:
            self.canvas.delete("all")
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            self.canvas.create_text(
                cw // 2, ch // 2,
                text="Nessuna immagine trovata\nin questa cartella.",
                font=("TkFixedFont", 14), fill=MUTED_COLOR, justify="center")
            return
        self._show_image()

    # --- popup / preset / config ---------------------------------------------

    def _toggle_browser(self):
        if self.folder_browser:
            self.folder_browser._on_close()
        else:
            try:
                self.folder_browser = FolderBrowser(self.root, self)
            except Exception:
                tb = traceback.format_exc()
                log = os.path.join(SCRIPT_DIR, "image_sorter_error.log")
                with open(log, "w") as f:
                    f.write(tb)
                messagebox.showerror("Errore Browser",
                    f"Impossibile aprire il browser:\n\n{tb[:600]}",
                    parent=self.root)

    def _toggle_deck_preset_mode(self):
        """Attiva/disattiva modalità preset sul deck fisico senza aprire il softdeck."""
        sdk = getattr(self, '_stream_deck', None)
        if not sdk or not sdk.is_active():
            self._show_toast("Stream Deck non connesso", color="#e74c3c", duration=1500)
            return
        if sdk._mode == "preset":
            sdk.set_mode("idle")
            self._show_toast("Deck: modalità idle", duration=1000)
        else:
            sdk.set_mode("preset")
            self._show_toast("Deck: modalità preset", color=SUCCESS, duration=1000)

    def _toggle_keypad(self):
        """Cicla: 1 colonna -> 2 colonne -> 3 colonne -> chiudi -> 1 colonna..."""
        sdk = getattr(self, '_stream_deck', None)
        if self.keypad_popup:
            current = get_keypad_cols(self.config)
            if current >= 3:
                # Chiudi → deck torna in modalità idle
                self.keypad_popup._on_close()
                self._update_keypad_btn(0)
                if sdk and sdk.is_active():
                    sdk.set_mode("idle")
            else:
                new_cols = current + 1
                self.config["keypad_cols"] = new_cols
                save_config(self.config)
                self.keypad_popup.refresh_labels()
                self._update_keypad_btn(new_cols)
        else:
            # Apri → deck passa a modalità preset
            self.config["keypad_cols"] = 1
            save_config(self.config)
            self.keypad_popup = KeypadPopup(self.root, self)
            self._update_keypad_btn(1)
            if sdk and sdk.is_active():
                sdk.set_mode("preset")
                sdk.refresh_all()

    def _update_keypad_btn(self, cols):
        if not self._keypad_btn_ref:
            return
        colors = {0: ACCENT_COLOR, 1: HUD_CYAN, 2: WARNING, 3: SUCCESS}
        fgs    = {0: TEXT_COLOR,   1: "#0a1a2e", 2: "#0a1a2e", 3: "#0a1a2e"}
        self._keypad_btn_ref.config(
            bg=colors.get(cols, ACCENT_COLOR),
            fg=fgs.get(cols, TEXT_COLOR))

    def _open_browser_to(self, path):
        """Apre il browser navigando a path (usato da DiskAnalyzer)."""
        if (getattr(self, 'folder_browser', None) and
                self.folder_browser.win.winfo_exists()):
            self.folder_browser._expand_to(path)
            self.folder_browser.win.lift()
        else:
            self.folder_browser = FolderBrowser(self.root, self)
            self.root.after(400, lambda p=path: (
                self.folder_browser._expand_to(p)
                if (self.folder_browser and
                    self.folder_browser.win.winfo_exists()) else None))

    def _quit(self):
        # Pulizia backup crop della cartella corrente
        if getattr(self, 'source_folder', None):
            self._cleanup_crop_backups(self.source_folder)
        # Chiudi il deck solo se siamo l'istanza che lo possiede
        if getattr(self, '_owns_deck', False):
            if getattr(self, '_stream_deck', None):
                try:
                    self._stream_deck.close()
                except Exception:
                    pass
            # Rimuovi il lock file
            try:
                lock = os.path.join(SCRIPT_DIR, ".deck_owner.lock")
                if os.path.isfile(lock):
                    os.unlink(lock)
            except Exception:
                pass
            # Riavvia StreamController con UI solo se non ci sono
            # altre istanze di Image Sorter attive
            other = self._count_other_sorter_instances()
            should_restart = self.config.get("deck_restart_sc", True)
            if other == 0 and should_restart:
                try:
                    subprocess.Popen(["streamdeck"],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    print("[StreamDeck] StreamController UI riavviato")
                except FileNotFoundError:
                    pass
            elif not should_restart:
                print("[StreamDeck] Riavvio StreamController disabilitato dall'utente")
            else:
                print(f"[StreamDeck] {other} altre istanze attive, non riavvio StreamController")
        try:
            ImageSorter._all_instances.remove(self)
        except ValueError:
            pass
        self.root.destroy()

    @staticmethod
    def _get_focused_instance():
        """Restituisce l'istanza con la finestra attiva/in primo piano."""
        active = [i for i in ImageSorter._all_instances
                  if i.root.winfo_exists()]
        if not active:
            return None
        # Cerca quella con focus reale
        for inst in reversed(active):
            try:
                fw = inst.root.focus_displayof()
                if fw is not None:
                    return inst
            except Exception:
                pass
        # Fallback: ultima registrata (più recente)
        return active[-1]

    def _count_other_sorter_instances(self):
        """Conta quante altre istanze di image_sorter.py sono in esecuzione."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", "image_sorter"],
                capture_output=True, text=True)
            pids = [p.strip() for p in result.stdout.splitlines() if p.strip()]
            my_pid = str(os.getpid())
            others = [p for p in pids if p != my_pid]
            return len(others)
        except Exception:
            return 0

    def _init_stream_deck(self):
        """Connette il deck solo se nessun'altra istanza lo possiede già."""
        self._owns_deck = False
        lock = os.path.join(SCRIPT_DIR, ".deck_owner.lock")

        # Controlla se un'altra istanza possiede già il deck
        if os.path.isfile(lock):
            try:
                with open(lock) as f:
                    owner_pid = int(f.read().strip())
                # Verifica se il processo owner è ancora vivo
                try:
                    os.kill(owner_pid, 0)   # segnale 0 = solo check esistenza
                    print(f"[StreamDeck] Posseduto dall'istanza PID {owner_pid}, skip")
                    return   # altra istanza attiva — non toccare il deck
                except (ProcessLookupError, PermissionError):
                    pass   # processo morto — il lock è stale, procediamo
            except Exception:
                pass

        # Chiudi StreamController per liberare il device
        try:
            result = subprocess.run(["pgrep", "-f", "streamdeck"],
                                    capture_output=True, text=True)
            if result.stdout.strip():
                subprocess.run(["pkill", "-f", "streamdeck"],
                               capture_output=True)
                time.sleep(1.5)
        except Exception:
            pass

        # Tenta connessione
        for attempt in range(3):
            try:
                sd = StreamDeckManager(self)
                if sd.is_active():
                    self._stream_deck = sd
                    self._owns_deck   = True
                    # Scrivi lock file con il nostro PID
                    try:
                        with open(lock, "w") as f:
                            f.write(str(os.getpid()))
                    except Exception:
                        pass
                    print(f"[StreamDeck] Connesso (owner PID {os.getpid()})")
                    sd.set_mode("idle")
                    return
            except Exception as ex:
                print(f"[StreamDeck] Tentativo {attempt+1}: {ex}")
                time.sleep(1.0)
        print("[StreamDeck] Non disponibile dopo 3 tentativi")

    def _hk_guard(self, fn):
        def _h(e):
            # Non intercettare se il focus è su un campo di testo
            fw = e.widget
            if isinstance(fw, (tk.Entry, tk.Text, tk.Spinbox)):
                return
            # Non intercettare se la barra rinomina è aperta
            if self._is_rename_active():
                return
            # Non intercettare se il focus è dentro un Toplevel aperto
            # (es. DuplicateFinder, FolderBrowser, Settings, DiskAnalyzer)
            try:
                focus_win = fw.winfo_toplevel()
                if focus_win is not self.root:
                    return
            except Exception:
                pass
            # Non intercettare se c'è un Toplevel con grab globale
            for w in self.root.winfo_children():
                try:
                    if (isinstance(w, tk.Toplevel) and
                            w.winfo_viewable() and
                            w.grab_status() == "global"):
                        return
                except Exception:
                    pass
            fn()
        return _h

    def _on_escape_key(self, e=None):
        if self._fullscreen:
            self._toggle_fullscreen()
        else:
            self._quit()

    def _canvas_click(self, event):
        """Click sul canvas: se su badge play di un video, avvia il player."""
        filepath = self._current_file()
        if not filepath or not is_video(filepath):
            return
        # Calcola posizione badge: angolo in basso a sinistra dell'immagine
        if not hasattr(self, '_tk_img') or not self._tk_img:
            return
        try:
            iw = self._tk_img.width()
            ih = self._tk_img.height()
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            ix = max(cw // 2, iw // 2)   # centro x immagine
            iy = max(ch // 2, ih // 2)   # centro y immagine
            # Angolo in basso a sinistra dell'immagine
            img_x0 = ix - iw // 2
            img_y1 = iy + ih // 2
            r  = max(10, min(iw, ih) // 8)
            pad = max(4, r // 3)
            cx = img_x0 + pad + r
            cy = img_y1 - pad - r
            # Controlla se il click è nel cerchio del badge
            dist = ((event.x - cx)**2 + (event.y - cy)**2) ** 0.5
            if dist <= r * 1.3:
                self._play_video()
        except Exception:
            pass

    def _suggest_rename_ext(self, filepath, correct_ext):
        """Mostra un popup che suggerisce di correggere l'estensione del file."""
        if not self.root.winfo_exists():
            return
        if getattr(self, '_suppress_ext_popup_for', None) == filepath:
            return
        cur_ext = os.path.splitext(filepath)[1].lower()
        if cur_ext == correct_ext.lower():
            return
        # Non suggerire tra estensioni equivalenti (es. .jpg <-> .jpeg)
        _equiv_groups = [
            {".jpg", ".jpeg"},
            {".tif", ".tiff"},
        ]
        for group in _equiv_groups:
            if cur_ext in group and correct_ext.lower() in group:
                return

        fname    = os.path.basename(filepath)
        new_name = os.path.splitext(fname)[0] + correct_ext

        # Chiudi eventuale popup precedente
        if hasattr(self, '_ext_popup') and self._ext_popup:
            try: self._ext_popup.destroy()
            except Exception: pass

        win = tk.Toplevel(self.root)
        win.withdraw()
        win.title("")
        win.resizable(False, False)
        win.configure(bg=PANEL_COLOR)
        win.transient(self.root)
        hud_apply(win)
        self._ext_popup = win

        tk.Label(win,
                 text=f"Estensione errata: {cur_ext or '(nessuna)'}  —  "
                      f"il file sembra un {correct_ext.upper()[1:]}",
                 font=("TkFixedFont", 9), bg=PANEL_COLOR,
                 fg=WARNING).pack(padx=14, pady=(10,4))

        def _rename():
            new_path = os.path.join(os.path.dirname(filepath), new_name)
            if os.path.exists(new_path):
                # Chiedi cosa fare
                choice = messagebox.askyesnocancel(
                    "File già esistente",
                    f"Esiste già un file chiamato:\n{new_name}\n\n"
                    f"Sì = sovrascrivi\n"
                    f"No = rinomina con suffisso (_1, _2…)\n"
                    f"Annulla = non fare nulla",
                    parent=win)
                if choice is None:   # Annulla
                    return
                if choice is False:  # No = aggiungi suffisso
                    base, ext = os.path.splitext(new_path)
                    i = 1
                    while os.path.exists(f"{base}_{i}{ext}"):
                        i += 1
                    new_path = f"{base}_{i}{ext}"
                # choice is True = sovrascrivi, new_path rimane invariato
            try:
                os.rename(filepath, new_path)
            except Exception as ex:
                messagebox.showerror("Errore", str(ex), parent=self.root)
                return
            self._suppress_ext_popup_for = new_path
            win.destroy()
            self.images = self._load_images()
            if new_path not in self.images and os.path.isfile(new_path):
                self.images.insert(self.current_index, new_path)
            if new_path in self.images:
                self.current_index = self.images.index(new_path)
            self._show_image()

        bf = tk.Frame(win, bg=PANEL_COLOR)
        bf.pack(padx=14, pady=(0,10))
        tk.Button(bf, text=f"Rinomina in  {new_name}",
                  font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=10,
                  command=_rename).pack(side="left", ipady=4)
        tk.Button(bf, text="Ignora",
                  font=("TkFixedFont", 9), bg=ACCENT_COLOR, fg=TEXT_COLOR,
                  relief="flat", padx=8,
                  command=win.destroy).pack(side="left", padx=(8,0), ipady=4)

        # Posiziona in basso a sinistra
        win.update_idletasks()
        pw = win.winfo_reqwidth()
        ph = win.winfo_reqheight()
        cx = self.root.winfo_rootx() + 20
        cy = self.root.winfo_rooty() + self.root.winfo_height() - ph - 60
        win.geometry(f"+{max(0,cx)}+{max(0,cy)}")
        win.deiconify()
        win.lift()
        # Non rubare il focus — lascia navigare liberamente con le frecce
        # Bind frecce: chiudi popup e naviga
        win.bind("<Right>", lambda e: (
            win.destroy(), self._skip()) if win.winfo_exists() else None)
        win.bind("<Left>",  lambda e: (
            win.destroy(), self._go_back()) if win.winfo_exists() else None)
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<Return>", lambda e: _rename())
        # Auto-chiudi dopo 10 secondi
        win.after(10000, lambda: win.destroy() if win.winfo_exists() else None)

    def _open_edit_with(self, filepath):
        """Apre il file con il programma di modifica configurabile."""
        editor = self.config.get("edit_with", "gimp")
        if not editor.strip():
            editor = "gimp"
        # Popup per cambiare programma al volo
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.title("Modifica con...")
        win.configure(bg=BG_COLOR)
        win.resizable(False, False)
        hud_apply(win)
        win.transient(self.root)

        tk.Label(win, text="Programma:",
                 font=("TkFixedFont", 9), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(padx=16, pady=(12,2), anchor="w")
        var = tk.StringVar(value=editor)
        entry = tk.Entry(win, textvariable=var,
                         font=("TkFixedFont", 10),
                         bg=ACCENT_COLOR, fg=TEXT_COLOR,
                         insertbackground=TEXT_COLOR,
                         relief="flat", bd=4, width=22)
        entry.pack(padx=16, pady=4, ipady=4)
        entry.selection_range(0, tk.END)
        entry.focus_force()

        tk.Label(win, text="Es: gimp, inkscape, darktable, shotwell",
                 font=("TkFixedFont", 7), bg=BG_COLOR,
                 fg=MUTED_COLOR).pack(padx=16, anchor="w")

        save_var = tk.BooleanVar(value=True)
        tk.Checkbutton(win, text="Ricorda per le prossime volte",
                       variable=save_var,
                       font=("TkFixedFont", 8), bg=BG_COLOR, fg=MUTED_COLOR,
                       selectcolor=BG_COLOR, activebackground=BG_COLOR,
                       activeforeground=HUD_CYAN
                       ).pack(padx=16, pady=(4,0), anchor="w")

        msg = tk.Label(win, text="", font=("TkFixedFont", 8),
                       bg=BG_COLOR, fg=HIGHLIGHT)
        msg.pack(padx=16)

        def _open():
            prog = var.get().strip()
            if not prog:
                return
            if save_var.get():
                self.config["edit_with"] = prog
                save_config(self.config)
            try:
                subprocess.Popen([prog, filepath],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                win.destroy()
            except FileNotFoundError:
                msg.config(text=f"'{prog}' non trovato.")
            except Exception as ex:
                msg.config(text=str(ex)[:40])

        bf = tk.Frame(win, bg=BG_COLOR)
        bf.pack(padx=16, pady=(8,12))
        tk.Button(bf, text="Apri",
                  font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=12,
                  command=_open).pack(side="left", padx=(0,8), ipady=4)
        tk.Button(bf, text="Annulla",
                  font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=8,
                  command=win.destroy).pack(side="left", ipady=4)
        entry.bind("<Return>", lambda e: _open())
        win.bind("<Escape>", lambda e: win.destroy())

        win.update_idletasks()
        pw, ph = win.winfo_reqwidth(), win.winfo_reqheight()
        px = self.root.winfo_rootx() + (self.root.winfo_width() - pw) // 2
        py = self.root.winfo_rooty() + (self.root.winfo_height() - ph) // 2
        win.geometry(f"+{max(0,px)}+{max(0,py)}")
        win.deiconify()
        win.grab_set()

    def _toggle_pdf_thumbs(self):
        """Mostra/nasconde il pannello miniature PDF laterale."""
        self._pdf_thumbs_visible = not self._pdf_thumbs_visible
        self.config["pdf_thumbs_open"] = self._pdf_thumbs_visible
        save_config(self.config)
        if hasattr(self, '_pdf_thumbs_btn') and self._pdf_thumbs_btn.winfo_exists():
            self._pdf_thumbs_btn.config(
                bg=HUD_CYAN if self._pdf_thumbs_visible else ACCENT_COLOR,
                fg="#0a1a2e" if self._pdf_thumbs_visible else TEXT_COLOR)
        if self._pdf_thumbs_visible:
            self._show_pdf_panel(self._current_file())
        else:
            self._hide_pdf_panel()

    def _show_pdf_panel(self, filepath):
        """Costruisce e mostra il pannello laterale con le miniature del PDF."""
        if not filepath or not is_pdf(filepath):
            return
        self._hide_pdf_panel()

        total = get_pdf_page_count(filepath)
        if total <= 1:
            return

        panel = tk.Frame(self._img_frame, bg=PANEL_COLOR, width=110)
        panel.grid(row=0, column=0, sticky="nsew", padx=(0,4), pady=0)
        panel.grid_propagate(False)
        panel.rowconfigure(0, weight=1)
        panel.columnconfigure(0, weight=1)
        self._pdf_panel = panel
        self._pdf_thumbs_fp = filepath

        # Canvas scrollabile
        canvas = tk.Canvas(panel, bg=PANEL_COLOR, width=100,
                           highlightthickness=0)
        vsb = tk.Scrollbar(panel, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        inner = tk.Frame(canvas, bg=PANEL_COLOR)
        inner_id = canvas.create_window((0,0), window=inner, anchor="nw")

        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(inner_id, width=e.width))
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Button-4>",      lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>",      lambda e: canvas.yview_scroll(1,  "units"))
        canvas.bind("<MouseWheel>",    lambda e: canvas.yview_scroll(
                                           -1 if e.delta > 0 else 1, "units"))
        # Anche sul frame interno per catturare rotella ovunque nel pannello
        inner.bind("<Button-4>",       lambda e: canvas.yview_scroll(-1, "units"))
        inner.bind("<Button-5>",       lambda e: canvas.yview_scroll(1,  "units"))

        self._pdf_thumb_imgs = []
        self._pdf_thumb_btns = {}  # {page: btn}

        THUMB_W = 90
        THUMB_H = 120

        def _load_thumb_page(page):
            """Carica una miniatura in background."""
            if not self._pdf_panel or not self._pdf_panel.winfo_exists():
                return
            if not (filepath == self._pdf_thumbs_fp):
                return
            try:
                img = get_pdf_preview(filepath, page=page)
                img.thumbnail((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._pdf_thumb_imgs.append(photo)

                def _add_btn(ph=photo, pg=page):
                    if not inner.winfo_exists():
                        return
                    cur = self._pdf_page.get(filepath, 1)
                    bg  = HIGHLIGHT if pg == cur else PANEL_COLOR
                    f   = tk.Frame(inner, bg=bg, padx=2, pady=2)
                    f.pack(fill="x", padx=4, pady=2)
                    btn = tk.Label(f, image=ph, bg=bg, cursor="hand2")
                    btn.pack()
                    lbl = tk.Label(f, text=str(pg),
                                   font=("TkFixedFont", 7),
                                   bg=bg, fg=MUTED_COLOR)
                    lbl.pack()
                    for w in [btn, lbl, f]:
                        w.bind("<Button-1>",
                               lambda e, p=pg: self._go_to_pdf_page(filepath, p))
                        w.bind("<Button-4>",
                               lambda e: canvas.yview_scroll(-1, "units"))
                        w.bind("<Button-5>",
                               lambda e: canvas.yview_scroll(1, "units"))
                    self._pdf_thumb_btns[pg] = f

                self.root.after(0, _add_btn)
            except Exception:
                pass
            # Prossima pagina
            if page < total and filepath == self._pdf_thumbs_fp:
                self.root.after(50, lambda: threading.Thread(
                    target=_load_thumb_page, args=(page+1,), daemon=True).start())

        threading.Thread(target=_load_thumb_page, args=(1,), daemon=True).start()

    def _hide_pdf_panel(self):
        """Nasconde e distrugge il pannello miniature."""
        if self._pdf_panel and self._pdf_panel.winfo_exists():
            self._pdf_panel.destroy()
        self._pdf_panel     = None
        self._pdf_thumbs_fp = None
        self._pdf_thumb_imgs.clear()
        self._pdf_thumb_btns = {}

    def _pdf_thumbs_highlight(self, cur_page):
        """Evidenzia la miniatura della pagina corrente."""
        for page, frame in getattr(self, '_pdf_thumb_btns', {}).items():
            if not frame.winfo_exists():
                continue
            bg = HIGHLIGHT if page == cur_page else PANEL_COLOR
            frame.config(bg=bg)
            for w in frame.winfo_children():
                try: w.config(bg=bg)
                except Exception: pass

    def _go_to_pdf_page(self, filepath, page):
        """Vai alla pagina PDF cliccata nel pannello miniature."""
        self._pdf_page[filepath] = page
        self._show_image()

    def _play_video(self):
        filepath = self._current_file()
        if not filepath or not os.path.isfile(filepath):
            return
        if not is_video(filepath):
            self._toggle_fullscreen()
            return
        # Prova player video dedicati nell'ordine, evita xdg-open che potrebbe
        # aprire Image Sorter stesso se è il programma predefinito
        players = ["mpv", "vlc", "totem", "celluloid", "dragon",
                   "smplayer", "mplayer", "xplayer"]
        launched = False
        for player in players:
            try:
                subprocess.Popen([player, filepath],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                launched = True
                break
            except FileNotFoundError:
                continue
            except Exception:
                continue
        if not launched:
            # Fallback a xdg-open solo se nessun player trovato
            try:
                subprocess.Popen(["xdg-open", filepath],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except Exception as ex:
                messagebox.showerror("Errore",
                    f"Nessun player video trovato.\n"
                    f"Installa mpv o vlc:\n  sudo apt install mpv",
                    parent=self.root)

    def _toggle_header(self):
        """Nasconde/mostra la barra superiore (tasto H)."""
        if self._hdr.winfo_viewable():
            self._hdr.grid_remove()
            if hasattr(self, "_hdr2"): self._hdr2.grid_remove()
        else:
            self._hdr.grid()
            if hasattr(self, "_hdr2"): self._hdr2.grid()
        self._show_image()

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            # Nasconde header e sidebar, canvas a tutta finestra
            self.root.attributes("-fullscreen", True)
            self._hdr.grid_remove()
            if hasattr(self, "_hdr2"): self._hdr2.grid_remove()
            # Salva stato sidebar e nascondila
            self._fs_sidebar_mode = get_sidebar_mode(self.config)
            self.sidebar.grid_remove()
            if self.sidebar_popup and self.sidebar_popup.win.winfo_exists():
                self.sidebar_popup.win.withdraw()
            # Canvas senza padding
            self.canvas.master.grid_configure(padx=0, pady=0)
            if self._fs_btn_ref:
                self._fs_btn_ref.config(bg=HUD_CYAN, fg="#0a1a2e")
        else:
            # Ripristina tutto
            self.root.attributes("-fullscreen", False)
            self._hdr.grid()
            if hasattr(self, "_hdr2"): self._hdr2.grid()
            self.canvas.master.grid_configure(padx=8, pady=8)
            # Ripristina sidebar
            if self.sidebar_popup and self.sidebar_popup.win.winfo_exists():
                self.sidebar_popup.win.deiconify()
            mode = get_sidebar_mode(self.config)
            if mode == "inline":
                self.sidebar.grid()
            if self._fs_btn_ref:
                self._fs_btn_ref.config(bg=ACCENT_COLOR, fg=TEXT_COLOR)

    def _next_preset(self):
        names = list(self.config["presets"].keys())
        if len(names) < 2:
            return
        idx = names.index(self.config["active_preset"]) if self.config["active_preset"] in names else 0
        self.config["active_preset"] = names[(idx + 1) % len(names)]
        save_config(self.config)
        self.labels = self.config["presets"][self.config["active_preset"]]
        self._build_sidebar()
        self._update_preset_label()
        self._toast_preset(self.config["active_preset"])

    def _prev_preset(self):
        names = list(self.config["presets"].keys())
        if len(names) < 2:
            return
        idx = names.index(self.config["active_preset"]) if self.config["active_preset"] in names else 0
        self.config["active_preset"] = names[(idx - 1) % len(names)]
        save_config(self.config)
        self.labels = self.config["presets"][self.config["active_preset"]]
        self._build_sidebar()
        self._update_preset_label()
        self._toast_preset(self.config["active_preset"])

    def _quick_set_dest(self, key, preset_name, event=None):
        """Popup veloce per cambiare la destinazione di un tasto (tasto destro sulla sidebar)."""
        # Usa come parent la finestra che contiene il widget cliccato
        # così il popup viene sopra il deck se aperto dal deck
        if event and hasattr(event, 'widget'):
            try:
                parent_win = event.widget.winfo_toplevel()
            except Exception:
                parent_win = self.root
        else:
            parent_win = self.root
        win = tk.Toplevel(parent_win)
        win.withdraw()
        win.title(f"Destinazione tasto {key}")
        win.configure(bg=BG_COLOR)
        win.resizable(False, False)
        hud_apply(win)
        # Forza il popup sopra il parent (es. deck)
        win.transient(parent_win)
        win.lift()

        slots = self.config["presets"].get(preset_name, {})
        cur_path  = slots.get(key, {}).get("path",  "") if key in slots else ""
        cur_label = slots.get(key, {}).get("label", "") if key in slots else ""

        tk.Label(win, text=f"Preset: {preset_name}  —  Tasto {key}",
                 font=("TkFixedFont", 9, "bold"), bg=BG_COLOR,
                 fg=HUD_CYAN).pack(padx=16, pady=(12,2))

        tk.Label(win, text="Etichetta:", font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR, anchor="w").pack(
                 fill="x", padx=16, pady=(6,0))
        lbl_var = tk.StringVar(value=cur_label)
        tk.Entry(win, textvariable=lbl_var, font=("TkFixedFont", 9),
                 bg=ACCENT_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR,
                 relief="flat", bd=4).pack(fill="x", padx=16, ipady=3)

        tk.Label(win, text="Percorso destinazione:", font=("TkFixedFont", 8),
                 bg=BG_COLOR, fg=MUTED_COLOR, anchor="w").pack(
                 fill="x", padx=16, pady=(8,0))
        path_var = tk.StringVar(value=cur_path)
        path_row = tk.Frame(win, bg=BG_COLOR)
        path_row.pack(fill="x", padx=16, pady=(2,0))
        path_row.columnconfigure(0, weight=1)
        path_entry = tk.Entry(path_row, textvariable=path_var,
                              font=("TkFixedFont", 9),
                              bg=ACCENT_COLOR, fg=TEXT_COLOR,
                              insertbackground=TEXT_COLOR,
                              relief="flat", bd=4)
        path_entry.grid(row=0, column=0, sticky="ew", ipady=3)
        def _browse():
            from tkinter import filedialog
            d = filedialog.askdirectory(parent=win, initialdir=path_var.get() or
                                        os.path.expanduser("~"))
            if d:
                path_var.set(d)
        tk.Button(path_row, text="...", font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=6,
                  command=_browse).grid(row=0, column=1, padx=(4,0), ipady=3)

        msg = tk.Label(win, text="", font=("TkFixedFont", 8),
                       bg=BG_COLOR, fg=HIGHLIGHT)
        msg.pack(padx=16)

        def _save():
            new_path  = path_var.get().strip()
            new_label = lbl_var.get().strip()
            if new_path and not os.path.isdir(new_path):
                try:
                    os.makedirs(new_path, exist_ok=True)
                except Exception as ex:
                    msg.config(text=f"Errore: {str(ex)[:40]}")
                    return
            if key not in self.config["presets"][preset_name]:
                self.config["presets"][preset_name][key] = {}
            self.config["presets"][preset_name][key]["path"]  = new_path
            self.config["presets"][preset_name][key]["label"] = new_label
            save_config(self.config)
            self.labels = self.config["presets"][self.config["active_preset"]]
            self._build_sidebar()
            if getattr(self, '_stream_deck', None):
                self._stream_deck.refresh_all()
            win.destroy()

        bf = tk.Frame(win, bg=BG_COLOR)
        bf.pack(padx=16, pady=(8,14), fill="x")
        tk.Button(bf, text="Salva", font=("TkFixedFont", 9, "bold"),
                  bg=SUCCESS, fg="white", relief="flat", padx=10,
                  command=_save).pack(side="left", padx=(0,6), ipady=4)
        tk.Button(bf, text="Annulla", font=("TkFixedFont", 9),
                  bg=ACCENT_COLOR, fg=TEXT_COLOR, relief="flat", padx=10,
                  command=win.destroy).pack(side="left", ipady=4)
        path_entry.bind("<Return>",   lambda e: _save())
        path_entry.bind("<KP_Enter>", lambda e: _save())
        win.bind("<Return>",   lambda e: _save())
        win.bind("<KP_Enter>", lambda e: _save())
        win.bind("<Escape>", lambda e: win.destroy())

        win.update_idletasks()
        pw = win.winfo_reqwidth()
        ph = win.winfo_reqheight()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        if event and hasattr(event, 'x_root'):
            # Posiziona vicino al punto di click, ma sempre visibile a schermo
            px = min(event.x_root + 4, sw - pw - 8)
            py = min(event.y_root + 4, sh - ph - 8)
        else:
            px = self.root.winfo_rootx() + (self.root.winfo_width()  - pw) // 2
            py = self.root.winfo_rooty() + (self.root.winfo_height() - ph) // 2
        win.geometry(f"+{px}+{py}")
        win.deiconify()
        win.lift()
        win.focus_set()
        win.grab_set()
        # Assicura che rimanga sopra il parent dopo il grab
        win.after(10, win.lift)
        win.after(50, win.lift)

    def _change_preset(self):
        """Compatibilità: apre impostazioni sulla tab preset."""
        self._open_settings(tab="preset")

    def _open_folder_config(self):
        """Compatibilità: apre impostazioni sulla tab destinazioni."""
        self._open_settings(tab="dest")

    def _open_settings(self, tab="preset"):
        # Se già aperta, chiudi
        if (self._settings_dialog and
                self._settings_dialog.win.winfo_exists()):
            self._settings_dialog.win.destroy()
            return
        dlg = SettingsDialog(self.root, self, initial_tab=tab)
        self._settings_dialog = dlg
        if self._settings_btn_ref:
            self._settings_btn_ref.config(bg=HUD_CYAN, fg="#0a1a2e")
        # Callback alla chiusura per resettare bottone e riferimento
        def _on_close_settings():
            self._settings_dialog = None
            if self._settings_btn_ref:
                self._settings_btn_ref.config(bg=HIGHLIGHT, fg="white")
            dlg.win.destroy()
        dlg.win.protocol("WM_DELETE_WINDOW", _on_close_settings)

# =============================================================================
# AVVIO
# =============================================================================

def main():

    log_file = os.path.join(SCRIPT_DIR, "image_sorter_error.log")

    # Avvisa se Wayland nativo senza XWayland
    if (os.environ.get("XDG_SESSION_TYPE","").lower() == "wayland"
            and not os.environ.get("DISPLAY")):
        print("[WARN] Sessione Wayland senza DISPLAY/XWayland.")
        print("[WARN] Prova: DISPLAY=:0 python3 image_sorter.py")

    root = tk.Tk(className="image_sorter")
    root.withdraw()

    root._icon_refs_main = []   # popolato in background dopo deiconify

    # Cattura TUTTI gli errori tkinter (anche quelli nei callback/eventi)
    def _tk_error_handler(exc, val, tb_obj):
        import datetime
        text = "".join(traceback.format_exception(exc, val, tb_obj))
        entry = f"\n{'='*60}\n{datetime.datetime.now()}\n{text}"
        with open(log_file, "a") as f:
            f.write(entry)
        # Mostra solo la riga esatta dell'errore nel toast, non aprire messagebox
        # che potrebbe causare altri problemi
        last_line = [l.strip() for l in text.splitlines() if l.strip()][-1]
        file_line = next((l for l in text.splitlines() if 'image_sorter.py' in l), '')
        print(f"[TK ERROR] {file_line} | {last_line}")
    root.report_callback_exception = _tk_error_handler

    start_file = None
    source     = None

    if len(sys.argv) > 1:
        # Avviato da riga di comando o doppio click su file/cartella
        arg = sys.argv[1]
        if os.path.isfile(arg):
            arg_abs = os.path.abspath(arg)
            source  = os.path.dirname(arg_abs)
            ext     = os.path.splitext(arg)[1].lower()
            # Accetta il file come start_file se:
            # 1. estensione nota, oppure
            # 2. magic bytes lo riconoscono come media
            if ext in MEDIA_EXTENSIONS or detect_media_type(arg_abs) in MEDIA_EXTENSIONS:
                start_file = arg_abs
            else:
                # Potrebbe essere un'immagine con estensione sbagliata:
                # prova comunque a caricarla — la verifica avverrà in _load_in_thread
                start_file = arg_abs
        elif os.path.isdir(arg):
            source = arg
        else:
            messagebox.showerror("Errore", f"Percorso non valido:\n{arg}", parent=root)
    else:
        # Avvio normale: usa ultima cartella salvata o ~/Immagini
        _cfg  = load_config()
        _last = _cfg.get("last_source", "")
        if _last and os.path.isdir(_last):
            source = _last
        else:
            # Prova le cartelle immagini standard
            for _candidate in [
                os.path.expanduser("~/Immagini"),
                os.path.expanduser("~/Pictures"),
                os.path.expanduser("~"),
            ]:
                if os.path.isdir(_candidate):
                    source = _candidate
                    break

    root.deiconify()
    root.lift()

    # Carica icone in background
    def _load_icons_bg():
        refs = []
        if os.path.isfile(ICON_FILE):
            try:
                from PIL import Image, ImageTk as _ITk
                _base = Image.open(ICON_FILE).convert("RGBA")
                for _sz in (256, 128, 48, 32, 16):
                    _sp = os.path.join(SORTER_ICONS_DIR, f"image_sorter_icon_{_sz}.png")
                    _im = Image.open(_sp).convert("RGBA") if os.path.isfile(_sp)                           else _base.resize((_sz, _sz), Image.LANCZOS)
                    refs.append(_ITk.PhotoImage(_im, master=root))
            except Exception:
                pass
        def _apply():
            if refs:
                root._icon_refs_main = refs
                try:
                    root.iconphoto(True, *refs)
                    root.wm_iconname("Image Sorter")
                except Exception:
                    pass
        root.after(0, _apply)
    import threading as _th
    _th.Thread(target=_load_icons_bg, daemon=True).start()

    try:
        ImageSorter(root, source or None, start_file=start_file)
    except Exception:
        tb = traceback.format_exc()
        # Scrivi sul log
        with open(log_file, "w") as f:
            f.write(tb)
        # Mostra finestra con testo selezionabile e percorso del log
        err_win = tk.Toplevel(root)
        err_win.title("Errore avvio")
        err_win.configure(bg=BG_COLOR)
        err_win.geometry("700x400")
        err_win.resizable(True, True)
        tk.Label(err_win,
                 text=f"Errore imprevisto. Log salvato in:\n{log_file}",
                 font=("TkFixedFont", 9), bg=BG_COLOR, fg=WARNING,
                 justify="left").pack(padx=14, pady=(12, 4), anchor="w")
        txt = tk.Text(err_win, font=("TkFixedFont", 9),
                      bg=PANEL_COLOR, fg=TEXT_COLOR,
                      relief="flat", wrap="word")
        txt.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        txt.insert("1.0", tb)
        txt.config(state="disabled")   # leggibile ma non modificabile
        txt.bind("<Button-4>", lambda e: txt.yview_scroll(-1, "units"))
        txt.bind("<Button-5>", lambda e: txt.yview_scroll(1, "units"))
        txt.bind("<MouseWheel>", lambda e: txt.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        tk.Button(err_win, text="Chiudi", font=("TkFixedFont", 9),
                  bg=HIGHLIGHT, fg="white", relief="flat",
                  command=root.destroy).pack(pady=(0, 12))
        root.mainloop()
        sys.exit(1)

    root.mainloop()

if __name__ == "__main__":
    main()