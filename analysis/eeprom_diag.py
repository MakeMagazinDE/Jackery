#!/usr/bin/env python3
"""
ONE injected BSPEEPROMRead call, maximum diagnostics. Figures out why the dump
returned 0 bytes. Reads-only. Power-cycle recovers if it stalls.
"""
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

BSP_EEPROM_READ = 0x08011840
TRAP            = 0x08000000
ADDR            = 0x0000
N               = 32
WAIT_S          = 7.0          # > the function's internal ~5s I2C timeout

s = ConnectHelper.session_with_chosen_probe(
    options={"target_override": "gd32f470zg", "connect_mode": "attach", "frequency": 1000000})
s.open(); t = s.target
try:
    t.halt()
    st = t.get_state()
    print(f"halted. state={st}")
    hw = int.from_bytes(bytes(t.read_memory_block8(BSP_EEPROM_READ,2)),"little")
    print(f"entry halfword=0x{hw:04X} ({'OK' if (hw&0xFF00)==0xB500 or hw==0xE92D else 'BAD'})")

    saved = {r: t.read_core_register(r) for r in ('r0','r1','r2','r3','r12','sp','lr','pc','xpsr')}
    print("saved task regs:", {k:hex(v) for k,v in saved.items()})
    sp = saved['sp']
    new_sp = (sp - 0x40) & ~7
    buf    = (sp - 0x300) & ~7
    print(f"new_sp=0x{new_sp:08X} buf=0x{buf:08X}")

    # poison the buffer so we can tell if it actually got written
    t.write_memory_block8(buf, b"\xAA"*N)
    pre = bytes(t.read_memory_block8(buf,N))
    print(f"buf BEFORE: {pre.hex()}")

    t.set_breakpoint(TRAP)
    t.write_core_register('sp', new_sp)
    t.write_core_register('r0', ADDR)
    t.write_core_register('r1', buf)
    t.write_core_register('r2', N)
    t.write_core_register('lr', TRAP|1)
    t.write_core_register('pc', BSP_EEPROM_READ)
    t.write_core_register('xpsr', 0x01000000)
    print(f"launching BSPEEPROMRead(0x{ADDR:04X}, 0x{buf:08X}, {N}) ...")
    t0=time.time(); t.resume()
    hit=False
    while time.time()-t0 < WAIT_S:
        if t.get_state()==Target.State.HALTED:
            hit=True; break
        time.sleep(0.01)
    dt=time.time()-t0
    if not hit:
        t.halt()
        pc=t.read_core_register('pc'); lr=t.read_core_register('lr'); spn=t.read_core_register('sp')
        print(f"  >>> STALLED after {dt:.2f}s. Did NOT return.")
        print(f"      stopped pc=0x{pc:08X}  lr=0x{lr:08X}  sp=0x{spn:08X}")
        print(f"      (pc tells us where it's stuck — likely a semaphore/mutex wait)")
    else:
        pc=t.read_core_register('pc'); r0=t.read_core_register('r0')
        print(f"  RETURNED after {dt:.3f}s.  trap pc=0x{pc:08X} (expect 0x{TRAP:08X})  r0(bytes read)={r0}")
        post=bytes(t.read_memory_block8(buf,N))
        print(f"  buf AFTER : {post.hex()}")
        print(f"  buf changed from 0xAA fill: {post!=pre}")

    t.remove_breakpoint(TRAP)
    for r,v in saved.items(): t.write_core_register(r,v)
    t.resume()
    print("task restored + resumed.")
finally:
    s.close()
print("== done ==")
