IMAGE SORTER v1.45
==================
A program to manage, view, and sort images, videos, and PDFs.

Version         : 1.45
Language        : Python 3.8+
Interface       : tkinter + Pillow
Platform        : Linux (tested on Linux Mint / Ubuntu)

QUICK INSTALL
-------------
  bash installa.sh

  or manually:
    pip install Pillow send2trash pymupdf streamdeck --user
    pip install piexif reverse-geocode folium tkinterdnd2 --user
    pip install pillow-avif-plugin --user   (for .avif files)
    pip install pillow-heif --user          (for .heic files)

LAUNCH
------
  python3 image_sorter.py
  python3 image_sorter.py /path/to/image.jpg   (opens the folder)

PROGRAM FILES
-------------
  image_sorter.py    main program                   v1.45.10
  disk_analyzer.py   disk usage analyzer            v1.45.0
  timeline.py        timeline and GPS map           v1.45.0
  exif_editor.py     EXIF metadata editor           v1.45.0
  translations.py    IT/EN strings                  v1.45.0
  installa.sh        installation script            v1.36.3

MAIN SHORTCUTS
--------------
  Arrows             Navigate between images
  1-9, 0             Move to active preset
  Ctrl+1-9,0         Copy to active preset
  DEL                Trash file
  Z / X              Fit / Original size
  + / -              Zoom in / out
  Ctrl+wheel         Zoom in / out (also while cropping)
  F                  Fullscreen
  H                  Show/hide header
  C / A              Rotate 90° CW / CCW
  K                  Crop (Krop)
  I                  EXIF info overlay
  Ctrl+F             Rating overlay (flag: stars and color)
  W                  Compare mode
  M                  PDF page thumbnails (with multi-page PDF open)
  T                  Open/close Timeline
  O / B              Folder browser — open/close
  S                  Sidebar
  R                  Open/close Settings
  Ctrl+R             Rename current file
  Ctrl+T             Open Tag window for current file
  Ctrl+H             Open/close operation History
  Ctrl+D             Physical deck: toggle idle/preset mode
  Ctrl+Z             Undo last move/crop
  Esc                Close open window / quit
  Q                  Quit

VERSIONING
----------
  x.Y.0   coordinated bump of all files (new features)
  x.y.Z   minor fixes, third number independent per file

CROP (key K)
------------
  - Floating draggable toolbar (wm_overrideredirect)
  - 14 aspect ratio presets (Free, 1:1, 16:9, 4:3, etc.)
  - "Next" button: advance without modifying
  - "Crop next": crops and opens crop on the next image
  - Esc closes crop

EXIF INFO (key I)
-----------------
  - Overlay on canvas with file info and EXIF data
  - Right-click > EXIF Info (also from browser)
  - Esc closes the overlay

TIMELINE (key T)  — Deep view
------------------------------
  - Colored border on thumbnails per source folder
  - Multiple selection: single click, Ctrl+click, Shift+click
  - Click on background deselects all
  - Del: trash selected files (with confirmation if >1)
  - Right-click on selection: acts on all selected
  - OptionMenu View (Timeline/Grid) and Sort (Shot/File/Place)
  - Recent/Old first button works after scan
  - Context menu uses tk_popup (stable on Linux/X11)

FOLDER BROWSER (key O/B)  — Navigate
--------------------------------------
  - Right-click: open, rename, EXIF, convert, preset, properties
  - EXIF Info: centered popup, single instance, above browser

SUPPORTED FORMATS
-----------------
  Images: JPG, PNG, GIF, BMP, TIFF, WebP, HEIC/HEIF, AVIF
  Video:  MP4, MKV, AVI, MOV, WebM, M4V, FLV
  PDF:    via pdftoppm (poppler-utils)

TECHNICAL NOTES
---------------
  - AVIF:        pip install pillow-avif-plugin --user
  - HEIC/HEIF:   pip install pillow-heif --user
  - NO emoji in tkinter widgets (X11 crash)
  - Context menu: tk_popup() not menu.post() on Linux
  - Popup bars: wm_overrideredirect(True) for stable position

WHAT'S NEW v1.27 → v1.28 (debug session)
-----------------------------------------
Note: the manuals had not been updated between v1.23 and v1.27; this
section only covers the fixes verified in this debugging session on the
v1.27.x code. Intermediate-version features (1.24-1.27) aren't documented
here since that material wasn't available in this session.

