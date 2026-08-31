#!/usr/bin/env python3
"""Firmware toolkit for dump_navi.bin (GD32F470, flash @ 0x08000000, app VTOR 0x08008000)."""
import struct, re, os, sys

BASE = r"DUMPS"    # <-- Pfad zum Ordner mit dump_navi.bin anpassen
FLASH_BASE = 0x08000000
fw = open(os.path.join(BASE,"dump_navi.bin"),"rb").read()

def faddr(off): return FLASH_BASE+off
def foff(addr): return addr-FLASH_BASE

def strings(minlen=4):
    out=[]
    cur=bytearray(); start=0
    for i,b in enumerate(fw):
        if 32<=b<127:
            if not cur: start=i
            cur.append(b)
        else:
            if len(cur)>=minlen:
                out.append((start,cur.decode('ascii')))
            cur=bytearray()
    return out

def find_str(substr):
    """Return list of (flash_addr, string) whose text contains substr."""
    res=[]
    for off,s in strings():
        if substr in s:
            res.append((faddr(off),s))
    return res

def xrefs_to(addr):
    """Find flash offsets holding the 32-bit little-endian value == addr (literal-pool pointer)."""
    needle=struct.pack("<I",addr)
    res=[]
    i=fw.find(needle)
    while i!=-1:
        res.append(faddr(i))
        i=fw.find(needle,i+1)
    return res

if __name__=="__main__":
    cmd=sys.argv[1] if len(sys.argv)>1 else "anchors"
    if cmd=="dumpstrings":
        with open(os.path.join(os.path.dirname(__file__),"strings.txt"),"w",encoding="utf-8") as f:
            for off,s in strings():
                f.write(f"0x{faddr(off):08X}  {s}\n")
        print("wrote strings.txt")
    elif cmd=="anchors":
        anchors=["ems fault pre","BatSWorkState","Standby:%d","ClrOneDeviceAllAlarm",
                 "Internal BMS","Internal battery","Internal device","fromMCU","BmsFault",
                 "MosFault","Sperr","lock","Lock","recclr","logclr","eeprom","EEPRom",
                 "BatSWorkState =","PcsWorkState"]
        for a in anchors:
            hits=find_str(a)
            print(f"\n=== '{a}'  ({len(hits)} hits) ===")
            for addr,s in hits[:12]:
                # find pointer xrefs to this exact string address
                xr=xrefs_to(addr)
                print(f"  0x{addr:08X}  xrefs={len(xr)} {['0x%08X'%x for x in xr[:6]]}  | {s[:70]!r}")
