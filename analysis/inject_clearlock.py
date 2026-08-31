#!/usr/bin/env python3
"""
Option A: clear CellUVLock by calling the firmware's own DeviceAlarmActionBy32BitCode.
Call: (r0=devtype=2, r1=serial_ptr, r2=group=3, r3=word=0, [stack]=new_word=0,0,0)
-> removes CellUVLock from the alarm ring and updates the device fault word.

Run with unit ON and SWD probe attached. Recoverable by power-cycle if anything hangs.
After it runs: REBOOT the unit and re-dump 0x10006810 to confirm it STAYS cleared.
"""
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

FUNC   = 0x0802439C
SERIAL = 0x100018D4      # "bms1_HA2A15100146HH3" in CCM
ARG0   = 2               # device type = battery
GROUP  = 3               # CellUVLock group
WORD   = 0               # CellUVLock word
NEWVAL = 0               # new fault word for group3/word0 (clears bit1 = CellUVLock)
TRAP   = 0x08000000
RING   = 0x10006810      # [low u16]=head, [high u16]=count

session = ConnectHelper.session_with_chosen_probe(
    options={"target_override": "gd32f470zg", "connect_mode": "attach", "frequency": 1000000})
session.open()
t = session.target
def ring_count():
    return (t.read_memory(RING) >> 16) & 0xFFFF
try:
    t.halt()
    before = ring_count()
    print(f"alarm-ring fault count BEFORE: {before}")

    saved = {r: t.read_core_register(r) for r in ('r0','r1','r2','r3','r12','sp','lr','pc','xpsr')}
    sp = saved['sp']
    scratch = (sp - 0x40) & ~7          # fresh frame below the task's stack
    t.write_memory(scratch + 0, NEWVAL) # arg5 = new fault word
    t.write_memory(scratch + 4, 0)      # arg6
    t.write_memory(scratch + 8, 0)      # arg7

    t.set_breakpoint(TRAP)
    t.write_core_register('sp', scratch)
    t.write_core_register('r0', ARG0)
    t.write_core_register('r1', SERIAL)
    t.write_core_register('r2', GROUP)
    t.write_core_register('r3', WORD)
    t.write_core_register('lr', TRAP | 1)
    t.write_core_register('pc', FUNC)
    t.write_core_register('xpsr', 0x01000000)
    t.resume()

    for _ in range(600):                # wait up to ~6s (it takes a 5s-timeout mutex)
        if t.get_state() == Target.State.HALTED:
            break
        time.sleep(0.01)
    r0 = t.read_core_register('r0')
    pc = t.read_core_register('pc')
    print(f"returned r0=0x{r0:08X}  (1=change made, 0=no change, 0x20=rejected)   trap pc=0x{pc:08X}")

    t.remove_breakpoint(TRAP)
    for r, v in saved.items():
        t.write_core_register(r, v)     # restore the interrupted task
    t.resume()
    print("firmware resumed; waiting 2 s ...")
    time.sleep(2.0)
    t.halt()
    after = ring_count()
    print(f"alarm-ring fault count AFTER : {after}")
    if after < before:
        print("  >>> CellUVLock REMOVED from the ring! <<<")
        print("  Now POWER-CYCLE the unit and re-dump 0x10006810 — if it stays 0, the lock is gone for good.")
    elif r0 == 0x20:
        print("  Call was rejected (arg validation) — tell me, I'll adjust the args.")
    else:
        print("  No change in the ring. Tell me r0 and I'll dig into why.")
    t.resume()
finally:
    session.close()
print("== done ==")
