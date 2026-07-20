# .nav (NovAtel binary) and RINEX header formats

`scripts/phoenix_lib.py` implements everything here — read this only if you need to extend or debug it.

## Phoenix `.nav` = NovAtel OEM binary log

Real-time GNSS/INS solution written by the SpatialExplorer rover. Two record framings:

- **Long header** — sync `AA 44 12`; `header_len`@byte 3 (u8); `msg_id`@4 (u16 LE); `msg_len`@8 (u16);
  `gps_week`@14 (u16); `gps_ms`@16 (u32, ms into week). Data starts at `i + header_len`.
  Total record = `header_len + msg_len + 4` (trailing CRC). Walk by total length.
- **Short header** — sync `AA 44 13`; `msg_len`@3 (u8); `msg_id`@4 (u16); `week`@6 (u16); `ms`@8 (u32);
  data@12. Total = `12 + msg_len + 4`.

**Position fields (little-endian doubles, degrees):**
- BESTPOS(42) / BESTGNSSPOS(1429) / PSRPOS(47,423): `lat`@data+8, `lon`@data+16, `hgt`@data+24
- INSPVA(507) / INSPVAS(508) / INSPVAX(1465): `lat`@data+12, `lon`@data+20, `hgt`@data+28

Collect all position epochs, keep those inside a Montana bounding box (rejects no-fix `0,0` and
garbage), sort by GPS time. A session with **zero in-box epochs** had no sky fix — treat it as a
bench test, not a valid acquisition.

**GPS time → UTC:** `datetime(1980,1,6) + (week*604800 + ms/1000) − 18` leap seconds.
The trajectory bbox/centroid = the scan footprint; consecutive-epoch distance/Δt = ground speed.

## Base-station RINEX

Read the **header only** — stop at `END OF HEADER`. Never open the obs body (can be >600 MB).
Fields used (label is columns 61+, value is columns 1–60):
- `APPROX POSITION XYZ` — ECEF metres → geodetic via `ecef2geo`. Autonomous (~1–2 m); if `|X| < 1e5`
  it's a zero/placeholder position → unusable, skip.
- `TIME OF FIRST OBS` / `TIME OF LAST OBS` — `YYYY MM DD hh mm ss.sss SYS`. These are **GPS time**
  (labelled GPS). Convert to seconds since the GPS epoch and compare directly to `.nav` GPS times.
- `MARKER NAME`, `REC # / TYPE / VERS`, `ANT # / TYPE` — identity/QA.

RINEX obs filenames: `NAME + DOY(3) + session(1) + . + YY + 'o'` (e.g. `.26o` = 2026 obs). Companion
nav files `.YYn/.YYg/.YYl/.YYc` (GPS/GLONASS/Galileo/BeiDou broadcast eph) travel with the obs file.
