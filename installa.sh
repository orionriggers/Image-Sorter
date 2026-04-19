#!/bin/bash
# =============================================================================
#  Image Sorter v1.11 — Script di installazione completo
#  Uso: bash installa.sh
#
#  Cosa fa:
#    1. Installa dipendenze di sistema (ffmpeg, poppler-utils, libhidapi, ecc.)
#    2. Installa dipendenze Python (Pillow, send2trash, streamdeck)
#    3. Configura Stream Deck (regola udev, gruppo plugdev)
#    4. Installa icona e file .desktop
#    5. Registra associazioni MIME (doppio click sui file)
#    6. Crea script Nemo/Nautilus (tasto destro)
#    7. Crea collegamento sul desktop
#    8. Configura StreamController in autostart (se installato)
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor"
VERSION="1.11"

# Colori per output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[!]${NC} $1"; }
err()  { echo -e "  ${RED}[ERRORE]${NC} $1"; }

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  Image Sorter v${VERSION} — Installazione${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Cerca eseguibile (binario compilato o script Python)
if [ -f "$SCRIPT_DIR/image_sorter_bin" ]; then
    EXEC="$SCRIPT_DIR/image_sorter_bin"
    IS_BINARY=true
    ok "Eseguibile binario trovato: image_sorter_bin"
elif [ -f "$SCRIPT_DIR/image_sorter.py" ]; then
    EXEC="$SCRIPT_DIR/image_sorter.py"
    IS_BINARY=false
    ok "Script Python trovato: image_sorter.py"
else
    err "Nessun eseguibile trovato in $SCRIPT_DIR"
    exit 1
fi

# =============================================================================
# 1. DIPENDENZE DI SISTEMA
# =============================================================================
echo ""
echo "--- Dipendenze di sistema ---"

# Rileva package manager
PKG_MANAGER=""
if   command -v apt-get &>/dev/null; then PKG_MANAGER="apt"
elif command -v dnf     &>/dev/null; then PKG_MANAGER="dnf"
elif command -v pacman  &>/dev/null; then PKG_MANAGER="pacman"
elif command -v zypper  &>/dev/null; then PKG_MANAGER="zypper"
elif command -v xbps-install &>/dev/null; then PKG_MANAGER="xbps"
fi

info "Package manager rilevato: ${PKG_MANAGER:-nessuno}"

# Mappa nomi pacchetti per distro
pkg_name() {
    local generic="$1"
    case "$PKG_MANAGER" in
        apt)
            case "$generic" in
                ffmpeg)          echo "ffmpeg" ;;
                poppler)         echo "poppler-utils" ;;
                hidapi)          echo "libhidapi-hidraw0" ;;
                python3-tk)      echo "python3-tk" ;;
                python3-pip)     echo "python3-pip" ;;
                x11-utils)       echo "x11-utils" ;;
                *)               echo "$generic" ;;
            esac ;;
        dnf)
            case "$generic" in
                ffmpeg)          echo "ffmpeg" ;;
                poppler)         echo "poppler-utils" ;;
                hidapi)          echo "hidapi" ;;
                python3-tk)      echo "python3-tkinter" ;;
                python3-pip)     echo "python3-pip" ;;
                x11-utils)       echo "xprop" ;;
                *)               echo "$generic" ;;
            esac ;;
        pacman)
            case "$generic" in
                ffmpeg)          echo "ffmpeg" ;;
                poppler)         echo "poppler" ;;
                hidapi)          echo "hidapi" ;;
                python3-tk)      echo "tk" ;;
                python3-pip)     echo "python-pip" ;;
                x11-utils)       echo "xorg-xprop" ;;
                *)               echo "$generic" ;;
            esac ;;
        zypper)
            case "$generic" in
                ffmpeg)          echo "ffmpeg" ;;
                poppler)         echo "poppler-tools" ;;
                hidapi)          echo "libhidapi-hidraw0" ;;
                python3-tk)      echo "python3-tk" ;;
                python3-pip)     echo "python3-pip" ;;
                x11-utils)       echo "xprop" ;;
                *)               echo "$generic" ;;
            esac ;;
        xbps)
            case "$generic" in
                ffmpeg)          echo "ffmpeg" ;;
                poppler)         echo "poppler-utils" ;;
                hidapi)          echo "hidapi" ;;
                python3-tk)      echo "python3-tkinter" ;;
                python3-pip)     echo "python3-pip" ;;
                x11-utils)       echo "xprop" ;;
                *)               echo "$generic" ;;
            esac ;;
        *)                       echo "$generic" ;;
    esac
}

