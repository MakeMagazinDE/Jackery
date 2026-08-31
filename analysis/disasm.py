#!/usr/bin/env python3
"""Thumb-2 disassembler with PC-relative literal resolution over dump_navi.bin."""
import struct, os, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN

BASE = r"DUMPS"    # <-- Pfad zum Ordner mit dump_navi.bin anpassen
FLASH_BASE = 0x08000000
fw = open(os.path.join(BASE,"dump_navi.bin"),"rb").read()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
md.detail = True

def foff(a): return a-FLASH_BASE
def u32(a):
    o=foff(a)
    return struct.unpack_from("<I",fw,o)[0]

def is_rom(a): return FLASH_BASE<=a<FLASH_BASE+len(fw)
def region(a):
    if 0x08000000<=a<0x08100000: return "FLASH"
    if 0x20000000<=a<0x20040000: return "SRAM"
    if 0x10000000<=a<0x10010000: return "CCM"
    if 0x40000000<=a<0x40080000: return "PERIPH"
    if 0x1FFF0000<=a<0x20000000: return "SYS"
    return "?"

def disasm(start, end, annotate=True):
    code = fw[foff(start):foff(end)]
    for ins in md.disasm(code, start):
        line=f"  0x{ins.address:08X}: {ins.mnemonic:<8} {ins.op_str}"
        note=""
        # resolve PC-relative literal loads: ldr rX, [pc, #imm]
        if ins.mnemonic.startswith("ldr") and "[pc" in ins.op_str:
            # literal address = (PC & ~3) + imm ; PC = addr+4
            try:
                imm = int(ins.op_str.split("#")[-1].rstrip("]"),0)
                lit = ((ins.address+4)&~3)+imm
                val = u32(lit)
                note=f"   ; [0x{lit:08X}]=0x{val:08X} ({region(val)})"
                # if val points into flash, show string if printable
                if is_rom(val):
                    o=foff(val); s=bytearray()
                    while o<len(fw) and 32<=fw[o]<127 and len(s)<48:
                        s.append(fw[o]); o+=1
                    if len(s)>=3: note+=f' "{s.decode()}"'
            except Exception as e:
                note=f"   ; (lit?) {e}"
        # branch/bl targets
        elif ins.mnemonic in ("bl","b","bl.w","b.w","blx","cbz","cbnz","beq","bne") and ins.op_str.startswith("#"):
            try:
                tgt=int(ins.op_str[1:],0)
                note=f"   ; -> 0x{tgt:08X}"
            except: pass
        print(line+note)

if __name__=="__main__":
    start=int(sys.argv[1],0); end=int(sys.argv[2],0)
    print(f"--- disasm 0x{start:08X}..0x{end:08X} ---")
    disasm(start,end)
