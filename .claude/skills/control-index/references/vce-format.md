# VCE format findings (control-index #6) -- outcome: point extraction works (no fallback needed)

Parser: .claude/skills/control-index/scripts/vce.py (`parse_vce`). Fixture: tests/fixtures/vce_tree/.../courthouse.vce
(real MILK RIVER .vce trimmed to 22 objects / 38 KB; points 60, 204).

## Container
- ZIP: ObjectData (binary), FieldNames, ComponentGuids, FileStatus, _rels, [Content_Types].xml.
- FieldNames: u32 count, then [u8 len][name][u32 id]. **Ids differ per file** (m_PointID = 0x50f-ish in 2026 file, 1069 in 2019 file)
  -> always resolve by name. Object type ids also differ per file -> detect objects by the field names they carry.
- ObjectData: "SG" then objects `{<` u32 oid, u32 ver, u32 type, u32 nfields, fields, `>}` u32 oid.
  Field: `MF` u16 type, u32 field-id, value. Types: 1 double; 2/3/5 u32; 4 string (7-bit varint len, latin1);
  7 double array (u32 1, u32 n, n doubles); 12 u32 array (u32 1, u32 n, ...); 14/16 nested sub-objects
  (`bs` u32 ... `cq` closers); 6 byte; others skipped by resyncing on next `MF` (heuristic, worked on both samples).

## Points
- Point entity = object with m_PointID + m_LayerSerialC. Coordinates: repeated (m_CoordSystem, components);
  each component has m_Position (double array). m_CoordSystem 0 = geodetic (lat, lon radians, + height comp),
  2 = grid (North, East metres, + elevation comp), 1 = seen once (global/ECEF-ish lat/lon).
  MRC 2026: 306 geodetic-only, 169 grid-only (keyed/TS). Shelby 2019: 1306 geodetic, 1234 grid-only.
- Codes are NOT on the point (m_FeatureCodeHosts empty). Feature-code objects (m_FeatureCodeSchema + m_Code,
  full "CODE /desc" string) are referenced from raw-data records (segments starting RawDataBase.Schema;
  KeyString ...Obs.RTKVector / TotalStation / RawDataCoordinate / GPSReference / Simple / Note). A record's
  `Dependencies` u32 array lists its point oid, its code oid, and base/backsight point oids; its own point =
  m_PointID string. Several objects hold several records.
- Rule used: per point, own records only, latest m_TimeStampLocal wins, non-check (not CHK/CHECK) preferred.
  Edits in TBC are reflected (206: jxl 1/2 IN, vce 5/8 IN, with a Misc.Note "Old values ...").
  Shelby pt 60: RTK 2019-04 "FND 2\" MDT ALUMC 2019", later keyed RawDataCoordinate 2019-10 "CP60/MDT CAP" -> we pick latter.
- Verified: 204 -> 48.5046,-111.8603 (jxl 48.504608,-111.860324); grid-only 60 projected -> 48.5051,-111.8551 (CP60 truth).
  474/475 MRC points get a code. Dates = latest own observation (placeholders 01/01/0001 ignored).

## Coordinate system (CSIB) -- notes for #7
- Field `CSIB`: string of space-separated decimal byte values = Trimble CSIB blob. "TNL CSIB" + 8 bytes, then
  NUL-separated names: system, [junk], zone, "Default"; later datum ("NAD83(2011)", "NAD 1983 (Conus)"), geoid.
- Projection block: `00 80 04` + zone name (empty in Shelby) + `00 00` + doubles:
  lat0(rad), lon0(rad), FalseNorthing, FalseEasting, k0, X.
  - MRC (RMCRS MILK RIVER, LCC 1SP): 48.5deg, -110.98deg, FN 200000, FE 150000, k0 1.000145, X 1.0.
  - Shelby (SP Montana 2500 "Converted to Ground"): 44.25, -109.5, FN 0, FE 600000, k0 1.0, **X 1.000420952**
    = the project/ground scale factor. Followed by a project origin (lat 48.50 rad-ish, lon, h ~985 m) and
    `02` + two doubles 49deg/45deg = the LCC 2SP standard parallels.
  - So: low-distortion systems fold ground into k0 (X=1); ground-scaled SP jobs carry the scale in X plus an
    origin. Shelby grid coords matched plain SP grid within ~2 m at 2 points (scaling origin near project), so
    the scale must be applied about that origin; not yet verified exactly.
- Other per-project scale fields (m_CombinedScaleFactor, m_ScaleFactor, FixedTerrestrialHorizontalScaleFactor)
  are 1.0 in both files -> not useful; use the CSIB.
- Parser currently only builds a projection for 1SP ("04"+named zone). Shelby-style 2SP/ground jobs: geodetic
  points indexed, grid-only points silently skipped (1234 in Shelby). TODO (#7 or follow-up): parse the "02"
  parallels block + ground scale/origin, and report skipped points.
