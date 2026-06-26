#!/bin/bash
# =============================================================================
#  Image Sorter v1.18 -- Installation script / Script di installazione
#  Usage / Uso: bash installa.sh
#
#  English: Installs Image Sorter and all dependencies on any Linux system.
#  Italiano: Installa Image Sorter e tutte le dipendenze su qualsiasi Linux.
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor"
VERSION="1.25.0"
MIN_PYTHON_MINOR=8

# ── Language detection / Rilevamento lingua ───────────────────────────────────
# Use English unless system locale is Italian
LANG_SYS="${LANG:-en}"
if echo "$LANG_SYS" | grep -qi "^it"; then
    UI_LANG="it"
else
    UI_LANG="en"
fi

# ── Translated strings / Stringhe tradotte ───────────────────────────────────
t() {
    local key="$1"
    if [ "$UI_LANG" = "it" ]; then
        case "$key" in
            title_install)    echo "Image Sorter v${VERSION} -- Installazione" ;;
            title_done)       echo "Installazione completata! -- Image Sorter v${VERSION}" ;;
            step_python)      echo "Verifica Python" ;;
            step_files)       echo "Verifica file programma" ;;
            step_sysdeps)     echo "Dipendenze di sistema" ;;
            step_pydeps)      echo "Dipendenze Python" ;;
            step_deck)        echo "Stream Deck" ;;
            step_icon)        echo "Icona" ;;
            step_desktop)     echo "File .desktop e MIME" ;;
            step_fm)          echo "Script file manager" ;;
            step_nemo)        echo "Azione tasto destro Nemo" ;;
            nemo_open_name)   echo "Apri con Image Sorter" ;;
            nemo_open_comment) echo "Apri questa cartella con Image Sorter" ;;
            nemo_installed)   echo "Azione Nemo installata" ;;
            nemo_restarted)   echo "Nemo riavviato" ;;
            nemo_not_running) echo "Nemo non in esecuzione -- l'azione sara' disponibile al prossimo avvio" ;;
            nemo_not_found)   echo "Nemo non rilevato -- passaggio saltato" ;;
            step_shortcut)    echo "Collegamento desktop" ;;
            step_sc)          echo "StreamController" ;;
            py_not_found)     echo "Python 3.${MIN_PYTHON_MINOR}+ non trovato!" ;;
            py_install_hint)  echo "Installa Python: sudo apt install python3 python3-pip python3-tk" ;;
            py_found)         echo "Python trovato" ;;
            pkg_manager)      echo "Package manager" ;;
            pkg_manual)       echo "Installa manualmente" ;;
            pkg_already)      echo "gia' presente" ;;
            pkg_installing)   echo "Installazione" ;;
            pkg_installed)    echo "installato" ;;
            pkg_failed)       echo "non installabile -- continuo" ;;
            dep_mandatory)    echo "Dipendenze obbligatorie:" ;;
            dep_optional)     echo "Dipendenze opzionali:" ;;
            dep_desc_pillow)  echo "visualizzazione immagini" ;;
            dep_desc_send2t)  echo "cestina file" ;;
            dep_desc_pymupdf) echo "supporto PDF" ;;
            dep_desc_sdeck)   echo "Stream Deck Elgato" ;;
            dep_desc_piexif)  echo "editor EXIF" ;;
            dep_desc_rgeo)    echo "geocoding GPS offline (timeline)" ;;
            dep_desc_folium)  echo "mappa GPS interattiva" ;;
            dep_desc_dnd)     echo "drag & drop tastierino" ;;
            dep_desc_heif)    echo "supporto HEIC/HEIF (foto iPhone)" ;;
            dep_installed)    echo "installato" ;;
            dep_failed_opt)   echo "non installabile -- funzionalita' opzionale disabilitata" ;;
            dep_failed_req)   echo "non installabile -- alcune funzionalita' potrebbero non funzionare" ;;
            file_found)       echo "trovato" ;;
            file_missing)     echo "non trovato (funzionalita' limitata)" ;;
            udev_create)      echo "Creazione regola udev..." ;;
            udev_ok)          echo "Regola udev creata" ;;
            udev_exists)      echo "Regola udev gia' presente" ;;
            plugdev_ok)       echo "Utente $USER gia' nel gruppo plugdev" ;;
            plugdev_add)      echo "Utente $USER aggiunto a plugdev (riavvia per attivare)" ;;
            icon_generate)    echo "Generazione icona HUD..." ;;
            icon_generated)   echo "Icona generata" ;;
            icon_installing)  echo "Installazione icona (tutte le risoluzioni)..." ;;
            icon_done)        echo "Icona installata" ;;
            desktop_done)     echo "File .desktop installato" ;;
            mime_done)        echo "Associazioni MIME registrate" ;;
            fm_done)          echo "Script installato in" ;;
            shortcut_done)    echo "Collegamento creato in" ;;
            sc_done)          echo "StreamController configurato in autostart (--no-ui)" ;;
            sc_missing)       echo "StreamController non installato (opzionale)" ;;
            sc_hint)          echo "Per installarlo: pip install streamdeck --user" ;;
            summary_prog)     echo "Programma" ;;
            summary_python)   echo "Python" ;;
            summary_menu)     echo "Menu" ;;
            summary_launch)   echo "Avvio rapido" ;;
            missing_deps)     echo "[!] Dipendenze opzionali non installate:" ;;
            missing_all)      echo "Per installarle tutte:" ;;
            reboot_warn)      echo "[!] Riavvia il PC per attivare i permessi Stream Deck." ;;
            open_hint)        echo "Per aprire con doppio click su un'immagine:" ;;
            open_hint2)       echo "  Tasto destro > Apri con > Image Sorter > Imposta come predefinito" ;;
            *)                echo "$key" ;;
        esac
    else
        case "$key" in
            title_install)    echo "Image Sorter v${VERSION} -- Installation" ;;
            title_done)       echo "Installation complete! -- Image Sorter v${VERSION}" ;;
            step_python)      echo "Python check" ;;
            step_files)       echo "Program files check" ;;
            step_sysdeps)     echo "System dependencies" ;;
            step_pydeps)      echo "Python dependencies" ;;
            step_deck)        echo "Stream Deck" ;;
            step_icon)        echo "Icon" ;;
            step_desktop)     echo ".desktop file and MIME" ;;
            step_fm)          echo "File manager scripts" ;;
            step_nemo)        echo "Nemo right-click action" ;;
            nemo_open_name)   echo "Open with Image Sorter" ;;
            nemo_open_comment) echo "Open this folder with Image Sorter" ;;
            nemo_installed)   echo "Nemo action installed" ;;
            nemo_restarted)   echo "Nemo restarted" ;;
            nemo_not_running) echo "Nemo not running -- action will be available on next launch" ;;
            nemo_not_found)   echo "Nemo not detected -- step skipped" ;;
            step_shortcut)    echo "Desktop shortcut" ;;
            step_sc)          echo "StreamController" ;;
            py_not_found)     echo "Python 3.${MIN_PYTHON_MINOR}+ not found!" ;;
            py_install_hint)  echo "Install Python: sudo apt install python3 python3-pip python3-tk" ;;
            py_found)         echo "Python found" ;;
            pkg_manager)      echo "Package manager" ;;
            pkg_manual)       echo "Install manually" ;;
            pkg_already)      echo "already installed" ;;
            pkg_installing)   echo "Installing" ;;
            pkg_installed)    echo "installed" ;;
            pkg_failed)       echo "could not install -- continuing" ;;
            dep_mandatory)    echo "Mandatory dependencies:" ;;
            dep_optional)     echo "Optional dependencies:" ;;
            dep_desc_pillow)  echo "image display" ;;
            dep_desc_send2t)  echo "trash files" ;;
            dep_desc_pymupdf) echo "PDF support" ;;
            dep_desc_sdeck)   echo "Elgato Stream Deck" ;;
            dep_desc_piexif)  echo "EXIF editor" ;;
            dep_desc_rgeo)    echo "offline GPS geocoding (timeline)" ;;
            dep_desc_folium)  echo "interactive GPS map" ;;
            dep_desc_dnd)     echo "drag & drop on keypad" ;;
            dep_desc_heif)    echo "HEIC/HEIF support (iPhone photos)" ;;
            dep_installed)    echo "installed" ;;
            dep_failed_opt)   echo "could not install -- optional feature disabled" ;;
            dep_failed_req)   echo "could not install -- some features may not work" ;;
            file_found)       echo "found" ;;
            file_missing)     echo "not found (limited functionality)" ;;
            udev_create)      echo "Creating udev rule..." ;;
            udev_ok)          echo "udev rule created" ;;
            udev_exists)      echo "udev rule already present" ;;
            plugdev_ok)       echo "User $USER already in plugdev group" ;;
            plugdev_add)      echo "User $USER added to plugdev (reboot to activate)" ;;
            icon_generate)    echo "Generating HUD icon..." ;;
            icon_generated)   echo "Icon generated" ;;
            icon_installing)  echo "Installing icon (all resolutions)..." ;;
            icon_done)        echo "Icon installed" ;;
            desktop_done)     echo ".desktop file installed" ;;
            mime_done)        echo "MIME associations registered" ;;
            fm_done)          echo "Script installed in" ;;
            shortcut_done)    echo "Shortcut created in" ;;
            sc_done)          echo "StreamController set up for autostart (--no-ui)" ;;
            sc_missing)       echo "StreamController not installed (optional)" ;;
            sc_hint)          echo "To install: pip install streamdeck --user" ;;
            summary_prog)     echo "Program" ;;
            summary_python)   echo "Python" ;;
            summary_menu)     echo "Menu" ;;
            summary_launch)   echo "Quick launch" ;;
            missing_deps)     echo "[!] Optional dependencies not installed:" ;;
            missing_all)      echo "To install all at once:" ;;
            reboot_warn)      echo "[!] Reboot your PC to activate Stream Deck permissions." ;;
            open_hint)        echo "To open images with double-click:" ;;
            open_hint2)       echo "  Right click > Open with > Image Sorter > Set as default" ;;
            *)                echo "$key" ;;
        esac
    fi
}