# Verifica se pacchetto è già installato
pkg_installed() {
    local pkg="$1"
    case "$PKG_MANAGER" in
        apt)    dpkg -l "$pkg" &>/dev/null 2>&1 ;;
        dnf)    rpm -q "$pkg" &>/dev/null 2>&1 ;;
        pacman) pacman -Q "$pkg" &>/dev/null 2>&1 ;;
        zypper) rpm -q "$pkg" &>/dev/null 2>&1 ;;
        xbps)   xbps-query "$pkg" &>/dev/null 2>&1 ;;
        *)      command -v "$pkg" &>/dev/null ;;
    esac
}

install_pkg() {
    local generic="$1"
    local pkg
    pkg="$(pkg_name "$generic")"
    if pkg_installed "$pkg"; then
        ok "$pkg già presente"
        return
    fi
    info "Installazione $pkg..."
    case "$PKG_MANAGER" in
        apt)    sudo apt-get install -y "$pkg" ;;
        dnf)    sudo dnf install -y "$pkg" ;;
        pacman) sudo pacman -S --noconfirm "$pkg" ;;
        zypper) sudo zypper install -y "$pkg" ;;
        xbps)   sudo xbps-install -y "$pkg" ;;
        *)      warn "Installa manualmente: $pkg"; return ;;
    esac && ok "$pkg installato" || warn "$pkg non installabile — continuo"
}

if [ -n "$PKG_MANAGER" ]; then
    [ "$PKG_MANAGER" = "apt" ] && {
        info "Aggiornamento lista pacchetti..."
        sudo apt-get update -qq 2>/dev/null || warn "apt update fallito, continuo..."
    }
    install_pkg ffmpeg
    install_pkg poppler
    install_pkg hidapi
    install_pkg python3-tk
    install_pkg python3-pip
    install_pkg x11-utils
else
    warn "Package manager non riconosciuto."
    warn "Installa manualmente: ffmpeg poppler-utils libhidapi python3-tk python3-pip xprop"
fi

# =============================================================================
# 2. DIPENDENZE PYTHON
# =============================================================================
echo ""
echo "--- Dipendenze Python ---"

pip_install() {
    local pkg="$1"
    local import_name="${2:-$1}"
    if python3 -c "import $import_name" &>/dev/null 2>&1; then
        ok "$pkg già presente"
    else
        info "Installazione $pkg..."
        # --break-system-packages esiste solo da Python 3.11+
        PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
        if [ "$PY_MINOR" -ge 11 ] 2>/dev/null; then
            pip3 install "$pkg" --break-system-packages 2>/dev/null || \
            pip3 install "$pkg" --user 2>/dev/null || true
        else
            pip3 install "$pkg" 2>/dev/null || \
            pip3 install "$pkg" --user 2>/dev/null || true
        fi
        python3 -c "import $import_name" &>/dev/null 2>&1 && ok "$pkg installato" || warn "$pkg potrebbe non funzionare"
    fi
}

pip_install "pillow" "PIL"
pip_install "send2trash" "send2trash"
pip_install "pymupdf" "fitz"
pip_install "streamdeck" "StreamDeck"

# =============================================================================
# 3. STREAM DECK — UDEV E PERMESSI
# =============================================================================
echo ""
echo "--- Stream Deck ---"

UDEV_FILE="/etc/udev/rules.d/70-streamdeck.rules"
if [ ! -f "$UDEV_FILE" ]; then
    info "Creazione regola udev..."
    sudo sh -c "cat > $UDEV_FILE << 'UDEVEOF'
SUBSYSTEM==\"hidraw\", ATTRS{idVendor}==\"0fd9\", GROUP=\"plugdev\", MODE=\"0660\"
SUBSYSTEM==\"usb\", ATTRS{idVendor}==\"0fd9\", GROUP=\"plugdev\", MODE=\"0660\"
UDEVEOF"
    sudo udevadm control --reload-rules 2>/dev/null || true
    sudo udevadm trigger 2>/dev/null || true
    ok "Regola udev creata"
else
    ok "Regola udev già presente"
fi

if groups "$USER" | grep -q plugdev; then
    ok "Utente $USER già nel gruppo plugdev"
else
    sudo usermod -aG plugdev "$USER"
    ok "Utente $USER aggiunto a plugdev (riavvia per attivare)"
fi

# =============================================================================
# 4. ICONA (multi-risoluzione per X11 _NET_WM_ICON / Alt+Tab)
# =============================================================================
echo ""
echo "--- Icona ---"

ICON_SRC="$SCRIPT_DIR/sorter_icons/image_sorter_icon.png"
ICON_NAME="image-sorter"

# Crea la cartella sorter_icons/ se non esiste
mkdir -p "$SCRIPT_DIR/sorter_icons"

