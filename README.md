# Image Sorter v1.45.0

**Visualizzatore e smistatore di immagini, video e PDF per Linux**
**Image, video, and PDF viewer & sorter for Linux**

Un'applicazione desktop per navigare e smistare rapidamente file multimediali in cartelle di destinazione, usando tastiera, mouse o uno Stream Deck Elgato fisico.
A desktop application for quickly browsing and sorting media files into destination folders, using keyboard, mouse, or a physical Elgato Stream Deck.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Linux](https://img.shields.io/badge/Platform-Linux-orange)
![License](https://img.shields.io/badge/License-CC%20BY-green)

---

# 🇮🇹 Italiano

## Cos'è

Image Sorter nasce per una necessità concreta: scorrere in fretta grandi quantità di foto (e video, e PDF) e smistarle in cartelle di destinazione con un tasto solo, senza mai staccare le mani dalla tastiera — con o senza uno Stream Deck fisico collegato. Attorno a questo nucleo si sono aggiunte nel tempo una timeline con mappa GPS, un editor EXIF, un analizzatore di spazio disco, un cercatore di doppioni, e — dalla v1.38 — un sistema completo di valutazione e etichette colorate.

## Caratteristiche principali

- **Navigazione rapida** tra immagini, video e PDF con frecce o rotella mouse
- **Smistamento con un tasto** — tasti 1–9 e 0 per spostare, Ctrl+1–9/0 per copiare nelle destinazioni configurate (anche da tastierino numerico)
- **Browser cartelle** con anteprima thumbnail, selezione multipla e operazioni batch
- **Valutazione a stelle (0–5) e colorlabel multiple** per foto/video/PDF, non a vicenda esclusive — visibili e modificabili direttamente sotto ogni miniatura, nell'anteprima, nel menu tasto destro, e in un overlay dedicato sull'immagine principale; filtrabili in Naviga e nella barra laterale della Timeline
- **Ritaglio interattivo** con 8 handle, griglia dei terzi, blocco proporzioni (inclusa l'opzione "Originale", che blocca il rapporto esatto della foto aperta) e undo (Ctrl+Z)
- **Rotazione non distruttiva** con undo
- **Ricerca doppioni** — SHA256 a tre fasi, nome+dimensione, confronto A vs B tra cartelle con anteprima affiancata e selezione multipla
- **Timeline con mappa GPS** — vista cronologica con filtri per anno/luogo/cartella/valutazione/colore, apertura diretta sulla mappa dei file georeferenziati
- **Editor EXIF** — lettura e scrittura metadati (data/ora, GPS, autore, copyright, descrizione)
- **Analizzatore spazio disco** — visualizzazione sunburst/treemap dell'occupazione delle cartelle
- **Stream Deck Elgato** — controllo fisico in modalità preset e idle configurabile, con demone in background che tiene il dispositivo attivo anche a programma chiuso (vedi sezione dedicata)
- **PDF multipagina** — navigazione pagina per pagina con miniature
- **Interfaccia HUD** — tema scuro con accenti ciano, ottimizzata per uso intensivo
- **Multilingua** — Italiano / English (estendibile)

## Formati supportati

| Tipo | Formati |
|------|---------|
| Immagini | JPG, PNG, GIF, BMP, TIFF, WEBP, AVIF, HEIC/HEIF, PNM/PBM/PGM/PPM |
| Video | MP4, MOV, AVI, MKV, WEBM, M4V, FLV *(richiede ffmpeg)* |
| PDF | PDF multipagina *(usa PyMuPDF se disponibile, altrimenti poppler-utils)* |
| Altro | File senza estensione rilevati via magic bytes |

---

## Installazione

### Metodo rapido (consigliato)

```bash
git clone https://github.com/orionriggers/Image-Sorter.git
cd Image-Sorter
bash installa.sh
```

Lo script rileva automaticamente il package manager (`apt`, `dnf`, `pacman`, `zypper`, `xbps`) e installa tutte le dipendenze.

**Senza Git**: dalla pagina del repository, **Code → Download ZIP**. Il file
scaricato è `Image-Sorter-main.zip`: va estratto (tasto destro → "Estrai
qui" nella maggior parte dei file manager), creando una cartella chiamata
`Image-Sorter-main` — nome diverso dal repository perché GitHub aggiunge il
nome del ramo (`main`) agli archivi scaricati così, a differenza di un
clone Git. Per aprire un terminale già dentro quella cartella senza
scrivere `cd`, tasto destro nell'area vuota della cartella nel file manager
→ "Apri terminale qui" (o simile), poi:

```bash
bash installa.sh
```

### Dipendenze manuali

**Sistema:**
```bash
# Ubuntu/Debian/Mint
sudo apt install ffmpeg poppler-utils libhidapi-hidraw0 python3-tk python3-pip xdotool x11-utils

# Fedora/RHEL
sudo dnf install ffmpeg poppler-utils hidapi python3-tkinter python3-pip xdotool xprop

# Arch/Manjaro
sudo pacman -S ffmpeg poppler hidapi tk python-pip xdotool xorg-xprop
```

`xdotool` serve per la simulazione delle scorciatoie da tastiera dal deck fisico (azione "hotkey"); `libhidapi-hidraw0`/`hidapi` per la comunicazione USB con lo Stream Deck. Nessuno dei due è necessario se non si usa un dispositivo fisico.

**Python:**
```bash
pip install pillow --user
```

Facoltative — l'app funziona comunque senza, con la relativa funzionalità disabilitata:
```bash
pip install piexif send2trash pymupdf reverse-geocode folium tkinterdnd2 --user
```

| Pacchetto | A cosa serve |
|---|---|
| `piexif` | editor EXIF (lettura/scrittura metadati) |
| `send2trash` | cestino di sistema (senza, si usa un cestino interno equivalente) |
| `pymupdf` | rendering PDF più veloce, senza processi esterni — se assente si ripiega su `poppler-utils` |
| `reverse-geocode` | geocoding GPS offline nella Timeline |
| `folium` | mappa GPS interattiva nella Timeline |
| `tkinterdnd2` | drag & drop sui tasti del tastierino/deck |

Facoltative (supporto formati immagine extra):
```bash
pip install pillow-heif pillow-avif-plugin --user
```

Facoltativa (solo per lo Stream Deck fisico):
```bash
pip install streamdeck --user
```

### Avvio

```bash
python3 image_sorter.py
# oppure con un file/cartella specifica:
python3 image_sorter.py /percorso/cartella
python3 image_sorter.py /percorso/immagine.jpg
# per aprire direttamente il Browser cartelle (Naviga) su una cartella:
python3 image_sorter.py --browser /percorso/cartella
```

L'app è pensata anche per l'avvio con doppio clic (non solo da terminale) una volta installate le dipendenze.

---

## Struttura file

```
image-sorter/
├── image_sorter.py       Programma principale, GUI Tkinter
├── timeline.py            Timeline, mappa GPS, "browser profondo"
├── exif_editor.py         Editor metadati EXIF
├── disk_analyzer.py       Analisi utilizzo disco (sunburst/treemap)
├── translations.py        Stringhe IT/EN
├── metadata_store.py      Database rating/colorlabel/tag
├── deck_core.py           Logica Stream Deck condivisa
├── deck_daemon.py         Demone per il deck fisico sempre attivo
├── installa.sh            Installazione completa
├── LEGGIMI.txt            Manuale italiano
├── README_en.txt          English manual
└── sorter_icons/          Icone applicazione
    ├── image_sorter_icon.png
    └── ...
```

---

## Scorciatoie da tastiera

### Navigazione
| Tasto | Azione |
|-------|--------|
| `→` | File successivo |
| `←` | File precedente / torna indietro |
| `↑` / `↓` | Pagina PDF precedente / successiva |
| `PagSu` / `PagGiù` | Preset precedente / successivo |
| `Tab` o `N` | Preset successivo |
| Rotella mouse | Naviga file |

### Smistamento
| Tasto | Azione |
|-------|--------|
| `1`–`9`, `0` | Sposta nel preset attivo (anche da tastierino numerico) |
| `Ctrl+1`–`9`/`0` | Copia nel preset attivo |
| `Canc × 2` o `Canc+Invio` | Cestina con conferma (3 secondi per confermare) |
| `Ctrl+Z`, `Ctrl+X`, `Ctrl+←` | Annulla ultimo spostamento |

### Visualizzazione
| Tasto | Azione |
|-------|--------|
| `+` / `-` | Zoom in / out |
| `Z` | Adatta al canvas |
| `X` | Dimensione originale (1:1) |
| `F` o `Invio` | Schermo intero |
| `C` / `A` | Ruota 90° orario / antiorario |
| `K` | Ritaglia |
| `H` | Mostra/nascondi intestazione |
| `I` | Overlay info EXIF |
| `Ctrl+F` | Overlay valutazione/colorlabel |
| `W` | Modalità Confronta |
| `M` | Miniature pagine PDF (con PDF multipagina aperto) |

### Pannelli
| Tasto | Azione |
|-------|--------|
| `O` o `B` | Browser cartelle |
| `S` | Sidebar (inline / popup / nascosta) |
| `D` / `P` | Tastierino |
| `T` | Timeline |
| `R` | Impostazioni |
| `Ctrl+R` | Rinomina file corrente |
| `Ctrl+T` | Apre la finestra Tag sul file corrente |
| `Q` / `Esc` | Esci |

---

## Sistema di valutazione e colorlabel

Dalla v1.38, ogni file (foto, video o PDF) può avere una **valutazione da 0 a 5 stelle** e una o più **colorlabel** tra rosso, giallo, verde, blu, viola — non escludenti tra loro, un file può portarne più di una insieme. I dati vivono in un database JSON unico e portabile (`metadata_store.py`), separato dai file stessi, così funziona identicamente per immagini, video e PDF.

Sono modificabili ovunque abbia senso: sotto ogni miniatura in Naviga e Timeline, nel pannello anteprima ingrandita, dal menu tasto destro, e da un overlay dedicato sull'immagine principale (tasto `Ctrl+F`). Naviga permette di filtrare per valutazione minima e colore accanto al filtro testuale esistente; Timeline mostra sezioni dedicate nella barra laterale con conteggi. Ogni cambiamento si riflette immediatamente ovunque, senza bisogno di ricaricare.

---

## Stream Deck (opzionale)

Supporto per qualunque modello **Elgato Stream Deck** riconosciuto dalla libreria `python-elgato-streamdeck` (non più legato a un solo modello a 15 tasti né a StreamController, sostituito da un'architettura propria):

- **`deck_core.py`** gestisce la connessione USB, il disegno dei tasti e l'esecuzione delle azioni, sia in modalità preset (smistamento rapido, stessi tasti 1-9-0 del software) sia in modalità idle (pagine configurabili con azioni libere per tasto: apri cartella/applicazione/URL, scorciatoia da tastiera, muto/smuto, testo).
- **`deck_daemon.py`** è un processo separato che tiene il dispositivo fisico attivo anche quando Image Sorter è chiuso, cedendo automaticamente il controllo quando si apre una finestra del programma e riprendendoselo alla chiusura.
- Oltre 29 comandi diretti a singolo tasto (ruota, elimina, zoom, invia a un editor esterno, e altri), ciascuno con icona personalizzabile.

---

## Note tecniche

- **Python 3.8+** — tkinter, Pillow, piexif, send2trash
- **Linux** — testato su Ubuntu 24 e Linux Mint (Cinnamon, X11); compatibile con le distro principali
- **Wayland** — funziona tramite XWayland (presente di default su GNOME/KDE moderni); non testato nativamente su Wayland
- **Configurazione** — file JSON leggibili nella stessa cartella dello script (`image_sorter_config.json`, `image_sorter_history.json`, `image_sorter_metadata.json`)
- I backup crop (`._crop_backup`) vengono puliti automaticamente al cambio cartella e alla chiusura
- Le eliminazioni passano sempre da un cestino con cronologia annullabile, mai una cancellazione diretta

---

## Licenza

Creative Commons Attribution (CC BY) — Carlo Porrone, 2026
[greencarlo@gmail.com](mailto:greencarlo@gmail.com)

> Questo programma non fornisce nessuna garanzia di utilizzo.

<br>

---

# 🇬🇧 English

## What it is

Image Sorter was built around a concrete need: quickly browsing large batches of photos (plus video and PDF) and sorting them into destination folders with a single keypress, hands never leaving the keyboard — with or without a physical Stream Deck attached. Around that core, over time, a GPS-mapped timeline, an EXIF editor, a disk-space analyzer, a duplicate finder, and — since v1.38 — a full rating and color-label system have been added.

## Key features

- **Fast browsing** through images, video, and PDFs with arrow keys or the mouse wheel
- **One-key sorting** — keys 1–9 and 0 move files, Ctrl+1–9/0 copy them, into configured destinations (numeric keypad works too)
- **Folder browser** with thumbnail previews, multi-select, and batch operations
- **Star ratings (0–5) and multiple color labels** for photos/videos/PDFs, non-exclusive — visible and editable right under every thumbnail, in the preview pane, in the right-click menu, and via a dedicated overlay on the main image; filterable in the browser and in the Timeline sidebar
- **Interactive cropping** with 8 handles, a rule-of-thirds grid, aspect-ratio locking (including an "Original" option matching the exact proportions of the photo being cropped), and undo (Ctrl+Z)
- **Non-destructive rotation** with undo
- **Duplicate finder** — three-stage SHA256, name+size matching, and an A-vs-B folder comparison mode with side-by-side preview and multi-select
- **GPS-mapped timeline** — chronological view with filters by year/location/folder/rating/color, opening geotagged files directly on a map
- **EXIF editor** — read and write metadata (date/time, GPS, author, copyright, description)
- **Disk space analyzer** — sunburst/treemap visualization of folder usage
- **Elgato Stream Deck support** — physical control in preset and configurable idle mode, with a background daemon that keeps the device responsive even while the app is closed (see dedicated section)
- **Multi-page PDF** navigation with thumbnails
- **HUD-style interface** — dark theme with cyan accents, built for heavy daily use
- **Multi-language** — Italian / English (extensible)

## Supported formats

| Type | Formats |
|------|---------|
| Images | JPG, PNG, GIF, BMP, TIFF, WEBP, AVIF, HEIC/HEIF, PNM/PBM/PGM/PPM |
| Video | MP4, MOV, AVI, MKV, WEBM, M4V, FLV *(requires ffmpeg)* |
| PDF | Multi-page PDF *(uses PyMuPDF if available, falls back to poppler-utils)* |
| Other | Extension-less files detected via magic bytes |

---

## Installation

### Quick method (recommended)

```bash
git clone https://github.com/orionriggers/Image-Sorter.git
cd Image-Sorter
bash installa.sh
```

The script auto-detects your package manager (`apt`, `dnf`, `pacman`, `zypper`, `xbps`) and installs all dependencies.

**Without Git**: from the repository page, **Code → Download ZIP**. The
downloaded file is `Image-Sorter-main.zip`: extract it (right-click →
"Extract Here" in most file managers), which creates a folder named
`Image-Sorter-main` — a different name from the repository itself, because
GitHub appends the branch name (`main`) to archives downloaded this way,
unlike a Git clone. To open a terminal already inside that folder without
typing `cd`, right-click an empty spot in the folder in your file manager
→ "Open Terminal Here" (wording varies), then:

```bash
bash installa.sh
```

### Manual dependencies

**System:**
```bash
# Ubuntu/Debian/Mint
sudo apt install ffmpeg poppler-utils libhidapi-hidraw0 python3-tk python3-pip xdotool x11-utils

# Fedora/RHEL
sudo dnf install ffmpeg poppler-utils hidapi python3-tkinter python3-pip xdotool xprop

# Arch/Manjaro
sudo pacman -S ffmpeg poppler hidapi tk python-pip xdotool xorg-xprop
```

`xdotool` is used to simulate keyboard shortcuts triggered from the physical deck (the "hotkey" action); `libhidapi-hidraw0`/`hidapi` handle USB communication with the Stream Deck. Neither is needed if you're not using the physical device.

**Python:**
```bash
pip install pillow --user
```

Optional — the app runs fine without them, with the related feature disabled:
```bash
pip install piexif send2trash pymupdf reverse-geocode folium tkinterdnd2 --user
```

| Package | What it's for |
|---|---|
| `piexif` | EXIF editor (read/write metadata) |
| `send2trash` | system trash (an equivalent internal trash is used otherwise) |
| `pymupdf` | faster PDF rendering, no external processes — falls back to `poppler-utils` if missing |
| `reverse-geocode` | offline GPS reverse geocoding in the Timeline |
| `folium` | interactive GPS map in the Timeline |
| `tkinterdnd2` | drag & drop on keypad/deck buttons |

Optional (extra image format support):
```bash
pip install pillow-heif pillow-avif-plugin --user
```

Optional (physical Stream Deck only):
```bash
pip install streamdeck --user
```

### Launching

```bash
python3 image_sorter.py
# or with a specific file/folder:
python3 image_sorter.py /path/to/folder
python3 image_sorter.py /path/to/image.jpg
# to open the folder browser (Naviga) directly on a folder:
python3 image_sorter.py --browser /path/to/folder
```

The app is also designed for double-click launch (not just from a terminal) once dependencies are installed.

---

## Project structure

```
image-sorter/
├── image_sorter.py       Main application, Tkinter GUI
├── timeline.py             Timeline, GPS map, "deep browser"
├── exif_editor.py          EXIF metadata editor
├── disk_analyzer.py        Disk usage analysis (sunburst/treemap)
├── translations.py         IT/EN interface strings
├── metadata_store.py       Rating/color-label/tag database
├── deck_core.py             Shared Stream Deck logic
├── deck_daemon.py           Background daemon for the physical deck
├── installa.sh               Full installer script
├── LEGGIMI.txt               Italian manual
├── README_en.txt             English manual
└── sorter_icons/             Application icons
    ├── image_sorter_icon.png
    └── ...
```

---

## Keyboard shortcuts

### Navigation
| Key | Action |
|-----|--------|
| `→` | Next file |
| `←` | Previous file / go back |
| `↑` / `↓` | Previous / next PDF page |
| `PgUp` / `PgDn` | Previous / next preset |
| `Tab` or `N` | Next preset |
| Mouse wheel | Browse files |

### Sorting
| Key | Action |
|-----|--------|
| `1`–`9`, `0` | Move to active preset (numeric keypad works too) |
| `Ctrl+1`–`9`/`0` | Copy to active preset |
| `Del ×2` or `Del+Enter` | Trash with confirmation (3-second window) |
| `Ctrl+Z`, `Ctrl+X`, `Ctrl+←` | Undo last move |

### Viewing
| Key | Action |
|-----|--------|
| `+` / `-` | Zoom in / out |
| `Z` | Fit to canvas |
| `X` | Original size (1:1) |
| `F` or `Enter` | Fullscreen |
| `C` / `A` | Rotate 90° clockwise / counter-clockwise |
| `K` | Crop |
| `H` | Show/hide header |
| `I` | EXIF info overlay |
| `Ctrl+F` | Rating/color-label overlay |
| `W` | Compare mode |
| `M` | PDF page thumbnails (with multi-page PDF open) |

### Panels
| Key | Action |
|-----|--------|
| `O` or `B` | Folder browser |
| `S` | Sidebar (inline / popup / hidden) |
| `D` / `P` | Keypad |
| `T` | Timeline |
| `R` | Settings |
| `Ctrl+R` | Rename current file |
| `Ctrl+T` | Open Tag window for current file |
| `Q` / `Esc` | Quit |

---

## Rating and color-label system

Since v1.38, every file (photo, video, or PDF) can carry a **0–5 star rating** and one or more **color labels** — red, yellow, green, blue, purple — non-exclusive, so a file can carry several at once. Data lives in a single portable JSON database (`metadata_store.py`), kept separate from your files, so it works identically for images, videos, and PDFs.

They're editable everywhere it makes sense: under every thumbnail in the browser and Timeline, in the enlarged preview pane, from the right-click menu, and via a dedicated overlay on the main image (`Ctrl+F`). The folder browser lets you filter by minimum rating and color alongside the existing text filter; Timeline shows dedicated sidebar sections with live counts. Every change is reflected instantly everywhere else — no reload needed.

---

## Stream Deck (optional)

Supports any **Elgato Stream Deck** model recognized by the `python-elgato-streamdeck` library (no longer tied to a single 15-key model or to StreamController, replaced by an in-house architecture):

- **`deck_core.py`** handles the USB connection, key rendering, and action dispatch, in both preset mode (quick sorting, same 1-9-0 keys as the software) and idle mode (configurable pages with free per-key actions: open folder/app/URL, keyboard shortcut, mute/unmute, text).
- **`deck_daemon.py`** is a separate process that keeps the physical device responsive even while Image Sorter is closed, automatically handing control back and forth as app windows open and close.
- Over 29 direct one-press commands (rotate, delete, zoom, send to an external editor, and more), each with a customizable icon.

---

## Technical notes

- **Python 3.8+** — tkinter, Pillow, piexif, send2trash
- **Linux** — tested on Ubuntu 24 and Linux Mint (Cinnamon, X11); compatible with major distros
- **Wayland** — works via XWayland (present by default on modern GNOME/KDE); not natively tested on Wayland
- **Configuration** — human-readable JSON files in the same folder as the script (`image_sorter_config.json`, `image_sorter_history.json`, `image_sorter_metadata.json`)
- Crop backups (`._crop_backup`) are cleaned up automatically on folder change and on exit
- Deletions always go through an undo-able trash with history, never a direct delete

---

## License

Creative Commons Attribution (CC BY) — Carlo Porrone, 2026
[greencarlo@gmail.com](mailto:greencarlo@gmail.com)

> This program comes with no warranty of use.
