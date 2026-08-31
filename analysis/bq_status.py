#!/usr/bin/env python3
"""
BQ76952 / pack status snapshot — READ-ONLY (no halt, no injection).
Reads the firmware's BQ register mirror + pack telemetry over SWD and prints a
pre-CFETOFF-override safety checklist.

Purpose: before physically neutralizing the BQ's CFETOFF pin, confirm that
  (1) the BQ has NO active protection or permanent-fail  -> we'd be releasing a
      stale HOST/pin lock, not silencing a live BQ safety event;
  (2) the charge path is currently OPEN (CHG FET off) -> packI ~ 0 under the charger;
  (3) cells are healthy.
Then it tells you how to determine the CFETOFF tie level with a multimeter.

Run with unit ON, charger connected (so packI shows whether current flows), SWD attached.
"""
import struct, time
from pyocd.core.helpers import ConnectHelper

BQ     = 0x20004944     # BQ register mirror base (offset == BQ register address; 1:1 for polled regs)
CELLS  = 0x20000E02     # 16x u16 cell mV
PACKV  = 0x20000E24     # float32 pack voltage (V)
PACKI  = 0x20000E34     # float32 pack current (A)
RING   = 0x10006810     # alarm ring [u16 head][u16 count]
PTRARR = 0x10006CC4
FWOFF  = 0x56

def main():
    s=ConnectHelper.session_with_chosen_probe(
        options={"target_override":"gd32f470zg","connect_mode":"attach","frequency":1000000})
    s.open(); t=s.target
    rd=lambda a,n: bytes(t.read_memory_block8(a,n))
    u16=lambda d,i: d[i]|(d[i+1]<<8)
    f32=lambda a: struct.unpack("<f", rd(a,4))[0]
    try:
        m = rd(BQ, 0x40)                       # mirror low block (status + cells)
        cb= rd(CELLS,32); cells=[u16(cb,2*i) for i in range(16)]
        pv=f32(PACKV); pi=f32(PACKI)
        ring=rd(RING,4); cnt=u16(ring,2)
        rec=rd(RING+4,4); code0=u16(rec,0)
        dev=struct.unpack("<I",rd(PTRARR,4))[0]
        fw=struct.unpack("<I",rd(dev+FWOFF,4))[0] if 0x20000000<=dev<0x20040000 else -1

        saA,saB,saC = m[0x03],m[0x05],m[0x07]
        pfA,pfB,pfC,pfD = m[0x0A],m[0x0C],m[0x0E],m[0x10]
        batt = u16(m,0x12)

        print("="*64)
        print("  BQ76952 / PACK STATUS SNAPSHOT")
        print("="*64)
        print(f"  cells (mV): {cells}")
        print(f"     min={min(cells)}  max={max(cells)}  spread={max(cells)-min(cells)}")
        print(f"  pack voltage : {pv:6.2f} V")
        print(f"  pack current : {pi:+6.3f} A   <-- with charger on: ~0 => CHG path OPEN (FET off)")
        print(f"  Battery Status (0x12) = 0x{batt:04X}")
        print(f"  Safety Status  A/B/C  = 0x{saA:02X} / 0x{saB:02X} / 0x{saC:02X}")
        print(f"     (Safety A bit2=CUV bit3=COV bit4=OCC bit5=OCD1 bit6=OCD2 bit7=SCD)")
        if saA: print(f"     CUV={(saA>>2)&1} COV={(saA>>3)&1} OCC={(saA>>4)&1} OCD1={(saA>>5)&1} OCD2={(saA>>6)&1} SCD={(saA>>7)&1}")
        print(f"  PF Status A/B/C/D     = 0x{pfA:02X} / 0x{pfB:02X} / 0x{pfC:02X} / 0x{pfD:02X}")
        print(f"  alarm ring count={cnt}  first code=0x{code0:04X}  dev faultword[+0x56]=0x{fw:08X} (bit1 CellUVLock={(fw>>1)&1 if fw>=0 else '?'})")

        clean = (saA==0 and saB==0 and saC==0 and pfA==0 and pfB==0 and pfC==0 and pfD==0)
        chg_open = abs(pi) < 0.3
        healthy = min(cells)>3000 and (max(cells)-min(cells))<150
        print("\n  PRE-OVERRIDE CHECKLIST")
        print(f"   [{'PASS' if clean else 'FAIL'}] BQ has NO active protection / permanent-fail  (releasing a stale host-lock, not a live BQ fault)")
        print(f"   [{'PASS' if chg_open else 'n/a '}] charge path open / CHG FET off  (packI~0 under charger)")
        print(f"   [{'PASS' if healthy else 'WARN'}] cells healthy (all >3.0V, spread <150mV)")
        if clean and healthy:
            print("\n  => SAFE to proceed with CFETOFF override (BQ will re-enable CHG once the pin is de-asserted).")
        else:
            print("\n  => DO NOT override: a real BQ protection/PF is active or a cell is unhealthy. Stop and re-check.")

        print("\n  NEXT (polarity, with a multimeter — BQ is powered):")
        print("   1. Find the CFETOFF pin on the BQ76952 (U29). (Ask me for the exact 48-TQFP pin.)")
        print("   2. Measure CFETOFF pin voltage NOW (it is currently ASSERTED = charge-disable level).")
        print("   3. Cut its trace from the F28379D and tie the pin to the OPPOSITE level through ~10k:")
        print("        if it reads HIGH now  -> active-high -> tie to GND (inactive=LOW)")
        print("        if it reads LOW  now  -> active-low  -> tie to 3V3/REG (inactive=HIGH)")
        print("   4. Watch packI on monitor_charge.py: non-zero => CHG FET re-enabled, charging.")
    finally:
        s.close()

if __name__=="__main__":
    main()
