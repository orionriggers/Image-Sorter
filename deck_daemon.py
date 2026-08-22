#!/usr/bin/env python3
# deck_daemon.py — tiene vivo lo Stream Deck fisico quando Image Sorter
# e' chiuso, usando la stessa logica di deck_core.py (nessun codice
# duplicato: le pagine idle, il disegno dei tasti, l'esecuzione delle
# sette azioni indipendenti sono ESATTAMENTE le stesse che usa Image
# Sorter, perche' e' lo stesso modulo).
#
# Cosa fa e cosa non fa:
#   - gestisce SOLO la modalita' idle (cartelle, applicazioni, tasti,
#     URL, muto, testo, cambio pagina) — la modalita' preset richiede
#     un'immagine "corrente" che esiste solo dentro una finestra di
#     Image Sorter aperta, non ha senso qui
#   - i comandi "command" (i 28 diretti) e "sorter" (apri Image Sorter
#     su una cartella), se premuti mentre solo il demone e' in
#     esecuzione, non fanno nulla: nessun avvio automatico di Image
#     Sorter e' previsto (scelta esplicita, non una dimenticanza)
#   - cede SEMPRE il dispositivo a una finestra di Image Sorter che si
#     apre, e lo rivuole indietro in automatico quando quella si chiude
#
# Uso:
#   python3 deck_daemon.py
#
# Pensato per girare come servizio utente systemd (vedi il file .service
# di esempio nei commenti in fondo), ma funziona anche lanciato a mano
# da terminale — si ferma con Ctrl+C.

import os
import sys
import json
import time
import random
import signal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import deck_core  # stesso modulo che usa image_sorter.py

CONFIG_FILE = os.path.join(SCRIPT_DIR, "image_sorter_config.json")

# Ogni quanto il demone, quando NON possiede il deck (una finestra di
# Image Sorter ce l'ha, o il device non e' fisicamente collegato),
# controlla se puo' riprenderselo.
RECLAIM_INTERVAL_S = 10
# Ogni quanto, quando lo possiede, controlla la propria casella (per una
# richiesta di cessione) e lo stato di collegamento fisico.
OWN_LOOP_INTERVAL_S = 1
# Ogni quanto ricarica il file di configurazione, per accorgersi di
# modifiche alle pagine idle senza dover riavviare il demone.
CONFIG_RELOAD_INTERVAL_S = 5


class _DaemonRoot:
    """Sostituto minimo di un root Tkinter: StreamDeckManager usa solo
    .after(ms, fn) per programmare un richiamo. Qui non c'e' nessun
    thread grafico con cui sincronizzarsi — o si esegue subito, o con un
    timer se il ritardo e' voluto."""

    def after(self, ms, fn):
        if ms <= 0:
            try:
                fn()
            except Exception:
                pass
            return None
        import threading
        t = threading.Timer(ms / 1000.0, lambda: _safe_call(fn))
        t.daemon = True
        t.start()
        return t


def _safe_call(fn):
    try:
        fn()
    except Exception:
        pass


class _DaemonSorter:
    """Sostituto minimo di ImageSorter: StreamDeckManager legge solo
    .config, .labels e .root. In modalita' idle .labels non serve mai
    (e' usato solo per disegnare i nomi delle cartelle sui tasti 1-9-0
    della modalita' preset, che qui non esiste), ma resta un dizionario
    vuoto per coerenza di interfaccia — non None, per non far esplodere
    un eventuale .get() su qualcosa che si aspetta un dizionario."""

    def __init__(self):
        self.config = _load_config()
        self.labels = {}
        self.root = _DaemonRoot()


def _load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _log(msg):
    print(f"[deck_daemon] {time.strftime('%H:%M:%S')}  {msg}", flush=True)


def _try_claim(sorter):
    """Un solo tentativo di prendere possesso del deck. Ritorna
    l'oggetto StreamDeckManager se riuscito, altrimenti None — non
    solleva mai un'eccezione verso il chiamante, il ciclo principale
    deve poter continuare qualunque cosa succeda qui dentro."""
    data = deck_core.read_lock()
    if data:
        if data.get("kind") == "gui":
            return None   # una finestra di Image Sorter ce l'ha: si aspetta
        if data.get("kind") == "daemon" and data.get("pid") != os.getpid():
            return None   # un altro demone (non dovrebbe capitare, ma non si insiste)
    try:
        sd = deck_core.StreamDeckManager(sorter)   # nessun action_executor:
        # usa execute_headless_action di default — command/sorter vengono
        # ignorate silenziosamente, com'e' previsto qui.
        if sd.is_active():
            deck_core.write_lock("daemon")
            sd.set_mode("idle")
            _log(f"connesso: {sd._deck_info.get('type','?')} "
                 f"({sd._deck_info.get('key_count','?')} tasti)")
            return sd
    except Exception as ex:
        _log(f"tentativo di connessione fallito: {ex}")
    return None