BUGS FIXED
  - timeline.py: build_map() referenced "self.sorter" with no self in
    scope (it's a module-level function, not a method). If folium wasn't
    installed, or no GPS images were found, the app crashed with a
    NameError instead of showing the intended message. Now it always
    uses messagebox, as appropriate for a standalone function.
  - timeline.py: IMG_EXT was missing ".heif" (only ".heic" was present),
    so HEIF files weren't recognized as images in the Timeline.
  - exif_editor.py: read_iptc_xmp() was called but never defined anywhere
    in the project. The error was swallowed by a bare except, so the
    IPTC/XMP tab always showed "No IPTC/XMP data found" even when XMP
    data was present in the file. Added a real implementation that reads
    the XMP block via Pillow (native IPTC stays empty: piexif doesn't
    support it and it wasn't already a project dependency).
  - image_sorter.py: the startup-crash error window used "self.config" in
    a spot where "self" doesn't exist (it's in the except block around
    app launch, before the ImageSorter instance exists). This caused a
    second error that prevented the message from displaying (the log was
    still written to disk). Language is now detected from the LANG
    environment variable, matching the pattern used elsewhere in startup
    fallbacks.
  - translations.py: some keys (btn_settings, btn_sidebar, btn_play,
    btn_quit, btn_fullscreen) were duplicated in both IT and EN. In
    English, "btn_fullscreen" had two different values ("Full Screen" and
    "Fullscreen"): the second one, overwriting the first, always won.
    Removed the duplicates, keeping one consistent value per key.

CHECKS PERFORMED (no issues found)
  - All files compile cleanly (py_compile + AST parsing)
  - LANG/SHORTCUTS structure consistent between IT and EN (no missing keys)
  - image_sorter_error.log empty (no crashes recorded by the user)

WHAT'S NEW v1.28 → v1.29
---------------------------

CROP — EDGE MAGNET
  - Automatically snaps crop edges to sharp color boundaries (useful for
    screenshots: panels, windows, UI bars)
  - Two-pass detection: rough profile on a downscaled image to stay
    instant, then full-resolution refinement of the candidates found
    (accurate to within 1px)
  - "Magnet" checkbox in the crop bar, on by default, toggleable; only
    active in free (unconstrained) aspect ratio mode

CROP — MAGNIFIER LOUPE
  - Floating window showing a crisp, pixel-sharp zoomed detail (no
    blurring) around the point being dragged
  - Reticle that outlines the exact single pixel being pointed at,
    without covering its color
  - Exact pixel coordinates shown below the preview

CROP — CTRL+WHEEL ZOOM
  - Ctrl+wheel zooms in/out, even while the crop tool is open
  - The view automatically scrolls to keep the selection visible after
    zooming

CROP — FIXES
  - A slightly imprecise click on a corner/edge no longer resets the
    current selection (increased tolerance before treating a click as
    "outside" the rectangle)
  - Fixed mouse coordinates when the canvas is scrolled (pre-existing
    bug, surfaced by the new crop zoom feature): without the fix,
    dragging a crop edge with the canvas scrolled produced position
    jumps or incorrect resizing
  - The image "pan" feature (scrolling a zoomed-in view) no longer
    interferes with dragging crop handles

HISTORY
  - Preview thumbnail (48px) between the checkbox and the date on each
    row, generated from the file at the time of the operation, saved in
    a dedicated temp folder and automatically removed when the list is
    cleared or old entries age out past the 200-entry limit
  - The row detail no longer repeats the filename when the destination
    has the same name (shows the destination folder instead of the
    duplicate name)

FULL AUDIT AND DEBUGGING (end-of-session review)
  - Added ~60 missing translations to the IT→EN auto-translation
    dictionary (hardcoded widgets), found by comparing every static
    string in the program against the existing dictionary
  - Removed 7 pre-existing duplicates in the same dictionary (identical
    values in every case, so just redundancy, not an override bug)
  - Fixed a functional bug in the "wrong file extension" popup: the
    "Rename to..." button never actually performed the rename on disk
    (missing the os.rename call), and the overwrite-confirmation
    response was never handled when the target file already existed
  - Cleaned up ~30 static-analysis warnings (unused imports, dead
    variables, f-strings without placeholders) across all 5 files — no
    behavior changes, cleanup only

WHAT'S NEW v1.29 → v1.30
---------------------------

ENLARGED PREVIEW PANEL (Naviga + Timeline)
  - New right-hand column, toggled via the "Preview" checkbox in the
    toolbar (hidden by default)
  - Shows the selected file enlarged, scaled to fit the available space
    while keeping proportions — images, video (extracted frame), and in
    Naviga also PDFs (first page)
  - Draggable divider to adjust proportions; open/closed state and
    proportions remembered between sessions
  - Right-click menu with the same functions already available on
    thumbnails (Open, Rename, Copy/Cut/Paste, Trash, EXIF, Convert
    format, Properties, Restore); double-click to open
  - Video and PDF processing runs on a separate thread so the interface
    doesn't freeze on every click while browsing

DUPLICATE FINDER
  - The "content check" (SHA256 hash) now uses a three-stage pipeline
    (size → quick hash → full hash) instead of hashing every single
    file: up to 87% less data read from disk on folders with many videos
  - Deletions from the duplicate finder (all 3 modes) now go through the
    transit trash and appear in History, instead of going straight to
    the system trash
  - Clearer alert for "Trash all duplicates": explicitly states the
    action applies to all duplicates found, not just selected ones
  - Fixed a bug in results re-sorting that duplicated blank rows on every
    sort change

TRASH AND HISTORY — full audit
  - Found and fixed several scattered deletion functions (Naviga: multi-
    selection, context menu; Timeline: context menu) that were still
    going straight to the system trash, bypassing the transit trash and
    therefore not appearing in History or being undoable
  - Documented exception: deleting an entire folder still uses the
    direct system trash (the transit mechanism is designed for
    individual files)
  - History thumbnail generation moved to a background thread: it used
    to block every single file move (the most frequent action while
    sorting) for the time it took to generate the preview, especially
    slow for videos

"NAVIGA" BROWSER — various stability fixes
  - Fixed the missing ".." (parent folder) cell in completely empty
    folders
  - Optimized batch loading of thumbnails (less artificial delay,
    smoother loading)
  - Resolved a long series of visible thumbnail "jumps" during
    navigation and file selection, caused by several UI bars changing
    height dynamically as they appeared/disappeared — now all have
    permanently reserved fixed space
  - Explicitly locked grid row/column sizes to eliminate the last
    residual visual instability

FORMAT CONVERSION
  - After a conversion (e.g. PNG→JPG), only the cells of the files
    actually converted are updated, instead of reloading the entire
    thumbnail grid

QUALITY CONTROL
  - Full translation audit: added ~60 missing translations to the IT→EN
    dictionary, removed pre-existing duplicates
  - Fixed a functional bug in the "wrong file extension" popup (the
    "Rename to..." button never actually performed the rename)
  - Verified full parity and absence of duplicates/missing keys across
    all translation dictionaries

WHAT'S NEW v1.30 → v1.31
---------------------------
A session focused on the stability of the "Naviga" browser and on
History coverage.

"NAVIGA" BROWSER — THUMBNAIL GRID
  - Fixed an accumulating minimum grid width: the column reset only
    covered the first 12 columns, but small thumbnails in a wide window
    can produce many more. Columns past the twelfth stayed configured
    forever, inflating the grid even after switching to large
    thumbnails or shrinking the window
  - The reset now also runs for empty folders and for the list/tree
    views, which previously skipped it

"NAVIGA" BROWSER — MOUSE WHEEL
  - The wheel was bound twice to the same panel (double scroll per
    notch) and through an application-wide binding: with Naviga open,
    scrolling in the viewer, in Timeline or in Settings also scrolled
    the thumbnail grid. It is now a single binding scoped to that
    window alone
  - The tree and list views now stop event propagation correctly

"NAVIGA" BROWSER — SCROLLABLE AREA
  - The scrollable area was computed with a method that returns no value
    under certain conditions; in that case the previous folder's area
    stayed in effect, allowing scrolling into empty space in an empty
    folder. The height is now always computed explicitly from the actual
    content

"NAVIGA" BROWSER — THUMBNAILS OF LARGE FILES
  - Thumbnails were generated on the main thread, in batches of 30
    files: with videos, PDFs or very large images the grid stayed frozen
    for seconds. The main thread now only creates the cells and reuses
    already-cached thumbnails, while anything requiring decoding is
    generated in the background and applied as soon as it's ready
  - When changing folder, results from the previous folder are
    recognised as stale and discarded
  - Fixed a hang: an unreadable or corrupt file sent the grid loading
    into an infinite loop on that same file

TIMELINE — HISTORY AND UNDO
  - Moves performed with the number keys 1-9 on a multiple selection
    never appeared in History and couldn't be undone from there (unlike
    the same moves performed from the context menu). They are now
    recorded properly
  - A single moved file is recorded as a single entry instead of a
    "batch"
  - Batch entries never had a preview thumbnail, because it was looked
    up in a path that for those entries is a folder rather than a file.
    The preview now appears
  - Undoing a batch could restore the wrong file: if a file with the
    same name already existed at the destination, the moved file gets a
    suffix, and the restore picked up the pre-existing file instead.
    Each entry now records the actual destination of every file
  - Files disappear from the view only if the move actually succeeded
    (previously they vanished on error too, while still on disk)

