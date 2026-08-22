#!/usr/bin/env python3
# deck_core.py — logica dello Stream Deck indipendente dall'interfaccia
# grafica di Image Sorter.
#
# Estratto da image_sorter.py: contiene tutto cio' che serve a gestire
# il dispositivo fisico SENZA bisogno di una finestra Tkinter aperta —
# connessione USB, disegno delle immagini dei tasti, e le sette azioni
# idle che non richiedono un'istanza di Image Sorter in esecuzione
# (folder, app, hotkey, url, mute, text, page).
#
# Le altre due azioni idle ("command", i 28 comandi diretti, e "sorter",
# apri Image Sorter su una cartella) richiedono per natura un'istanza
# grafica viva — restano gestite da image_sorter.py, che importa questo
# modulo e lo usa come base.
#
# Pensato per essere importabile sia da image_sorter.py sia da un
# eventuale processo separato (demone) che tenga vivo il deck anche a
# Image Sorter chiuso — nessuna delle due parti sa nulla dell'altra:
# StreamDeckManager riceve un oggetto "sorter" generico, di cui usa solo
# tre attributi (config, labels, root).
#
# L'instradamento verso "quale finestra ha il fuoco" NON usa piu' un
# riferimento Python diretto (impossibile fra processi separati, vedi
# la sezione INSTRADAMENTO FRA PIU' ISTANZE piu' sotto): passa da un
# file condiviso e da una casella per processo, cosi' funziona anche
# quando la finestra a fuoco e quella che possiede il deck sono due
# processi del sistema operativo diversi.
#
# VERSION = "1.36.9" — allineata a image_sorter.py al momento
# dell'estrazione; da qui in poi le due versioni possono divergere sul
# terzo numero se si corregge solo uno dei due file.
VERSION = "1.1.0"

import os
import sys
import io
import json
import time
import math
import subprocess
import traceback

from PIL import Image, ImageDraw, ImageFont

# --- PERCORSI ------------------------------------------------------------
# Duplicati (non importati) da image_sorter.py apposta: questo modulo
# deve restare importabile da solo, senza dover avviare l'intero
# programma. I due file vivono sempre nella stessa cartella, quindi il
# calcolo da' lo stesso risultato in entrambi.
SCRIPT_DIR       = os.path.dirname(os.path.abspath(
                       sys.executable if getattr(sys, 'frozen', False)
                       else __file__))
BUNDLE_DIR       = getattr(sys, '_MEIPASS', SCRIPT_DIR)
SORTER_ICONS_DIR = os.path.join(BUNDLE_DIR, "sorter_icons")
DECK_ICONS_DIR   = os.path.join(SCRIPT_DIR, "deck_icons")


def _deck_icons_dir():
    """Cartella delle icone personalizzate del deck, creata al primo
    utilizzo. Se la creazione fallisce si ripiega su SORTER_ICONS_DIR,
    che esiste sempre."""
    try:
        os.makedirs(DECK_ICONS_DIR, exist_ok=True)
        return DECK_ICONS_DIR
    except OSError:
        return SORTER_ICONS_DIR


# --- TASTI E COLORI --------------------------------------------------------
# Duplicati da image_sorter.py per lo stesso motivo dei percorsi sopra:
# sono la disposizione fisica di una tastiera a 10 tasti (1-9-0) e i
# colori assegnati ad ognuno, usati per disegnare le immagini dei tasti
# in modalita' preset. Valori fissi, non cambiano da soli — se si
# modificano in image_sorter.py vanno aggiornati anche qui.
KEYS = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "0"]
KEY_COLORS = [
    "#e94560", "#f5a623", "#7ed321",
    "#4a90e2", "#9b59b6", "#1abc9c",
    "#e67e22", "#2ecc71", "#3498db",
    "#e74c3c",
]