if [ ! -f "$ICON_SRC" ]; then
    info "Generazione icona HUD..."
    python3 - "$ICON_SRC" << 'PYEOF'
import sys
from PIL import Image, ImageDraw
out = sys.argv[1]
SIZE = 256
img = Image.new("RGBA", (SIZE, SIZE), (0,0,0,0))
d = ImageDraw.Draw(img)
s = SIZE; cx = cy = s // 2
d.ellipse([2,2,s-3,s-3], fill=(13,17,23,255))
d.ellipse([4,4,s-5,s-5], outline=(30,70,100,200), width=2)
px1,py1,px2,py2 = int(s*.20),int(s*.25),int(s*.80),int(s*.65)
d.rounded_rectangle([px1,py1,px2,py2], radius=8,
                     fill=(10,26,42,255), outline=(0,200,255,220), width=2)
d.polygon([(px1+10,py2-8),(px1+10,py1+20),(px1+60,py2-8)], fill=(0,150,200,180))
d.ellipse([px2-50,py1+8,px2-20,py1+38], outline=(0,200,255,200), width=2)
ay = py2+14
d.line([(cx-30,ay),(cx+30,ay)], fill=(0,200,255,220), width=3)
d.polygon([(cx+20,ay-8),(cx+20,ay+8),(cx+40,ay)], fill=(0,200,255,220))
img.save(out, "PNG")
print(f"Icona generata: {out}")
PYEOF
    ok "Icona generata"
fi

info "Installazione icona in tutte le risoluzioni (XDG hicolor)..."
python3 - "$ICON_SRC" "$ICON_DIR" "$ICON_NAME" << 'PYEOF'
import sys, os
from PIL import Image
src, icon_dir, icon_name = sys.argv[1], sys.argv[2], sys.argv[3]
img = Image.open(src).convert("RGBA")
sizes = [16, 22, 24, 32, 48, 64, 96, 128, 256, 512]
for size in sizes:
    d = os.path.join(icon_dir, f"{size}x{size}", "apps")
    os.makedirs(d, exist_ok=True)
    # Salva sia con il nome XDG standard che con quello legacy
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(os.path.join(d, f"{icon_name}.png"), "PNG")
    resized.save(os.path.join(d, "image_sorter.png"), "PNG")
    # Salva anche nella cartella dello script per iconphoto()
    icons_dir = os.path.dirname(src)
    resized.save(os.path.join(icons_dir, f"image_sorter_icon_{size}.png"), "PNG")
d = os.path.join(icon_dir, "scalable", "apps")
os.makedirs(d, exist_ok=True)
img.resize((512,512), Image.Resampling.LANCZOS).save(
    os.path.join(d, f"{icon_name}.png"), "PNG")
# Salva anche nella cartella sorter_icons/ per iconphoto() e _NET_WM_ICON
icons_dir = os.path.join(os.path.dirname(src), "sorter_icons")
os.makedirs(icons_dir, exist_ok=True)
import shutil
shutil.copy(src, os.path.join(icons_dir, "image_sorter_icon.png"))
for sz in sizes:
    resized = img.resize((sz, sz), Image.Resampling.LANCZOS)
    resized.save(os.path.join(icons_dir, f"image_sorter_icon_{sz}.png"), "PNG")
print(f"Icone installate: {icon_name}")
PYEOF

# Aggiorna cache icone
gtk-update-icon-cache -f -t "$ICON_DIR" 2>/dev/null || true
update-icon-caches "$ICON_DIR" 2>/dev/null || true
kbuildsycoca6 --noincremental 2>/dev/null || kbuildsycoca5 --noincremental 2>/dev/null || true
ok "Icona installata (${ICON_NAME}, tutte le risoluzioni)"

# =============================================================================
# 5. FILE .DESKTOP E ASSOCIAZIONI MIME
# =============================================================================
echo ""
echo "--- File .desktop e MIME ---"

mkdir -p "$INSTALL_DIR"

if [ "$IS_BINARY" = true ]; then
    EXEC_CMD="$EXEC %F"
else
    chmod +x "$EXEC"
    EXEC_CMD="python3 $EXEC %F"
fi

cat > "$INSTALL_DIR/image_sorter.desktop" << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=Image Sorter
GenericName=Smistatore immagini e video
Comment=Visualizza e smistate immagini, video e PDF con la tastiera
Exec=$EXEC_CMD
Icon=image-sorter
Terminal=false
StartupNotify=false
StartupWMClass=image_sorter
Categories=Graphics;Photography;
MimeType=image/jpeg;image/png;image/gif;image/bmp;image/tiff;image/webp;image/x-bmp;
Keywords=immagini;foto;video;pdf;smista;sort;
DESKTOP
chmod +x "$INSTALL_DIR/image_sorter.desktop"
update-desktop-database "$INSTALL_DIR" 2>/dev/null || true
ok "File .desktop installato"

