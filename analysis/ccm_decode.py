#!/usr/bin/env python3
"""Decode alarm ring buffer + context from CCM/SRAM dumps."""
import struct, os
BASE = r"DUMPS"    # <-- Pfad zum Ordner mit ccm_3fault.bin / ram_3fault_a.bin anpassen
ccm = open(os.path.join(BASE,"ccm_3fault.bin"),"rb").read()      # 0x10000000
sram= open(os.path.join(BASE,"ram_3fault_a.bin"),"rb").read()    # 0x20000000

def rd(addr,n):
    if 0x10000000<=addr<0x10010000: b=ccm; base=0x10000000
    elif 0x20000000<=addr<0x20040000: b=sram; base=0x20000000
    else: return None
    o=addr-base
    if o+n>len(b): return None
    return b[o:o+n]
def u32(addr):
    d=rd(addr,4); return struct.unpack("<I",d)[0] if d else None
def u16(addr):
    d=rd(addr,2); return struct.unpack("<H",d)[0] if d else None

print("=== Alarm context @ CCM 0x10000280 ===")
for off in range(0,0x20,4):
    v=u32(0x10000280+off)
    print(f"  [0x{0x10000280+off:08X}] = 0x{v:08X}" if v is not None else f"  [+{off}] oob")

tbl = u32(0x10000284)   # [sb+4] = alarm table ptr
mtx = u32(0x1000028C)   # [sb+0xc] = mutex
print(f"\nalarm table ptr [0x10000284] = 0x{tbl:08X}")
if tbl:
    head=u16(tbl); cnt=u16(tbl+2)
    print(f"  ring head(idx)=0x{head:04X}={head}  count=[tbl+2]={cnt}")
    # records: 60-byte (0x3c) entries, array starts at tbl+4, modulus 20
    print(f"  --- up to 20 records (60B each) at 0x{tbl+4:08X} ---")
    for i in range(20):
        rec_addr = tbl+4 + i*0x3c
        rec = rd(rec_addr,0x3c)
        if rec is None:
            print(f"   slot{i:2d} @0x{rec_addr:08X} oob"); continue
        if all(x==0 for x in rec):
            continue
        code = struct.unpack_from("<I",rec,0)[0]
        b6 = rec[6]
        asc = "".join(chr(x) if 32<=x<127 else "." for x in rec)
        print(f"   slot{i:2d} @0x{rec_addr:08X} code=0x{code:08X} [+6]={b6:#04x} | {asc}")

print("\n=== CCM 0x10006CC4 -> SRAM active-alarm list head ===")
p=u32(0x10006CC4); print(f"  [0x10006CC4]=0x{p:08X}")
print("\n=== GetAlarmMark inputs: 0x100018D4, 0x10006CC4 ===")
d=rd(0x100018D4,40)
if d: print("  0x100018D4:", "".join(chr(x) if 32<=x<127 else "." for x in d))
