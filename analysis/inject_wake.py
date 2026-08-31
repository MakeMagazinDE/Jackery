#!/usr/bin/env python3
"""
Inject 'Set Inv Bat Wake Up' (or 'Set Inv Force Chg') over SWD to revive the cell-BMS.
Run on the PC with the ST-Link/J-Link attached and the Jackery powered ON.

  python inject_wake.py            # default: Bat Wake Up, data=5
  edit CMD / DATA below to try other combinations.

Safe to power-cycle the unit if anything hangs.
"""
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

# ---------------- choose what to inject ----------------
CMD  = "wake"     # "wake" = Bat Wake Up (0xA09A) | "force" = Force Chg (0xA0AB)
DATA = 5          # 5 or 10
# -------------------------------------------------------

CMDS = {
    "wake":  dict(handler=0x080410E8, cmd_id=0x0365BC01),
    "force": dict(handler=0x0804088C, cmd_id=0x0365C001),
}
PAYLOAD = {5: 0x080A008C, 10: 0x080A0104}   # flash words holding 0x00000005 / 0x0000000A
TRAP = 0x08000000                            # return-trap (HW breakpoint; halts before executing)
RING = 0x10006810                            # alarm ring: low u16 = head, high u16 = count

c = CMDS[CMD]
HANDLER, CMD_ID, PTR = c["handler"], c["cmd_id"], PAYLOAD[DATA]

def ring_count(t):
    return (t.read_memory(RING) >> 16) & 0xFFFF

print(f"== Injecting {CMD!r}  id=0x{CMD_ID:08X}  data={DATA}  handler=0x{HANDLER:08X} ==")
session = ConnectHelper.session_with_chosen_probe(
    options={"target_override": "gd32f470zg", "connect_mode": "attach", "frequency": 1000000})
session.open()
t = session.target
try:
    t.halt()
    before = ring_count(t)
    print(f"  alarm-ring fault count BEFORE : {before}")

    saved = {r: t.read_core_register(r) for r in ('r0','r1','r2','r3','r12','lr','pc','xpsr')}
    t.set_breakpoint(TRAP)
    t.write_core_register('r0', CMD_ID)
    t.write_core_register('r1', PTR)
    t.write_core_register('r2', 4)
    t.write_core_register('lr', TRAP | 1)     # thumb return
    t.write_core_register('pc', HANDLER)
    t.write_core_register('xpsr', 0x01000000) # Thumb bit set
    t.resume()

    for _ in range(400):                      # wait up to ~4 s for the call to return
        if t.get_state() == Target.State.HALTED:
            break
        time.sleep(0.01)
    r0 = t.read_core_register('r0')
    pc = t.read_core_register('pc')
    print(f"  handler returned r0=0x{r0:08X}  (1 = queued OK)   trap pc=0x{pc:08X}")

    t.remove_breakpoint(TRAP)
    for r, v in saved.items():
        t.write_core_register(r, v)           # restore the interrupted task's context
    t.resume()
    print("  firmware resumed; waiting 3 s for inverter to act + BMS to re-report ...")
    time.sleep(3.0)

    t.halt()
    after = ring_count(t)
    print(f"  alarm-ring fault count AFTER  : {after}")
    if after < before:
        print("  >>> FAULT COUNT DROPPED - looks like it worked! Re-dump 0x10006810 to confirm. <<<")
    elif r0 != 1:
        print("  NOTE: handler did not return 1 - command was rejected (check update flag / args).")
    else:
        print("  No change yet. Try DATA=10, or CMD='force'. If still nothing, the inverter")
        print("  route doesn't clear it and we go to direct cell-BMS access.")
    t.resume()
finally:
    session.close()
print("== done ==")
