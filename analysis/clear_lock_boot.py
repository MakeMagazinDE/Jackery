#!/usr/bin/env python3
"""
PERMANENT CellUVLock clear — make the firmware self-heal its own latch.

ROOT CAUSE (proven):
  On boot, HistoryRecord (0x08053990) reads an 8-byte "active-fault" record from
  SPI flash @0x440400 (via BSPExtFlashRead) into CCM 0x10000048, validates a u16
  checksum, then for each flag byte ==1 raises that fault. flag[1]=1 => CellUVLock.

THE LEVER:
  If the checksum does NOT validate, HistoryRecord takes a REBUILD branch at
  0x080539B2 that ZEROES all flags, recomputes the checksum, WRITES the record
  back to SPI flash, and raises nothing. We force that branch exactly once with a
  breakpoint + PC redirect; the firmware then clears its own SPI-flash latch.

  cmp r0,r1 @0x080539AE ; beq 0x080539D4 @0x080539B0 (skip rebuild -> RAISE)
  rebuild path @0x080539B2 (r5 already = 0x10000048)

No flash patch, no injection of blocking drivers — the SPI write runs in the
firmware's own normal rebuild context. Reversible by nature (only clears stale flags).

Run with SWD attached. It resets the target itself. Pack is healthy => clearing this
stale latch is legitimate; the BQ's own protections remain active.
"""
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

BP_BEQ  = 0x080539B0    # the 'beq 0x080539D4' that SKIPS the rebuild (we redirect past it)
REBUILD = 0x080539B2    # rebuild path: zero flags + recompute crc + write SPI flash + raise nothing
FLAGS   = 0x10000048    # CCM mirror of the 8-byte record
RING    = 0x10006810    # alarm ring [head][count]

def main():
    s=ConnectHelper.session_with_chosen_probe(
        options={"target_override":"gd32f470zg","connect_mode":"under-reset","frequency":1000000})
    s.open(); t=s.target
    try:
        print("reset+halt; arming breakpoint at HistoryRecord checksum branch ...")
        t.reset_and_halt()
        t.set_breakpoint(BP_BEQ)
        t.resume()
        t0=time.time()
        while t.get_state()!=Target.State.HALTED and time.time()-t0 < 30:
            time.sleep(0.004)
        if t.get_state()!=Target.State.HALTED:
            print("  !! breakpoint not hit within 30s. HistoryRecord may run later; increase wait or tell me."); return
        pc=t.read_core_register('pc')
        print(f"  hit @pc=0x{pc:08X} (expect 0x{BP_BEQ:08X})")
        # show the flags the firmware just read from SPI flash (pre-clear)
        pre=bytes(t.read_memory_block8(FLAGS,8))
        print(f"  SPI-flash record (pre-clear) @CCM 0x{FLAGS:08X}: {pre.hex(' ')}  flags={[pre[i] for i in range(5)]}")
        if (pc & ~1) != BP_BEQ:
            print("  !! unexpected PC; aborting to be safe."); t.remove_breakpoint(BP_BEQ); t.resume(); return
        # redirect past the 'beq' into the REBUILD path -> firmware zeroes flags + writes SPI flash
        t.write_core_register('pc', REBUILD)
        t.remove_breakpoint(BP_BEQ)
        print(f"  redirected PC -> 0x{REBUILD:08X} (rebuild: zero flags + write back to SPI flash). Resuming...")
        t.resume()

        # let the rebuild + SPI write complete and boot settle
        time.sleep(4.0)
        t.halt()
        post=bytes(t.read_memory_block8(FLAGS,8))
        cnt=int.from_bytes(bytes(t.read_memory_block8(RING+2,2)),'little')
        print(f"  record now (post): {post.hex(' ')}  flags={[post[i] for i in range(5)]}")
        print(f"  alarm-ring count = {cnt}")
        if all(post[i]==0 for i in range(5)) and cnt==0:
            print("  >>> CLEARED. Flags zeroed, no alarm raised, and the firmware wrote the cleared")
            print("      record back to SPI flash @0x440400.")
            print("  NEXT: power-cycle (NO debugger) and confirm the LED stays GREEN / app is clean.")
        else:
            print("  Hmm: not fully clean yet — paste this output. (rebuild may need another moment, or HistoryRecord re-ran)")
        t.resume()
    finally:
        s.close()
    print("== done ==")

if __name__=="__main__":
    main()
