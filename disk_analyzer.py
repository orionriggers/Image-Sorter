#!/usr/bin/env python3
"""disk_analyzer.py v3 — Analizzatore utilizzo disco per Image Sorter v1.21.0"""
VERSION = "1.25.0"

import os, sys, threading, math
import tkinter as tk
from tkinter import ttk, messagebox

BG_COLOR="#0a0f1a"; PANEL_COLOR="#0d1117"; ACCENT_COLOR="#1a2030"
HUD_CYAN="#00c8ff"; TEXT_COLOR="#c8d8e8"; MUTED_COLOR="#4a6080"
HIGHLIGHT="#e74c3c"; SUCCESS="#27ae60"
PALETTE=["#2980b9","#27ae60","#e67e22","#8e44ad","#16a085","#c0392b",
         "#d35400","#1abc9c","#2c3e50","#7f8c8d","#3498db","#2ecc71",
         "#e74c3c","#9b59b6","#f39c12","#00bcd4","#8bc34a","#ff5722",
         "#607d8b","#795548"]

# soglia angolo minimo (gradi) perché uno spicchio mostri testo
MIN_LABEL_DEG = 18   # sotto questa soglia: nessun testo

def fmt_size(n):
    for u in ["B","KB","MB","GB"]:
        if n<1024: return f"{n:.1f} {u}"
        n/=1024
    return f"{n:.1f} TB"

def tk_safe(t): return "".join(c if ord(c)<0x10000 else "?" for c in str(t))
def _lighten(hx, f=1.4):
    h=hx.lstrip('#'); r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return f"#{min(255,int(r*f)):02x}{min(255,int(g*f)):02x}{min(255,int(b*f)):02x}"
def _darken(hx,f=0.6):
    h=hx.lstrip("#"); r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"
def _hud_apply(win):
    try: win.config(highlightbackground=HUD_CYAN,highlightthickness=2,highlightcolor=HUD_CYAN)
    except Exception: pass

# ── DirNode ───────────────────────────────────────────────────────────────────
class DirNode:
    __slots__=("path","name","size","children","color_idx","parent")
    def __init__(self,path,name,parent=None):
        self.path=path; self.name=name; self.size=0
        self.children=[]; self.color_idx=0; self.parent=parent

def scan_dir(path, stop=None, depth=0, max_depth=10):
    node=DirNode(path, os.path.basename(path) or path)
    if stop and stop.is_set(): return node
    try: entries=list(os.scandir(path))
    except Exception: return node
    for e in entries:
        if stop and stop.is_set(): break
        try:
            if e.is_symlink(): continue
            if e.is_file(follow_symlinks=False):
                try: node.size+=e.stat(follow_symlinks=False).st_size
                except Exception: pass
            elif e.is_dir(follow_symlinks=False) and depth<max_depth:
                ch=scan_dir(e.path,stop,depth+1,max_depth)
                ch.parent=node; node.size+=ch.size; node.children.append(ch)
        except Exception: continue
    node.children.sort(key=lambda c:-c.size)
    for i,ch in enumerate(node.children): ch.color_idx=i%len(PALETTE)
    return node

