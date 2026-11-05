# Payloads

Single source of truth for payload numbers. Both workflows read flight-time limits and sensor geometry from here.

| Payload | Type | Per-flight limit | Sensor | Image size | Pixel pitch | Focal length | Orientation | Min trigger interval |
|---|---|---|---|---|---|---|---|---|
| Phoenix MiniRanger-3 | LiDAR | 15 min | — | — | — | — | — | — |
| Sony ILX-LR1 + 24 mm lens on Freefly Astro | Camera | 26 min | 35.7 × 23.8 mm | 9504 × 6336 px | 3.76 µm | 24 mm | Long side across-track | 2 s |

## Flight-time model

Time per flight = `1.05 × distance / speed` + `4 s per turn` + `1.5 min overhead per flight`.

These factors are provisional: recalibrate them against flown logs before trusting estimates near the per-flight limit. (LiDAR plans still use the calibrated `scripts/estimate_flight_time.py`; see [lidar.md](lidar.md).)

Machine-readable copy: `scripts/payloads.json` (keys `lr1_24mm`, `miniranger3`), read by `scripts/camera_plan_set.py`. Keep both in sync.