DISK ANALYZER
  - HEIC/HEIF, AVIF and PNM/PBM/PGM/PPM ended up in the chart's "Other"
    slice instead of "Images", despite being handled as images
    everywhere else in the program

CLEANUP
  - Removed the hover preview on thumbnails, dead code never called from
    anywhere since v1.17: the same need is covered by the enlarged
    preview panel

WHAT'S NEW v1.31 → v1.32
---------------------------
A session focused on renaming, GPS location and context-menu stability.

BATCH RENAME — CUSTOM TEMPLATE
  - Fourth mode in the rename dialog (Navigate > multiple selection >
    right-click > Batch rename), alongside the three existing ones
  - The name is composed from placeholders, arranged as you like:
      {nome} {n} {data} {anno} {mese} {giorno} {ora} {marca} {modello}
      {iso} {focale} {diaframma} {esposizione} {larghezza} {altezza}
      {cartella}
    Example: "{data}_{modello}_{n}"  ->  20240714_NIKON D750_001
  - {n} uses the start number and digit fields already present, {data}
    the format chosen in the dropdown
  - A placeholder with no value (e.g. {modello} on a file without EXIF)
    disappears from the name without leaving doubled separators
  - The last template used is remembered between sessions
  - Batch rename now appears in History and can be undone: it previously
    renamed files directly without recording anything
  - Two files that would produce the same new name: the second is
    skipped with an error, never overwritten