# ── Sunburst ──────────────────────────────────────────────────────────────────
class SunburstRenderer:
    MAX_RINGS=5
    def __init__(self,canvas):
        self.canvas=canvas; self.root=None; self.current=None; self._items={}
        self._highlight_node=None   # spicchio evidenziato (da selezione treeview)
    def set_root(self,n): self.root=n; self.current=n; self._highlight_node=None; self.draw()
    def navigate_to(self,n): self.current=n; self._highlight_node=None; self.draw()
    def draw(self):
        c=self.canvas; c.delete("all"); self._items.clear()
        w=c.winfo_width() or 700; h=c.winfo_height() or 700
        cx=w//2; cy=h//2; self._cx=cx; self._cy=cy
        # Raggio: usa il massimo spazio disponibile nel canvas
        size=min(w,h)-2
        rmin=size*0.05
        rmax=size*0.499
        rw=(rmax-rmin)/self.MAX_RINGS
        self._slices=[]   # raccolta (ri, ro, angle, sweep, col, node)
        if not self.current or self.current.size==0:
            c.create_text(cx,cy,text="Cartella vuota",fill=MUTED_COLOR,font=("TkFixedFont",12)); return
        # (il cerchio centrale sarà disegnato DOPO gli anelli per mascherare il buco)
        # freccia Su gestita dalla barra esterna (_up_bar)
        self._ring(self.current.children,rmin,rw,90,360,0,None)
        # Disegna tutti gli spicchi raccolti, ordine: esterno→interno
        self._draw_slices()
        # BUCO CENTRALE: disegnato DOPO gli anelli, copre tutto dentro rmin
        cid=c.create_oval(cx-rmin,cy-rmin,cx+rmin,cy+rmin,
            fill=PANEL_COLOR,outline=HUD_CYAN,width=2,tags="center_cover")
        self._items[cid]=self.current
        nm=tk_safe(self.current.name or "/")
        if len(nm)>13: nm=nm[:11]+"…"
        c.create_text(cx,cy-9,text=nm,fill=HUD_CYAN,font=("TkFixedFont",9,"bold"))
        c.create_text(cx,cy+9,text=fmt_size(self.current.size),
                      fill=TEXT_COLOR,font=("TkFixedFont",8))


    def _ring(self,nodes,ri,rw,start,total,depth,pcol,parent_size=None):
        """Raccoglie spicchi da disegnare. Non disegna direttamente."""
        if depth>=self.MAX_RINGS or not nodes: return
        if parent_size is None:
            ref = sum(n.size for n in nodes)
        else:
            ref = parent_size
        if ref == 0: return
        angle=start
        for node in nodes:
            if node.size==0: continue
            sweep=(node.size/ref)*total
            if sweep<0.5:
                angle += sweep
                continue
            if depth==0: col=PALETTE[node.color_idx%len(PALETTE)]
            else: col=_darken(pcol or PALETTE[node.color_idx%len(PALETTE)],0.72+depth*0.06)
            # Raccogli per disegno successivo (in ordine depth decrescente)
            self._slices.append((depth, ri, ri+rw, angle, sweep, col, node))

            # RICORSIONE: i figli vanno nell'anello successivo
            self._ring(node.children,ri+rw,rw,angle,sweep,depth+1,col,parent_size=node.size)
            angle+=sweep

    def _draw_slices(self):
        """Disegna gli spicchi raccolti dall'ESTERNO all'INTERNO così i PIESLICE
        interni coprono la parte interna di quelli esterni → effetto anello separato."""
        c=self.canvas; cx=self._cx; cy=self._cy
        # Ordina per depth DECRESCENTE (esterno prima)
        slices = sorted(self._slices, key=lambda s: -s[0])
        # Disegna ogni spicchio come PIESLICE pieno dal centro a ro
        for depth, ri, ro, angle, sweep, col, node in slices:
            # Gap visibile: ro effettivo leggermente ridotto
            ro_eff = ro - 2
            is_highlighted = (node is self._highlight_node)
            outline_col = HUD_CYAN if is_highlighted else BG_COLOR
            outline_w = 3 if is_highlighted else 1
            fill_col = _lighten(col) if is_highlighted else col
            cid = c.create_arc(cx-ro_eff, cy-ro_eff, cx+ro_eff, cy+ro_eff,
                               start=angle, extent=sweep,
                               outline=outline_col, width=outline_w,
                               fill=fill_col, style=tk.PIESLICE)
            self._items[cid] = node


    def hit_test(self,x,y):
        for it in reversed(self.canvas.find_overlapping(x-3,y-3,x+3,y+3)):
            if it in self._items: return self._items[it]
        return None

