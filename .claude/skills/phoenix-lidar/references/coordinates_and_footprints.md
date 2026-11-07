# Coordinates, T04 naming, and the footprint model

## ECEF → geodetic
WGS84 (a=6378137, 1/f=298.257223563), iterative Bowring. In `phoenix_lib.ecef2geo`.

## Montana State Plane → WGS84
Survey control often arrives in **Montana State Plane NAD83, INTERNATIONAL feet (EPSG:2256; NAD83(2011) = 6515)** — a single
Lambert Conformal Conic (2SP) zone. Params: standard parallels 45° & 49°, origin 44.25°/−109.5°,
false easting 600000 m, false northing 0, ellipsoid GRS80. `phoenix_lib.mt_stateplane_to_wgs84`
does the inverse (feet → metres via the **international** foot 0.3048 by default; `foot=` overrides). Montana's legal State Plane foot is international — verified 2026-11-05 (SB 536 bridges): TBC control in ift reproduced the RINEX header APPROX POSITION to 0.00 m; read as US ft it was 1.3–1.5 m off. pyproj confirms 2256/6515 unit = foot (ift); vertical NAVD88 ift = **EPSG 8228** (6360 is ftUS). It matches RINEX-derived base
positions to ~2 m — good enough that mileage decisions don't change, but prefer surveyed control when
the user provides it. If a project is in another state, add its LCC params rather than reusing these.

## Custom LDPs — control does NOT always arrive in State Plane
A **Low Distortion Projection** (a.k.a. RMCRS) is a local grid with a scale factor chosen so grid
distance ≈ ground distance. It has **no EPSG code**, so it can't be selected from a code list
anywhere downstream — it must be entered from its parameters. Recognise one by a k₀ that isn't a
standard-zone value (e.g. 1.000191 rather than 0.9999) and a round false origin in *feet*.

Seen 2026-07-31 (MVM, Helena): Transverse Mercator, lat₀ 46.5, lon₀ −111.95, **k₀ 1.000191**,
FE 200000 / FN 100000 **international ft**, NAD83(2011) epoch 2010.00 on GRS80, GEOID18.

Two traps, both measured on that job:
- **Which foot.** International (0.3048) vs US survey (1200/3937) is 2 ppm — ~0.40 ft of
  horizontal at a 200,000 ft easting, and *proportional to the coordinate*, so it reads as a scale
  error. MT State Plane is **international ft** (earlier versions of this skill said US survey ft — wrong); MT LDPs are also commonly international ft. Never inherit it
  from the last project.
- **The false origin's unit.** A JXL stores `FalseEasting`/`FalseNorthing` in **metres**
  (60960 / 30480 = exactly 200000 / 100000 ift). Pairing those raw metre values with a foot `UNIT`
  in a WKT is a ~450,000 ft blunder — convert them.

When control arrives as a Trimble `.jxl`, the **`jxl-parser` skill** pulls projection, units,
geoid, and datum out of it directly. Note its `generate_wkt1()` has the false-origin unit bug above.

**Control CSV** is typically PNEZD: `point, northing, easting, elevation, description`. Base stations
are specific point numbers (the user tells you which, e.g. `1,2,5`). `analyze.py --control file.csv
--control-points 1,2,5` snaps each base RINEX to the nearest named control point (<0.2 mi) and labels
it `CP1/CP2/CP5`; obs files not on a named point are ignored. Building a PNEZD *from* a JXL: the
`<Grid>` `North`/`East`/`Elevation` values are in **metres regardless of the file's DisplaySettings**
— divide by the job's foot. Elevations there are **orthometric** (geoid applied), not ellipsoidal.

## Trimble T04 filenames
`[4-char receiver serial][3-digit day-of-year][1-char session].T04`. Decode gives the acquisition
**date** (DOY→date) and lets you pair base files to survey days before you even convert to RINEX.
`phoenix_lib.decode_t04`. Note: on-disk file timestamps are the *copy* date and are useless.

## LiDAR footprint (ground swath)
Flat-ground, constant-AGL model (no DEM). The corridor **half-swath = 1.5 × AGL** from the flight
centerline (full swath = 3 × AGL; 75 m at 50 m AGL) — the convention from the auterion-plan-generator
LiDAR spec. Footprint = the trajectory buffered by the half-swath (shapely, in a local equirectangular
projection about the centroid). `phoenix_lib.footprint_rings`.

**Speed-band masking:** LiDAR point density is only uniform on the productive survey lines. Filtering
the footprint to trajectory segments flown within a ground-speed band (e.g. 9.5–12.25 m/s) drops the
turns and accel/decel, so the footprint shows true on-line coverage. `phoenix_lib.speed_runs` resamples
to ~1 Hz for a stable speed estimate, then returns the in-band runs to buffer individually.
