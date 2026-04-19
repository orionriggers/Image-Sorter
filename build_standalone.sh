#!/bin/bash
# =============================================================================
#  Image Sorter v1.11 — Build eseguibile standalone con PyInstaller
#  Uso: bash build_standalone.sh
#
#  Produce: dist/image_sorter (eseguibile singolo, Linux x86_64)
#  Requisiti: pip install pyinstaller
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="1.11"
APP_NAME="image_sorter"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "  ${RED}[ERR]${NC} $1"; exit 1; }

echo ""
echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}  Image Sorter v${VERSION} — Build Standalone${NC}"
echo -e "${CYAN}================================================${NC}"
echo ""

# ── Verifica prerequisiti ────────────────────────────────────────────────────
info "Verifica prerequisiti..."
command -v python3 >/dev/null || err "python3 non trovato"
python3 -c "import PyInstaller" 2>/dev/null || {
    warn "PyInstaller non trovato. Installazione..."
    pip install pyinstaller --break-system-packages || err "Impossibile installare PyInstaller"
}
ok "PyInstaller disponibile"

python3 -c "import PIL" 2>/dev/null   || err "Pillow non installato (pip install pillow)"
python3 -c "import send2trash" 2>/dev/null || warn "send2trash non trovato — cestino potrebbe non funzionare"

# ── Pulizia precedenti build ──────────────────────────────────────────────────
info "Pulizia build precedenti..."
rm -rf "$SCRIPT_DIR/build" "$SCRIPT_DIR/dist" "$SCRIPT_DIR/${APP_NAME}.spec" 2>/dev/null || true
ok "Pulizia completata"

# ── Raccolta file da includere ────────────────────────────────────────────────
info "Raccolta file aggiuntivi..."

DATAS=""
# translations.py
[ -f "$SCRIPT_DIR/translations.py" ] && \
    DATAS="$DATAS --add-data '$SCRIPT_DIR/translations.py:.' "
# sorter_icons/
[ -d "$SCRIPT_DIR/sorter_icons" ] && \
    DATAS="$DATAS --add-data '$SCRIPT_DIR/sorter_icons:sorter_icons' "
# Manuali
[ -f "$SCRIPT_DIR/LEGGIMI.txt" ] && \
    DATAS="$DATAS --add-data '$SCRIPT_DIR/LEGGIMI.txt:.' "
[ -f "$SCRIPT_DIR/README_en.txt" ] && \
    DATAS="$DATAS --add-data '$SCRIPT_DIR/README_en.txt:.' "

ok "File aggiuntivi: translations.py, sorter_icons/, manuali"

# ── Icona per l'eseguibile ────────────────────────────────────────────────────
ICON_OPT=""
ICO="$SCRIPT_DIR/sorter_icons/image_sorter_icon.ico"
PNG="$SCRIPT_DIR/sorter_icons/image_sorter_icon.png"
if [ -f "$ICO" ]; then
    ICON_OPT="--icon='$ICO'"
    ok "Icona: $ICO"
elif [ -f "$PNG" ]; then
    # Converti PNG → ICO se imagemagick disponibile
    if command -v convert >/dev/null 2>&1; then
        convert "$PNG" -resize 256x256 "$SCRIPT_DIR/sorter_icons/image_sorter_icon_build.ico" && \
            ICON_OPT="--icon='$SCRIPT_DIR/sorter_icons/image_sorter_icon_build.ico'" && \
            ok "Icona convertita da PNG"
    else
        warn "imagemagick non trovato — icona non inclusa nell'eseguibile"
    fi
fi

# ── Build ─────────────────────────────────────────────────────────────────────
info "Avvio build PyInstaller (modalità --onefile)..."
echo ""

eval python3 -m PyInstaller \
    --onefile \
    --name "$APP_NAME" \
    --noconsole \
    $ICON_OPT \
    $DATAS \
    --hidden-import="PIL._tkinter_finder" \
    --hidden-import="PIL.ImageTk" \
    --hidden-import="send2trash" \
    --hidden-import="streamdeck" \
    --collect-submodules="PIL" \
    --strip \
    "$SCRIPT_DIR/image_sorter.py"

echo ""

# ── Verifica output ───────────────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/dist/$APP_NAME" ]; then
    SIZE=$(du -sh "$SCRIPT_DIR/dist/$APP_NAME" | cut -f1)
    ok "Build completata: dist/${APP_NAME}  (${SIZE})"
    echo ""
    echo -e "  ${GREEN}Eseguibile:${NC} $SCRIPT_DIR/dist/$APP_NAME"
    echo ""
    info "Nota: al primo avvio potrebbe impiegare qualche secondo (estrazione)"
    info "Copia il file 'dist/$APP_NAME' dove vuoi — è autosufficiente"
    info "I file di configurazione (config.json, translations.py) vengono"
    info "cercati nella stessa cartella dell'eseguibile"
else
    err "Build fallita — dist/${APP_NAME} non trovato"
fi

# ── Pulizia file temporanei ───────────────────────────────────────────────────
rm -rf "$SCRIPT_DIR/build" "$SCRIPT_DIR/${APP_NAME}.spec" 2>/dev/null || true
rm -f "$SCRIPT_DIR/sorter_icons/image_sorter_icon_build.ico" 2>/dev/null || true
ok "File temporanei rimossi"

echo ""
echo -e "${CYAN}================================================${NC}"
echo -e "${CYAN}  Build v${VERSION} completata${NC}"
echo -e "${CYAN}================================================${NC}"
echo ""
