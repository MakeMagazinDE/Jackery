#!/usr/bin/env python3
"""
Dump the external I2C EEPROM THROUGH the GD32, by injecting the firmware's own
BSPEEPROMRead(addr, buf, len) over SWD. No chip clip, no desolder.

WHY this chip: the EEPROM (BSPEEPROM.c, bit-bang/BSPI2C) is the firmware's
structured, checksummed, boot-loaded record store, written by the alarm subsystem.
It is the prime suspect for the persistent CellUVLock latch (the SPI 'extflash' is
OTA firmware staging, not small fault records).

Pattern is identical to the WORKING inject_clearlock.py: attach, halt, set a
return-trap breakpoint at 0x08000000, give the call a clean scratch stack + buffer
carved from BELOW the interrupted task's SP, resume to run the call, halt on return,
read the buffer back. Registers are fully restored at the end and the task resumed.

Run with the unit ON + SWD probe attached. Recoverable by power-cycle if anything hangs.
"""
import sys, time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

# ---- firmware entry points (resolved from dump_navi.bin symbol table) ----
BSP_EEPROM_READ = 0x08011840    # int BSPEEPROMRead(uint32 addr, void *buf, uint32 len) -> bytes read
TRAP            = 0x08000000    # bx lr lands here (lr = TRAP|1); never executed normally

# ---- what to dump ----
START   = 0x0000
END     = 0x2000                # covers up to a 24C64 (8 KB); shrink if it's a 24C32 (0x1000)
CHUNK   = 128                   # bytes per injected call (small -> small scratch/stack footprint)
OUTFILE = "eeprom_navi.bin"
TIMEOUT_S = 3.0                 # per-call wait (BSPEEPROMRead has internal ~5s I2C timeout; calls are fast when bus is free)

def main():
    session = ConnectHelper.session_with_chosen_probe(
        options={"target_override": "gd32f470zg", "connect_mode": "attach", "frequency": 1000000})
    session.open()
    t = session.target
    try:
        t.halt()

        # sanity-check the entry has a real Thumb prologue (PUSH {..,lr})
        hw = int.from_bytes(bytes(t.read_memory_block8(BSP_EEPROM_READ, 2)), "little")
        if (hw & 0xFF00) != 0xB500 and hw != 0xE92D:
            print(f"  !! 0x{BSP_EEPROM_READ:08X} first halfword=0x{hw:04X} is not a PUSH prologue — aborting.")
            return

        saved = {r: t.read_core_register(r) for r in
                 ('r0','r1','r2','r3','r12','sp','lr','pc','xpsr')}
        sp = saved['sp']
        # carve scratch from BELOW the interrupted task's SP (free stack region).
        new_sp = (sp - 0x40) & ~7           # injected call's stack top (grows DOWN from here)
        buf    = (sp - 0x300) & ~7          # read buffer, well below where the small frame reaches
        print(f"task sp=0x{sp:08X}  -> inj stack=0x{new_sp:08X}  buf=0x{buf:08X}  (dump 0x{START:04X}..0x{END:04X}, chunk {CHUNK})")

        t.set_breakpoint(TRAP)
        image = bytearray()
        ok = True
        addr = START
        while addr < END:
            n = min(CHUNK, END - addr)
            # set up the call
            t.write_core_register('sp', new_sp)
            t.write_core_register('r0', addr)
            t.write_core_register('r1', buf)
            t.write_core_register('r2', n)
            t.write_core_register('lr', TRAP | 1)
            t.write_core_register('pc', BSP_EEPROM_READ)
            t.write_core_register('xpsr', 0x01000000)
            t.resume()

            deadline = time.time() + TIMEOUT_S
            while t.get_state() != Target.State.HALTED and time.time() < deadline:
                time.sleep(0.005)
            if t.get_state() != Target.State.HALTED:
                print(f"  !! call at addr 0x{addr:04X} did not return within {TIMEOUT_S}s (mutex/bus stall). Halting + stopping.")
                t.halt(); ok = False; break

            ret = t.read_core_register('r0')
            pc  = t.read_core_register('pc')
            if (pc & ~1) != TRAP:
                print(f"  !! addr 0x{addr:04X}: trapped at unexpected pc=0x{pc:08X} — stopping.")
                ok = False; break
            data = bytes(t.read_memory_block8(buf, n))
            image += data
            if ret != n:
                print(f"  ~ addr 0x{addr:04X}: BSPEEPROMRead returned {ret} (requested {n}) — possible end-of-device/short read.")
            if (addr // CHUNK) % 8 == 0:
                print(f"    ..0x{addr:04X} ret={ret} {data[:8].hex()}")
            addr += n

        t.remove_breakpoint(TRAP)
        for r, v in saved.items():
            t.write_core_register(r, v)     # restore the interrupted task exactly
        t.resume()
        print("firmware resumed.")

        with open(OUTFILE, "wb") as f:
            f.write(image)
        print(f"wrote {len(image)} bytes -> {OUTFILE}  (complete={ok})")

        scan(image, START)
    finally:
        session.close()
    print("== done ==")

def scan(image, base):
    print("\n=== scan for the CellUVLock record ===")
    needles = {
        b"bms1":               "serial prefix 'bms1'",
        b"HA2A15100146HH3":    "device serial",
        b"\x05\x00":           "fault code 0x0005 (CellUVLock, LE u16)",
        b"\x02\x00\x00\x00":   "fault word 0x00000002 (group3/word0 bit1)",
    }
    for needle, desc in needles.items():
        i = image.find(needle); hits = 0
        while i != -1 and hits < 12:
            lo = max(0, i - 8); hi = min(len(image), i + 24)
            print(f"  EEPROM 0x{base+i:04X}  [{desc}]  ctx: {image[lo:hi].hex()}")
            hits += 1
            i = image.find(needle, i + 1)
        if hits == 0:
            print(f"  (none) {desc}")

if __name__ == "__main__":
    main()
