#!/usr/bin/env python3
"""
Live, READ-ONLY float-dump of the EMS / meter / PCS RAM blocks, to PIN the exact
field that holds the Shelly net-grid power (the signed number that goes negative
on export). No halt, writes nothing. Ctrl-C to stop.

HOW TO USE (pin the field by matching a KNOWN value):
  Run this while you know the current grid flow from the app (e.g. +2090 W import
  during car charging, house ~2890 W, Jackery out ~800 W). Look in the 'plausible
  power' columns for floats that match those numbers:
     ~+2090  -> net grid (import positive)      <-- the one we want; goes NEGATIVE on export
     ~2890   -> total house load
     ~800    -> Jackery output
     per-phase values that sum to the grid total
  Once identified, tell me the offset and we lock it into the main probe so you can
  watch the export sign directly, read from the device's own memory.

Blocks dumped (bases found by RE):
  EMS ctrl   0x10000174  (+0x38 = 'loadpre'/Load setpoint)
  PCS live   0x100057F4  (+0x48 ac_v, +0x58 InvEspW, +0x5c InvOnGridW, +0x60, +0x88)
  Meter blk  0x20002A40  (Smart-CT / Shelly subsystem; heavily referenced global)
Battery truth: packI 0x20000E34 (>0 charging), packV 0x20000E24.
"""
import time, struct
from pyocd.core.helpers import ConnectHelper

BLOCKS = [("EMS ", 0x10000174, 0x90),
          ("PCS ", 0x100057F4, 0xC0),
          ("METR", 0x20002A40, 0xB0)]
PACKI=0x20000E34; PACKV=0x20000E24

def f32(t,a):
    try: return struct.unpack("<f", bytes(t.read_memory_block8(a,4)))[0]
    except: return float("nan")

def plausible(v):
    # a power reading in W: finite, |v| between 5 and 6000, not absurd
    return (v==v) and (abs(v) >= 5.0) and (abs(v) <= 6000.0)

def main():
    s=ConnectHelper.session_with_chosen_probe(
        options={"target_override":"gd32f470zg","connect_mode":"attach","frequency":1000000})
    s.open(); t=s.target
    print("Meter/EMS float dump (read-only). Match the app's known grid/house/output numbers.")
    try:
        while True:
            pi=f32(t,PACKI); pv=f32(t,PACKV)
            print(f"\n--- {time.strftime('%H:%M:%S')}   packI={pi:+.2f}A  packV={pv:.2f}V ---")
            for name, base, span in BLOCKS:
                cells=[]
                for off in range(0, span, 4):
                    v=f32(t, base+off)
                    if plausible(v):
                        cells.append(f"+0x{off:02X}={v:+8.1f}")
                if cells:
                    print(f"  {name} 0x{base:08X}: " + "  ".join(cells))
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        s.close()

if __name__=="__main__":
    main()
