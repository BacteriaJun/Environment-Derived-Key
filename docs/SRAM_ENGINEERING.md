# MCP7940N laboratory engineering package

0.2.0a0 includes a real-register **host-side writer**, an injectable register bus, a Linux i2c-dev transport, synthetic tests, record specification and a bench plan. It is not a flashed MCU firmware image, manufactured PCB, measured retention device, authenticated token or complete real-PIN system.

## Primary references and implementation boundary

- [Microchip DS20005010J](https://ww1.microchip.com/downloads/en/DeviceDoc/MCP7940N-Battery-Backed-I2C-RTCC-with-SRAM-20005010J.pdf), particularly register map, backup supply and on-board memory sections.
- [Linux i2c-dev interface](https://www.kernel.org/doc/html/latest/i2c/dev-interface.html) for adapter discovery, address ownership, capabilities and combined transfers.

The chip has a fixed 7-bit address 0x6f, SRAM at 0x20–0x5f, and RTCWKDAY at 0x03 with VBATEN/PWRFAIL flags. SRAM is not initialized by power-on reset. Access requires main power; backup retention requires a present and enabled backup supply. See the datasheet for electrical corners. The program verifies flags, not actual backup voltage or device identity; MCP7940N has no authenticated identity check in this implementation. A different chip at the same address can be damaged by an incorrect board mapping.

The writer accesses SRAM plus an explicitly requested backup-enable read/modify/write. It refuses that write if a power failure is already recorded. Every RTCWKDAY write physically clears PWRFAIL, so a concurrent power event during the read/modify/write can be lost; stable bench power and electrical fault testing remain requirements. Reading flags cannot establish a guaranteed safe supply. The probe also reports oscillator status; accurate power-fail time stamps need a running oscillator, which the writer does not start. The writer does not configure the time, write flash/EEPROM, configure GPIO, scan a bus, or submit a PIN. Transfers crossing the RTC/SRAM block boundary are rejected because the chip wraps addresses within each block.

## Record layout: exactly 64 bytes

| Offset | Length | Content |
|---|---:|---|
| 0 | 4 | `EDK1` magic |
| 4 | 1 | Record version 1 |
| 5 | 1 | Share coordinate |
| 6 | 1 | Threshold configuration |
| 7 | 1 | Reserved, zero |
| 8 | 16 | Public generation ID |
| 24 | 32 | Secret share payload |
| 56 | 4 | CRC32 of bytes 0..55, big-endian |
| 60 | 4 | `DONE` commit tag |

There is no spare capacity for a second image or a conventional authentication tag. CRC is forgeable and is **not a MAC**. All 512 single-bit image errors are rejected in synthetic tests, but this is not resistance to chosen corruption, physical extraction or bus interception. A security-grade record needs a reviewed integrity/reader/key-storage design, potentially larger SRAM. This format is for laboratory lifecycle tests.

Programming clears and verifies the tag, writes/verifies the first 60 bytes in bounded chunks, then commits and verifies the entire record. A valid existing share is never overwritten, even with `--initialize-unrecognized`. A nonblank unrecognized image needs that explicit initialization option because random power-on SRAM is not a reliable blank indication. Partial writes are not retried or rolled back. Failed six-node provisioning may leave a committed subset; the program does not create a persistent master-secret recovery file.

The prefix model and driver fault-injection tests cover ordered interruption, not arbitrary hardware failure or concurrency. There is no distributed atomic refresh protocol. See [formal assumptions](FORMAL_SPEC.md).

## Candidate single-node power architecture

```text
External regulated input -> protection/current limit -> main VCC
                       \-> controlled reservoir charger -> local reservoir -> VBAT
Reader -> guarded I2C + common reference -> MCP7940N SRAM
Separate voltage monitoring and isolation prevent reader/pull-up back-powering
```

Every node needs its own reservoir and fault domain. The reader must not unintentionally extend retention through I²C protection paths. A capacitor, battery, charger and PCB cannot be chosen solely from the chip's typical standby current. No unverified wiring diagram or KiCad production file is shipped.

For the first bench board, prefer a current-limited laboratory supply and characterized reservoir. A rechargeable cell needs a compatible charger/protection design; never treat a primary coin cell as rechargeable. The vehicle node needs separate temperature/abuse validation and components rated for the actual enclosure conditions.

## Preliminary BOM and cost scope

Sources inspected 2026-10-22; displayed catalog prices may be cached. USD, one-off quantities, excluding tax/shipping/assembly. No purchase, stock reservation or supplier quote was obtained.

| Group | Candidate / source | Unit basis | Six-node basis |
|---|---|---:|---:|
| SRAM/RTC | MCP7940N-I/SN, [Mouser catalog](https://www.mouser.com/en/ProductDetail/Microchip-Technology/MCP7940N-I-SN?qs=o%2FJGMiCJeCOTsMP4nrR5Uw%3D%3D) | displayed USD 0.85 in indexed catalog; direct page access failed | USD 5.10 arithmetic only |
| Bench reservoir | Eaton KR-5R5V105-R, [DigiKey](https://www.digikey.com/en/products/detail/eaton-electronics-division/KR-5R5V105-R/1556244) | approximately USD 6.62 displayed reference; recheck before order | USD 39.72 arithmetic only |
| Passives/connectors | crystal/load parts, decoupling, pull-ups, connector | USD 1–4 planning allowance, unquoted | USD 6–24 allowance |
| Charge/isolation/protection | topology and actual devices still unselected | USD 3–10 allowance, unquoted | USD 18–60 allowance |
| PCB/enclosure | laboratory quantities | USD 4–15 allowance, unquoted | USD 24–90 allowance |
| Reader and adapters | Linux host/separate adapters; actual platform unselected | USD 30–120 shared allowance, unquoted | same shared allowance |

Illustrative total is roughly USD 123–339 including the shared reader allowance. It is a planning range, not a costed production BOM. Missing automotive qualification, instrumentation, assembly, fixtures, labor, shipping and security hardware can dominate it.

The [Eaton KR datasheet](https://www.eaton.com/content/dam/eaton/products/electronic-components/resources/data-sheet/eaton-kr-supercapacitors-coin-cells-data-sheet.pdf) lists a 1 F part and temperature/voltage derating limits. This bench candidate is not a qualified vehicle recommendation. The formerly considered Panasonic EEC-S5R5V105 is listed obsolete by its distributor and is not selected.

## Retention estimate: equations, not a promised duration

Under a constant-current approximation:

```text
t ≈ C (Vstart - Vmin) / (Idevice + Ileakage + Iboard).
```

For an entirely illustrative C=1 F and usable drop 1.7 V, total drain 1 µA gives about 19.7 days, 10 µA about 1.97 days, and 100 µA about 4.72 hours. These are dimensional estimates, not measurements of the candidate capacitor. Leakage, voltage dependence, temperature, tolerances, aging, reader backfeed and the actual retention boundary invalidate a simple constant-current extrapolation. Crossing a supply limit does not prove that SRAM data is irrecoverably erased.

## Linux host deployment and device replacement

Adapters must support plain combined I²C transactions and be explicitly identified as `/dev/i2c-N`. The implementation checks a character device, takes an advisory process lock, uses I2C_SLAVE without FORCE and checks I2C_FUNC_I2C. Advisory locks do not exclude unrelated programs that ignore them. Do not run a kernel RTC driver or another master concurrently on the same chip.

The current six-node CLI requires **six distinct adapter identities**, one intended chip per adapter. It does not implement an address multiplexer or GPIO switching. Same-address chips cannot just be connected together on one bus. Distinct adapters also do not establish geographic or supply independence.

Read-only lab status:

```sh
edk-lab hardware-probe --bus /dev/i2c-1 --laboratory-hardware
```

Provision six confirmed laboratory devices (adapter numbers below are placeholders):

```sh
edk-lab hardware-provision --buses /dev/i2c-1 /dev/i2c-2 /dev/i2c-3 /dev/i2c-4 /dev/i2c-5 /dev/i2c-6 --enable-backup --laboratory-hardware
```

Use `--initialize-unrecognized` only after inspecting the intended empty/replacement laboratory chip. Successful provisioning writes KV shares only; it does not enroll a real environmental key or PIN. KV/slots are not printed or stored on disk by this program. Python memory, swap and host compromise remain exposure paths.

For an original share confirmed destroyed beyond recovery, read three healthy same-generation nodes and write a new target at the missing coordinate:

```sh
edk-lab hardware-repair --sources /dev/i2c-1 /dev/i2c-2 /dev/i2c-3 --target /dev/i2c-7 --index 5 --enable-backup --laboratory-hardware
```

Do not use this to respond to theft, loss or suspected copying. Old copies remain valid; authenticated coordinated refresh is still absent. The program cannot verify the investigator's assertion that a share was physically destroyed. It also intentionally stops on a recorded power-failure flag rather than automatically clearing forensic status; a bench operator must investigate before further use.

## Bench acceptance record still required

1. Confirm exact part/package, pinout, voltage levels and physical adapter identity before connecting.
2. On one nonvaluable testboard measure I²C waveforms and compare all readback bytes; record software/board revisions.
3. Sweep main/backup power, inject interruptions at each programming stage, and verify no undetected wrong record under the stated fault model.
4. Measure whole-board drain and retention on 10+ independent units with temperature and aging variation; inspect back-power paths.
5. Compare ordinary read failure with forensic recovery after loss. A failed I²C read is not a zeroization result.
6. Test simultaneous home/vehicle/reader faults and replacement interruptions on six independent supplies.
7. Perform authenticated-reader and tamper review before real secrets or hardware PIN use.

Every item above is **pending physical execution**. This package does not fabricate those measurements or declare the full system deployable for valuable secrets.