# ── Output helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'
RED='\033[0;31m';   CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC}  $1"; }
info() { echo -e "  ${CYAN}[..]${NC}  $1"; }
warn() { echo -e "  ${YELLOW}[!]${NC}   $1"; }
err()  { echo -e "  ${RED}[X]${NC}   $1"; }
step() { echo -e "\n${BOLD}--- $1 ---${NC}"; }

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  $(t title_install)${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# =============================================================================
# 0. PYTHON CHECK
# =============================================================================
step "$(t step_python)"

PYTHON_CMD=""
for cmd in python3 python3.8 python3.9 python3.10 python3.11 python3.12; do
    if command -v "$cmd" &>/dev/null; then
        MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
        MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge "$MIN_PYTHON_MINOR" ] 2>/dev/null; then
            PYTHON_CMD="$cmd"
            PY_VERSION=$("$cmd" --version 2>&1 | awk '{print $2}')
            ok "$(t py_found): $PY_VERSION ($cmd)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    err "$(t py_not_found)"
    warn "$(t py_install_hint)"
    exit 1
fi

# =============================================================================
# 1. PROGRAM FILES
# =============================================================================
step "$(t step_files)"

if [ -f "$SCRIPT_DIR/image_sorter.py" ]; then
    EXEC="$SCRIPT_DIR/image_sorter.py"
    ok "image_sorter.py $(t file_found)"