# ── DiskAnalyzer ──────────────────────────────────────────────────────────────
class DiskAnalyzer:
    IMG_EXT={'.jpg','.jpeg','.png','.gif','.bmp','.webp','.tiff','.tif'}
    VID_EXT={'.mp4','.mov','.avi','.mkv','.webm','.m4v','.flv'}
    DOC_EXT={'.pdf','.doc','.docx','.xls','.xlsx','.ppt','.pptx','.txt','.odt'}

    def __init__(self,parent,sorter=None,initial_dir=None):
        self.sorter=sorter; self._stop=threading.Event()
        self._scan_th=None; self._root=None; self._hover=None
        start=(initial_dir or (getattr(sorter,'source_folder',None) if sorter else None)
               or os.path.expanduser("~"))
        win=tk.Toplevel(parent); win.title(f"Analisi cartelle  v{VERSION}")
        # finestra più larga per dare spazio al grafico
        win.geometry("1280x820"); win.minsize(800,600)
        win.configure(bg=BG_COLOR); _hud_apply(win)
        win.protocol("WM_DELETE_WINDOW",self._close)
        win.bind("<Escape>",lambda e:self._close())
        self.win=win; self._build(start)
        win.after(150,lambda: self._start(start))

    def _build(self,start):
        w=self.win; w.columnconfigure(0,weight=1); w.rowconfigure(1,weight=1)

        # ── Top bar ──────────────────────────────────────────────────────────
        top=tk.Frame(w,bg=PANEL_COLOR); top.grid(row=0,column=0,sticky="ew")
        top.columnconfigure(1,weight=1)
        tk.Label(top,text="Analisi cartelle",font=("TkFixedFont",10,"bold"),
                 bg=PANEL_COLOR,fg=HUD_CYAN).pack(side="left",padx=10,pady=6)
        self._pvar=tk.StringVar(value=start)
        tk.Entry(top,textvariable=self._pvar,font=("TkFixedFont",9),
                 bg=ACCENT_COLOR,fg=TEXT_COLOR,insertbackground=HUD_CYAN,
                 relief="flat",bd=3).pack(side="left",fill="x",expand=True,padx=6,pady=6,ipady=3)
        tk.Button(top,text="Analizza",font=("TkFixedFont",9,"bold"),
                  bg=SUCCESS,fg="white",relief="flat",padx=10,
                  command=lambda:self._start(self._pvar.get().strip())
                  ).pack(side="left",padx=(0,2),pady=6,ipady=3)
        tk.Button(top,text="...",font=("TkFixedFont",9),
                  bg=ACCENT_COLOR,fg=TEXT_COLOR,relief="flat",padx=6,
                  command=self._browse).pack(side="left",padx=(0,10),pady=6,ipady=3)
        tk.Frame(top,bg=MUTED_COLOR,width=1).pack(side="left",fill="y",pady=4,padx=4)
        tk.Frame(top,bg=MUTED_COLOR,width=1).pack(side="left",fill="y",pady=4,padx=4)
        # Fader livelli
        tk.Label(top,text="Livelli:",font=("TkFixedFont",10),
                 bg=PANEL_COLOR,fg=TEXT_COLOR).pack(side="left",padx=(8,2))
        self._levels_var=tk.IntVar(value=3)
        self._levels_lbl=tk.Label(top,text="3",font=("TkFixedFont",12,"bold"),
                                   bg=PANEL_COLOR,fg=HUD_CYAN,width=2)
        self._levels_lbl.pack(side="left")
        tk.Scale(top,from_=1,to=6,orient="horizontal",
                 variable=self._levels_var,
                 length=110,showvalue=0,
                 bg=PANEL_COLOR,fg=HUD_CYAN,
                 troughcolor=ACCENT_COLOR,
                 highlightthickness=0,bd=0,
                 command=self._on_levels_change
                 ).pack(side="left",padx=(0,8))

        # ── Main: PanedWindow con divisore ridimensionabile ──────────────────
        main=tk.PanedWindow(w,orient=tk.HORIZONTAL,bg=ACCENT_COLOR,
                            sashwidth=5,sashrelief="flat",bd=0,
                            sashpad=0,opaqueresize=True)
        main.grid(row=1,column=0,sticky="nsew")

        # Frame contenitore: barra "Su" fissa + canvas
        cf=tk.Frame(main,bg=BG_COLOR)
        cf.rowconfigure(1,weight=1); cf.columnconfigure(0,weight=1)
        # Barra "▲ Su" — sempre visibile sopra il grafico
        self._up_bar=tk.Frame(cf,bg=PANEL_COLOR,height=24)
        self._up_bar.grid(row=0,column=0,sticky="ew")
        self._up_bar.grid_propagate(False)
        self._up_btn=tk.Button(self._up_bar,text="▲  Su",
                               font=("TkFixedFont",9,"bold"),
                               bg=PANEL_COLOR,fg=HUD_CYAN,
                               relief="flat",bd=0,padx=10,
                               activebackground=ACCENT_COLOR,
                               command=self._go_up)
        self._up_btn.pack(side="left",padx=4,pady=2)
        self._up_bar.grid_remove()  # nascosta finché non c'è un parent
        self.canvas=tk.Canvas(cf,bg=BG_COLOR,highlightthickness=0,
                              width=800,height=650)
        self.canvas.grid(row=1,column=0,sticky="nsew")
        self.canvas.bind("<Configure>",lambda e:self._redraw())
        self.canvas.bind("<Button-1>",self._click)
        self.canvas.bind("<Double-Button-1>",self._dblclick)
        self.canvas.bind("<Button-3>",self._rclick)
        self.canvas.bind("<Motion>",self._motion)
        self.canvas.bind("<Leave>",lambda e:self._clrtip())
        # Tooltip follow-mouse — appare vicino al cursore sullo spicchio
        self._tt=tk.Label(self.canvas,text="",
                          font=("TkFixedFont",10,"bold"),
                          bg=PANEL_COLOR,fg=HUD_CYAN,
                          padx=6,pady=3,relief="flat",
                          highlightbackground=MUTED_COLOR,highlightthickness=1)
        self._tt_visible=False
        main.add(cf,minsize=300,stretch="always")

        # ── Pannello destro ───────────────────────────────────────────────────
        rp=tk.Frame(main,bg=BG_COLOR)
        main.add(rp,minsize=200,stretch="never")
        rp.columnconfigure(0,weight=1); rp.rowconfigure(0,weight=1)

        # Treeview — tre colonne, tutte liberamente ridimensionabili dall'utente
        self.tv=ttk.Treeview(rp,columns=("dim","nf"),
                             show="tree headings",selectmode="browse")
        self.tv.heading("#0",  text="Nome", anchor="w")
        self.tv.heading("dim", text="Dim.",  anchor="e")
        self.tv.heading("nf",  text="File",  anchor="e")
        self.tv.column("#0",   width=220, stretch=False, minwidth=80)
        self.tv.column("dim",  width=80,  stretch=False, minwidth=50, anchor="e")
        self.tv.column("nf",   width=70,  stretch=False, minwidth=45, anchor="e")

        vsb=ttk.Scrollbar(rp,orient="vertical",  command=self.tv.yview)
        hsb=ttk.Scrollbar(rp,orient="horizontal",command=self.tv.xview)
        self.tv.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        self.tv.grid(row=0,column=0,sticky="nsew",padx=(4,0),pady=(2,0))
        vsb.grid(row=0,column=1,sticky="ns",pady=(2,0))
        hsb.grid(row=1,column=0,sticky="ew",padx=(4,0))

        # Stile HUD — solo colori, NO relief/theme: mantiene resize colonne
        sty=ttk.Style(self.win)
        sty.configure("DA.Treeview",
                      background=PANEL_COLOR, foreground=TEXT_COLOR,
                      fieldbackground=PANEL_COLOR, rowheight=22,
                      font=("TkFixedFont",8))
        sty.configure("DA.Treeview.Heading",
                      background=ACCENT_COLOR, foreground=HUD_CYAN,
                      font=("TkFixedFont",8,"bold"))
        sty.map("DA.Treeview",
                background=[("selected","#1a3a5a")],
                foreground=[("selected","white")])
        self.tv.configure(style="DA.Treeview")
        self.tv.bind("<Double-Button-1>",self._tv_dbl)
        self.tv.bind("<Return>",         self._tv_dbl)
        self.tv.bind("<KP_Enter>",       self._tv_dbl)
        self.tv.bind("<<TreeviewOpen>>", self._tv_expand)
        self.tv.bind("<<TreeviewSelect>>", self._tv_select)
        # Click singolo su riga "▲ Su" → sale subito
        self.tv.bind("<Button-1>", self._tv_click1)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bot=tk.Frame(w,bg=PANEL_COLOR); bot.grid(row=2,column=0,sticky="ew")
        self._stlbl=tk.Label(bot,text="",font=("TkFixedFont",8),
                             bg=PANEL_COLOR,fg=MUTED_COLOR,anchor="w")
        self._stlbl.pack(side="left",padx=10,pady=4)
        tk.Button(bot,text="Chiudi",font=("TkFixedFont",8),
                  bg=ACCENT_COLOR,fg=TEXT_COLOR,relief="flat",padx=8,
                  command=self._close).pack(side="right",padx=(0,6),pady=4,ipady=2)
        if self.sorter:
            tk.Button(bot,text="Apri nel browser",font=("TkFixedFont",8,"bold"),
                      bg="#1a3a2a",fg=HUD_CYAN,relief="flat",padx=8,
                      command=self._open_cur).pack(side="right",padx=4,pady=4,ipady=2)
            tk.Button(bot,text="File manager",font=("TkFixedFont",8),
                      bg=ACCENT_COLOR,fg=TEXT_COLOR,relief="flat",padx=8,
                      command=self._open_filemanager
                      ).pack(side="right",padx=(0,2),pady=4,ipady=2)
        # Nome cartella corrente — grande e visibile
        self._curlbl=tk.Label(bot,text="",font=("TkFixedFont",12,"bold"),
                              bg=PANEL_COLOR,fg=HUD_CYAN,anchor="w")
        self._curlbl.pack(side="left",padx=(10,0),pady=4,fill="x",expand=True)
        # Info file — piccole, accanto al nome
        self._nflbl=tk.Label(bot,text="",font=("TkFixedFont",8),
                             bg=PANEL_COLOR,fg=MUTED_COLOR,anchor="w")
        self._nflbl.pack(side="left",padx=(4,0),pady=4)
        # Tooltip hover — nome cartella sotto il mouse, ben visibile
        self._tiplbl=tk.Label(bot,text="",font=("TkFixedFont",11,"bold"),
                              bg=PANEL_COLOR,fg=TEXT_COLOR,anchor="e")
        self._tiplbl.pack(side="right",padx=10,pady=4)
        self._prog=ttk.Progressbar(bot,mode="indeterminate",length=100)
        self._prog.pack(side="right",padx=8,pady=6)

        self._sb=SunburstRenderer(self.canvas)

    # ── Selezione cartella ────────────────────────────────────────────────────
    def _browse(self):
        cur=self._pvar.get().strip(); result=None
        try:
            import sys as _sys
            for mn in list(_sys.modules):
                m=_sys.modules[mn]
                if m and hasattr(m,'browse_folder_hud'):
                    result=m.browse_folder_hud(self.win,
                        title="Scegli cartella da analizzare",initial_dir=cur)
                    break
        except Exception: pass
        if result is None:
            import tkinter.filedialog as fd
            result=fd.askdirectory(parent=self.win,initialdir=cur,
                                   title="Scegli cartella da analizzare")
        if result: self._pvar.set(result); self._start(result)

    # ── Scansione ─────────────────────────────────────────────────────────────
    def _start(self,path):
        if not path or not os.path.isdir(path):
            messagebox.showwarning("Percorso non valido",
                        f"Cartella non trovata:\n{path}", parent=self.win)
            return
        self._stop.set()
        if self._scan_th and self._scan_th.is_alive(): self._scan_th.join(timeout=0.5)
        self._stop.clear(); self._root=None
        self.canvas.delete("all"); self.tv.delete(*self.tv.get_children())
        self._pvar.set(path)
        self._stlbl.config(text=tk_safe(f"Scansione: {path} …"))
        self._prog.pack(side="right",padx=8,pady=6); self._prog.start(10)
        self._scan_th=threading.Thread(target=self._worker,args=(path,),daemon=True)
        self._scan_th.start()

    def _worker(self,path):
        node=scan_dir(path,self._stop)
        if not self._stop.is_set():
            self.win.after(0,lambda:self._done(node))

    def _done(self,node):
        if not self.win.winfo_exists(): return
        self._prog.stop(); self._prog.pack_forget()
        self._root=node
        nd=sum(1 for _ in self._all(node))
        self._stlbl.config(text=tk_safe(
            f"{fmt_size(node.size)}  —  {nd} cartelle"))
        self._update_curlbl(node)
        self._sb.set_root(node)
        self._redraw(); self._poptv(node)
        self._update_up_bar()

    def _all(self,n):
        yield n
        for c in n.children: yield from self._all(c)

    # ── Rendering ─────────────────────────────────────────────────────────────
    def _rend(self): return self._sb
    def _on_levels_change(self,val=None):
        """Aggiorna MAX_RINGS in base al fader e ridisegna."""
        n=self._levels_var.get()
        self._levels_lbl.config(text=str(n))
        self._sb.MAX_RINGS=n
        self._redraw()

    def _redraw(self):
        if not self._root: return
        self._sb.draw()
    def _nav(self,node):
        if not node: return
        self._rend().navigate_to(node)
        self._poptv(node)
        self._stlbl.config(text=tk_safe(fmt_size(node.size)))
        self._update_curlbl(node)
        self._update_up_bar()

    # ── Treeview ──────────────────────────────────────────────────────────────
    def _update_curlbl(self,node):
        """Aggiorna nome cartella e conteggio file nella barra in basso."""
        if not hasattr(self,'_curlbl'): return
        name=tk_safe(node.name or node.path)
        self._curlbl.config(text=name)
        # Conteggio file e sottocartelle
        if hasattr(self,'_nflbl'):
            nf=self._count_files(node)
            nsub=len(node.children)
            self._nflbl.config(text=tk_safe(
                f"  {fmt_size(node.size)}  |  {nsub} cartelle  |  {nf}"))

    def _count_files(self,node):
        tot=img=vid=doc=0
        try:
            for e in os.scandir(node.path):
                if e.is_file(follow_symlinks=False):
                    tot+=1; ext=os.path.splitext(e.name)[1].lower()
                    if ext in self.IMG_EXT: img+=1
                    elif ext in self.VID_EXT: vid+=1
                    elif ext in self.DOC_EXT: doc+=1
        except Exception: pass
        parts=[]
        if img: parts.append(f"{img} immagini" if img>1 else "1 immagine")
        if vid: parts.append(f"{vid} video")
        if doc: parts.append(f"{doc} documenti" if doc>1 else "1 documento")
        rest=tot-img-vid-doc
        if rest: parts.append(f"{rest} altri" if rest>1 else "1 altro")
        return f"{tot} ({', '.join(parts)})" if parts else str(tot)

    def _poptv(self,node):
        self.tv.delete(*self.tv.get_children())
        # Riga ▲ Su — sempre visibile, disabilitata alla radice
        if node.parent:
            pname=tk_safe(f"▲  {node.parent.name or '/'}")
            self.tv.insert("","end",iid="__up__",text=pname,
                           values=("",""),tags=("up",))
        else:
            self.tv.insert("","end",iid="__up__",text="▲  (radice)",
                           values=("",""),tags=("up_disabled",))
        for ch in node.children:
            nf=self._count_files(ch)
            self.tv.insert("","end",iid=ch.path,
                           text=tk_safe(ch.name),
                           values=(fmt_size(ch.size),nf),tags=("dir",))
            if ch.children:
                self.tv.insert(ch.path,"end",iid=ch.path+"/__ph__",
                               text="…",values=("",""))
        self.tv.tag_configure("up",          foreground=HUD_CYAN)
        self.tv.tag_configure("up_disabled",  foreground=MUTED_COLOR)
        self.tv.tag_configure("dir",          foreground=TEXT_COLOR)

    def _go_up(self):
        """Torna alla cartella superiore dal tasto Su sopra il grafico."""
        r=self._rend()
        if r.current and r.current!=r.root and r.current.parent:
            r.navigate_to(r.current.parent)
            self._update_curlbl(r.current)
            self._stlbl.config(text=tk_safe(fmt_size(r.current.size)))
            self._poptv(r.current)
            self._update_up_bar()

    def _update_up_bar(self):
        """Mostra/nasconde la barra Su in base alla posizione corrente."""
        if not hasattr(self,"_up_bar"): return
        r=self._rend()
        if r.current and r.current!=r.root and r.current.parent:
            parent_name=tk_safe(r.current.parent.name or "/")
            self._up_btn.config(text=f"▲  {parent_name}")
            self._up_bar.grid()
        else:
            self._up_bar.grid_remove()

    def _tv_select(self,e=None):
        """Quando l'utente seleziona una riga: evidenzia lo spicchio nel sunburst."""
        sel = self.tv.selection()
        if not sel: return
        iid = sel[0]
        if iid == "__up__" or iid.endswith("/__ph__"): return
        node = self._findnode(iid)
        if not node: return
        # Ridisegna evidenziando lo spicchio selezionato
        self._rend()._highlight_node = node
        self._rend().draw()
        self._update_curlbl(node)
        self._stlbl.config(text=tk_safe(fmt_size(node.size)))

    def _tv_expand(self,e=None):
        sel=self.tv.focus()
        if not sel or sel=="__up__": return
        for ch in self.tv.get_children(sel):
            if ch.endswith("/__ph__"): self.tv.delete(ch)
        node=self._findnode(sel)
        if not node: return
        for ch in node.children:
            if self.tv.exists(ch.path): continue
            nf=self._count_files(ch)
            self.tv.insert(sel,"end",iid=ch.path,
                           text=tk_safe(ch.name),
                           values=(fmt_size(ch.size),nf),tags=("dir",))
            if ch.children:
                self.tv.insert(ch.path,"end",iid=ch.path+"/__ph__",
                               text="…",values=("",""))

    def _findnode(self,path):
        if not self._root: return None
        def _s(n):
            if n.path==path: return n
            for c in n.children:
                r=_s(c)
                if r: return r
        return _s(self._root)

    def _tv_click1(self,e):
        """Click singolo: se su riga ▲ Su, sale subito senza aspettare doppio click."""
        iid=self.tv.identify_row(e.y)
        if iid=="__up__":
            r=self._rend()
            if r.current and r.current.parent:
                self.tv.after(10, lambda: self._nav(r.current.parent))
            # se up_disabled (radice) non fa nulla

    def _tv_dbl(self,e=None):
        sel=self.tv.selection()
        if not sel: return
        iid=sel[0]
        if iid.endswith("/__ph__"): return
        if iid=="__up__":
            r=self._rend()
            if r.current and r.current.parent: self._nav(r.current.parent)
            return
        node=self._findnode(iid)
        if node: self._nav(node)

    # ── Interazione canvas ────────────────────────────────────────────────────
    def _click(self,e):
        n=self._rend().hit_test(e.x,e.y)
        if n: self._nav(n)
    def _dblclick(self,e):
        n=self._rend().hit_test(e.x,e.y)
        if n and os.path.isdir(n.path): self._tobrowser(n.path)
    def _rclick(self,e):
        n=self._rend().hit_test(e.x,e.y)
        if not n: return
        menu=tk.Menu(self.win,tearoff=0,bg=PANEL_COLOR,fg=TEXT_COLOR,
                     activebackground="#1a3a5a",activeforeground=HUD_CYAN,relief="flat")
        menu.add_command(label=tk_safe(n.name[:50]),state="disabled",font=("TkFixedFont",8,"bold"))
        menu.add_command(label=fmt_size(n.size),state="disabled",font=("TkFixedFont",7))
        menu.add_separator()
        menu.add_command(label="Naviga qui",          command=lambda:self._nav(n))
        menu.add_command(label="Apri nel file manager",command=lambda:self._fm(n.path))
        if self.sorter:
            menu.add_command(label="Apri nel browser Image Sorter",
                             command=lambda:self._tobrowser(n.path))
        menu.tk_popup(e.x_root,e.y_root)
        try: menu.grab_release()
        except Exception: pass
    def _motion(self,e):
        n=self._rend().hit_test(e.x,e.y)
        if n:
            if n!=self._hover:
                self._hover=n
                self._tiplbl.config(text=tk_safe(
                    f"{n.name}  {fmt_size(n.size)}  ({len(n.children)} subdir)"))
            if hasattr(self,"_tt"):
                txt=tk_safe(f"{n.name}  {fmt_size(n.size)}")
                self._tt.config(text=txt)
                cw=self.canvas.winfo_width(); ch=self.canvas.winfo_height()
                self._tt.update_idletasks()
                tw=self._tt.winfo_reqwidth(); th=self._tt.winfo_reqheight()
                tx=e.x+16; ty=e.y+16
                if tx+tw>cw: tx=e.x-tw-8
                if ty+th>ch: ty=e.y-th-8
                self._tt.place(x=tx,y=ty); self._tt.lift()
                self._tt_visible=True
        else:
            self._hover=None; self._tiplbl.config(text="")
            if hasattr(self,"_tt") and self._tt_visible:
                self._tt.place_forget(); self._tt_visible=False
    def _clrtip(self,e=None):
        self._hover=None; self._tiplbl.config(text="")
        if hasattr(self,"_tt") and self._tt_visible:
            self._tt.place_forget(); self._tt_visible=False

    # ── Azioni ────────────────────────────────────────────────────────────────
    def _open_filemanager(self):
        """Apre la cartella corrente nel file manager."""
        r=self._rend(); n=r.current or self._root
        if not n: return
        path=n.path
        import subprocess
        for fm in ["nautilus","nemo","thunar","dolphin","pcmanfm","caja","xdg-open"]:
            try:
                subprocess.Popen([fm, path])
                return
            except FileNotFoundError:
                continue

    def _open_cur(self):
        r=self._rend(); n=r.current or self._root
        if n: self._tobrowser(n.path)
    def _tobrowser(self,path):
        if not self.sorter: self._fm(path); return
        try:
            if hasattr(self.sorter,'_open_browser_to'): self.sorter._open_browser_to(path)
            else: self._fm(path)
        except Exception: self._fm(path)
    def _fm(self,path):
        import subprocess
        for fm in ["nautilus","nemo","thunar","dolphin","pcmanfm","caja","xdg-open"]:
            if subprocess.run(["which",fm],capture_output=True).returncode==0:
                try: subprocess.Popen([fm,path],stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL); return
                except Exception: continue
    def _close(self): self._stop.set(); self.win.destroy()

def open_disk_analyzer(parent,sorter=None,initial_dir=None):
    DiskAnalyzer(parent,sorter=sorter,initial_dir=initial_dir)

if __name__=="__main__":
    path=sys.argv[1] if len(sys.argv)>1 else os.path.expanduser("~")
    root=tk.Tk(); root.withdraw()
    app=DiskAnalyzer(root,initial_dir=path)
    app.win.protocol("WM_DELETE_WINDOW",root.destroy)
    root.mainloop()
