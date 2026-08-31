#!/usr/bin/env python3
"""
Second watchpoint - on the DEVICE FAULT WORD (the authoritative CellUVLock bit),
not the alarm-ring display. This catches the code that DECIDES the UV-lock
(sets [dev+0x56] = 0x00000002), which is the precise instruction to patch.

dev struct has been stable at 0x2002F528 on every cold boot -> fault word @ 0x2002F57E.
If your cold-boot dump shows a different dev ptr ([0x10006CC4]), edit DEV below.

Run with SWD attached; it resets the target itself. Paste the fire block.
"""
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

DEV   = 0x2002F528
WATCH = DEV + 0x56          # 0x2002F57E - group3/word0 fault word (CellUVLock = bit1)

def walk_stack(t, sp, depth=0xC0):
    out=[]
    for i in range(0, depth, 4):
        try: w=t.read_memory(sp+i)
        except Exception: break
        if 0x08008000 <= w < 0x08100000 and (w & 1):
            out.append((i, w & ~1))
    return out

def main():
    s=ConnectHelper.session_with_chosen_probe(
        options={"target_override":"gd32f470zg","connect_mode":"under-reset","frequency":1000000})
    s.open(); t=s.target
    try:
        print(f"reset+halt; arming WRITE watchpoint on fault word @0x{WATCH:08X} ...")
        t.reset_and_halt()
        try:
            t.set_watchpoint(WATCH, 1, Target.WatchpointType.WRITE)   # byte watch (addr not 4-aligned)
        except Exception as e:
            print(f"  set_watchpoint failed: {e}"); return
        fired=0
        while fired < 60:
            t.resume()
            t0=time.time()
            while t.get_state()!=Target.State.HALTED and time.time()-t0 < 180:
                time.sleep(0.004)
            if t.get_state()!=Target.State.HALTED:
                print(f"  no further fault-word write within 180s after {fired} fire(s).")
                print("  (Lock not re-raised in window. If the address is wrong, re-dump [0x10006CC4] and tell me.)")
                break
            fired+=1
            val=int.from_bytes(bytes(t.read_memory_block8(WATCH,4)),'little')   # byte-read (unaligned)
            pc=t.read_core_register('pc'); lr=t.read_core_register('lr'); sp=t.read_core_register('sp')
            print(f"  fire #{fired}: [0x{WATCH:08X}]=0x{val:08X} pc=0x{pc:08X} lr=0x{lr:08X}")
            if (val>>1)&1:    # bit1 (CellUVLock) just got set
                print("\n  >>> CellUVLock bit SET in the fault word. Decision call chain:")
                print(f"      PC = 0x{pc:08X}")
                print(f"      LR = 0x{(lr&~1):08X}")
                for off,a in walk_stack(t, sp):
                    print(f"      sp+0x{off:02X} -> 0x{a:08X}")
                break
        try: t.remove_watchpoint(WATCH)
        except Exception: pass
        try: t.resume()
        except Exception: pass
    finally:
        s.close()
    print("== done == paste the PC/LR/stack from the bit-set fire.")

if __name__=="__main__":
    main()
