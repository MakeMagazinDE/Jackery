#!/usr/bin/env python3
"""Clear the CellUVLock fault word AND the alarm ring in RAM (direct SWD, no injection).
Then power off the unit GRACEFULLY (button) to see if the firmware persists the clean state."""
import time
from pyocd.core.helpers import ConnectHelper

PTRARR = 0x10006CC4
RING   = 0x10006810
FWOFF  = 0x56

session = ConnectHelper.session_with_chosen_probe(
    options={"target_override": "gd32f470zg", "connect_mode": "attach", "frequency": 1000000})
session.open()
t = session.target
try:
    t.halt()
    dev = t.read_memory(PTRARR)
    typ = t.read_memory_block8(dev + 4, 1)[0]
    ser = bytes(t.read_memory_block8(dev + 6, 20)).split(b"\x00")[0].decode("ascii", "replace")
    print(f"device @0x{dev:08X} type={typ} serial={ser!r}")
    if typ != 2 or not ser.startswith("bms1"):
        print("sanity fail - aborting"); raise SystemExit
    # clear device fault word (group3/word0)
    t.write_memory_block8(dev + FWOFF, bytes(4))
    # clear alarm ring head+count
    ring_before = t.read_memory(RING)
    t.write_memory(RING, 0x00000000)
    ring_after = t.read_memory(RING)
    print(f"cleared device word @0x{dev+FWOFF:08X} and ring @0x{RING:08X} ({ring_before:#010x} -> {ring_after:#010x})")
    t.resume()
    print("DONE. Now power OFF with the BUTTON (graceful), wait, power on, and re-dump 0x10006810.")
finally:
    session.close()