GPS LOCATION
  - Copy/paste of a location between files, recognising pasted text in
    several formats: decimal, degrees/minutes/seconds, geo: links,
    Google Maps URLs
  - Group geotagging from the Timeline: assign one photo's location to
    all other selected ones. If the photo you right-click has no
    location but exactly one in the group does, that one is used and the
    menu says so
  - Writing touches ONLY the GPS block: artist, copyright and
    description of the other files stay intact
  - Undoable from History: each file's previous location is stored,
    including photos that had none, which go back to having none
  - An empty field or text without coordinates no longer produces a
    location of zeros (a point in the Atlantic Ocean)
  - Files in formats that don't accept GPS writing (PNG, HEIC, AVIF...)
    are skipped and counted separately

GPS MAP — THUMBNAILS
  - Markers show the photo thumbnail, with a different border colour for
    files already sorted
  - Below a certain zoom level thumbnails become dots so they don't
    overlap; they turn back into photos when zooming in
  - The same thumbnail, larger, appears in the marker popup
  - Images are embedded in the HTML file: the map stays a single
    openable, movable file. Past 400 photos it falls back to plain icons
    to avoid generating a file that is too heavy
  - Status bar progress while generating

TIMELINE — SELECT BY MONTH
  - Each month header is clickable and selects every file in that group;
    Ctrl+click adds to the existing selection
  - The group's file count is shown next to the title

TRANSIT TRASH — CLOSING DIALOG
  - New "Open folder" button to look at the files before deciding (the
    dialog stays open)
  - New "Don't ask again today" checkbox, valid until midnight (the
    permanent switch remains in Settings)
  - The dialog also shows the transit folder path

TIMELINE CONTEXT MENU — FIX
  - The menu opened and closed itself within a few milliseconds: showing
    it makes the window lose focus, and the automatic close didn't
    distinguish that from switching to another application. It now
    checks where the focus actually went
  - Clicking another program or the system bar closes the menu again
    correctly: the focus-lost event arrives only once, at opening, so
    the check is now periodic while the menu is visible

VIDEO FRAME CACHE
  - It was a FIFO: it evicted the frame inserted first, not the least
    used, so a frequently revisited video could be discarded while
    frames seen once stayed in memory
  - The key now includes the modification date: after replacing a video
    you no longer see the old frame
  - Added protection for access from multiple threads

WHAT'S NEW v1.32 → v1.33
---------------------------
Quick filter, thumbnail indicators, context-menu alignment and
context-menu fixes.

QUICK NAME FILTER (Navigate)
  - "Filter:" field in the top bar, next to favourites: narrows the view
    to files and folders whose name contains the typed text
  - Several space-separated terms must all appear, in any order ("vac
    2024" finds "2024_vacanze_mare.jpg"); case insensitive
  - Match count next to the field (e.g. 12/347), x button and Esc to
    clear, delayed reload so the grid isn't rebuilt on every keystroke
  - Folders are filtered like files, except ".." which always stays
  - The filter is not cleared when changing folder: it stays active until
    you empty it
  - With a filter active and no matches it says "No match for the filter"
    instead of "Empty folder"

THUMBNAIL INDICATORS
  - Green dot: the file contains GPS coordinates
  - Amber dot: it is an image but NOT a JPEG (PNG, WebP, AVIF, HEIC/HEIF,
    TIFF, GIF, BMP, PNM). Videos and PDFs get no indicator
  - Present in the viewer, in Timeline thumbnails and in Navigate ones;
    when both apply, amber sits below green
  - In the VIEWER the dots are clickable and, on hover, show a label
    explaining what they are and what a click does:
      green -> click copies the location to the shared clipboard,
               right-click opens the map
      amber -> click converts to JPG, after confirmation (the original
               is removed)
  - Added "Show on map" and "Copy GPS location" to the viewer's
    right-click menu, where they were missing
  - In Navigate, GPS detection runs on a separate thread with a cache
    (reading EXIF for hundreds of files would freeze the interface)

NAVIGATE CONTEXT MENU — ALIGNMENT
  Added the entries the other two menus had but this one didn't:
  - Crop... (the only viewer function with no equivalent here: you
    previously had to open the image first). It brings the viewer to the
    front, otherwise the crop opened behind the Navigate window
  - Rotate 90 CW / CCW, also on multiple selected files
  - Destination presets, as in the Timeline: they were only in the
    selection bar, so unreachable by right-clicking an unselected file
  - Open folder and Edit with...

EXIF FORMATS — READ AND WRITE SEPARATED
  They were a single set, with two wrong consequences: iPhone photos
  (HEIC/HEIF) showed no EXIF entries despite having the data, and on TIFF
  saving failed silently.
  - EXIF_READ_EXT  (read, via Pillow): jpg, jpeg, tiff, tif, webp, heic,
    heif
  - EXIF_WRITE_EXT (write, via piexif): jpg, jpeg, webp
  - GPS_WRITABLE_EXT aligned accordingly: TIFF removed

CONTEXT MENU — THREE FIXES
  - Timeline: it didn't close when switching application. Focus-based
    closing couldn't work (focus never reads as "inside the application"
    while the menu is visible); replaced with a pointer-position check,
    plus the outside-click binding extended to the main window, which is
    a separate toplevel
  - Navigate: with a file selected the menu closed immediately. The click
    that opens the menu reaches the window an instant later: normally it
    falls inside the menu and closes nothing, but if the menu is too tall
    for the space below the pointer, Tk moves it up and the click ends up
    outside. The added entries had crossed that threshold
  - Video frame cache: converted from FIFO to a real LRU, with the
    modification date in the key and a lock for multi-thread access

