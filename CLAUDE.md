# Image Sorter

App desktop Linux (Python 3.8+, Tkinter, Pillow) per smistare rapidamente
foto/video/PDF in cartelle di destinazione, con Stream Deck fisico opzionale.
Sviluppatore: Carlo Porrone. Lavora principalmente da terminale (non IDE),
testa ogni consegna sul suo sistema reale (Linux Mint/Ubuntu, tre monitor).

**Prima di qualsiasi task non banale, leggi `journal_generale.txt`** — contiene
la cronologia completa, l'architettura dettagliata (deck fisico, sistema
rating/tag), e ~25 principi codificati da bug reali già risolti. Questo file
è il riassunto operativo, quello è l'approfondimento.

## Struttura e versioning

- `image_sorter.py` — programma principale (~24.600 righe)
- `timeline.py`, `exif_editor.py`, `disk_analyzer.py`, `translations.py` —
  moduli "core": **stesso numero di versione**, bump coordinato quando si
  toccano insieme più file (secondo numero), altrimenti solo il terzo numero
  del singolo file toccato
- `metadata_store.py`, `deck_core.py`, `deck_daemon.py` — versione
  **indipendente** ciascuno
- `installa.sh` — versione indipendente

Non alzare MAI il secondo numero di versione di un file non toccato in
quella sessione, salvo bump coordinato esplicito a fine fase.

**Al bump coordinato** (quando il secondo numero di versione cambia sui
cinque file core insieme): creare una cartella alla radice del progetto
con il numero della nuova versione come nome (es. `1.42/`, stesso schema
già in uso da `1.41/` a `1.43/`, fatte a mano da Carlo) e copiarci dentro
un backup parallelo dei file di progetto veri — non generati, non di
prova:

```
image_sorter.py, timeline.py, disk_analyzer.py, exif_editor.py, translations.py
metadata_store.py, deck_core.py, deck_daemon.py
installa.sh
CLAUDE.md, journal_generale.txt
LEGGIMI.txt, README.md, README_en.txt
```

