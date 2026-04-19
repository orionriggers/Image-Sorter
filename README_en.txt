==============================================================================
  IMAGE SORTER v1.12
  Image, video and PDF viewer and sorter for Linux
==============================================================================

DESCRIPTION
-----------
Image Sorter is a Linux desktop application for quickly viewing, navigating
and sorting images, videos and PDFs into destination folders using the
keyboard, mouse or an Elgato Stream Deck.

Supported formats:
  Images : JPG, PNG, GIF, BMP, TIFF, WEBP  (+ additional formats in settings)
  Videos : MP4, MOV, AVI, MKV, WEBM, M4V, FLV  (requires ffmpeg)
  PDF    : multi-page PDF  (requires pymupdf or poppler-utils)
  Other  : files without extension detected via magic bytes


==============================================================================
  INSTALLATION
==============================================================================

1. Install dependencies:
     bash installa.sh

2. Restart the PC (required for Stream Deck and MIME associations).

PYTHON DEPENDENCIES (installed automatically)
     pip3 install pillow streamdeck send2trash pymupdf

SYSTEM DEPENDENCIES
     sudo apt install ffmpeg poppler-utils libhidapi-hidraw0 python3-tk

BUILD STANDALONE EXECUTABLE
     pip3 install pyinstaller
     bash compila_eseguibile.sh
Produces "image_sorter_bin" — no Python required on the target machine.


==============================================================================
  KEYBOARD SHORTCUTS
==============================================================================

NAVIGATION
  Arrow RIGHT                Next file (loop)
  Arrow LEFT                 Previous file (loop)
  C                          Rotate 90° clockwise
  A                          Rotate 90° anticlockwise
  Ctrl + ←  or  Ctrl + X    Undo last move and restore file
  Arrow UP                   Previous page (multi-page PDF only)
  Arrow DOWN                 Next page (multi-page PDF only)
  PgUp / PgDn                Previous / next preset
  Tab  or  N                 Next preset
  Shift+Tab                  Previous preset
  Mouse wheel                Next/prev file (scrolls if zoom > 1)

SORTING  [requires Sidebar or Keypad active]
  Keys 1–9, 0                Move file to active preset destination
  Ctrl + 1–9, 0              Copy file (without moving)
  DEL × 2                    Move file to trash
  DEL + Enter                Move to trash (alternative confirm)

ZOOM & DISPLAY
  +  /  −                    Zoom in / out
  Z                          Fit to canvas
  X                          Original size (1:1 pixels)
  F                          Fullscreen (images only)
  Enter                      Fullscreen / External player (video/PDF)
  H                          Show/hide top header bar

INFO
  I                          EXIF overlay (technical image data)

RIGHT-CLICK MENU  (on the displayed file)
  Rename                     Rename file inline
  Rotate 90 CW               Rotate and save (images only)
  Rotate 90 CCW              Rotate and save (images only)
  Crop...                    Interactive crop overlay (images only)
  Open folder                Show file in file manager
  Edit with...               Open with configurable editor (default: GIMP)
  Copy path                  Copy full path to clipboard

WINDOWS & PANELS
  O  or  B                   Folder browser (tree + thumbnails)
  S                          Sidebar (cycle: inline / popup / hidden)
  D  or  P                   Keypad (cycle 1/2/3 columns)
  Ctrl + D                   S-Deck: toggle preset mode on physical deck
  R                          Settings
  Ctrl + R                   Rename current file directly
  Q  or  Esc                 Quit

FOLDER BROWSER
  Ctrl + A                   Select all files
  Ctrl + C                   Copy selected files
  Ctrl + X                   Cut selected files
  Ctrl + V                   Paste into current folder
  Delete                     Trash selected files
  Single click               Select file or folder (green highlight)
  Ctrl + click               Add/remove from multi-selection
  Double click               Open file / navigate into folder
  1–9, 0  (folder selected)  Move folder to corresponding preset

==============================================================================
  SETTINGS  (key R)
==============================================================================

TAB PRESET
  Manage and select sorting presets.
  Double-click or Enter to activate the selected preset.

TAB DESTINATIONS
  Configure label and path for each key 1–9/0 of the active preset.
  - "..." button  : opens folder browser with quick access and drives
  - "X" button    : clears the key destination
  - Label field   : name shown on the key (auto-filled from folder name)
  Press Apply (or Enter) to save.