else
    err "image_sorter.py not found / non trovato in $SCRIPT_DIR"
    exit 1
fi

for mod in disk_analyzer.py deep_browser.py exif_editor.py translations.py; do
    if [ -f "$SCRIPT_DIR/$mod" ]; then
        ok "$mod $(t file_found)"
    else
        warn "$mod $(t file_missing)"
    fi
done

# =============================================================================
# 2. SYSTEM DEPENDENCIES
# =============================================================================
step "$(t step_sysdeps)"

PKG_MANAGER=""
if   command -v apt-get      &>/dev/null; then PKG_MANAGER="apt"
elif command -v dnf          &>/dev/null; then PKG_MANAGER="dnf"
elif command -v pacman       &>/dev/null; then PKG_MANAGER="pacman"
elif command -v zypper       &>/dev/null; then PKG_MANAGER="zypper"
elif command -v xbps-install &>/dev/null; then PKG_MANAGER="xbps"
fi

info "$(t pkg_manager): ${PKG_MANAGER:-none}"

pkg_name() {
    local g="$1"
    case "$PKG_MANAGER" in
        apt)
            case "$g" in
                ffmpeg)      echo "ffmpeg" ;;
                poppler)     echo "poppler-utils" ;;
                hidapi)      echo "libhidapi-hidraw0" ;;
                python3-tk)  echo "python3-tk" ;;
                python3-pip) echo "python3-pip" ;;
                x11-utils)   echo "x11-utils" ;;
                *)           echo "$g" ;;
            esac ;;
        dnf)
            case "$g" in
                ffmpeg)      echo "ffmpeg" ;;
                poppler)     echo "poppler-utils" ;;
                hidapi)      echo "hidapi" ;;
                python3-tk)  echo "python3-tkinter" ;;
                python3-pip) echo "python3-pip" ;;
                x11-utils)   echo "xprop" ;;
                *)           echo "$g" ;;
            esac ;;
        pacman)
            case "$g" in
                ffmpeg)      echo "ffmpeg" ;;
                poppler)     echo "poppler" ;;
                hidapi)      echo "hidapi" ;;
                python3-tk)  echo "tk" ;;
                python3-pip) echo "python-pip" ;;
                x11-utils)   echo "xorg-xprop" ;;
                *)           echo "$g" ;;
            esac ;;
        zypper)
            case "$g" in
                ffmpeg)      echo "ffmpeg" ;;
                poppler)     echo "poppler-tools" ;;
                hidapi)      echo "libhidapi-hidraw0" ;;
                python3-tk)  echo "python3-tk" ;;
                python3-pip) echo "python3-pip" ;;
                x11-utils)   echo "xprop" ;;
                *)           echo "$g" ;;
            esac ;;
        *)  echo "$g" ;;
    esac
}