WHAT'S NEW v1.33 → v1.34
---------------------------
Drag and drop, name-conflict handling, History as its own window and a
context menu for folders.

DRAG AND DROP INTO FOLDERS
  - Drag selected thumbnails onto a folder in the left-hand tree to move
    them; hold Ctrl to copy
  - A count label follows the pointer and the target folder highlights
  - Both operations appear in History and can be undone

FILES WITH THE SAME NAME
  - Collisions were previously resolved silently by appending "_1": a
    dialog now asks what to do, once for the whole group and before any
    file is touched
  - Rename (as before) / Overwrite / Skip / Cancel
  - When overwriting, the existing file goes through the transit trash
    instead of disappearing: even an overwrite is recoverable

HISTORY
  - Now has its own window, with a button between Timeline and Settings
    and the Ctrl+H shortcut; it is no longer a Settings tab
  - Copy/Paste is recorded: it was the last file operation in Navigate
    that couldn't be undone. Undoing a copy removes the copies (to the
    transit trash), undoing a move puts the files back

FOLDER RIGHT-CLICK MENU
  - Folders only had a button bar while files had a full menu: folders
    now have the menu too, with the same entries plus New subfolder
    (created where you click), Paste here, disk usage analysis for that
    folder, and Properties
  - The button bar below the grid has been removed: it was rebuilt on
    every selection and caused the grid to jump

FOLDER GRID
  - Much more compact cells: the icon is capped at 80px, so keeping cells
    as large as a thumbnail left 60-70% of each one empty
  - Folders re-flow as you drag the divider, without waiting for a full
    reload
  - Fixed-width columns: a long name no longer breaks the alignment
  - The ".." cell is the same size as the others

PREVIEW PANEL (Navigate)
  - Full filename below the image
  - EXIF info from the right-click menu appears in the panel instead of a
    popup covering the image
  - The preview no longer empties after rotation, cropping or GPS
    assignment, and follows the file when it is renamed or converted
  - The arrow keys update the preview just like a click

FIXES
  - The context menu could trigger a random entry: when it doesn't fit
    below the pointer the system moves it up, placing it under the
    cursor, and releasing the button activated whatever entry was there.
    The menu is now flipped and the release ignored for a moment
  - The menu didn't close when clicking another program or the system
    bar: that event never reaches the window, so the pointer position is
    now checked instead
  - Rotating a photo in a folder other than the one open in the viewer
    sent you back to the initial folder
  - Folder counts in the tree update after moves and copies
  - The last system-styled dialogs (EXIF editor, disk analyzer) are now
    HUD-styled

WHAT'S NEW v1.34 → v1.35
--------------------------
Mostly about the physical Stream Deck and the sidebar. The startup and
detached-sidebar fixes below were resolved here before the new features.

SIDEBAR — LIST APPEARANCE
  - Settings > Sidebar now has "Appearance" alongside "Mode": Grid (the
    original) or List
  - In List mode each key is a single full-width colored button with
    number and label together, ordered 9 at the top down to 0 — more
    room for the folder name, which was less readable than the number
    in the grid
  - The deck (physical and on-screen) stays grid-only: the drag-to-swap
    feature relies on that layout

UNREACHABLE DESTINATIONS
  - A key/preset pointing to an unplugged drive or an unmounted network
    share dims itself automatically
  - Applies to the deck (physical and on-screen) and to the sidebar, in
    both display modes
  - Checked in the background, rechecked every 15 seconds

DRAG TO SWAP PRESETS (deck)
  - Drag one key onto another to swap label and destination, keeping
    number and color where they are
  - Works across columns with different presets too

DECK — EXTRA BUTTONS WITH MORE COLUMNS
  - CROP appears next to BACK/SKIP/DEL at 4 open columns
  - ROTATE appears too at 5 or more