# Associazioni MIME
MIME_APPS="$HOME/.local/share/applications/mimeapps.list"
touch "$MIME_APPS"
if ! grep -q "\[Default Applications\]" "$MIME_APPS"; then
    echo "" >> "$MIME_APPS"
    echo "[Default Applications]" >> "$MIME_APPS"
fi
ADDED_MIME=0
# Solo immagini come default — video e PDF mantengono il loro programma predefinito
for mime in \
    image/jpeg image/png image/gif image/bmp image/tiff image/webp; do
    if ! grep -q "^$mime=" "$MIME_APPS"; then
        sed -i "/^\[Default Applications\]/a $mime=image_sorter.desktop" "$MIME_APPS"
        ADDED_MIME=$((ADDED_MIME+1))
    fi
done
ok "Associazioni MIME registrate ($ADDED_MIME nuove)"

# Aggiungi image_sorter come applicazione disponibile (non predefinita)
# per video e PDF — appare nel menu "Apri con" ma non sostituisce il default
ADDED_FILE="$HOME/.local/share/applications/mimeapps.list"
if ! grep -q "\[Added Associations\]" "$ADDED_FILE"; then
    echo "" >> "$ADDED_FILE"
    echo "[Added Associations]" >> "$ADDED_FILE"
fi
for mime in video/mp4 video/x-matroska video/quicktime application/pdf; do
    if ! grep -A9999 "\[Added Associations\]" "$ADDED_FILE" | grep -q "^$mime="; then
        echo "$mime=image_sorter.desktop" >> "$ADDED_FILE"
    fi
done

# =============================================================================
# 6. SCRIPT NEMO / NAUTILUS
# =============================================================================
echo ""
echo "--- Script file manager ---"

for NM_DIR in \
    "$HOME/.local/share/nautilus/scripts" \
    "$HOME/.local/share/nemo/scripts"; do
    mkdir -p "$NM_DIR"
    printf '#!/bin/bash\nFIRST="$(echo "$NAUTILUS_SCRIPT_SELECTED_FILE_PATHS$NEMO_SCRIPT_SELECTED_FILE_PATHS" | head -n1)"\n[ -n "$FIRST" ] && %s "$FIRST" &\n' \
        "$([ "$IS_BINARY" = true ] && echo "$EXEC" || echo "python3 $EXEC")" \
        > "$NM_DIR/Apri con Image Sorter"
    chmod +x "$NM_DIR/Apri con Image Sorter"
    ok "Script installato in: $NM_DIR"
done

# =============================================================================
# 7. COLLEGAMENTO DESKTOP
# =============================================================================
echo ""
echo "--- Collegamento desktop ---"

for DDIR in "$HOME/Desktop" "$HOME/Scrivania"; do
    if [ -d "$DDIR" ]; then
        cp "$INSTALL_DIR/image_sorter.desktop" "$DDIR/image_sorter.desktop"
        chmod +x "$DDIR/image_sorter.desktop"
        gio set "$DDIR/image_sorter.desktop" metadata::trusted true 2>/dev/null || true
        ok "Collegamento creato in: $DDIR"
        break
    fi
done

# =============================================================================
# 8. STREAMCONTROLLER AUTOSTART
# =============================================================================
echo ""
echo "--- StreamController ---"

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
    ok "StreamController configurato in autostart (--no-ui)"
else
    warn "StreamController non trovato — salta autostart"
    info "Per installarlo: pip3 install streamdeck --break-system-packages"
fi

# =============================================================================
# RIEPILOGO
# =============================================================================
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  Installazione completata! — Image Sorter v${VERSION}${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "  File installato:  $EXEC"
echo "  Icona:            $ICON_DIR"
echo "  Menu:             $INSTALL_DIR/image_sorter.desktop"
echo ""

# Avvisi post-installazione
NEEDS_REBOOT=false
if ! groups "$USER" | grep -q plugdev 2>/dev/null; then
    warn "Riavvia o fai logout/login per attivare il gruppo plugdev (Stream Deck)"
    NEEDS_REBOOT=true
fi

echo "  Per aprire file con doppio click:"
echo "    Tasto destro > Apri con > Image Sorter"
echo "    Spunta 'Ricorda per sempre'"
echo ""

if [ "$NEEDS_REBOOT" = true ]; then
    echo -e "  ${YELLOW}Consigliato riavviare il PC per attivare tutti i permessi.${NC}"
    echo ""
fi