pkg_installed() {
    local pkg="$1"
    case "$PKG_MANAGER" in
        apt)    dpkg -l "$pkg" &>/dev/null 2>&1 ;;
        dnf)    rpm -q "$pkg" &>/dev/null 2>&1 ;;
        pacman) pacman -Q "$pkg" &>/dev/null 2>&1 ;;
        zypper) rpm -q "$pkg" &>/dev/null 2>&1 ;;
        *)      command -v "$pkg" &>/dev/null ;;
    esac
}

install_pkg() {
    local pkg
    pkg="$(pkg_name "$1")"
    if pkg_installed "$pkg"; then
        ok "$pkg $(t pkg_already)"; return
    fi
    info "$(t pkg_installing) $pkg..."
    case "$PKG_MANAGER" in
        apt)    sudo apt-get install -y -qq "$pkg" ;;
        dnf)    sudo dnf install -y -q "$pkg" ;;
        pacman) sudo pacman -S --noconfirm --quiet "$pkg" ;;
        zypper) sudo zypper install -y -q "$pkg" ;;
        xbps)   sudo xbps-install -y "$pkg" ;;
        *)      warn "$(t pkg_manual): $pkg"; return ;;
    esac && ok "$pkg $(t pkg_installed)" \
          || warn "$pkg $(t pkg_failed)"
}

if [ -n "$PKG_MANAGER" ]; then
    [ "$PKG_MANAGER" = "apt" ] && {
        info "apt-get update..."
        sudo apt-get update -qq 2>/dev/null || true
    }
    install_pkg python3-tk
    install_pkg python3-pip
    install_pkg ffmpeg
    install_pkg poppler
    install_pkg hidapi
    install_pkg x11-utils
else
    warn "$(t pkg_manual): ffmpeg poppler-utils libhidapi python3-tk python3-pip"
fi

# =============================================================================
# 3. PYTHON DEPENDENCIES
# =============================================================================
step "$(t step_pydeps)"

pip_install() {
    local pkg="$1"
    local import_name="${2:-$1}"
    local optional="${3:-false}"
    local desc="${4:-}"

    if "$PYTHON_CMD" -c "import $import_name" &>/dev/null 2>&1; then
        ok "$pkg $(t pkg_already)${desc:+ ($desc)}"; return
    fi
    info "$(t pkg_installing) $pkg${desc:+ -- $desc}..."
    if "$PYTHON_CMD" -m pip install "$pkg" --user -q 2>/dev/null; then
        "$PYTHON_CMD" -c "import $import_name" &>/dev/null 2>&1 \
            && ok "$pkg $(t dep_installed)" \
            || warn "$pkg $(t dep_failed_opt)"
    elif "$PYTHON_CMD" -m pip install "$pkg" --break-system-packages -q 2>/dev/null; then
        ok "$pkg $(t dep_installed)"
    else
        if [ "$optional" = "true" ]; then
            warn "$pkg $(t dep_failed_opt)"
        else
            err "$pkg $(t dep_failed_req)"
        fi
    fi
}

echo ""
echo "  $(t dep_mandatory)"
pip_install "Pillow"           "PIL"              "false" "$(t dep_desc_pillow)"

