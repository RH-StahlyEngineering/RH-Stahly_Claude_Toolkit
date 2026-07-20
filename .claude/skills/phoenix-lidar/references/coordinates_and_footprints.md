# Coordinates, T04 naming, and the footprint model

## ECEF → geodetic
WGS84 (a=6378137, 1/f=298.257223563), iterative Bowring. In `phoenix_lib.ecef2geo`.

## Montana State Plane → WGS84
Survey control often arrives in **Montana State Plane NAD83, US survey feet (EPSG:2256)** — a single
Lambert Conformal Conic (2SP) zone. Params: standard parallels 45° & 49°, origin 44.25°/−109.5°,
false easting 600000 m, false northing 0, ellipsoid GRS80. `phoenix_lib.mt_stateplane_to_wgs84`
does the inverse (feet → metres via the US survey foot 1200/3937). It matches RINEX-derived base
positions to ~2 m — good enough that mileage decisions don't change, but prefer surveyed control when
the user provides it. If a project is in another state, add its LCC params rather than reusing these.

**Control CSV** is typically PNEZD: `point, northing, easting, elevation, description`. Base stations
are specific point numbers (the user tells you which, e.g. `1,2,5`). `analyze.py --control file.csv
--control-points 1,2,5` snaps each base RINEX to the nearest named control point (<0.2 mi) and labels
it `CP1/CP2/CP5`; obs files not on a named point are ignored.

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
