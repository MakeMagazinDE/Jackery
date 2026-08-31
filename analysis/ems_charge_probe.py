#!/usr/bin/env python3
"""
Live, READ-ONLY probe for WHY Self-consumption (run mode 3) discharges but never
charges from AC surplus. Run while the rooftop PV genuinely exports. No CPU halt,
writes nothing. Ctrl-C to stop.

--- CORRECTED MODEL (2026-07-07, after an earlier wrong theory) ---
The GD32 EMS runs a fast power-leveling loop @0x0802D790 that:
  * computes a power SETPOINT ("Load", a float) via a calculator sub-fn,
  * applies +-10 W hysteresis,
  * sends it to the PCS/inverter board as command 0x03242C01,
  * stores it at EMS(0x10000174)+0x38  (== the last setpoint sent).
The PCS board (separate MCU, not in this dump) executes that setpoint.

So the decisive question is the SIGN of that setpoint during export:
    setpoint = *(float*)(0x10000174 + 0x38)
  * At night the unit levels your load, so setpoint is on the DISCHARGE side.
  * If, during daytime export, the setpoint NEVER crosses to the charge side
    (stays >=0 / clamped), the GD32 is emitting a discharge-only command -> the
    charge suppression is on THIS board and is what we'd override.
  * If the setpoint DOES go to the charge side but pack current stays ~0, the
    GD32 asks for charge and the PCS refuses -> suppression is on the PCS board
    (out of reach of this dump; different attack surface).

NOTE ON THE "800 W": that value is a grid-code / max-feed-in cap (== the German
Steckersolar limit), pulled from country table 0x0809DCF0. It is NOT a charge
threshold. (Earlier probe text claimed otherwise; that was wrong.)

Watched values:
  EMS 0x10000174:
    +0x38  setpoint  f32   last "Load" setpoint sent to PCS (SIGN is the point)
    +0x18  devptr          -> device struct; +0x54 = live EMS operating STATE
                            (NOT the app work-mode selector; e.g. 2=supplying/discharging,
                             3=idle. Diagnostic only -- packI is ground truth.)
  PCS 0x100057F4:
    +0x5c  InvOnGridW f32  inverter on-grid-port power (its own port, not the Shelly)
    +0x58  InvEspW    f32  inverter EPS/backup-port power
    +0x48  ac_v       f32  AC voltage
  Battery (SRAM, verified in monitor_charge.py):
    0x20000E34 f32 pack current (>0 = CHARGING, <0 = discharging)
    0x20000E24 f32 pack voltage
Sign of setpoint vs sign of pack current at night gives us the convention; then
watch what happens under daytime export.
"""
import time, struct
from pyocd.core.helpers import ConnectHelper

EMS   = 0x10000174
PCS   = 0x100057F4
PACKI = 0x20000E34
PACKV = 0x20000E24

def blk(t, a, n): return bytes(t.read_memory_block8(a, n))
def u8(t, a):  return blk(t, a, 1)[0]
def u32(t, a): return struct.unpack("<I", blk(t, a, 4))[0]
def f32(t, a):
    try: return struct.unpack("<f", blk(t, a, 4))[0]
    except: return float("nan")
def in_ram(a): return (0x20000000 <= a < 0x20040000) or (0x10000000 <= a < 0x10010000)

def main():
    s = ConnectHelper.session_with_chosen_probe(
        options={"target_override": "gd32f470zg",
                 "connect_mode": "attach", "frequency": 1000000})
    s.open()
    t = s.target
    print("Self-consumption charge probe (read-only). Run during real PV export.")
    print("Watch the SIGN of 'setpoint' vs 'packI'. Note it at night first to learn the convention.")
    print("time      state setpoint(W)  InvOnGridW InvEspW  ac_v    packI(A)  packV   batt")
    try:
        while True:
            try:
                dev  = u32(t, EMS + 0x18)
                state = u8(t, dev + 0x54) if in_ram(dev) else -1
                sp   = f32(t, EMS + 0x38)
                og   = f32(t, PCS + 0x5c)
                esp  = f32(t, PCS + 0x58)
                ac_v = f32(t, PCS + 0x48)
                pi   = f32(t, PACKI)
                pv   = f32(t, PACKV)
                batt = "CHARGING" if pi > 0.3 else ("discharging" if pi < -0.3 else "idle")
                print(f"{time.strftime('%H:%M:%S')}  {state:>2}   {sp:>10.1f}   "
                      f"{og:>9.1f} {esp:>8.1f} {ac_v:>5.1f}  {pi:>+7.2f}  {pv:>6.2f}  {batt}")
            except Exception as e:
                print(f"  (read hiccup: {e})")
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        s.close()

if __name__ == "__main__":
    main()