echo ""
echo "  $(t dep_optional)"
pip_install "send2trash"       "send2trash"       "true"  "$(t dep_desc_send2t)"
pip_install "pymupdf"          "fitz"             "true"  "$(t dep_desc_pymupdf)"
pip_install "streamdeck"       "StreamDeck"       "true"  "$(t dep_desc_sdeck)"
pip_install "piexif"           "piexif"           "true"  "$(t dep_desc_piexif)"
pip_install "reverse-geocode"  "reverse_geocode"  "true"  "$(t dep_desc_rgeo)"
pip_install "folium"           "folium"           "true"  "$(t dep_desc_folium)"
pip_install "tkinterdnd2"      "tkinterdnd2"      "true"  "$(t dep_desc_dnd)"
pip_install "pillow-heif"      "pillow_heif"      "true"  "$(t dep_desc_heif)"

# =============================================================================
# 4. STREAM DECK
# =============================================================================
step "$(t step_deck)"

UDEV_FILE="/etc/udev/rules.d/70-streamdeck.rules"
if [ ! -f "$UDEV_FILE" ]; then
    info "$(t udev_create)"
    sudo sh -c "cat > $UDEV_FILE << 'UDEVEOF'
SUBSYSTEM==\"hidraw\", ATTRS{idVendor}==\"0fd9\", GROUP=\"plugdev\", MODE=\"0660\"
SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"0fd9\", GROUP=\"plugdev\", MODE=\"0660\"
UDEVEOF"
    sudo udevadm control --reload-rules 2>/dev/null || true
    sudo udevadm trigger 2>/dev/null || true
    ok "$(t udev_ok)"
else
    ok "$(t udev_exists)"
fi

if groups "$USER" | grep -q plugdev; then
    ok "$(t plugdev_ok)"
else
    sudo usermod -aG plugdev "$USER"
    ok "$(t plugdev_add)"
    NEEDS_REBOOT=true
fi

# =============================================================================
# 5. ICON
# =============================================================================
step "$(t step_icon)"

ICON_SRC="$SCRIPT_DIR/sorter_icons/image_sorter_icon.png"
ICON_NAME="image-sorter"
mkdir -p "$SCRIPT_DIR/sorter_icons"

if [ ! -f "$ICON_SRC" ]; then
    info "$(t icon_generate)"
    "$PYTHON_CMD" - "$ICON_SRC" << 'PYEOF'
import sys
from PIL import Image, ImageDraw
out = sys.argv[1]
SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0,0,0,0))
d = ImageDraw.Draw(img)
s = SIZE
d.ellipse([2,2,s-3,s-3], fill=(13,17,23,255))
d.ellipse([4,4,s-5,s-5], outline=(30,70,100,200), width=2)
px1,py1,px2,py2 = int(s*.20),int(s*.25),int(s*.80),int(s*.65)
d.rounded_rectangle([px1,py1,px2,py2], radius=8,
                     fill=(10,26,42,255), outline=(0,200,255,220), width=2)