Non includere: file generati a runtime (config/log/history/metadata json,
`__pycache__/`), `deck_icons/` (asset, non codice — già tracciato da Git
di suo), cartelle di prova, altre cartelle di backup già esistenti (mai
annidare un backup dentro l'altro). Queste cartelle di backup restano
FUORI da Git (vedi `.gitignore`, pattern `/[0-9].[0-9][0-9]/`) — sono un
backup parallelo per Carlo, non fanno parte della cronologia versionata.

Sempre al bump coordinato, in `LEGGIMI.txt`, `README_en.txt` e
`README.md`: aggiornare SIA i numeri di versione SIA il contenuto —
sono due cose distinte, fatte entrambe, non solo la prima:

- Numeri di versione: intestazione + tabella "FILE DEL PROGRAMMA"/
  "PROGRAM FILES" di `LEGGIMI.txt`/`README_en.txt` (un rigo per file
  core con il suo numero esatto — non tutti uguali se solo alcuni hanno
  un terzo numero già avanzato), e titolo `# Image Sorter vX.Y.Z` in
  testa a `README.md`. Controllare con grep il numero vecchio su tutti
  e tre, non fidarsi della memoria di quali righe lo contengono.
- Contenuto: una nuova voce di changelog in `LEGGIMI.txt`/`README_en.txt`
  (sezione "NOVITÀ/WHAT'S NEW vX.Y → vX.Z", stesso stile delle
  precedenti) che descrive cosa è cambiato dal bump precedente, e le
  sezioni descrittive di `README.md` (caratteristiche, scorciatoie,
  ecc.) aggiornate se il bump ha introdotto o modificato funzionalità
  visibili. Scritto a fine di OGNI bump coordinato, non accumulato per
  sessioni successive — è così che si è creato il debito poi ripagato
  in blocco da v1.36 a v1.43 (vedi quella sezione in `LEGGIMI.txt` per
  il precedente).

## Verifica obbligatoria prima di ogni consegna

Ambiente grafico non disponibile: usare sempre `xvfb-run -a` per qualunque
test che apra una finestra Tkinter.

```bash
python3 -m py_compile <file>.py     # su OGNI file toccato
python3 -m pyflakes <file>.py       # avvisi noti: pillow_avif/fitz "unused" (import di fallback, intenzionali)
bash -n installa.sh                 # se toccato
```

Confronto AST cumulativo contro l'originale, per scovare funzioni perse per
errore durante una modifica (non solo quelle toccate volutamente):

```python
import ast
def method_sigs(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    out = {}
    class V(ast.NodeVisitor):
        def __init__(self): self.stack = []
        def visit_ClassDef(self, n):
            self.stack.append(n.name); self.generic_visit(n); self.stack.pop()
        def visit_FunctionDef(self, n):
            out[".".join(self.stack+[n.name])] = [a.arg for a in n.args.args]
            self.generic_visit(n)
    V().visit(tree)
    return out
# prima = method_sigs("originale.py"); dopo = method_sigs("file.py")
# "rimossi" deve essere SEMPRE vuoto, salvo rimozione intenzionale dichiarata
```

Per funzionalità nuove/corrette: **test funzionale reale** con xvfb-run che
riproduce lo scenario esatto segnalato (non solo verifica sintattica) —
costruire lo stato minimo necessario, eseguire l'azione, verificare il
risultato con `assert`. Ripetere finché non passa, non fidarsi di "sembra
corretto a occhio".

**`image_sorter_config.json`/`image_sorter_history.json`/
`image_sorter_metadata.json` nella cartella del progetto sono i file
VERI di Carlo, mai residui di test** — anche se sembrano generati "di
default", perché li rigenera `load_config()` non appena mancano. Non
vanno MAI cancellati con `rm -f` a fine sessione, nemmeno "per
pulizia": lo si è fatto due volte (22/08 e 23/08 2026) perdendo preset
e impostazioni reali entrambe le volte. Un test che istanzia
`ImageSorter`/chiama `load_config()` deve girare in una cartella di
lavoro isolata (copiare `image_sorter.py` e i moduli serviti in una
tmpdir e lanciare lo script da lì, oppure `cd` in una tmpdir prima di
eseguire), cosi' il file vero non viene toccato e non serve alcun
cleanup successivo su di esso.

## Convenzioni di codice non ovvie (causa di bug reali, non teoria)

- **Mai `grab_set()`** nei popup: bloccherebbe altri programmi. Di
  conseguenza, `entry.focus_set()` NON basta per garantire il fuoco reale
  sotto un vero window manager (che spesso impedisce a una finestra appena
  aperta di rubarlo da sola) — serve `entry.focus_force()`.
- **`Entry.bind("<Return>", handler)` senza `return "break"`**: l'evento si
  propaga oltre il campo fino a un binding di livello superiore nella stessa
  finestra. Controllare sempre gli altri campi testo nella stessa classe per
  lo schema già in uso.
- **Popup con `highlightthickness` per evidenziare selezione**: impostarlo
  allo stesso valore FISSO sia da selezionato che da non selezionato
  (cambia solo il colore) — sia alla creazione del widget sia negli
  aggiornamenti successivi. Un valore diverso anche solo alla creazione
  causa un salto di dimensione alla prima interazione.
- **Righe/barre che appaiono-scompaiono in base al contenuto** (es. nessuna
  selezione): altezza SEMPRE riservata (`height=N` + `grid_propagate(False)`,
  mai `grid_remove()`) se il cambio è automatico e frequente (ad ogni
  click/selezione) — usare `grid_remove()`/`grid()` solo per cambi rari e
  deliberati (es. una casella di spunta).
- **`subprocess.Popen` verso un comando che si stacca da solo in background**
  (es. `xclip`, resta vivo dopo l'uscita del "processo principale"): mai
  `stderr=PIPE` — il processo in background eredita la pipe e la tiene
  aperta, Python resta in attesa fino al timeout. Usare `DEVNULL`.
- **Ricalcolo di geometria dopo un cambio di layout** (es. pannello aggiunto
  a un `PanedWindow`): `winfo_width()` può restare non aggiornato anche
  dopo `update_idletasks()`/`update()` espliciti — se più eventi
  `<Configure>` ravvicinati sono attesi, usare un debounce condiviso invece
  di indovinare un ritardo fisso.
- **Widget con contenuto ricostruito ad ogni interazione** (es. nuvola di
  bottoni che si aggiorna ad ogni selezione): se l'insieme degli elementi
  spesso non cambia, aggiornare i widget esistenti invece di
  distruggerli/ricrearli — altrimenti lampeggio visibile.
- **Rating/colorlabel/tag** (`metadata_store.py`, indicizzato per percorso
  assoluto): qualunque nuovo punto che sposta o rinomina un file DEVE
  chiamare `metadata_store.rename_path()` (o `rename_path_prefix()` per
  cartelle intere), altrimenti i metadati restano orfani sul percorso
  vecchio. Fare sempre un controllo grep di tutti i punti `os.rename(`/
  `shutil.move(` quando si tocca quest'area, non fidarsi della memoria.

## Lingua e stile

Italiano per UI, commenti nel codice, e `journal_generale.txt`. Risposte a
Carlo concise, con passi di riproduzione precisi invece di spiegazioni
lunghe. Sessioni collaborative: Carlo testa ogni consegna sul suo sistema
reale e riporta l'esito in un ciclo stretto.

## Non fare

- Non aggiungere dipendenze esterne senza controllare se serve aggiornare
  anche `installa.sh` (mappatura pacchetti per le distro coperte).
- Non presumere lo stato del codice dal riassunto di una sessione precedente
  — verificare sempre con grep/lettura diretta prima di modificare.
- Non chiudere una sessione di lavoro senza aggiornare
  `journal_generale.txt` se il task ha introdotto un'architettura nuova o
  un insegnamento generalizzabile (non per ogni piccolo fix).

## Git

Repository su GitHub: `github.com/orionriggers/image-sorter`, ramo `main`.

- Commit dopo ogni funzionalità completata e verificata (non ad ogni
  piccola modifica) — messaggio breve, in italiano, che descrive cosa
  cambia.
- `git push` quando ha senso, non necessariamente ad ogni commit —
  **ma sempre chiedendo prima conferma esplicita a Carlo**, mai in
  automatico dopo il commit.
- **Mai `--force` o riscrittura della cronologia senza chiedere prima
  esplicitamente conferma a Carlo.** L'unico force push fatto finora
  (agosto 2026) è stato un caso eccezionale per allineare due storie
  Git mai collegate tra loro (il repository veniva aggiornato a mano via
  web, non con `git push`) — non è un'abitudine da ripetere su un
  repository ormai sano: rischierebbe di cancellare commit veri senza
  che Carlo se ne accorga.
