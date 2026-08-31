#!/usr/bin/env python3
"""
Catch the BOOT-TIME writer of CellUVLock with a hardware watchpoint.

Sets a WRITE watchpoint on the alarm-ring first-record 'code' field (CCM 0x10006814).
On a cold boot (under-reset) the firmware re-creates the CellUVLock alarm from its local
source; the watchpoint halts the CPU at the instant 0x0005 is written, and we dump the
PC + return-address chain so we can trace back to the loader (EEPROM read? BQ read? logic?).

Run with the unit's SWD attached. It resets the target itself.
After it halts on the 0x0005 write, paste the pc/lr/stack lines.
"""
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

WATCH = 0x10006814     # alarm ring slot0 'code' (u16); 0x0005 = CellUVLock
ALT   = 0x10006812     # ring 'count' (u16) - fallback target

def walk_stack(t, sp, depth=0xC0):
    outs=[]
    for i in range(0, depth, 4):
        try: w=t.read_memory(sp+i)
        except Exception: break
        if 0x08008000 <= w < 0x08100000 and (w & 1):   # app flash, thumb
            outs.append((i, w & ~1))
    return outs

def run(watch_addr):
    s=ConnectHelper.session_with_chosen_probe(
        options={"target_override":"gd32f470zg","connect_mode":"under-reset","frequency":1000000})
    s.open(); t=s.target
    try:
        print(f"reset+halt; arming WRITE watchpoint @0x{watch_addr:08X} ...")
        t.reset_and_halt()
        try:
            t.set_watchpoint(watch_addr, 4, Target.WatchpointType.WRITE)
        except Exception as e:
            print(f"  set_watchpoint failed: {e}")
            return False
        fired=0
        while fired < 40:
            t.resume()
            t0=time.time()
            while t.get_state()!=Target.State.HALTED and time.time()-t0 < 25:
                time.sleep(0.004)
            if t.get_state()!=Target.State.HALTED:
                print(f"  no watchpoint hit within 25s after {fired} fire(s).")
                print("  (If 0 fires: DWT may not see this region — rerun will try the count field.)")
                t.remove_watchpoint(watch_addr); return fired>0
            fired+=1
            val=t.read_memory(watch_addr)
            pc=t.read_core_register('pc'); lr=t.read_core_register('lr'); sp=t.read_core_register('sp')
            low=val & 0xFFFF
            print(f"  fire #{fired}: [0x{watch_addr:08X}]=0x{val:08X} (low=0x{low:04X}) pc=0x{pc:08X} lr=0x{lr:08X} sp=0x{sp:08X}")
            if low==0x0005:
                print("\n  >>> CellUVLock (0x0005) WRITTEN. Call chain (return addrs on stack):")
                print(f"      PC = 0x{pc:08X}")
                print(f"      LR = 0x{(lr&~1):08X}")
                for off,a in walk_stack(t, sp):
                    print(f"      sp+0x{off:02X} -> 0x{a:08X}")
                t.remove_watchpoint(watch_addr); t.resume()
                return True
        print("  hit fire cap without seeing 0x0005.")
        t.remove_watchpoint(watch_addr); t.resume()
        return True
    finally:
        s.close()

if __name__=="__main__":
    ok=run(WATCH)
    print("== done ==  paste the PC / LR / stack lines from the 0x0005 fire.")
