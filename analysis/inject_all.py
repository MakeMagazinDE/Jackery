#!/usr/bin/env python3
"""Try all inverter-recovery commands in sequence: wake-5, wake-10, force-5, force-10.
Stops as soon as the alarm-ring fault count drops. Run with unit ON, probe attached,
inverter 'Interface' connector seated, and (for force) AC grid connected if possible."""
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

CMDS = {"wake": 0x0365BC01, "force": 0x0365C001}
HANDLER = {"wake": 0x080410E8, "force": 0x0804088C}
PAYLOAD = {5: 0x080A008C, 10: 0x080A0104}
TRAP = 0x08000000
RING = 0x10006810
COMBOS = [("wake", 5), ("wake", 10), ("force", 5), ("force", 10)]

def ring_count(t):
    return (t.read_memory(RING) >> 16) & 0xFFFF

def inject(t, cmd, data):
    saved = {r: t.read_core_register(r) for r in ('r0','r1','r2','r3','r12','lr','pc','xpsr')}
    t.set_breakpoint(TRAP)
    t.write_core_register('r0', CMDS[cmd])
    t.write_core_register('r1', PAYLOAD[data])
    t.write_core_register('r2', 4)
    t.write_core_register('lr', TRAP | 1)
    t.write_core_register('pc', HANDLER[cmd])
    t.write_core_register('xpsr', 0x01000000)
    t.resume()
    for _ in range(400):
        if t.get_state() == Target.State.HALTED: break
        time.sleep(0.01)
    r0 = t.read_core_register('r0')
    t.remove_breakpoint(TRAP)
    for r, v in saved.items():
        t.write_core_register(r, v)
    return r0

session = ConnectHelper.session_with_chosen_probe(
    options={"target_override": "gd32f470zg", "connect_mode": "attach", "frequency": 1000000})
session.open()
t = session.target
cleared = False
try:
    for cmd, data in COMBOS:
        t.halt()
        before = ring_count(t)
        r0 = inject(t, cmd, data)
        t.resume()
        print(f"[{cmd:>5} data={data:<2}] queued r0=0x{r0:08X}  count {before} -> ", end="", flush=True)
        time.sleep(4.0)
        t.halt()
        after = ring_count(t)
        print(f"{after}")
        if after < before:
            print(f"\n  >>> CLEARED by {cmd} data={data} !  Re-dump 0x10006810 to confirm. <<<")
            cleared = True
            t.resume()
            break
        t.resume()
        time.sleep(1.0)
    if not cleared:
        print("\n  None of the inverter commands cleared it.")
        print("  -> The inverter route can't reach/clear the latch (likely halted by the BMS fault).")
        print("  -> Next: direct cell-BMS access (dump/clear at the source).")
finally:
    session.close()
print("== done ==")