def main():
    sorter = _DaemonSorter()
    sd = None
    ultimo_reload_config = time.time()

    # Uscita pulita: rilascia il lock se e' nostro, cosi' chi aspetta
    # (una finestra di Image Sorter, o nessuno) non trova un lock
    # fantasma da un demone che non c'e' piu'. _pid_alive() lo
    # scarterebbe comunque da solo dopo la morte del processo, ma
    # rilasciarlo subito evita l'attesa inutile a chi lo controlla.
    def _on_terminate(signum, frame):
        _log("chiusura richiesta, rilascio il deck se e' mio")
        if sd is not None:
            try:
                # Qui close() va bene (non release_hardware()): il
                # processo esce subito dopo con sys.exit(0), quindi e'
                # il sistema operativo a liberare l'handle davvero, come
                # gia' avviene per Image Sorter quando chiude.
                sd.close()
            except Exception:
                pass
        deck_core.release_lock_if_mine()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _on_terminate)
    signal.signal(signal.SIGINT, _on_terminate)

    # Piccolo ritardo casuale all'avvio, stesso motivo di
    # image_sorter.py: se il demone parte insieme a una finestra di
    # Image Sorter (per esempio il demone si avvia al login e Image
    # Sorter viene aperto subito dopo), questo riduce le probabilita'
    # che entrambi arrivino al controllo del lock nello stesso istante.
    time.sleep(random.uniform(0, 0.4))

    _log("avviato, in attesa del deck fisico")

    while True:
        if sd is None:
            sd = _try_claim(sorter)
            if sd is None:
                time.sleep(RECLAIM_INTERVAL_S)
                continue

        # Da qui in poi il deck e' nostro: si controlla la casella (per
        # una richiesta di cessione) e lo stato del collegamento fisico,
        # a un ritmo piu' stretto di quando si e' in attesa.
        time.sleep(OWN_LOOP_INTERVAL_S)

        try:
            azione = deck_core.poll_inbox()
        except Exception:
            azione = None
        if azione and azione.get("action") == "__release_deck__":
            _log("richiesta di cessione ricevuta, rilascio il deck")
            try:
                # release_hardware(), non close(): il demone RESTA vivo
                # dopo questo punto, in attesa di riprendersi il deck —
                # deve chiudere davvero l'handle, non solo scartare il
                # riferimento Python. close() conta sul processo che sta
                # per uscire, qui non e' il caso.
                sd.release_hardware()
            except Exception:
                pass
            deck_core.release_lock_if_mine()
            sd = None
            # Non si riprova subito: chi ha chiesto la cessione ha
            # bisogno di un momento per aprire davvero il dispositivo.
            # Senza questa attesa, il ciclo tornava in cima e tentava di
            # riprendersi il deck nello STESSO istante in cui Image
            # Sorter stava tentando di aprirlo — la stessa corsa che
            # cedere il passo doveva evitare, solo spostata di un
            # istante dopo invece di eliminata.
            _log(f"aspetto {RECLAIM_INTERVAL_S}s prima di riprovare a "
                 f"riprendere il deck")
            time.sleep(RECLAIM_INTERVAL_S + random.uniform(0, 2))
            continue

        try:
            ancora_collegato = sd.deck.connected() if sd.deck else False
        except Exception:
            ancora_collegato = False
        if not ancora_collegato:
            _log("dispositivo fisico scollegato")
            try:
                sd.release_hardware()   # stesso motivo: il demone resta vivo
            except Exception:
                pass
            deck_core.release_lock_if_mine()
            sd = None
            continue

        if time.time() - ultimo_reload_config > CONFIG_RELOAD_INTERVAL_S:
            sorter.config = _load_config()
            ultimo_reload_config = time.time()


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────────────────────────────────
# ESEMPIO DI SERVIZIO SYSTEMD --user (NON installato automaticamente da
# questo file: da salvare a mano, se lo si vuole, in
# ~/.config/systemd/user/image-sorter-deck.service — poi abilitarlo con
# "systemctl --user enable --now image-sorter-deck.service").
#
# Attenzione: non verificato su una macchina reale con systemd — solo
# scritto secondo la sintassi standard di un servizio utente. Da provare
# e correggere se qualcosa non torna, in particolare i percorsi.
#
# [Unit]
# Description=Image Sorter - deck fisico in background
# After=graphical-session.target
#
# [Service]
# Type=simple
# ExecStart=/usr/bin/python3 /percorso/completo/deck_daemon.py
# Restart=on-failure
# RestartSec=3
#
# [Install]
# WantedBy=default.target
# ─────────────────────────────────────────────────────────────────────────