def open_in_filemanager(filepath):
    """Apre il file manager nella cartella del file, evidenziandolo se
    possibile. Duplicata da image_sorter.py: e' usata sia dai comandi
    idle "folder" sia da altre parti del programma, e deve restare
    disponibile qui senza importare l'intero image_sorter.py."""
    if not filepath:
        return
    filepath = os.path.abspath(filepath)
    folder   = os.path.dirname(filepath) if os.path.isfile(filepath) else filepath

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

    for fm in ["nautilus", "nemo", "thunar", "dolphin", "pcmanfm",
               "caja", "spacefm", "xdg-open"]:
        if subprocess.run(["which", fm], capture_output=True).returncode == 0:
            try:
                target = filepath if fm in ("nautilus","nemo","dolphin") else folder
                subprocess.Popen([fm, target],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                continue

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

def get_command_icon(command_id, size=72):
    """Carica l'icona di un comando diretto (action="command"), con
    fallback None se il file manca."""
    fp = os.path.join(DECK_ICONS_DIR, f"cmd_{command_id}.png")
    if os.path.isfile(fp):
        try:
            img = Image.open(fp).convert("RGB")
            return img.resize((size, size), Image.Resampling.LANCZOS)
        except Exception:
            pass
    return None


# --- Metadata (rating / colorlabel), per i tasti "rating"/"color_label" ----
# Import dinamico dal percorso esatto, stesso motivo di SCRIPT_DIR sopra:
# questo modulo deve restare importabile da solo (es. da un demone), senza
# fare affidamento su sys.path. Se manca, i due tasti restano disegnati
# ma sempre "spenti" (_render_key_idle lo gestisce), non ha senso bloccare
# il resto del deck per questo.
try:
    import importlib.util as _ilu_ms
    _ms_path = os.path.join(SCRIPT_DIR, "metadata_store.py")
    _ms_spec = _ilu_ms.spec_from_file_location("metadata_store", _ms_path)
    metadata_store = _ilu_ms.module_from_spec(_ms_spec)
    _ms_spec.loader.exec_module(metadata_store)
except Exception:
    metadata_store = None


# --- AZIONI IDLE -------------------------------------------------------------
# Tipi di azione per i tasti idle. "command" e "sorter" compaiono qui per
# completezza dell'elenco mostrato nell'editor, ma la loro ESECUZIONE
# resta in image_sorter.py (richiedono un'istanza grafica viva) — vedi
# execute_headless_action() piu' sotto, che gestisce solo le altre sette.
# "rating" e "color_label" sono nella stessa situazione: leggono/scrivono
# il file ATTUALMENTE aperto in Image Sorter (sorter._current_file()),
# quindi la loro esecuzione resta anch'essa in image_sorter.py.
IDLE_ACTION_TYPES = [
    ("folder",  "Apri cartella"),
    ("app",     "Apri applicazione"),
    ("hotkey",  "Scorciatoia tastiera"),
    ("url",     "Apri URL"),
    ("mute",    "Muto / smuto audio"),
    ("sorter",  "Image Sorter su cartella"),
    ("page",    "Cambia pagina"),
    ("text",    "Scrivi testo (xdotool)"),
    ("command", "Comando di Image Sorter"),
    ("rating",      "Valutazione (stella)"),
    ("color_label", "Colore etichetta"),
]
IDLE_ACTION_LABELS = {k: v for k, v in IDLE_ACTION_TYPES}

# Id ed etichette dei 28 comandi diretti — solo i DATI (id, etichetta
# italiana), niente funzioni: le funzioni sono legate a metodi di
# ImageSorter (ruota, zoom, file successivo...) e vivono per forza in
# image_sorter.py, che costruisce DECK_COMMAND_FUNCS a partire da questi
# stessi id, cosi' i due elenchi non possono disallinearsi in silenzio.
DECK_COMMAND_IDS = [
    ("next_file",         "File successivo"),
    ("prev_file",         "File precedente"),
    ("rotate_cw",         "Ruota 90 gradi orario"),
    ("rotate_ccw",        "Ruota 90 gradi antiorario"),
    ("delete_current",    "Elimina (doppia pressione)"),
    ("delete_previous",   "Elimina precedente (Ctrl+Canc)"),
    ("undo_last",         "Annulla ultimo spostamento"),
    ("rename_current",    "Rinomina file corrente"),
    ("convert_jpg",       "Converti in JPG"),
    ("copy_path",         "Copia percorso file corrente"),
    ("open_filemanager",  "Apri cartella nel file manager"),
    ("copy_gps",          "Copia posizione GPS"),
    ("show_map",          "Mostra posizione su mappa"),
    ("zoom_fit",          "Adatta al canvas"),
    ("zoom_original",     "Dimensione originale"),
    ("zoom_in",           "Zoom avanti"),
    ("zoom_out",          "Zoom indietro"),
    ("toggle_info",       "Mostra/nascondi info EXIF"),
    ("toggle_header",     "Mostra/nascondi intestazione"),
    ("toggle_fullscreen", "Schermo intero"),
    ("toggle_sidebar",    "Mostra/nascondi sidebar"),
    ("toggle_keypad",     "Apri/chiudi il deck software"),
    ("toggle_browser",    "Apri/chiudi il browser cartelle"),
    ("open_new_source",   "Scegli nuova cartella"),
    ("open_timeline",     "Apri/chiudi Timeline"),
    ("open_history",      "Apri/chiudi storico operazioni"),
    ("open_settings",     "Apri/chiudi impostazioni"),
    ("next_preset",       "Preset successivo"),
    ("prev_preset",       "Preset precedente"),
    ("send_to_editor",    "Invia a modifica (programma configurato)"),
    ("open_resize",       "Ridimensiona... (apre il popup)"),
]
DECK_COMMAND_LABELS = {cid: lbl for cid, lbl in DECK_COMMAND_IDS}


# --- INSTRADAMENTO FRA PIU' ISTANZE ------------------------------------------
# Ogni finestra di Image Sorter e' un processo separato del sistema
# operativo (nessuna funzione "nuova finestra" ne apre una seconda dentro
# lo stesso interprete). Questo significa che sapere "quale finestra ha
# il fuoco" non basta per farle eseguire un comando: un oggetto Python di
# un processo non e' raggiungibile da un altro processo, per costruzione.
# Servono due pezzi distinti:
#   1) un file che dice CHI ha il fuoco adesso (announce_focus/
#      get_focused_pid) — aggiornato solo quando una finestra lo
#      guadagna, non ad ogni istante
#   2) una "casella" per processo dove lasciare il comando da eseguire
#      (send_to_inbox/poll_inbox) — ogni istanza controlla solo la
#      propria, periodicamente
# Chi possiede il deck fisico decide a chi instradare (resolve_target_pid),
# ma l'esecuzione vera avviene sempre nel processo bersaglio, mai a
# distanza: e' quel processo stesso, controllando la propria casella, a
# chiamare il proprio _deck_execute_action() su se stesso.

# --- PROPRIETA' DEL DECK FISICO (lock file) -------------------------------
# Un solo processo alla volta puo' avere il dispositivo USB aperto — non e'
# una scelta di disegno, e' un limite dell'hardware. Il file di lock
# arbitra chi ce l'ha, e ora distingue ANCHE il TIPO di proprietario
# ("gui" o "daemon"): serve a decidere se cedere il posto a chi lo chiede.
# Una finestra di Image Sorter non cede mai a un'altra finestra (si
# comportano da pari, la prima arrivata vince e basta) — ma un demone
# in background deve SEMPRE cedere il passo a una finestra che si apre,
# perche' l'utente davanti allo schermo viene prima di un processo
# silenzioso. Il verso opposto non vale: il demone non tenta mai di
# strappare il deck a una finestra aperta, si limita ad aspettare che
# si liberi.
LOCK_FILE = os.path.join(SCRIPT_DIR, ".deck_owner.lock")


def read_lock():
    """Legge il file di lock, ritorna {"pid":.., "kind":.., "ts":..} o
    None se manca, e' illeggibile, o il processo che lo ha scritto non
    esiste piu'. Tollera anche il formato vecchio (solo un numero di PID
    scritto come testo semplice, senza kind/ts) per non rompersi su un
    file di lock rimasto da una versione precedente del programma."""
    if not os.path.isfile(LOCK_FILE):
        return None
    try:
        with open(LOCK_FILE) as f:
            raw = f.read().strip()
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                # Un numero puro (il vecchio formato) e' JSON valido di
                # per se' — json.loads("536") non solleva nessun errore,
                # ritorna semplicemente l'intero 536. Bisogna controllare
                # il TIPO del risultato, non solo se il parsing riesce.
                raise ValueError("formato vecchio: non e' un dizionario")
        except (ValueError, json.JSONDecodeError):
            # Formato vecchio: solo il PID come testo semplice.
            data = {"pid": int(raw), "kind": "gui", "ts": 0}
        pid = data.get("pid")
    except Exception:
        return None
    if not _pid_alive(pid):
        return None
    return data


def write_lock(kind):
    """Scrive il lock col PID di QUESTO processo. kind e' "gui" (una
    finestra di Image Sorter) o "daemon" (il processo in background)."""
    try:
        with open(LOCK_FILE, "w") as f:
            json.dump({"pid": os.getpid(), "kind": kind, "ts": time.time()}, f)
        return True
    except Exception:
        return False


def release_lock_if_mine():
    """Toglie il lock, ma solo se e' ancora il nostro — non si tocca mai
    il lock di qualcun altro, anche per errore."""
    data = read_lock()
    if data and data.get("pid") == os.getpid():
        try:
            os.unlink(LOCK_FILE)
        except Exception:
            pass


def request_release(pid):
    """Chiede al processo pid (un demone) di rilasciare il deck: stessa
    casella gia' usata per instradare i comandi, con un'azione speciale
    che non e' un vero comando idle. Il demone la riconosce controllando
    la propria casella nel suo giro periodico, esattamente come farebbe
    con qualunque altro comando instradato."""
    send_to_inbox(pid, {"action": "__release_deck__"})


FOCUS_FILE          = os.path.join(SCRIPT_DIR, ".deck_focus.json")
_INBOX_FILE_PATTERN = os.path.join(SCRIPT_DIR, ".deck_inbox_{pid}.json")

FOCUS_MAX_AGE_S = 30   # oltre questa eta' il file di focus si considera
                       # scaduto: se nessuna finestra ha guadagnato il
                       # fuoco da piu' di cosi', meglio eseguire in loco
                       # (dal proprietario del deck) che fidarsi di un
                       # dato vecchio
INBOX_MAX_AGE_S = 5    # un comando rimasto in casella piu' di cosi' non
                       # e' mai stato consumato — il processo bersaglio
                       # puo' essersi chiuso nel frattempo — e va
                       # scartato invece di eseguirlo in ritardo su
                       # un'immagine che nel frattempo e' cambiata


def _pid_alive(pid):
    """True se un processo con questo PID esiste ancora. Non manda
    nessun segnale vero: il segnale 0 su Unix serve solo a verificare
    l'esistenza del processo, senza alcun effetto su di lui."""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def announce_focus():
    """Da chiamare quando la finestra di QUESTA istanza guadagna il
    fuoco (evento <FocusIn> su root). Sovrascrive il file condiviso col
    proprio PID: l'ultima istanza che lo scrive e' quella che vince,
    esattamente il significato di "ultima cliccata"."""
    try:
        with open(FOCUS_FILE, "w") as f:
            json.dump({"pid": os.getpid(), "ts": time.time()}, f)
    except Exception:
        pass


def get_focused_pid(max_age=FOCUS_MAX_AGE_S):
    """Legge il file di focus e ritorna il PID che l'ha scritto per
    ultimo, o None se il file manca, e' illeggibile, troppo vecchio, o
    il processo che lo ha scritto non esiste piu'."""
    try:
        with open(FOCUS_FILE) as f:
            data = json.load(f)
        pid = data.get("pid")
        ts  = data.get("ts", 0)
    except Exception:
        return None
    if time.time() - ts > max_age:
        return None
    if not _pid_alive(pid):
        return None
    return pid


def resolve_target_pid():
    """A chi instradare un comando idle: il PID con il fuoco piu'
    recente, se e' vivo e diverso dal proprio — altrimenti il proprio
    (comportamento storico: esegui dove sei, che e' anche la scelta
    giusta se nessun'altra finestra e' piu' recente o se questa stessa
    istanza e' quella a fuoco)."""
    me = os.getpid()
    other = get_focused_pid()
    return other if (other and other != me) else me


def send_to_inbox(pid, action_dict):
    """Lascia un comando nella casella dell'istanza pid, che lo
    eseguira' al prossimo giro del proprio poll_inbox()."""
    path = _INBOX_FILE_PATTERN.format(pid=pid)
    try:
        with open(path, "w") as f:
            json.dump({"action": action_dict, "ts": time.time()}, f)
    except Exception:
        pass


def poll_inbox():
    """Legge e consuma il comando in attesa per QUESTO processo, se
    c'e' e non e' troppo vecchio. Va chiamata periodicamente (un
    root.after ricorrente) da ogni istanza — non solo dal proprietario
    del deck, perche' e' proprio un'ALTRA istanza a dover eseguire il
    comando instradato a lei.

    Il file viene sempre cancellato se esiste, anche quando scartato per
    eta': un comando vecchio non consumato non deve restare li' per
    sempre in attesa del prossimo giro.
    """
    path = _INBOX_FILE_PATTERN.format(pid=os.getpid())
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        data = None
    try:
        os.unlink(path)
    except Exception:
        pass
    if not data:
        return None
    if time.time() - data.get("ts", 0) > INBOX_MAX_AGE_S:
        return None
    return data.get("action")


def _normalize_hotkey(param):
    """Corregge un difetto di aspettativa comune con xdotool: per lui
    "C" e "c" sono due simboli DIVERSI — "C" significa "il tasto C con
    Shift gia' premuto", non "il tasto C". Scrivere "Ctrl+C" pensando a
    "Ctrl piu' la lettera C" mandava in realta' Ctrl+Shift+c, una
    combinazione diversa da quella voluta (e spesso gia' presa da
    qualcos'altro, per esempio "copia con selezione" in alcuni terminali
    invece del semplice "copia").

    Solo i pezzi di UNA lettera sola vengono messi in minuscolo — quelli
    sono gli unici dove maiuscolo/minuscolo indica solo "con Shift o
    senza", non fa parte del nome del tasto. I nomi di tasti speciali
    (Return, Escape, F1, Page_Up...) restano esattamente come scritti:
    la loro capitalizzazione e' parte del nome vero in X11, non
    un'indicazione di maiuscolo.
    """
    if not param:
        return param
    parti = param.split("+")
    normalizzate = [p.lower() if len(p) == 1 and p.isalpha() else p
                    for p in parti]
    return "+".join(normalizzate)


def execute_headless_action(action_dict, sorter=None):
    """Esegue un'azione idle che NON richiede un'istanza grafica.

    Gestisce folder/app/hotkey/url/mute/page/text. "command" e "sorter"
    sono compiti di image_sorter.py (che li intercetta PRIMA di
    chiamare questa funzione, se ha un'istanza viva a cui affidarli) —
    qui vengono ignorati silenziosamente, cosi' un demone senza nessuna
    finestra aperta puo' chiamare questa funzione direttamente su
    QUALUNQUE azione idle, senza doverle filtrare prima: quelle che non
    puo' gestire semplicemente non fanno nulla, invece di sollevare un
    errore.
    """
    if not action_dict:
        return
    kind  = action_dict.get("action", "")
    param = action_dict.get("param", "")

    def _run(cmd):
        """Lancia un comando esterno senza aspettarlo (fire-and-forget).

        Segnala solo il caso "il programma non e' installato"
        (FileNotFoundError, sollevato in modo SINCRONO da Popen() stesso,
        prima ancora che il processo parta — non serve nessun thread in
        piu' per saperlo). Non controlla piu' se il comando, una volta
        partito, e' anche riuscito: lo faceva con un thread dedicato, ma
        quel thread veniva creato proprio mentre si e' dentro la callback
        del thread della libreria dello Stream Deck che rileva la
        pressione del tasto fisico — il sospetto principale per un
        crash osservato SOLO con Image Sorter aperto (mai con il demone
        da solo, che ha molti meno thread attivi insieme). Non e'
        confermato con certezza — un'assertion fallita dentro libusb non
        si puo' diagnosticare da qui — ma e' l'unica cosa cambiata di
        recente in questo punto, quindi si arretra per prima.
        """
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            print(f"[deck] comando non trovato: {cmd[0]!r} "
                  f"(azione '{kind}') — installalo per usare questa "
                  f"funzione del deck")
        except Exception as ex:
            print(f"[deck] azione '{kind}' fallita ad avviarsi: {ex}")

    if kind == "folder":
        open_in_filemanager(param)
    elif kind == "app":
        _run(param.split())
    elif kind == "hotkey":
        _run(["xdotool", "key", _normalize_hotkey(param)])
    elif kind == "url":
        _run(["xdg-open", param])
    elif kind == "mute":
        _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
    elif kind == "page":
        pass   # gestita dentro StreamDeckManager (idle_next_page/prev)
    elif kind == "text":
        _run(["xdotool", "type", "--clearmodifiers", param])
    # "command", "sorter", "rating", "color_label": intenzionalmente
    # ignorate qui, vedi sopra.


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
    # Riga 1: [7][8][9][<<             ][>>      ]
    # Riga 2: [4][5][6][^preset prev   ][vpreset ]
    # Riga 3: [1][2][3][0=preset attivo][Canc    ]
    LAYOUT = {
        0:  ("key", "7"),
        1:  ("key", "8"),
        2:  ("key", "9"),
        3:  ("nav", "left"),
        4:  ("nav", "right"),
        5:  ("key", "4"),
        6:  ("key", "5"),
        7:  ("key", "6"),
        8:  ("preset_prev",),
        9:  ("preset_next",),
        10: ("key", "1"),
        11: ("key", "2"),
        12: ("key", "3"),
        13: ("key", "0"),
        14: ("delete",),
    }

    # Colori azioni speciali (R, G, B) 0-255
    COLOR_FLASH   = (255, 255, 255)

    def __init__(self, sorter, action_executor=None):
        self.sorter       = sorter
        self.deck         = None
        self._active      = False
        self._mode        = "idle"     # "preset" | "idle" — default idle
        self._idle_page   = 0          # pagina corrente in idle
        self._deck_info   = {}         # info modello: key_count, rows, cols
        # Chi esegue davvero un'azione idle. Chi costruisce questo oggetto
        # DENTRO image_sorter.py passa il proprio dispatcher, che sa gestire
        # anche "command" e "sorter" (richiedono un'istanza grafica). Senza
        # nessuno che lo fornisca — un demone senza finestre, per esempio —
        # si ripiega su execute_headless_action, che quelle due le ignora
        # in silenzio invece di sollevare un errore.
        self._action_executor = action_executor or execute_headless_action
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
            # Niente deck.reset(): cancella tutte le immagini prima di
            # ridisegnarle, causando un lampeggio a vuoto visibile ogni
            # volta che il possesso passa da un processo all'altro
            # (demone <-> Image Sorter). refresh_all(), chiamato subito
            # sotto, riscrive comunque OGNI tasto uno per uno — se il
            # contenuto e' lo stesso di prima (config condivisa fra
            # demone e Image Sorter, il caso comune), la sostituzione e'
            # impercettibile; se e' diverso, si vede comunque un
            # passaggio ordinato tasto per tasto, non un buio improvviso.
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
        # Ogni pressione diventa un'azione instradabile (un dizionario),
        # mai una chiamata diretta a un metodo: solo cosi' puo' essere
        # spedita alla casella di un'altra istanza, se e' lei ad avere il
        # fuoco in questo momento. Vedi resolve_target_pid()/send_to_inbox()
        # piu' sopra nel modulo.
        if kind == "key":
            action_dict = {"action": "preset_key", "param": action[1]}
        elif kind == "nav":
            action_dict = {"action": "preset_nav", "param": action[1]}
        elif kind == "delete":
            action_dict = {"action": "preset_delete", "param": ""}
        elif kind == "preset_prev":
            action_dict = {"action": "preset_prev", "param": ""}
        elif kind == "preset_next":
            action_dict = {"action": "preset_next", "param": ""}
        else:
            return
        self._route_action(action_dict)

    def _route_action(self, action_dict):
        """Instrada un'azione (idle o preset) verso chi deve eseguirla:
        in loco se questa istanza e' quella col fuoco (o se nessun'altra
        lo e' piu' di recente), nella casella dell'istanza giusta
        altrimenti. Unico punto che decide "qui o altrove", usato sia
        dalla modalita' preset sia da quella idle.
        """
        target_pid = resolve_target_pid()
        if target_pid == os.getpid():
            self.sorter.root.after(
                0, lambda a=action_dict: self._action_executor(a, self.sorter))
        else:
            send_to_inbox(target_pid, action_dict)

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
        self._route_action(slot)

    @staticmethod
    def _star_points(cx, cy, r_out, r_in):
        """Vertici di una stella a 5 punte (10 vertici, raggio esterno/
        interno alternati), punta rivolta in alto."""
        pts = []
        for i in range(10):
            ang = math.radians(-90 + i * 36)
            r = r_out if i % 2 == 0 else r_in
            pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        return pts

    def _render_rating_color_key(self, idx, slot, fmt, w, h):
        """Disegna i tasti "stella"/"colore" della pagina Rating/Flag:
        l'acceso/spento riflette il file ATTUALMENTE aperto in Image
        Sorter — sia lettura (mostra il rating/colore corrente) che
        scrittura (il click lo cambia, vedi _deck_execute_action in
        image_sorter.py). Senza un file corrente leggibile (nessuna
        cartella aperta, o metadata_store non disponibile) resta
        semplicemente "spento": niente errore, solo nessuna informazione."""
        action_type = slot.get("action", "")
        param       = slot.get("param", "")
        cur_fp = None
        try:
            get_cur = getattr(self.sorter, "_current_file", None)
            if callable(get_cur):
                cur_fp = get_cur()
        except Exception:
            cur_fp = None
        if cur_fp and metadata_store is not None:
            try:
                meta = metadata_store.get_meta(cur_fp)
            except Exception:
                meta = {"rating": 0, "colors": []}
        else:
            meta = {"rating": 0, "colors": []}

        img  = Image.new("RGB", (w, h), (10, 15, 26))
        draw = ImageDraw.Draw(img)
        cx, cy = w // 2, h // 2
        label = ""

        if action_type == "rating":
            try:
                n = int(param)
            except (TypeError, ValueError):
                n = 0
            lit = meta.get("rating", 0) >= n > 0
            r_out, r_in = min(w, h) * 0.32, min(w, h) * 0.13
            pts = self._star_points(cx, cy - h * 0.04, r_out, r_in)
            if lit:
                draw.polygon(pts, fill=(255, 200, 0), outline=(255, 230, 140))
            else:
                draw.polygon(pts, fill=(45, 45, 50), outline=(110, 110, 110))
            label = str(n) if n > 0 else ""
        else:   # "color_label"
            lit = param in meta.get("colors", [])
            hexcol = (metadata_store.COLOR_HEX.get(param, "#888888")
                     if metadata_store is not None else "#888888")
            try:
                rgb = tuple(int(hexcol[i:i+2], 16) for i in (1, 3, 5))
            except Exception:
                rgb = (136, 136, 136)
            r = min(w, h) * 0.30
            box = (cx - r, cy - r, cx + r, cy + r)
            if lit:
                draw.ellipse(box, fill=rgb, outline=(255, 255, 255), width=2)
            else:
                draw.ellipse(box, fill=None, outline=rgb, width=3)

        if label:
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
            except Exception:
                font = ImageFont.load_default()
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((cx - tw // 2, h - th - 6), label,
                      fill=(210, 210, 210), font=font)

        if fmt.get("flip"):
            fh, fv = fmt["flip"]
            if fh: img = img.transpose(Image.FLIP_LEFT_RIGHT)
            if fv: img = img.transpose(Image.FLIP_TOP_BOTTOM)
        try:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            self.deck.set_key_image(idx, buf.getvalue())
        except Exception as ex:
            print(f"[StreamDeck] render idle key {idx} (rating/color): {ex}")

    def _render_key_idle(self, idx):
        """Renderizza un tasto in modalità idle."""
        if not self.is_active():
            return
        fmt      = self.deck.key_image_format()
        w, h     = fmt["size"]
        page_data = self._idle_page_data()
        pages    = self._idle_pages()

        # Ogni tasto è libero — leggi semplicemente lo slot configurato
        if isinstance(page_data, list) and idx < len(page_data):
            slot = page_data[idx] or {}
        else:
            slot = {}
        # Tasti "stella"/"colore" (pagina Rating/Flag): resa dedicata, con
        # stato acceso/spento che riflette il file attualmente aperto in
        # Image Sorter — non passano dal disegno generico qui sotto.
        if slot.get("action") in ("rating", "color_label"):
            self._render_rating_color_key(idx, slot, fmt, w, h)
            return
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
                # Prova icona di default per il tipo di azione (o, per i
                # comandi diretti, per il singolo comando scelto)
                action_type = slot.get("action","") if slot else ""
                if action_type == "command":
                    icon_base = get_command_icon(slot.get("param",""), size=w)
                else:
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
                pos   = slot.get("label_pos", "middle")
                if pos == "middle":
                    # Storico, invariato: le righe si distribuiscono su
                    # tutta l'altezza del tasto. Chi non ha mai toccato
                    # l'impostazione vede lo stesso identico risultato di
                    # prima.
                    line_h = h // (len(lines) + 1)
                    for li, line in enumerate(lines):
                        bbox = draw.textbbox((0,0), line)
                        tw = bbox[2] - bbox[0]
                        x  = (w - tw) // 2
                        y  = (li + 1) * line_h - (bbox[3] - bbox[1]) // 2
                        draw.text((x, y), line, fill=(220, 220, 220))
                else:
                    # Alto/basso: blocco compatto ancorato al margine
                    # scelto. Distribuire su tutta l'altezza come sopra
                    # renderebbe "alto" e "basso" indistinguibili con
                    # poche righe di testo.
                    margin, gap = 4, 2
                    heights = [draw.textbbox((0,0), line)[3]
                              - draw.textbbox((0,0), line)[1] for line in lines]
                    total_h = sum(heights) + gap * max(0, len(lines) - 1)
                    y = margin if pos == "top" else max(margin, h - margin - total_h)
                    for line, lh in zip(lines, heights):
                        bbox = draw.textbbox((0,0), line)
                        tw = bbox[2] - bbox[0]
                        x  = (w - tw) // 2
                        draw.text((x, y - bbox[1]), line, fill=(220, 220, 220))
                        y += lh + gap

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

    def release_hardware(self):
        """Chiude DAVVERO il dispositivo (il vero deck.close() della
        libreria, non solo scartare il riferimento Python come fa
        close()).

        close() conta sul fatto che il processo stia per USCIRE — a quel
        punto e' il sistema operativo a liberare il device alla chiusura
        del processo, e chiamare close() esplicitamente in quel momento
        creava un problema diverso (vedi il commento li' sopra). Ma un
        demone che cede il deck per poi restare in attesa di riprenderselo
        NON esce mai: senza una chiusura vera qui, l'handle resterebbe
        occupato a livello di sistema operativo per tutto il tempo in cui
        il processo gira, anche se il nostro Python ha gia' "dimenticato"
        il riferimento — chi prova a riaprire il device lo troverebbe
        occupato indefinitamente, non importa quanto aspetti.
        """
        self._active = False
        if self.deck is not None:
            try:
                self.deck.close()
            except Exception:
                pass
        self.deck = None