TAB DISPLAY
  Choose which file types to show: Images, Videos, PDFs, files without ext.
  Each filter has a clear ON/OFF button.
  Additional extensions: add extra formats (e.g. .heic, .arw, .cr2).
  Settings are saved and remembered between sessions.

TAB SHORTCUTS
  Full list of keyboard shortcuts, organized by category.

TAB LANGUAGE
  Switch interface language. Requires restart to apply.
  Add new languages by editing translations.py.

TAB MANUAL
  Open this file or the Italian README.


==============================================================================
  FOLDER BROWSER  (key O)
==============================================================================

QUICK ACCESS BAR
  Quick access buttons: ~, Images, Videos, Desktop, Documents, /
  Mounted drives detected automatically from /media/ and /mnt/
  Last visited folder shown as "< name"

TREE NAVIGATION
  Click on tree               Show folder contents on the right
  Double-click on tree        Open folder as main source
  Double-click on thumbnail   Open file in main window
  Right-click on folder       Rename folder

TREE INDICATORS
  [+]   Contains images   [v]  Contains videos   [p]  Contains PDFs

MULTI-SELECTION
  Single click               Select / deselect (green background)
  Ctrl+A                     Select all files in current folder

  Action bar (appears with selected files):
  - Colored preset buttons   Move selected files to destination
  - Batch rename             Rename with prefix + sequential numbering
  - Copy                     Copy files to a chosen folder
  - Deselect all             Clear selection

ASSIGNMENT PANEL  (button "Assign")
  3 rows of presets with dropdown menus and colored buttons 1–9/0.
  Right-click a button to rename its label.


==============================================================================
  DISK ANALYZER  ("Disk analysis" button in the folder browser)
==============================================================================

Opens a separate window with a navigable sunburst chart and treemap.

CHART (sunburst or treemap, selectable at the top)
  Click on slice              Navigate into the folder
  Double click on slice       Open folder in Image Sorter browser
  Right click on slice        Menu: navigate / open in file manager / browser
  ▲ up (center)               Go up to parent folder
  Levels slider (1–6)         Depth of rings displayed

FOLDER TREE (right panel, resizable with the divider)
  Double click on row         Navigate into folder
  Arrow ▸                     Expand subfolders (without closing other levels)
  Columns Name / Size / Files Resizable by dragging the heading

BOTTOM BAR
  Current folder name         Shown large on the left
  Size + files                Next to name: 128 MB | 4 folders | 47 (12 images...)
  Hover tooltip               Name + size of folder under cursor
  Open in browser             Opens folder in Image Sorter browser

==============================================================================
  CROPPING
==============================================================================

Right-click > Crop...  (images only)
  - 8 handles to define area, rule-of-thirds grid
  - "Crop"               : asks whether to overwrite or use new name
  - "Crop & advance"     : overwrites and moves to next file
  - "Crop next"          : overwrites and opens crop on next file
  - "Remember" checkbox  : reuses relative position and size
  - ESC or Cancel        : exit without changes


==============================================================================
  MULTI-PAGE PDF
==============================================================================

  Arrow UP / DOWN        Navigate between pages
  Page slider (bar)      Jump directly to a page
  < > buttons            Previous / next page
  "Thumbs" button        Side thumbnail panel (scrollable)
  Badge "PDF N/TOT"      Shows current page and total (bottom-left corner)

  At first page:   Arrow UP goes to previous file
  At last page:    Arrow DOWN advances to next file


==============================================================================
  DUPLICATE FINDER
==============================================================================

Open from folder browser toolbar with "Find duplicates" button.

Three modes:
  Content (SHA256)     Exact byte comparison — finds copies even with
                       different names. Slower but 100% accurate.
  Quick (name+size)    Compares only file name and size — instant.
  Compare A vs B       Two specific folders: shows only files present
                       in both. Useful for comparing backup vs original.

Files named "copy", "copia", "(1)", "(2)" etc. are automatically ranked
last in each group (marked [COPY]) so they get trashed first.

Right-click a result to: Open / Show in file manager / Move to trash.
"Trash all duplicates" keeps the first file in each group.


==============================================================================
  STREAM DECK  (optional)
