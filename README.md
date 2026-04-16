# Image Sorter v1.11

**Visualizzatore e smistatore di immagini, video e PDF per Linux**

Un'applicazione desktop per navigare e smistare rapidamente file multimediali in cartelle di destinazione, usando tastiera, mouse o uno Stream Deck Elgato.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Linux](https://img.shields.io/badge/Platform-Linux-orange)
![License](https://img.shields.io/badge/License-CC%20BY-green)

---

## Caratteristiche principali

- **Navigazione rapida** tra immagini, video e PDF con frecce o rotella mouse
- **Smistamento con un tasto** — tasti 1–9 per spostare o copiare nelle destinazioni configurate
- **Browser cartelle** con anteprima thumbnail, selezione multipla e operazioni batch
- **Ritaglio interattivo** con 8 handle, griglia dei terzi e undo (Ctrl+Z)
- **Rotazione non distruttiva** con undo
- **Ricerca doppioni** — SHA256, nome+dimensione, confronto A vs B tra cartelle
- **Stream Deck Elgato** — controllo fisico in modalità preset e idle configurabile
- **PDF multipagina** — navigazione pagina per pagina con miniature
- **Interfaccia HUD** — tema scuro con accenti ciano, ottimizzata per uso intensivo
- **Multilingua** — Italiano / English (estendibile)

## Formati supportati

| Tipo | Formati |
|------|---------|
| Immagini | JPG, PNG, GIF, BMP, TIFF, WEBP + formati aggiuntivi configurabili |
| Video | MP4, MOV, AVI, MKV, WEBM, M4V, FLV *(richiede ffmpeg)* |
| PDF | PDF multipagina *(richiede poppler-utils)* |
| Altro | File senza estensione rilevati via magic bytes |

---

## Installazione

### Metodo rapido (consigliato)

```bash
git clone https://github.com/TUO_USERNAME/image-sorter.git
cd image-sorter
bash installa.sh
```

Lo script rileva automaticamente il package manager (`apt`, `dnf`, `pacman`, `zypper`, `xbps`) e installa tutte le dipendenze.

### Dipendenze manuali

**Sistema:**
```bash
# Ubuntu/Debian/Mint
sudo apt install ffmpeg poppler-utils libhidapi-hidraw0 python3-tk python3-pip xprop

# Fedora/RHEL
sudo dnf install ffmpeg poppler-utils hidapi python3-tkinter python3-pip xprop

# Arch/Manjaro
sudo pacman -S ffmpeg poppler hidapi tk python-pip xorg-xprop
```

**Python:**
```bash
pip install pillow send2trash
pip install streamdeck  # opzionale, solo per Stream Deck
```

### Avvio

```bash
python3 image_sorter.py
# oppure con un file/cartella specifica:
python3 image_sorter.py /percorso/cartella
python3 image_sorter.py /percorso/immagine.jpg
```

---

## Struttura file

```
image-sorter/
├── image_sorter.py       Script principale
├── translations.py       Stringhe IT/EN
├── installa.sh           Installazione completa
├── build_standalone.sh   Build eseguibile PyInstaller
├── LEGGIMI.txt           Manuale italiano
├── README_en.txt         English manual
└── sorter_icons/         Icone app + Stream Deck
    ├── image_sorter_icon.png
    └── ...
```

---

## Scorciatoie da tastiera

### Navigazione
| Tasto | Azione |
|-------|--------|
| `→` / `←` | File successivo / precedente |
| `↑` / `↓` | Pagina PDF precedente / successiva |
| `PagSu` / `PagGiu` | Preset precedente / successivo |
| `Tab` o `N` | Preset successivo |
| Rotella mouse | Naviga file |

### Smistamento
| Tasto | Azione |
|-------|--------|
| `1`–`9`, `0` | Sposta nel preset attivo |
| `Ctrl+1`–`9` | Copia nel preset attivo |
| `Canc × 2` o `Canc+Invio` | Cestina con conferma |
| `Ctrl+Z` | Annulla ultimo crop |
| `Ctrl+X` o `Ctrl+←` | Annulla ultimo spostamento |

### Visualizzazione
| Tasto | Azione |
|-------|--------|
| `+` / `-` | Zoom in / out |
| `Z` | Adatta al canvas |
| `X` | Dimensione originale (1:1) |
| `F` o `Invio` | Schermo intero / Player |
| `H` | Mostra/nascondi intestazione |
| `I` | Overlay info EXIF |

### Pannelli
| Tasto | Azione |
|-------|--------|
| `O` o `B` | Browser cartelle |
| `S` | Sidebar (inline / popup / nascosta) |
| `D` / `P` | Tastierino |
| `R` | Impostazioni |
| `Ctrl+R` | Rinomina file corrente |
| `Q` / `Esc` | Esci |

---

## Stream Deck (opzionale)

Supporto per **Elgato Stream Deck Standard (15 tasti)** via [StreamController](https://github.com/StreamController/StreamController).

**Layout in modalità preset:**
```
[1]  [2]  [3]  [Preset]   [Canc]
[4]  [5]  [6]  [^ Prec]   [v Succ]
[7]  [8]  [9]  [<< Ind.]  [>> Av.]
```

---

## Note tecniche

- **Python 3.8+** — tkinter, Pillow, send2trash
- **Linux** — testato su Ubuntu 24 e Linux Mint; compatibile con tutte le distro principali
- **Wayland** — funziona tramite XWayland (presente di default su GNOME/KDE moderni)
- **Cache thumbnail** — LRU in memoria, max 200 entry
- **Configurazione** — `image_sorter_config.json` nella stessa cartella dello script
- I backup crop (`._crop_backup`) vengono puliti automaticamente al cambio cartella e alla chiusura

---

## Licenza

Creative Commons Attribution (CC BY) — Carlo Porrone, 2026  
[greencarlo@gmail.com](mailto:greencarlo@gmail.com)

> Questo programma non fornisce nessuna garanzia di utilizzo.
