#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Per-stage latency profiler for OCUDU DU UE-lifecycle procedures.

Measures DU-MNG / MAC / SCHED / DU-F1 procedure stages for UE creation,
(re)configuration and removal. Declarative registry => degrades gracefully
when a build omits intermediate trace lines (reports only present stages).

Usage: ocudu_ue_proc_latency.py <gnb.log|srsdu.log> [proc-filter-substr]
"""
import re, sys, math

# ---- procedure registry: name -> ordered list of (stage_key, exact_label) ----
# First entry = open trigger, last entry = close trigger. Absent stages skipped.
PROCS = {
 "UE Create": [
   ("start","Procedure started...."),("resmgr","Created DU UE resource manager."),
   ("ctxt","Created DU UE context."),("updres","Updated UE ctxt resources."),
   ("srb","Created DU UE SRB1."),("f1ap","Created DU UE F1AP."),
   ("rlc","Created UE RLC bearers."),("conn","Connected UE bearers."),
   ("startmac","Starting MAC UE creation."),("maccreated","MAC UE created."),
   ("flush","Flushed CCCH."),("done","Procedure finished successfully.")],
 "MAC UE Creation": [
   ("start","started..."),("ul","MAC UE UL context created successfully."),
   ("dl","MAC UE DL context created successfully."),
   ("ctx","UE context created successfully"),("done","finished successfully")],
 "UE Configuration": [
   ("start","Procedure started...."),("done","Procedure finished successfully.")],
 "MAC UE Reconfiguration": [
   ("start","started..."),("done","finished successfully")],
 "Sched UE Config": [
   ("start","started..."),("done","successfully finished")],
 "UE Delete": [
   ("start","Procedure started...."),("done","Procedure finished successfully.")],
 "MAC UE Removal": [
   ("start","started..."),("done","finished successfully")],
 "UE Context Release": [
   ("start","Started."),("lower","Initiate UE release in lower layers."),
   ("done","Finished successfully.")],
}

# optional explicit transitions per proc: (label, from, to); from/to may be tuple => max()
TRANSITIONS = {
 "MAC UE Creation": [
   ("start -> ul", "start","ul"),("start -> dl","start","dl"),
   ("ctx ready -> ctx created", ("ul","dl"), "ctx"),("ctx -> done","ctx","done")],
}

# group procedures for report ordering
GROUPS = [("CREATION",["UE Create","MAC UE Creation"]),
          ("CONFIGURATION",["UE Configuration","MAC UE Reconfiguration","Sched UE Config"]),
          ("REMOVAL",["UE Delete","MAC UE Removal","UE Context Release"])]

LINE = re.compile(r'T(\d{2}:\d{2}:\d{2}\.\d{6}) \[[A-Z0-9 -]+\s*\] \[.\] .*?(?:ue|du_ue)=(\d+).*?proc="([^"]+)": (.*?)\s*$')
def secs(t):
    h,m,s=t.split(':'); s,us=s.split('.'); return ((int(h)*60+int(m))*60+int(s))+int(us)/1e6

# label->key per proc, and first/last key
LBL2KEY={p:{lbl:k for k,lbl in st} for p,st in PROCS.items()}
FIRST={p:st[0][0] for p,st in PROCS.items()}
LAST ={p:st[-1][0] for p,st in PROCS.items()}

if len(sys.argv)<2:
    sys.exit("usage: ocudu_ue_proc_latency.py <gnb.log|srsdu.log> [proc-filter-substr]")
path=sys.argv[1]
filt=sys.argv[2] if len(sys.argv)>2 else None

open_rec={}                 # (ue,proc)->dict
records={p:[] for p in PROCS}
def close(ue,p):
    k=(ue,p)
    if k in open_rec: records[p].append(open_rec.pop(k))

for ln in open(path,errors='replace'):
    if 'proc="' not in ln: continue
    m=LINE.search(ln)
    if not m: continue
    t,ue,proc,lbl=m.group(1),m.group(2),m.group(3),m.group(4)
    if proc not in PROCS: continue
    key=LBL2KEY[proc].get(lbl)
    if key is None: continue
    rk=(ue,proc)
    if key==FIRST[proc]:
        close(ue,proc); open_rec[rk]={}
    elif rk not in open_rec:
        open_rec[rk]={}        # lazy open (missing start)
    open_rec[rk].setdefault(key,secs(t))
    if key==LAST[proc]:
        close(ue,proc)

def pct(xs,p):
    xs=sorted(xs); i=min(len(xs)-1,max(0,math.ceil(p/100*len(xs))-1)); return xs[i]
def f(x): return f"{x/1000:.2f}ms" if x>=1000 else f"{x:.0f}us"

def report(proc):
    recs=records[proc]
    if not recs: return
    st=PROCS[proc]; present=[k for k,_ in st]
    print(f"\n### proc=\"{proc}\"   instances={len(recs)}")
    hdr=f"{'stage transition':34} {'n':>5} {'mean':>9} {'p50':>9} {'p90':>9} {'p99':>9} {'max':>10}"
    print(hdr); print('-'*len(hdr))
    def mk(frm,to):
        def g(r):
            fs=frm if isinstance(frm,tuple) else (frm,)
            if to not in r or any(k not in r for k in fs): return None
            return r[to]-max(r[k] for k in fs)
        return g
    rows=[]
    if proc in TRANSITIONS:
        for lbl,frm,to in TRANSITIONS[proc]:
            rows.append((lbl, mk(frm,to)))
    else:
        for (ka,_),(kb,_) in zip(st,st[1:]):
            rows.append((f"{ka} -> {kb}", mk(ka,kb)))
    fa,la=FIRST[proc],LAST[proc]
    rows.append((f"== TOTAL ({fa}->{la})", mk(fa,la)))
    for lbl,fn in rows:
        vals=[fn(r) for r in recs]; vals=[v*1e6 for v in vals if v is not None and v>=0]
        if not vals: print(f"{lbl:34} {0:>5}       -"); continue
        n=len(vals); mean=sum(vals)/n
        print(f"{lbl:34} {n:>5} {f(mean):>9} {f(pct(vals,50)):>9} {f(pct(vals,90)):>9} {f(pct(vals,99)):>9} {f(max(vals)):>10}")

print(f"# log: {path}")
for gname,plist in GROUPS:
    plist=[p for p in plist if records[p] and (not filt or filt in p)]
    if not plist: continue
    print(f"\n========== {gname} ==========")
    for p in plist: report(p)
