#!/usr/bin/env python3
"""
Direct SWD clear of the CellUVLock bit — NO function call, NO mutex, NO RTOS risk.
The whole fault state of bms1 is one word (group3/word0) at [device_struct + 0x56].
device_struct ptr = [0x10006CC4][0]. We sanity-check type/serial, then zero the word.

Run with unit ON + probe attached. Then POWER-CYCLE + re-dump 0x10006810 to test persistence.
"""
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

PTRARR = 0x10006CC4     # array of device-struct pointers; [0] = bms1
RING   = 0x10006810     # [high u16] = active-alarm count
FWOFF  = 0x56           # group3/word0 fault word offset within the device struct

session = ConnectHelper.session_with_chosen_probe(
    options={"target_override": "gd32f470zg", "connect_mode": "attach", "frequency": 1000000})
session.open()
t = session.target
def ring_count():
    return (t.read_memory(RING) >> 16) & 0xFFFF
def rd_word(a):
    return int.from_bytes(bytes(t.read_memory_block8(a, 4)), "little")
try:
    t.halt()
    dev = t.read_memory(PTRARR)
    typ = t.read_memory_block8(dev + 4, 1)[0]
    ser = bytes(t.read_memory_block8(dev + 6, 20)).split(b"\x00")[0].decode("ascii", "replace")
    print(f"device struct @ 0x{dev:08X}  type={typ}  serial={ser!r}")
    if typ != 2 or not ser.startswith("bms1"):
        print("  !! sanity check FAILED (wrong struct) — aborting, no write done.")
        raise SystemExit
    fwaddr = dev + FWOFF
    val = rd_word(fwaddr)
    cnt0 = ring_count()
    print(f"  fault word @0x{fwaddr:08X} = 0x{val:08X}  (bit1 CellUVLock = {(val>>1)&1})")
    print(f"  ring count BEFORE: {cnt0}")
    if (val >> 1) & 1 == 0:
        print("  bit1 already clear — nothing to do.")
        raise SystemExit

    # clear bit1 (write the whole word = 0; only CellUVLock is set there)
    t.write_memory_block8(fwaddr, bytes(4))
    print(f"  >>> wrote 0x00000000 to 0x{fwaddr:08X} <<<")

    # let the firmware run and reconcile the ring
    t.resume()
    time.sleep(3.0)
    t.halt()
    dev2 = t.read_memory(PTRARR)
    val2 = rd_word(dev2 + FWOFF)
    cnt1 = ring_count()
    print(f"  AFTER 3 s: fault word = 0x{val2:08X}   ring count = {cnt1}")
    if val2 == 0 and cnt1 < cnt0:
        print("  >>> CLEARED — and the firmware reconciled the ring. <<<")
        print("  Now POWER-CYCLE + re-dump 0x10006810: if it stays 0, it persisted (DONE).")
    elif val2 != 0:
        print(f"  word RE-SET to 0x{val2:08X} → it's re-derived from a persistent source. Go to Option B (clear external flash).")
    else:
        print("  word stayed 0 but ring not yet reconciled — firmware may catch it next cycle; re-dump 0x10006810 to check.")
    t.resume()
finally:
    session.close()
print("== done ==")
