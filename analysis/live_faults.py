#!/usr/bin/env python3
"""Decode the live fault bitmask at CCM 0x100028C0 using metadata table @0x080A22E8."""
import struct, os
BASE = r"DUMPS"    # <-- Pfad zum Ordner mit dump_navi.bin / ccm_3fault.bin anpassen
fw  = open(os.path.join(BASE,"dump_navi.bin"),"rb").read()      # 0x08000000
ccm = open(os.path.join(BASE,"ccm_3fault.bin"),"rb").read()     # 0x10000000

def fw_at(addr,n): return fw[addr-0x08000000:addr-0x08000000+n]
def ccm_u32(addr): return struct.unpack_from("<I",ccm,addr-0x10000000)[0]

TBL=0x080A22E8; STRIDE=0x26; N=67
FAULTBASE=0x100028C0   # = 0x10001A00 + 0xEC0

# Parse metadata
defs=[]
for i in range(N):
    e=fw_at(TBL+i*STRIDE, STRIDE)
    code=struct.unpack_from("<H",e,0)[0]
    name=bytearray()
    for b in e[2:2+0x20]:
        if 32<=b<127 and b!=0x20: name.append(b)
        elif b==0x20 and name: break
        elif b==0: break
        else:
            if name: break
    name=name.decode('ascii','replace')
    group=e[0x22]
    packed=struct.unpack_from("<H",e,0x24)[0]
    wordidx=(packed>>5)&0xFF
    bit=packed&0x1f
    defs.append((i,code,name,group,wordidx,bit))

# Dump the raw fault word array
print("=== raw fault bitmask array @0x100028C0 (4 groups x 4 words) ===")
for g in range(4):
    words=[ccm_u32(FAULTBASE+g*16+w*4) for w in range(4)]
    print(f"  group{g}: "+" ".join(f"0x{w:08X}" for w in words))

print("\n=== ACTIVE faults (bit set) ===")
active=[]
for (i,code,name,group,wordidx,bit) in defs:
    if group>=4 or wordidx>=4 or bit>=32: continue
    word=ccm_u32(FAULTBASE+group*16+wordidx*4)
    if word & (1<<bit):
        active.append((i,code,name,group,wordidx,bit))
        print(f"  idx{i:2d} code=0x{code:04X} grp{group} w{wordidx} bit{bit:2d}  {name}")
if not active:
    print("  (none set in this region)")

print(f"\n=== all 67 definitions (idx code grp/word/bit name) ===")
for (i,code,name,group,wordidx,bit) in defs:
    print(f"  {i:2d} 0x{code:04X} g{group} w{wordidx} b{bit:2d} {name}")