==============================================================================

OPERATING MODES
  The physical deck operates in two distinct modes:

  IDLE mode (default)
    Active when the software keypad is closed.
    Shows freely configurable pages (2-3 pages with < > navigation).
    Each key can: open folder, launch app, keyboard shortcut,
    open URL, toggle mute, open Image Sorter on a folder.

  PRESET mode
    Active when the software keypad is open (key D/P).
    Shows file sorting keys (1-9, navigation, etc.).

HOW TO ACTIVATE PRESET MODE
  Method 1: Open the software keypad with D or P → deck switches to preset.
  Method 2: Press "Deck [P]" button in the top bar to toggle preset mode
            on the physical deck without opening the software keypad.

PRESET MODE LAYOUT  (Standard 15 keys, 3 rows × 5 columns)
  Row 1:  [1]  [2]  [3]  [Active preset]  [Del]
  Row 2:  [4]  [5]  [6]  [^ Prev preset]  [v Next preset]
  Row 3:  [7]  [8]  [9]  [<< Back      ]  [>> Forward   ]

  Right-click a key   Change label and destination on the fly

CONFIGURING IDLE PAGES
  Open Settings (R) → "Stream Deck" tab
  - Shows connected model and brightness slider
  - Visual grid of all idle pages
  - Click any key to configure it:
      Label, action, parameter, RGB color, background image
  - "+ Page" button to add pages
  - Last 2 keys become < Pag / > N/TOT page navigation
    when multiple pages are configured

SUPPORTED IDLE ACTIONS
  Open folder          Opens in file manager
  Open application     Launches a program (e.g. "gimp", "firefox")
  Keyboard shortcut    E.g. "ctrl+c", "ctrl+alt+t" (requires xdotool)
  Open URL             Opens in default browser
  Toggle mute          Mute/unmute audio (requires pactl)
  Image Sorter         Opens on a specific folder
  Change page          next / prev between idle pages

SETUP
  1. Install StreamController 2.0.6+
  2. Launch: streamdeck --no-ui
  3. Open Image Sorter — it takes control automatically
  4. On softdeck close, physical deck returns to idle mode
  5. On Image Sorter close, StreamController resumes

PERMISSIONS  (if deck not recognized)
  sudo udevadm trigger  +  unplug/replug USB
  Check group: groups | grep plugdev
  If missing: sudo usermod -aG plugdev $USER  (then reboot)


==============================================================================
  CONFIGURATION  (image_sorter_config.json)
==============================================================================

Saved automatically in the same folder as the script/binary.
Contains: presets, destinations, last folder, display filters,
          sidebar mode, crop size, extension settings, language.

To transfer presets to another PC:
  Copy image_sorter_config.json alongside the executable.
  Paths auto-adapt to the current user.


==============================================================================
  TROUBLESHOOTING
==============================================================================

"Stream Deck not found"
  sudo udevadm trigger  +  unplug/replug USB
  groups | grep plugdev  (if missing: sudo usermod -aG plugdev $USER)

"Video thumbnails not visible"
  sudo apt install ffmpeg

"PDF thumbnails not visible"
  pip3 install pymupdf  or  sudo apt install poppler-utils

"Program slow on large files"
  Thumbnails use cache and draft mode automatically.
  For very large videos, ffmpeg stops after 8 seconds.

"Double-click doesn't open file"
  bash installa.sh
  Then: right-click file > Open With > Image Sorter > Set as default


==============================================================================
  TECHNICAL NOTES
==============================================================================

Version         : 1.12
Language        : Python 3.8+
Dependencies    : Pillow, tkinter, streamdeck*, send2trash*, pymupdf*
System          : Linux (tested on Ubuntu 24 and Linux Mint)
Video previews  : ffmpeg (sudo apt install ffmpeg)
PDF previews    : PyMuPDF (pip3 install pymupdf) or pdftoppm
Trash           : Standard freedesktop.org (~/.local/share/Trash)
Stream Deck     : Elgato Standard 15 keys, StreamController v2.0.6+
UI icons        : Generated with Pillow (no external files)
Thumbnail cache : LRU in memory, max 200 entries
NOTE            : Do not use emoji in tkinter widgets (X11 RenderAddGlyphs crash)

==============================================================================