PHYSICAL STREAM DECK
  - New action type for idle keys: "Image Sorter command" — a dropdown
    with 28 direct functions of the program (rotate, zoom, next/previous
    file, copy path, open the current file's folder, copy GPS position,
    open/close panels, switch preset, and more). Unlike keyboard-shortcut
    actions ("hotkey"), these work even if another window has focus
  - Built-in icons for the 28 commands: "deck_icons" folder next to the
    script, files named "cmd_<command name>.png" — optional, the key
    just shows text without one
  - "deck_icons" is also where custom per-key icons now live (previously
    "sorter_icons", which holds the program's own resources)
  - Icon preview now shows as soon as you pick a command or a file, not
    only after "Save key"
  - Label position on the key: Top / Middle / Bottom
  - Empty idle pages remove themselves (leaving them by switching tabs,
    or clearing them with "Clear"): a "+Page" pressed by mistake no
    longer sits there with no way to remove it
  - The S-Deck toolbar button changes color with the deck's state: gray
    when disconnected, cyan when connected in idle, green when connected
    in preset mode. Right-click opens Settings on the Deck tab; hovering
    shows both shortcuts in the tooltip
  - Settings > Deck reorganized: the current mode reads in the right
    order and updates live, the selected key is shown on the tab row
    (no longer inside the editor), available actions are laid out in 3
    columns instead of 2

MORE READABLE CONFIG FILE
  - image_sorter_config.json now starts with a "_note" key explaining
    the file's structure (JSON has no real comment syntax: this is the
    closest thing that stays valid)
  - Compact formatting: a preset or a deck key now sits on a single line
    instead of one line per field — much easier to read by hand

DUPLICATE FINDER — A vs B COMPARISON
  - The two lists stay as they were, but a resizable panel below now
    shows side-by-side thumbnails of the selected row's A and B files —
    especially useful with the "Name+Size" or "Name only" methods, where
    a false match is obvious once you see both images
  - Multiple selection in both lists (Ctrl/Shift-click): pick just a few
    files and trash them together, with one confirmation instead of one
    per file
  - New "Trash selected (B)" button next to "Trash all B duplicates
    (keep A)", for the same purpose but only on the rows you pick