d.polygon([(px1+10,py2-8),(px1+10,py1+20),(px1+60,py2-8)], fill=(0,150,200,180))
d.ellipse([px2-50,py1+8,px2-20,py1+38], outline=(0,200,255,200), width=2)
ay = py2+14
d.line([(s//2-30,ay),(s//2+30,ay)], fill=(0,200,255,220), width=3)
d.polygon([(s//2+20,ay-8),(s//2+20,ay+8),(s//2+40,ay)], fill=(0,200,255,220))
img.save(out, "PNG")
PYEOF
    ok "$(t icon_generated)"
fi

info "$(t icon_installing)"
"$PYTHON_CMD" - "$ICON_SRC" "$ICON_DIR" "$ICON_NAME" << 'PYEOF'
import sys, os, shutil
from PIL import Image
src, icon_dir, icon_name = sys.argv[1], sys.argv[2], sys.argv[3]
img = Image.open(src).convert("RGBA")
sizes = [16, 22, 24, 32, 48, 64, 96, 128, 256, 512]
for size in sizes:
    d = os.path.join(icon_dir, f"{size}x{size}", "apps")
    os.makedirs(d, exist_ok=True)
    r = img.resize((size, size), Image.Resampling.LANCZOS)
    r.save(os.path.join(d, f"{icon_name}.png"))
    r.save(os.path.join(d, "image_sorter.png"))
d = os.path.join(icon_dir, "scalable", "apps")
os.makedirs(d, exist_ok=True)
img.resize((512,512), Image.Resampling.LANCZOS).save(os.path.join(d, f"{icon_name}.png"))
icons_dir = os.path.dirname(src)
os.makedirs(icons_dir, exist_ok=True)
dst_icon = os.path.join(icons_dir, "image_sorter_icon.png")
if os.path.abspath(src) != os.path.abspath(dst_icon):
    shutil.copy(src, dst_icon)
for sz in sizes:
    img.resize((sz,sz), Image.Resampling.LANCZOS).save(
        os.path.join(icons_dir, f"image_sorter_icon_{sz}.png"))
PYEOF

gtk-update-icon-cache -f -t "$ICON_DIR" 2>/dev/null || true
update-icon-caches "$ICON_DIR" 2>/dev/null || true
ok "$(t icon_done)"

# =============================================================================
# 6. .DESKTOP FILE AND MIME
# =============================================================================
step "$(t step_desktop)"

mkdir -p "$INSTALL_DIR"
chmod +x "$EXEC"

cat > "$INSTALL_DIR/image_sorter.desktop" << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Image Sorter
GenericName=Smistatore immagini e video
Comment=Visualizza e smistate immagini, video e PDF con la tastiera
Exec=$PYTHON_CMD $EXEC %F
Icon=image-sorter
Terminal=false
StartupNotify=false
StartupWMClass=image_sorter
Categories=Graphics;Photography;
MimeType=image/jpeg;image/png;image/gif;image/bmp;image/tiff;image/webp;
Keywords=immagini;foto;video;pdf;smista;sort;image;photo;
DESKTOP

chmod +x "$INSTALL_DIR/image_sorter.desktop"
update-desktop-database "$INSTALL_DIR" 2>/dev/null || true
ok "$(t desktop_done)"

MIME_APPS="$HOME/.local/share/applications/mimeapps.list"
touch "$MIME_APPS"
grep -q "\[Default Applications\]" "$MIME_APPS" || {
    echo ""       >> "$MIME_APPS"
    echo "[Default Applications]" >> "$MIME_APPS"
}
ADDED_MIME=0
for mime in image/jpeg image/png image/gif image/bmp image/tiff image/webp; do
    if ! grep -q "^$mime=" "$MIME_APPS"; then
        sed -i "/^\[Default Applications\]/a $mime=image_sorter.desktop" "$MIME_APPS"
        ADDED_MIME=$((ADDED_MIME+1))
    fi
done
ok "$(t mime_done) ($ADDED_MIME)"

grep -q "\[Added Associations\]" "$MIME_APPS" || {
    echo ""       >> "$MIME_APPS"
    echo "[Added Associations]" >> "$MIME_APPS"
}
for mime in video/mp4 video/x-matroska video/quicktime application/pdf; do
    grep -A9999 "\[Added Associations\]" "$MIME_APPS" | grep -q "^$mime=" \
        || echo "$mime=image_sorter.desktop" >> "$MIME_APPS"
done

# =============================================================================
# 7. FILE MANAGER SCRIPTS
# =============================================================================
step "$(t step_fm)"

# Script per Nautilus (appare sotto "Script" — fallback per chi non usa Nemo)
NAUTILUS_SCRIPTS="$HOME/.local/share/nautilus/scripts"
mkdir -p "$NAUTILUS_SCRIPTS"
cat > "$NAUTILUS_SCRIPTS/Open with Image Sorter" << NMEOF
#!/bin/bash
FIRST="\$(echo "\$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS" | head -n1)"
[ -n "\$FIRST" ] && $PYTHON_CMD "$SCRIPT_DIR/image_sorter.py" "--browser" "\$FIRST" &
NMEOF
chmod +x "$NAUTILUS_SCRIPTS/Open with Image Sorter"
cp "$NAUTILUS_SCRIPTS/Open with Image Sorter" "$NAUTILUS_SCRIPTS/Apri con Image Sorter"
ok "$(t fm_done): $NAUTILUS_SCRIPTS"
# Nota: per Nemo viene usata un'azione diretta (step 7b) — più visibile degli script

# =============================================================================
# 7b. NEMO RIGHT-CLICK ACTION
# =============================================================================
step "$(t step_nemo)"

NEMO_ACTIONS_DIR="$HOME/.local/share/nemo/actions"

if command -v nemo &>/dev/null; then
    mkdir -p "$NEMO_ACTIONS_DIR"
    # Rileva lingua sistema per nome azione
    _LANG="${LANG%%_*}"
    _NEMO_OPEN_NAME="$(t nemo_open_name)"
    _NEMO_OPEN_COMMENT="$(t nemo_open_comment)"

    # Azione 1: Apri con Image Sorter (su cartelle)
    {
        echo "[Nemo Action]"
        echo "Name=$_NEMO_OPEN_NAME"
        echo "Comment=$_NEMO_OPEN_COMMENT"
        printf "Exec=bash -c '\"%s\" \"%s\" \"--browser\" \"%%F\"'\n" "$PYTHON_CMD" "$SCRIPT_DIR/image_sorter.py"
        echo "Icon-Name=image-sorter"
        echo "Selection=d"
        echo "Extensions=dir;"
    } > "$NEMO_ACTIONS_DIR/image_sorter_open.nemo_action"

    # Azione 2: Analizza cartella (Disk Analyzer)
    cat > "$NEMO_ACTIONS_DIR/image_sorter_disk_analyzer.nemo_action" << NEMOEOF
[Nemo Action]
Name=Analizza cartella (Image Sorter)
Comment=Apri il Disk Analyzer di Image Sorter su questa cartella
Exec=bash -c '$PYTHON_CMD "$SCRIPT_DIR/disk_analyzer.py" "%F"'
Icon-Name=utilities-system-monitor
Selection=d
Extensions=dir;
NEMOEOF
    ok "$(t nemo_installed): $NEMO_ACTIONS_DIR"
    if pgrep -x nemo > /dev/null; then
        nemo -q 2>/dev/null || true
        sleep 1
        nemo --no-default-window &
        ok "$(t nemo_restarted)"
    else
        info "$(t nemo_not_running)"
    fi
else
    info "$(t nemo_not_found)"
fi

# =============================================================================
# 8. DESKTOP SHORTCUT
# =============================================================================
step "$(t step_shortcut)"

for DDIR in "$HOME/Desktop" "$HOME/Scrivania"; do
    if [ -d "$DDIR" ]; then
        cp "$INSTALL_DIR/image_sorter.desktop" "$DDIR/image_sorter.desktop"
        chmod +x "$DDIR/image_sorter.desktop"
        gio set "$DDIR/image_sorter.desktop" metadata::trusted true 2>/dev/null || true
        ok "$(t shortcut_done): $DDIR"
        break
    fi
done

# =============================================================================
# 9. STREAMCONTROLLER AUTOSTART
# =============================================================================
step "$(t step_sc)"

if command -v streamdeck &>/dev/null; then
    AUTOSTART_DIR="$HOME/.config/autostart"
    mkdir -p "$AUTOSTART_DIR"
    cat > "$AUTOSTART_DIR/streamdeck.desktop" << SDEOF
[Desktop Entry]
Type=Application
Name=StreamDeck Controller
Exec=streamdeck --no-ui
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
SDEOF
    ok "$(t sc_done)"
else
    info "$(t sc_missing)"
    info "$(t sc_hint)"
fi

# =============================================================================
# SUMMARY / RIEPILOGO
# =============================================================================
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  $(t title_done)${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "  $(t summary_prog):    $EXEC"
echo "  $(t summary_python):      $PYTHON_CMD ($PY_VERSION)"
echo "  $(t summary_menu):        $INSTALL_DIR/image_sorter.desktop"
echo "  $(t summary_launch): python3 $EXEC"
echo ""

# Check missing optional deps
MISSING=""
for pkg_imp in "piexif:piexif" "reverse_geocode:reverse_geocode" "folium:folium" "tkinterdnd2:tkinterdnd2"; do
    pkg="${pkg_imp%%:*}"; imp="${pkg_imp##*:}"
    "$PYTHON_CMD" -c "import $imp" &>/dev/null 2>&1 \
        || MISSING="${MISSING}    pip install ${pkg} --user\n"
done

if [ -n "$MISSING" ]; then
    echo -e "  $(t missing_deps)"
    echo -e "$MISSING"
    echo "  $(t missing_all)"
    echo "    pip install piexif reverse-geocode folium tkinterdnd2 --user"
    echo ""
fi

if [ "${NEEDS_REBOOT:-false}" = "true" ]; then
    echo -e "  ${YELLOW}$(t reboot_warn)${NC}"
    echo ""
fi

echo "  $(t open_hint)"
echo "$(t open_hint2)"
echo ""
