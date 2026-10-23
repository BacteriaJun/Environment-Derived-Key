# Hardware exploratory specification (no schematic released yet)

## Candidate: Microchip MCP7940N

Official product page: https://www.microchip.com/en-us/product/MCP7940N

Documented properties include **64-byte battery-backed SRAM**, I²C interface, VCC automatic switchover to VBAT, 1.8–5.5 V operation and 1.3–5.5 V backup supply. Verify device ordering code, current draw, leakage, exact retention corner conditions and timing in the datasheet before PCB work.

**NOT a secure element**: unprotected I²C can leak an entire plaintext share to a physical attacker. The chip is a laboratory candidate for observing retention / loss, not certified storage.

## Single-node proposed block diagram

```text
    USB-C 5V input (power only)
                 |
    charging/protection/power-path
                 |
          local storage element
       (supercapacitor or cell)
                 |
     independently backed VBAT rail
                 |
   MCP7940N SRAM (share + generation)
                 |
          I2C gated interface
                 |
      trusted reader (later phase)
```

Every node MUST have its own storage element and its own fault domain. Five share nodes supplied by one backup cell do not implement gradual independent loss. S5 may use a dedicated always-powered supply **but is not literally immortal**.

### Physical placement candidate

- S1: on person; mobile temperature and physical-loss risks.
- S2: home drawer.
- S3: consider a second physical location, NOT home wardrobe if using a 3-of-6 threshold with home S2+S5.
- S4: vehicle; extreme heat/cold, battery safety, vehicle theft; requires qualified power components.
- S5: home fixed mount with primary power and independent failsafe design.
- S6: office drawer; must be **a distinct sixth share**, not a copy of S2 unless intentionally designing a 3-of-5 plus replica scheme.

### Storage capacity check

A 256-bit Shamir share occupies 32 bytes. Public share index (1 B) + 16 B generation ID leaves about 15 B within a 64 B SRAM, before integrity metadata. **Two simultaneous 32 B copies plus metadata exceed this capacity**; atomic firmware transaction or proactive refresh requires a different storage plan or larger backed SRAM.

The stage-1 Python model also carries a public threshold integer. A hypothetical one-byte encoding would leave 14 B rather than 15 B; no firmware/wire encoding has been selected. Python dataclass layout is not an SRAM storage layout. No retention time, BOM quote, circuit or supply-switching behavior was validated by the software review.

### Measurements needed before selecting battery

- Whole-node standby current at worst-case temperature, not chip typical alone.
- Supercapacitor **leakage** after stabilization and self-discharge across temperature.
- Charge-path, supply-switchover and brownout behavior; must never falsely output the wrong secret.
- Actual retention time distribution: 10+ samples, varied supply, cycles and temperatures.
- Post-loss recoverability under a defined forensic attacker; do not assume instantaneous zeroization.
- Reset, read, charge and share replacement operations must be verified not to write secrets to EEPROM/Flash, firmware logs or host storage.

## Prototype BOM categories (quantity 6)

| Component group | Candidate | Evidence status |
|---|---|---|
| Battery-backed SRAM | MCP7940N x6 | Official specification confirmed |
| Storage element | Supercapacitor or approved rechargeable backup cell x6 | **Not selected; duration unverified** |
| Power path | USB-C, protections and charging circuitry | **To be engineered** |
| Mechanical packaging | Small PCB, enclosure, contact connector | **To be engineered** |
| Reader | Trusted MCU-based reader with guarded I²C | **To be engineered** |

**No released wiring schematic or estimated full-device security certification.** A cheap SRAM price is not the same as a cheap secure node.

## v0.2 host implementation

An experimental Python/Linux host writer and a full 64-byte record are now implemented, with synthetic register-bus and interruption tests. A prototype BOM budget, official references, power architecture and bench instructions are in [SRAM_ENGINEERING.md](SRAM_ENGINEERING.md). This supersedes the stage-1 hypothetical byte layout above; the current record uses all 64 bytes and adds a CRC/commit tag without authentication. No target-MCU firmware binary, circuit, real retention result or security certification is delivered.
