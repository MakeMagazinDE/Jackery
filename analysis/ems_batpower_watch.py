#!/usr/bin/env python3
"""
Live, READ-ONLY watcher for the battery-power setpoint pipeline. Purpose: learn
HOW the Navi commands charging internally, so we can drive proportional
surplus-charging (charge power == live export) instead of a crude on/off toggle.

Run it, then in the app switch between **Battery-priority** (charges from grid,
~1200 W), **Self-consumption**, and idle. Watch which field moves and its sign.

Key variables (from disasm of the 'Set Inv Bat Power' handler @0x080409C0,
cmd id 0x0325AC01):
    0x20002B04  batpow_sp  int16   signed battery-power setpoint queued to PCS.
                                    NOTE the handler inverts sign: app value +P is
                                    stored as -P here. We learn the physical
                                    convention by watching it while charging.
    0x10000174+0x38 load_sp f32     the leveling-loop 'Load' setpoint (cmd 0x03242C01)
    0x100057F4+0x5c InvOnGridW f32  net grid power (~0 when leveled)
    0x100057F4+0x58 InvEspW    f32  output/backup power
    0x20000E34 packI f32  pack current  (>0 = CHARGING, <0 = discharging)  <-- truth
    0x20000E24 packV f32  pack voltage
    0x10000174+0x18 -> dev; +0x54 = live EMS state (diagnostic only)

This is pure observation. If it shows batpow_sp taking a clean signed value while
Battery-priority charges, that's the field HA would set (via cmd 0x0325AC01) to
charge at an arbitrary wattage == surplus.
"""
import time, struct
from pyocd.core.helpers import ConnectHelper

EMS=0x10000174; PCS=0x100057F4; BATSP=0x20002B04; PACKI=0x20000E34; PACKV=0x20000E24

def blk(t,a,n): return bytes(t.read_memory_block8(a,n))
def u32(t,a): return struct.unpack("<I", blk(t,a,4))[0]
def s16(t,a): return struct.unpack("<h", blk(t,a,2))[0]
def u8(t,a):  return blk(t,a,1)[0]
def f32(t,a):
    try: return struct.unpack("<f", blk(t,a,4))[0]
    except: return float("nan")
def in_ram(a): return (0x20000000<=a<0x20040000) or (0x10000000<=a<0x10010000)

def main():
    s=ConnectHelper.session_with_chosen_probe(
        options={"target_override":"gd32f470zg","connect_mode":"attach","frequency":1000000})
    s.open(); t=s.target
    print("Battery-power setpoint watcher (read-only).")
    print("Toggle Battery-priority / Self-consumption / idle in the app and watch batpow_sp + packI.")
    print("time      state  batpow_sp  load_sp   InvOnGridW  packI(A)  packV   batt")
    try:
        while True:
            try:
                dev=u32(t,EMS+0x18); st=u8(t,dev+0x54) if in_ram(dev) else -1
                bsp=s16(t,BATSP); lsp=f32(t,EMS+0x38); og=f32(t,PCS+0x5c)
                pi=f32(t,PACKI); pv=f32(t,PACKV)
                batt="CHARGING" if pi>0.3 else ("discharging" if pi<-0.3 else "idle")
                print(f"{time.strftime('%H:%M:%S')}  {st:>2}    {bsp:>7}   {lsp:>8.1f}   "
                      f"{og:>9.1f}  {pi:>+7.2f}  {pv:>6.2f}  {batt}")
            except Exception as e:
                print(f"  (read hiccup: {e})")
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        s.close()

if __name__=="__main__":
    main()