FIXES
  - Starting with the sidebar in "Window" (detached) mode failed with an
    AttributeError: a reference was read before being assigned. This bug
    predates this session — it just never surfaced because the default
    inline mode never hit that code path
  - The detached sidebar didn't refresh when reordering presets or
    switching one from the keypad/deck: several places in the program
    forgot to also update the separate window. Fixed at the source, in
    one place, instead of case by case
  - The "jump" of the first image on startup: caused by three
    overlapping issues — repeated file reads while the window settled,
    scrollbars created already visible (13 pixels returned to the canvas
    after the first draw), and a wrong initialization order. Added an
    internal diagnostic (DIAG_STARTUP) to help spot similar cases later
  - The "S-Deck" button never updated its own color: that was already
    true back in 1.34, not a regression from this session
  - Closing Settings by pressing the toolbar button again (instead of
    the window's X) left the button lit and the reference stale: both
    closing paths now converge on the same cleanup

WHAT'S NEW v1.35 → v1.36
--------------------------
Continuation of the Stream Deck session, plus the error indicator.

ERROR LOG
  - Red dot on the canvas (like the GPS green dot) when an error gets
    logged: previously it only went into the file, with no indicator
  - Clicking it opens a window with the tail of the log, copyable text
    (a "Copy all" button, or Ctrl+A/Ctrl+C)
  - "Clear log" button: needs two clicks to confirm (like deleting a
    file), doesn't leave an empty file but writes a line with the date
    it was cleared
  - Fixed a bug where two of the four places writing to the log opened
    it in overwrite mode instead of append: a browser error used to
    wipe out the entire previous history

DUPLICATE FINDER — FIX
  - The A vs B preview, with multiple selection, sometimes didn't update
    on a new click: it always showed the lowest-index selected row, not
    the one just clicked. It now follows the actual key pressed
WHAT'S NEW - PHYSICAL DECK ALWAYS ON (background daemon)
-------------------------------------------------------------
Session dedicated to a new way of keeping the physical Stream Deck
alive even with Image Sorter closed, replacing the dependency on
StreamController.

deck_core.py (NEW FILE)
  - Deck logic (connection, key rendering, the seven idle actions that
    don't touch the GUI) was extracted into its own importable module -
    no behavior change, just a move. It's the shared base for both
    Image Sorter and the new daemon
  - Copy it into the same folder as image_sorter.py

deck_daemon.py (NEW FILE, optional)
  - A separate program that keeps the physical deck busy while Image
    Sorter is closed, handling the independent idle actions (folders,
    apps, shortcuts, URLs, mute, text, page switch - not the 28 direct
    commands, which need a live GUI instance)
  - Always yields as soon as an Image Sorter window opens, and reclaims
    the deck on its own once that window closes - no manual step needed
  - Run it separately (e.g. Cinnamon's "Startup Applications", or a
    systemd --user service - a commented example is at the bottom of
    the file)
  - Replaces the old "restart StreamController on close", removed from
    Settings

ROUTING ACROSS MULTIPLE WINDOWS
  - With several Image Sorter windows open together, physical deck
    commands now go to whichever one has focus (the last one you
    clicked), not necessarily the one that physically owns the device -
    via a small shared file, updated on every focus change
  - Applies to both idle commands and preset mode (sorting)
  - Known limitation: if several windows have different active presets,
    the physical keys always show the preset of whoever owns the deck,
    not whoever has focus - can be confusing in that specific case,
    rare in everyday use

DISCONNECT AND RECONNECT DETECTION
  - The program now notices if the physical deck is unplugged (within
    5 seconds) and replugged (within 10 seconds), without a restart
  - Fixed a real bug found during development: closing the connection
    without exiting the process didn't actually release the device at
    the system level - it stayed occupied even though Python "thought"
    it had released it

DELETE THE PREVIOUS FILE (Ctrl+Delete)
  - Trashes the file you'd reach with BACK, without moving away from
    the one you're looking at - handy for quick side-by-side judgment
    calls ("this one is better than the last one")
  - Also available as a direct command for the physical Stream Deck
  - Routed through the transit trash like every other deletion: stays
    undoable with Ctrl+Z

MISSING SHORTCUT FIXED
  - The K key (Crop) had been documented for a while but was never
    actually wired up: it works now

STREAM DECK - DIRECT KEY CAPTURE
  - The "Keyboard shortcut" field in the deck editor now has a
    "Record" button: press it, and it listens for the real key
    combination on your keyboard instead of having to type it by hand -
    removes at the root the confusion between "capital C" and "Ctrl+C"
    (two different things to the system; typing them by hand can be
    misleading)
  - Manual typing is still available, useful for special hardware keys
    (backlight, brightness) that the system intercepts before they ever
    reach any application, and so can't be "recorded" - but can still be
    typed and sent

STREAM DECK - AUTOMATIC SAVING
  - The deck key editor no longer requires pressing "Save key": every
    field saves itself as soon as you complete it (leaving the field,
    picking from a menu, finishing a key capture)
  - "Cancel" now restores the key exactly to how it was when you opened
    the editor, instead of just closing the window

STREAM DECK - LESS FLICKER ON OWNERSHIP HANDOFF
  - When ownership of the physical deck passes between the daemon and
    Image Sorter (or back), keys no longer go through a blank state
    before being redrawn - if the content is the same (the common case,
    shared configuration), the switch is imperceptible

NEW DEPENDENCY: xdotool
  - The "Keyboard shortcut" and "Type text" deck actions require
    xdotool, now included in the installer (sudo apt install xdotool
    on systems that don't go through installa.sh)
  - Missing external commands now print a clear warning instead of
    failing silently

MULTI-INSTANCE RACE FIXES
  - If several Image Sorter windows start nearly together, the one that
    loses the race for the physical deck now notices it was beaten to
    it instead of wrongly declaring itself "unavailable"
  - Small random delays keep repeated attempts from colliding at the
    same rhythm every time

STILL OPEN
  - Detecting multiple physical decks connected at once hasn't been
    addressed yet
  - Whether it's worth giving the user a choice, in Settings, between
    the new daemon and the old StreamController - for now the daemon is
    assumed to be the wanted solution
  - When ownership of the deck changes hands, the idle page always
    resets to the first one instead of staying on the current one

WHAT'S NEW v1.36 -> v1.43
----------------------------
Note: as already happened between 1.23 and 1.27, the manuals weren't
updated session by session over this stretch. This section summarizes
the main changes by theme (not version by version), based on
journal_generale.txt, which remains the reference for technical detail
and the session-by-session history.

RATING, COLOR-LABEL AND TAG SYSTEM (NEW, since v1.38)
  - Every photo/video/PDF can carry a 0-5 star rating and one or more
    color labels (red, yellow, green, blue, purple, non-exclusive) -
    data lives in a new independent module, metadata_store.py, indexed
    by absolute path and kept separate from the configuration
  - Editable everywhere: under every thumbnail in the browser and
    Timeline, in the enlarged preview, from the right-click menu, and
    via a dedicated overlay on the main image (Ctrl+F, previously V)
  - Dedicated Tag window (Ctrl+T, previously Shift+T): a filterable tag
    cloud (type to filter), new tags created with Enter, follows the
    current image as you navigate, toggle behavior - with multiple
    files selected, a tag only shows as active if present on ALL of
    them
  - Settings > Tags (new tab): create/rename/delete tags and Tag Groups
    (organizational - one click in the browser filter adds every tag in
    the group); cloud ordering (alphabetical/recently used/frequency)
    moved here from the Display tab
  - Folder browser: rating/color/tag filter with removable "pills", a
    clickable tag row under the presets (later extended to Timeline too)
  - Physical deck: new "Rating/Flag" idle page (color labels on row 1,
    stars on row 2), key state synced live with the currently open file
  - Rating/color/tag now automatically follow EVERY move or rename done
    by the program (previously wired up in only one place, leaving
    metadata orphaned everywhere else)

CROP, RESIZE AND SYSTEM CLIPBOARD
  - Resize/crop directly from the main viewer, not just the classic crop
    tool
  - Copy/Cut/Paste now go through the real system clipboard (xclip),
    interoperable with Nemo/Nautilus/Thunar - previously an internal
    Python list, never actually connected to the real clipboard; "Cut"
    has a dedicated, undoable holding folder

"COMPARE" MODE (NEW, W key)
  - Two smaller previews appear next to the main canvas, previous and
    next file, following navigation - view-only, all commands still
    apply to the center image
  - Loaded on separate threads, with an instant low-resolution
    placeholder while the full-quality version arrives

OTHER ADDITIONS
  - "Open with..." shows the real name of the associated program
  - "Open" on a video launches the system's external player (browser
    and Timeline)
  - Right-click also works on empty grid background in the browser
  - Deck key icon picker with live preview
  - PDF page thumbnails (M key) with a multi-page PDF open
  - Ctrl+N in the folder browser: new subfolder in the open folder

VARIOUS FIXES (a selection, not exhaustive - see journal_generale.txt)
  - Fixed several race-condition TclErrors (window closed while a
    background load was still writing to its canvas)
  - Ctrl+Delete (delete previous) no longer wraps around to the last
    image when starting from the first file
  - Browser/Timeline layout: fixed dividers and alignment in several
    spots (thumbnail/preview split with the tree off, preset/tag bars
    not spanning full width, filename merged with stars/dot)
  - Rating/color set from the Timeline right-click menu sometimes
    didn't appear saved (a metadata_store double-import bug, already
    hit and fixed once before in another spot)

WHAT'S NEW v1.43 -> v1.44
-------------------------
BROWSER REDRAW FIXES
  - Fixed the flash/jump that happened when clicking a folder in the
    grid (the clicked folder and the ones after it, including the
    file star/colorlabel rows below): caused by an inner container
    missing grid_propagate(False), which made Tk recompute its own
    geometry (with a wrong transient value) on every minor
    reconfiguration of a folder cell
  - Fixed the double load when navigating with "previous folder" (Back
    button or the ".." cell), and after moving/trashing a folder: some
    spots loaded the thumbnails twice in a row (one direct call, one
    via debounce)
  - Fixed the divider jump between the thumbnail column and the
    preview column (and between the tree and thumbnails) visible for
    an instant when opening the Browse window, before the thumbnails
    finished loading

BROWSER: PRESET ROW ALWAYS VISIBLE
  - The row with the active preset's destinations (up to 10, keys 0-9)
    now stays visible under the grid even with no file selected -
    before it disappeared entirely, leaving an empty row with the
    "Preset" checkbox on. With no selection the buttons stay present
    but "off" (disabled); they turn active again as soon as you select
    a file. Same behavior in Timeline

BROWSER: PAGE UP/DOWN AND HOME/END KEYS
  - In the browser's thumbnail grid, besides the single arrow keys,
    Page Up/Down (jump one screenful of rows) and Home/End (first/last
    file) now work - they were completely missing

BROWSER: CUT/COPY/PASTE LIKE A REAL FILE MANAGER
  - Pasting a copy into the SAME source folder now creates a new file
    with a different name (e.g. "photo_1.jpg"), like in
    Nemo/Nautilus/Explorer - before it tried to copy the file onto
    itself, with no visible effect
  - Cutting and pasting into the same source folder now does nothing
    (the file is already there), instead of an empty move attempt
  - Fixed a crash (AttributeError) in the "File already exists" dialog
    (Rename/Overwrite/Skip/Cancel) when pasting or moving into a
    DIFFERENT folder with a genuine name collision - the delegation of
    that dialog from the browser to the main window was missing

BROWSER: FOLDER COLOR IN THE RIGHT-CLICK MENU
  - The 5 assignable folder colors are now on a single row of SQUARES
    (no longer round dots with a text label across several rows) - so
    they're not confused at a glance with the round file colorlabel
    dots

CPU AND RESOURCE USAGE — THOROUGH DEBUG PASS
  - Physical deck: fonts were reloaded from disk for every single key
    rendered (every press, every page change) - now cached, read once
  - Main navigation: holding down an arrow key (or scrolling fast)
    started a full decode thread for EVERY step, even though only the
    last one ever got shown - a short debounce (50ms, imperceptible on
    a single step) now avoids the wasted decodes
  - Timeline: loading a page of thumbnails opened up to 120 threads at
    once (one per photo) - now capped at 6 shared threads, with no
    slowdown in loading
  - Rating/colorlabel/tags: every single change rewrote the entire file
    to disk right away - nearby changes are now batched into one save
    (still never lost, even closing the program right after a change)

WHAT'S NEW v1.44 -> v1.45
--------------------------
Fixes for two regressions introduced by v1.44 (always-visible preset
row), reported right away by Carlo after real-world use:
  - Browser slower to open a folder: the active preset's buttons were
    destroyed and recreated for every single folder opened, even
    staying on the same preset - now reused (only rebuilt if the
    active preset or its destinations actually change)
  - Timeline opening with the center column squeezed by the preview
    column: restoring the saved divider position only had two closely
    spaced attempts (20/90ms) to apply after the window reached its
    real size - a margin that can fall short on a real system. Added
    two later attempts (500ms, 1000ms), the same margin already used
    successfully in the Browser
  - Small gray window briefly visible at startup, before the real main
    window: the window was made visible BEFORE the whole interface
    (canvas, sidebar...) was built, showing an empty default-sized
    window (200x200, gray) for a fraction of a second - now it only
    becomes visible once fully built, as the Browser and Timeline
    already did
