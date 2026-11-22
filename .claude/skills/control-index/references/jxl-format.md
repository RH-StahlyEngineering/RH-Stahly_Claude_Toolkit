# JXL format findings (control-index #4)

- JobXML (Trimble Access 25.x, schema 6.3). Root `JOBFile` attr `TimeStamp` = job date.
- Two point sections: `FieldBook/PointRecord` (raw, incl. `Deleted`, stakeout/check shots, repeats) and
  `Reductions/Point` (one final per point). Index uses Reductions only.
- Reductions/Point: `Name`, `Code`, `SurveyMethod`, `Classification` (Normal/Averaged/Stakeout), `Grid/North,East,Elevation`
  always in METERS regardless of UnitsRecord (InternationalFeet display only), optional `WGS84/Latitude,Longitude,Height`.
- Measured GNSS points carry WGS84 (306/306 in MRC). Keyed-in points are grid only (7/15 in UV job) -> project.
- Coordinate system: several `ProjectionRecord`s; the LAST one with Type != NotSet is active (first is a default).
  Seen: Lambert1Parallel (CentralLatitude/Longitude, FalseNorthing/Easting, Scale). Scale already folds in ground
  scale for low-distortion systems (RMCRS Milk River k=1.000145), so projected locators need no separate factor.
  `CoordinateSystemRecord` (last non-empty SystemName): SystemName=RMCRS, ZoneName=MILK RIVER, DatumName.
  DatumRecord: NAD83(2011), EPSG 6318. NAD83 vs WGS84 (~1 m) ignored at 10 m locator.
- Code convention: `CODE [CODE..] /description` (sometimes no space: `CP/2 INCH MDT AC`). Split on first '/'.
  Checks look like `CP60 CHECK` or `CHK` (no slash) -> kind other. Base stations `PRS<digits>` with empty code.
- Real condition text seen: `FND /1/2 IN. REBAR BENT OBS. VP`.
- Job number from path: `\stahly\PROJECTS\2071-Toole County\-07D26_...` -> 2071-07D26;
  `\Stahly\Archives\PROJECTS (L)\A2423-...\-00519-...` -> 2423-00519 (regex `A?(\d{4})-...\-([0-9A-Za-z]{5})`).
- Not handled yet: TransverseMercator/Lambert2Parallel param names guessed (NorthParallel/SouthParallel) - verify on a
  real file; other projection types and grid-only points with no projection are silently skipped (should be reported).
- Sibling `.job` (binary) sits next to every .jxl; `<name> Files/` folder holds photos.
