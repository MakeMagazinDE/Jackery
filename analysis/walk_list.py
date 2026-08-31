#!/usr/bin/env python3
import struct, os
BASE = r"DUMPS"    # <-- Pfad zum Ordner mit ccm_3fault.bin / ram_3fault_a.bin anpassen
ccm = open(os.path.join(BASE,"ccm_3fault.bin"),"rb").read()
sram= open(os.path.join(BASE,"ram_3fault_a.bin"),"rb").read()
def rd(a,n):
    if 0x10000000<=a<0x10010000: return ccm[a-0x10000000:a-0x10000000+n]
    if 0x20000000<=a<0x20040000: return sram[a-0x20000000:a-0x20000000+n]
    return None
def u32(a):
    d=rd(a,4); return struct.unpack("<I",d)[0] if d and len(d)==4 else None
def hexdump(a,n):
    d=rd(a,n)
    for i in range(0,n,16):
        row=d[i:i+16]; h=" ".join(f"{x:02X}" for x in row)
        s="".join(chr(x) if 32<=x<127 else "." for x in row)
        print(f"  0x{a+i:08X}: {h:<48} {s}")

print("=== full per-device record @0x10006810 (64B) ===")
hexdump(0x10006810,64)

print("\n=== SRAM active-alarm list head @0x2002E998 (256B raw) ===")
hexdump(0x2002E998,256)

# try to interpret as linked list: guess node = {next_ptr, ...}. Walk pointers that look like SRAM.
print("\n=== pointer-chase from 0x2002E998 ===")
seen=set(); a=0x2002E998
for _ in range(12):
    if a in seen or not (0x20000000<=a<0x20040000): break
    seen.add(a)
    nxt=u32(a)
    d=rd(a,60)
    asc="".join(chr(x) if 32<=x<127 else "." for x in d) if d else ""
    codes=struct.unpack_from("<IIII",d,0) if d else ()
    print(f"  node@0x{a:08X} next?=0x{nxt:08X} first4w={[hex(c) for c in codes]}")
    print(f"      | {asc}")
    if not nxt or nxt==a: break
    a=nxt
