#!/usr/bin/env python3
"""
Live, READ-ONLY monitor of the Navi 2000 EMS run mode + charge config over SWD.

Purpose: empirically pin the run-mode integer -> mode-name mapping that static RE
could not label. Run this, then change the work mode in the Jackery app; watch the
`runmode` column change. That number is the value the app sends in command
0x0160F801 ("Set Ems Run Mode", payload = 1..7), and is what HA can replay over
MQTT/BLE to force SelfConsumption / Battery-First (AC-surplus charging).

Provenance of the addresses (from dump_navi.bin disasm of the Set Ems Run Mode
handler @0x0802E8E8):
    emsctrl   = 0x10000174                         (CCM anchor)
    devstruct = *(u32*)(emsctrl + 0x18)  = *(u32*)0x1000018C   (ptr, moves per boot)
    runmode   = *(u8 *)(devstruct + 0x54)          (1..7; stored by the set handler)
    soc_ul    = *(u16*)(devstruct + 0x5a)          (forwarded to PCS via id 0x0365B401)
    soc_ll    = *(u16*)(devstruct + 0x5c)          (forwarded to PCS via id 0x0365B001)
    field52   = *(u8 *)(devstruct + 0x52)          (read in the EMS tick; unlabelled)

Does NOT halt the CPU (halting >500 ms trips the BMS-CAN timeouts) and writes
nothing. Ctrl-C to stop.

Tentative run-mode legend (UNCONFIRMED — the point of this script is to confirm it):
  the firmware validates 1..7; modes 2/3/4 carry SoC bounds (SelfConsumption and
  Battery-First both have SoC LL/UL). Verify by toggling each app mode and noting
  the number here.
"""
import time, struct
from pyocd.core.helpers import ConnectHelper

EMSCTRL   = 0x10000174
PTR_OFF   = 0x18          # devstruct pointer at EMSCTRL+0x18 (=0x1000018C)
RUNMODE   = 0x54
FIELD52   = 0x52
SOC_UL    = 0x5a
SOC_LL    = 0x5c

def u8(t, a):  return t.read_memory_block8(a, 1)[0]
def u16(t, a): return int.from_bytes(bytes(t.read_memory_block8(a, 2)), "little")
def u32(t, a): return int.from_bytes(bytes(t.read_memory_block8(a, 4)), "little")

def in_ram(a): return (0x20000000 <= a < 0x20040000) or (0x10000000 <= a < 0x10010000)

def main():
    session = ConnectHelper.session_with_chosen_probe(
        options={"target_override": "gd32f470zg",
                 "connect_mode": "attach", "frequency": 1000000})
    session.open()
    t = session.target
    print("EMS run-mode monitor (read-only). Change the work mode in the app and watch 'runmode'.")
    print("time      dev_ptr     runmode  f52   soc_ul  soc_ll   raw devstruct+0x40..0x60")
    prev = None
    try:
        while True:
            try:
                dev = u32(t, EMSCTRL + PTR_OFF)
                if not in_ram(dev):
                    print(f"{time.strftime('%H:%M:%S')}  dev_ptr=0x{dev:08X}  <- not a RAM/CCM ptr "
                          f"(EMS not populated yet? PCS offline / unit locked?)")
                    time.sleep(2.0); continue
                rm   = u8(t, dev + RUNMODE)
                f52  = u8(t, dev + FIELD52)
                ul   = u16(t, dev + SOC_UL)
                ll   = u16(t, dev + SOC_LL)
                raw  = bytes(t.read_memory_block8(dev + 0x40, 0x20))
                rawhex = raw.hex()
                mark = ""
                if prev is not None and rm != prev:
                    mark = f"   <== CHANGED {prev} -> {rm}"
                prev = rm
                print(f"{time.strftime('%H:%M:%S')}  0x{dev:08X}   {rm:>3}    {f52:>3}   "
                      f"{ul:>5}   {ll:>5}   {rawhex}{mark}")
            except Exception as e:
                print(f"  (read hiccup: {e})")
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        session.close()

if __name__ == "__main__":
    main()
