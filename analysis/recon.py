#!/usr/bin/env python3
"""Cheap high-value checks: SCB fault regs (Q8), backup SRAM (H6), RAM-dump structural diff."""
import struct, sys, os

BASE = r"DUMPS"    # <-- Pfad zum Ordner mit den RAM/SCB/BKPSRAM-Dumps anpassen
def load(name):
    with open(os.path.join(BASE, name), "rb") as f: return f.read()

def u32(b, off): return struct.unpack_from("<I", b, off)[0]

# ---------- Q8: SCB / fault status registers ----------
print("="*70)
print("Q8  CORTEX-M SCB / FAULT STATUS  (scb dumped from 0xE000E000)")
print("="*70)
scb = load("scb_3fault.bin")
def reg(addr): return u32(scb, addr - 0xE000E000)
regs = {
 "CPUID  0xED00": 0xE000ED00,
 "ICSR   0xED04": 0xE000ED04,
 "VTOR   0xED08": 0xE000ED08,
 "AIRCR  0xED0C": 0xE000ED0C,
 "SCR    0xED10": 0xE000ED10,
 "CCR    0xED14": 0xE000ED14,
 "SHCSR  0xED24": 0xE000ED24,
 "CFSR   0xED28": 0xE000ED28,
 "HFSR   0xED2C": 0xE000ED2C,
 "MMFAR  0xED34": 0xE000ED34,
 "BFAR   0xED38": 0xE000ED38,
}
for name, a in regs.items():
    print(f"  {name} = 0x{reg(a):08X}")
cfsr = reg(0xE000ED28); hfsr = reg(0xE000ED2C)
print("  --- decode ---")
if cfsr==0 and hfsr==0:
    print("  CFSR=0 HFSR=0  -> NO latched CPU fault. Firmware is NOT crashing; it is cleanly latching the BMS fault in software.")
else:
    print(f"  CFSR=0x{cfsr:08X} HFSR=0x{hfsr:08X}  -> a CPU fault IS latched, decode bits.")
# ICSR active vector
icsr = reg(0xE000ED04)
print(f"  ICSR.VECTACTIVE = {icsr & 0x1FF}  (0=thread mode at dump time)")

# ---------- H6: backup SRAM ----------
print()
print("="*70)
print("H6  BACKUP SRAM 4KB (0x40024000, supercap-held)")
print("="*70)
bk = load("bkpsram_3fault.bin")
nz = [(i,b) for i,b in enumerate(bk) if b!=0]
print(f"  size={len(bk)}  nonzero bytes={len(nz)}  (of {len(bk)})")
if nz:
    print(f"  nonzero range: 0x{nz[0][0]:03X} .. 0x{nz[-1][0]:03X}")
    # hex dump of nonzero region
    lo = (nz[0][0])//16*16; hi = (nz[-1][0])//16*16+16
    for off in range(lo, min(hi, len(bk)), 16):
        row = bk[off:off+16]
        hexs = " ".join(f"{x:02X}" for x in row)
        asc = "".join(chr(x) if 32<=x<127 else "." for x in row)
        print(f"   +0x{off:03X}: {hexs}  {asc}")
else:
    print("  ALL ZERO.")

# ---------- RAM structural overview ----------
print()
print("="*70)
print("RAM dumps: nonzero footprint + cross-capture equality")
print("="*70)
names = ["ram_faulted.bin","ram_faulted2after_boot.bin","ram_faulted3after_boot.bin",
         "ram_faulted4after_boot.bin","ram_3fault_a.bin","ram_3fault_b.bin"]
rams = {n: load(n) for n in names}
a = rams["ram_3fault_a.bin"]; b = rams["ram_3fault_b.bin"]
diff = sum(1 for x,y in zip(a,b) if x!=y)
print(f"  3fault_a vs 3fault_b (same state, noise ref): {diff} differing bytes of {len(a)}")
