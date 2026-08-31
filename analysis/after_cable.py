#!/usr/bin/env python3
import struct, os
NEW = r"ram_after_cable.bin"     # <-- Pfad zum RAM-Dump nach Kabelverbindung anpassen (0x20000000)
OLD = r"ram_faulted.bin"         # <-- Pfad zum RAM-Dump vor Kabelverbindung anpassen
new = open(NEW,"rb").read()
old = open(OLD,"rb").read()
print(f"new size={len(new)}  old size={len(old)}")
BASE=0x20000000
def rd(buf,addr,n): return buf[addr-BASE:addr-BASE+n]
def hd(buf,addr,n,label=""):
    print(f"--- {label} 0x{addr:08X} ({'NEW' if buf is new else 'OLD'}) ---")
    d=rd(buf,addr,n)
    for i in range(0,n,16):
        row=d[i:i+16]; h=" ".join(f"{x:02X}" for x in row)
        s="".join(chr(x) if 32<=x<127 else "." for x in row)
        print(f"  0x{addr+i:08X}: {h:<48} {s}")

codes={0:'CellOV1',1:'CellOV2',2:'CellOVLock',3:'CellUV1',4:'CellUV2',5:'CellUVLock',
 6:'BatOV1',7:'BatOV2',8:'BatUV1',9:'BatUV2',0x17:'SOHLowLock',0xe:'CELLOTLOCK',
 0x26:'BmsIntTimeout',0x27:'AfeComTimeout',0x28:'EEPRomTimeout',0x2b:'BATfromMCU_ERR',
 0x34:'PACKfromMCUERR',0x35:'CurfromMCUERR',0x1d:'PCSComFail',0x1c:'IntegraParComTimeOut'}

def scan_bms1(buf,label):
    print(f"\n=== '{label}': bms1_ occurrences + preceding code u16s ===")
    i=buf.find(b'bms1_'); n=0
    while i!=-1 and n<30:
        if i>=4:
            c0,c1=struct.unpack_from('<HH',buf,i-4)
            print(f"  @0x{BASE+i:08X}  u16@-4=0x{c0:04X}({codes.get(c0,'?')})  u16@-2=0x{c1:04X}({codes.get(c1,'?')})")
        i=buf.find(b'bms1_',i+1); n+=1

scan_bms1(new,"NEW after-cable")
scan_bms1(old,"OLD faulted")

# SRAM active-alarm list head region
hd(new,0x2002E990,96,"active-alarm list head NEW")

# diff with noise awareness: count differing, then show structured nonzero diffs in low SRAM (control structs)
print("\n=== diff new vs old (whole) ===")
ndiff=sum(1 for a,b in zip(new,old) if a!=b)
print(f"  total differing bytes: {ndiff} of {len(new)}")
