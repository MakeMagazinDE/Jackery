#!/usr/bin/env python3
"""Find function start (backward prologue scan) + dispatch-table finder."""
import struct, os, sys
sys.path.insert(0,os.path.dirname(__file__))
from fw import fw, faddr, foff, FLASH_BASE

def find_func_start(addr, maxback=0x600):
    """Scan backward for a push{...,lr} prologue (16-bit B5xx or 32-bit E92D ....)."""
    o=foff(addr)
    for back in range(0, maxback, 2):
        p=o-back
        if p<0: break
        hw=struct.unpack_from("<H",fw,p)[0]
        # 16-bit PUSH {..,lr}: 1011 0101 xxxx xxxx = 0xB5xx
        if (hw & 0xFF00)==0xB500:
            return faddr(p)
        # 32-bit PUSH.W {..,lr}: 0xE92D + reg mask with lr(bit14) ... first hw 0xE92D
        if hw==0xE92D:
            return faddr(p)
    return None

def find_dispatch_tables(lo=0x08040000, hi=0x08044200, minrun=6):
    """Find runs of consecutive 4-byte words that are odd (thumb) pointers into code range."""
    runs=[]; run=[]
    for off in range(0,len(fw)-4,4):
        v=struct.unpack_from("<I",fw,off)[0]
        ok = (lo<=v<hi) and (v&1)
        if ok:
            run.append((faddr(off),v))
        else:
            if len(run)>=minrun: runs.append(run)
            run=[]
    if len(run)>=minrun: runs.append(run)
    return runs

if __name__=="__main__":
    targets={
      "InvReadClearHandle(err@0x08042B2F)":0x08042B2F,
      "InvAlarmHandle(err@0x08040673)":0x08040673,
      "InvReadClearHandle_mid":0x08042A00,
    }
    for name,a in targets.items():
        s=find_func_start(a)
        print(f"{name}: start ~ 0x{s:08X}" if s else f"{name}: not found")
    print("\n=== dispatch-table candidate runs (odd ptrs into 0x08040000-0x08044200) ===")
    for run in find_dispatch_tables():
        print(f"  table @0x{run[0][0]:08X} .. 0x{run[-1][0]:08X}  ({len(run)} entries)")
        for a,v in run:
            print(f"     [0x{a:08X}] -> 0x{v:08X}  (func 0x{v&~1:08X})")
