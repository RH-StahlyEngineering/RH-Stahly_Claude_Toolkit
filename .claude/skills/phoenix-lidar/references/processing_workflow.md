# PPK processing workflow — SpatialExplorer / NavLab (Inertial Explorer)

Downstream of the QA'd plan: driving the actual point-cloud production. Checklist form. NavLab =
NovAtel Inertial Explorer engine inside SpatialExplorer (SE). One processing session = **one base
RINEX = one saved `.plp`** (Save-As per batch). CRS/geoid/unit values below are the Fergus project's
(NAD83(2011) MT State Plane). **They are an example, not a default — run §0a first.** NOTE: MT State Plane is **international ft**; earlier text here called it US survey ft, which was wrong.

## 0a. Establish the job CRS BEFORE anything else
Two things vary per job and both bite silently. Settle them from the survey's own metadata, not
from the last project.

- **Is it a State Plane zone or a custom LDP?** If the control came from TBC/Trimble Access as a
  `.jxl`, the `jxl-parser` skill extracts the projection, units, geoid, and datum straight from it.
  A **Low Distortion Projection has no EPSG code** — you cannot pick it from SE's list; enter it as
  a user-defined grid from the parameters (type, lat₀/lon₀, k₀, false E/N, unit). Seen 2026-07-31
  (MVM, Helena): TM, lat₀ 46.5, lon₀ −111.95, **k₀ 1.000191**, FE 200000, FN 100000, ift.
- **Which foot?** International (0.3048) and US survey (1200/3937) differ by 2 ppm. That is
  ~0.008 ft vertically — invisible — but at a 200,000 ft false easting it is **0.40 ft of
  horizontal shift**, and the error is *proportional to the coordinate*, so it looks like a scale
  problem rather than a unit problem. MT State Plane (2256/6515) is **international ft** (vertical NAVD88 ift = EPSG **8228**; 6360 is ftUS — only ~0.006 ft at 3000 ft elevation, but keep it consistent); MT LDPs
  are commonly **international ft**. Verify per job; never inherit.
- Whatever you land on, use the SAME unit in **all four** places: project CRS, control CSV import,
  base measure-up field, and export. A measure-up is safe either way (2 ppm of ~5 ft is nothing);
  it is the *coordinates* that bite.
- **Measurement epoch: match the control, not the flight date.** NAD83(2011) is defined at epoch
  **2010.00** — the "2011" is the adjustment name. SE's 2010.00 default is correct for ordinary
  NAD83(2011) control; leave it. Entering the observation date (e.g. 2026.58) runs the
  time-dependent ITRF↔NAD83 terms over a 16-year span and lands you a few cm off your own control.
  Only change it if the control itself is published at a different epoch (e.g. a raw ITRF2014/2020
  OPUS solution — convert that to NAD83(2011) 2010.00 instead).

## 0b. Keep raw isolated — SE WRITES INTO WHATEVER IT OPENS (measured 2026-11-05/06, SB 536 Box Elder)
- NavLab writes decoded `.gpb/.epp/.sta` (+ `_resampled` copies, ~1 GB) **next to the base `.O` it is pointed at**, and writes `.gpb/.epp/.sta/.imr` into the **session folder** and rewrites the `.nav` timestamp. Colorize adds `cam0\cache\depthmaps` (one `.depth` per photo).
- So: **copy the full session folder** (all of cam0) into `Processing\<site>\<session>\` and **copy that site's base RINEX into `Processing\<site>\Base\`** before opening anything. Then, after opening the project PLP, **confirm the mission PLP path points at the copy, not the raw folder** — a project PLP saved before the copy finishes will happily load the raw mission.
- A partial robocopy (killed mid-photos) is useless for colorize; finish it or delete it.

## 0c. Base antenna height — VERIFY AGAINST THE FIELD JOB BEFORE PPK (blocker, not a note)
- **`convertToRinex.exe <T04> -p <out> -v 3.04 -n` (CLI, no job applied) writes `ANTENNA: DELTA H` straight from the T04, and it is NOT the ARP height.** Measured on 4 R12i files: short by exactly **0.12932 m (0.424 ft) = the R12i ARP→L1 offset**. A GUI conversion with the job applied (15472780, 10/14) was correct. SE then adds ARP→L1 again → base too low by 0.424 ft → **whole cloud 0.424 ft low**.
- Get the truth from the Trimble Access `.job`: the base record holds method text (e.g. **"Lever of R12i extension"**), the measured value, and the method's offsets. For "Lever of R12i extension": slant **S** to the lever tip, horizontal **0.12 m**, lever→ARP **0.20 m** (job also stores 0.32932 = 0.20 + 0.12932). **Cap→ARP = √(S² − 0.12²) + 0.20.** (Binary job: search for the method string near the base receiver serial; the doubles 1.2315 / 0.12 / 0.32932 sit within ~250 bytes.)
- Enter **cap→ARP** in SE (vertical to ARP); SE applies ARP→L1 itself. Report should read measured h, ARP→L1 0.12932 m, applied = sum.
- Confirm on the cloud before trusting it: target ΔZ (control − cloud) ≈ the height error, uniform across targets.

## 0. Setup (once per batch PLP)
- Open all of the batch's mission PLPs into one project (Astro rover profile loads the CAD lever-arm — leave it).
- **Compound CRS:** horizontal **EPSG 6515**, vertical **EPSG 8228** (NAVD88, international ft; Fergus used 6360/ftUS — negligible vertically but wrong), geoid **GEOID18 = "US NOAA G 2018 U0"** (Select geoid → search "18" → Download → Use selected grid). Default is 7664 = WGS84 geocentric (replace it). *(Fergus values — per §0a, a custom-LDP job uses a user-defined grid + its own unit instead of 6515/6360.)*
- Stay in **GRID** the whole time — **no scale or ground factors, and this matters more on an LDP**: the LDP's k₀ is already a ground scale baked into the projection, so a second factor double-applies it.
- **Base RINEX (NavLab → Reference Stations → folder icon):** point to the **`.O`** obs file (keep the broadcast eph files beside it). Import runs a gap check — confirm the base fully brackets the scan.
- **Create + SELECT the base coordinate:** double-click station → Manage Positions → Create → name it (e.g. CP5) → coord system = the project → type (don't paste) N/E/vert (surveyed, orthometric ft). **Then SELECT it in the base dropdown** and **delete the RINEX "approximate"** so only the real coord is selectable. Set antenna type; ARP "height above ARP" auto-fills from the NGS model; enter the measured **marker→ARP** height (verify units against §0a — the SE base field followed the project unit, US survey ft on Fergus).
- **Before you delete that approximate, project the RINEX header `APPROX POSITION XYZ` into the job CRS and compare it to your control.** Two outcomes, both useful:
  - **Metres off** → ordinary autonomous position. The usual rule applies: it's garbage, delete it.
  - **Millimetres off** → *the RINEX was written with the surveyed coordinate already in it.* Not garbage — it's a free independent check that you typed N/E correctly. Measured 2026-07-31 (MVM, marker 50 = CP/RPC NASH): **0.000 ft E / 0.003 ft N**. Still create and SELECT your own coord; just don't dismiss the header sight-unseen.
- **Back-compute the geoid separation to prove the height type and the geoid model.**
  `separation = (RINEX ARP ellipsoidal h) − (ANTENNA: DELTA H) − (your orthometric Z)`.
  MVM 2026-07-31: 1261.450 − 1.6688 − 1274.190 m = **−14.41 m**, a textbook GEOID18 value for
  Helena. **A separation near zero means your Z is ellipsoidal, not orthometric** — enter it wrong
  and the cloud moves by the full separation (~47 ft in Montana). This also sanity-checks the geoid
  *model*, though GEOID18 vs GEOID12B differ by only a few cm here — take the model from the JXL /
  OPUS datasheet rather than inferring it.

## 1. PPK — aerial (per mission, one nav file at a time)
- Profile **SPAN UAV (STIM300)** (SE auto-default; matches IMU-27 = STIM300 — leave it).
- **Differential GNSS + INS, tightly coupled · Multi-pass ON** · output **InertialExplorer** · **precise ephemeris OFF** · Advanced: **min alignment velocity 8** · **QC2** · **lever-arm estimate OFF** · dedicated output folder.
- Run each mission with only that one checked (uncheck the others; re-confirm tightly-coupled + Advanced between runs — they can silently reset). Yields one **CTS** trajectory per mission (the CTS builds the cloud, not the real-time nav).
- **Read the two separation plots:** position within **±2 cm**, attitude within **±2 arc-min** (yaw always worst). Single-epoch spikes in a turn/hotswap are fine.

## 1b. PPK — mobile (vehicle) variant
- Profile **Ground Vehicle** (not UAV) · **try tightly AND loosely coupled, keep the better** · open-sky highway → **QC2** (QC4 can reduce quality on good mobile GPS). Trust the vehicle lever-arm in the PLP (different from the Astro).

## 2. Create Intervals (flightlines)
- **After the final PPK.** Auto tool: threshold **12°/second** → name it (`B##_lines`) → Compute.
- **Delete the kinematic-alignment line(s)** — one per mission's figure-8, each via its OWN red X.
- **ONE interval list** across all the batch's missions (that's where flights merge into one cloud/one Snap). Adjacent AB/BA passes must **overlap** (line scanner — gaps = holes; loosen 12° / Close Gaps ~2 s / raise Min interval duration to fix).
- **Mobile = MANUAL:** all layers off except CTS → clear picks → pick each end of each pass → "create intervals from picks" (one per direction).

- Toolbar button (top bar) in SE 9 — there's no menu item named "Create Intervals (auto)".

## 3. Build the point cloud
- Lidars → double-click Lidar 0 → Processing tab.
- **Aerial:** FOV **90°**, min range **10 m**, max ~200, **multi-returns**, full density (first shot/first line), don't pre-filter noise → Apply.
- **Mobile:** min range **~1 m**, **first-return only**, set **Minimum velocity ~0.1 m/s** (drops stopped data).
- Create Cloud → name **`Fergus_B##_CP#_<base>`** → save in batch folder → **Time intervals = Flightlines** → single cloud → OK. (AC power = faster GPU.)
- Stage snapshots via save-as suffix if wanted: `_raw / _snap / _gcp / _class / _rgb`.

## 4. LiDAR Snap (strip alignment) — run AFTER the cloud
- **Aerial preset: Trajectory Optimization → Linear Dense / 10 s / 3 iterations.** The preset defaults to "Sensor Calibration" every open — **reselect the trajectory preset each run.**
- **NEVER boresight** a vegetated topo survey (sensor is factory-cal'd; boresight only for urban/building datasets).
- **Keep GCPs OUT of Snap on aerial** (you want to see a bias, not have Snap hide it).
- **NEVER mix mobile + aerial in one Snap** — different geometry/dynamics/preset. Snap aerial clouds together (reconciles seams), mobile alone (Mobile preset; back rate off to 5–10 s for open sky; turn off E/N if unobservable).
- Read the report: correspondence-residual histogram **StdDev / StdDevMAD before→after** (target down to ~0.1 ft = laser-precision floor); well-flown AB/BA may show ~no improvement (expected).

## 5. Ground control / accuracy
- Import control CSV (File→Open): assign **Easting/Northing/Height**, units **per §0a** (US survey ft on Fergus; ift on an LDP job — this dropdown is one of the four places the wrong foot hides), height **orthometric**, start row (1 if no header). Type = **control** (adjusts) vs **check** (reports only, independent).
- **PNEZD from a JXL:** `<Grid>` `North`/`East`/`Elevation` are stored in **metres regardless of the file's display units** — convert with the job's foot before import. Standard PNEZD is `point,northing,easting,elevation,description`, no header row.
- **Align to GCPs** → point-to-mesh, search radius **~16.4 ft** → computes ΔZ per point (control − cloud). **Apply** = vertical de-bias (Snap doesn't move the cloud vertically vs control — the GCP de-bias does).
- Accuracy: **RMSEz** from independent checkpoints; **NVA = RMSEz × 1.96** (95%). System ≈ 1.5 cm typical. ≥30 checkpoints for a formal ASPRS number (a handful is a spot-check).

## 5b. Vertical de-bias — prefer the physical cause; validate on hard surface (SB 536 Box Elder, 2026-11-06)
- SE target ΔZ (5 × 2 ft cross targets) said **+0.49 ft**; the antenna bust was **0.424 ft**. Target tenting / edge fuzz put ~0.07 ft of its own bias into the target check. With +0.49 applied, 34 independent ground checks read **mean −0.135 ft** (cloud high); with **+0.424** they read **−0.065 ft**, and the **8 road (hard-surface) checks: mean −0.004, RMSEz 0.031 ft, NVA95 0.060 ft**. The residual −0.06 on grass/trail shots is the classification ground thickness (0.10 ft ≈ +0.05 ft lift) plus grass.
- Rule: if a known physical error explains the offset (antenna height), shift by **that**, not by the target mean; never shift by the checkpoint mean (it stops being an independent check). Split checks into hard-surface vs vegetated and report both; hard surface is the real accuracy statement.
- Pure Z shift without rewriting points: copy the LAZ and add dz to the **public-header doubles Z offset @171, Max Z @211, Min Z @219** (point records are scaled integers, so every point moves exactly dz; compressed data byte-identical). Name `<cloud>_Zplus0p42.laz`. Verify: size unchanged, `fc /b` differs only in header bytes 0xAB–0xE0, class counts unchanged. PDAL alternative: `filters.transformation` matrix `1 0 0 0 0 1 0 0 0 0 1 dz 0 0 0 1` (rewrites all points).
- Independent check: `scripts/pt2tin_check.py` (local ground-only TIN within r=3.28 ft at each shot, ΔZ = shot − cloud; stats overall / per source).

## 6. Classify → colorize → export
- Classify order **noise → ground → SOR**. **CONFIRMED SETTINGS — AERIAL LiDAR dataset** (Fergus, ~50 m AGL corridor; values in international feet, the project's units):
  - **Noise:** defaults (<10 neighbors within 1 m) **classified powerlines as noise on SB 536 Box Elder** — radius **5** (same 10 neighbours) kept wires and was much better. Check wires after noise on any site with lines.
  - **Cliffs / vertical cut banks:** the 6°/0.5 ft ground filter can't climb them (face left unclassified, top/bottom shots get no ground). Polygon-select the bank strip in **plan view** (Selection toolbar; hidden points are still selected), Classify By Class 2→1 on the selection to reset, then re-run ground on the selection only with **angle 30–45°, distance 2–3 ft**. Interactive classify-on-selection needs the SpatialPro module. Afterwards check every checkpoint has ground within ~3 ft — on Box Elder 3 bank/deck shots still had none.
  - **Bridge decks** are not ground; a check shot on the deck has no ground TIN (compare to deck points instead).
  - **Ground (AERIAL):** cell size **60 ft** · feature size **7 ft** · iteration distance **0.5 ft** · iteration angle **6.0°** · **10 iterations** · ground thickness **0.10 ft**.
    ⚠️ **These are tuned for an AERIAL (~50 m AGL) dataset.** A **mobile/terrestrial** cloud needs a MUCH smaller cell + feature size (points are dense and close to the sensor) — do not reuse these aerial numbers on mobile.
  - **SOR (outliers):** neighbors **k = 32**, sigma = **2.5** (conservative/light-touch: high k catches small isolated clusters like birds; 2.5σ trims the tail without eating thin features).
  - **Power lines / wires:** query **height-above-ground > 2 m** first → **Wire = class 14**, and **classify wires BEFORE SOR and exclude class 14 from SOR** so conductors aren't culled as outliers.
- Colorize after PPK + Snap, sun 10–2 / >30°. Export LAS/LAZ/SHP/OBJ/CAD; **LandXML forces ONE unit** → set it to the job's unit from §0a (International Foot on the MT jobs seen so far).

## 7. Post-export deliverable QA (do this BEFORE anything reaches TBC)
The SE export is not the deliverable — verify every derived cloud (thinned, colorized, cropped) against the source it came from. A cloud can pass a viewer's eye and still be silently broken.
- **Aggregate + witness verification.** For any transform that is supposed to change only ONE thing, confirm everything else is byte-identical: point count, per-class histogram, X/Y/Z ranges, PDRF + point size, scales/offsets, and CRS (single WKT VLR, no `COMPD_CS`). Pick 3 witness points (the true W-most, E-most, and a mid point) and match them **by coordinate, not index** (derivation reorders points) — report measured XYZ and per-axis deltas, never "matches". A **uniform Z delta = ellipsoid/geoid failure** (see §0 — ~47 ft in MT); a uniform XY delta = datum/offset change. (Harness: `verify_colorized.py` in the session scratchpad.)
- **⚠️ Agisoft/Metashape colorization silently downgrades the container.** Observed: LAS 1.4/PDRF 7 → **LAS 1.2/PDRF 3** (adds `normal x/y/z` extra bytes, resets offsets → re-quantizes coords, swaps WKT VLR → GeoTIFF keys). **The dangerous one: PDRF 3 gives classification only 5 bits (0–31).** A project delivering classes 163–183 would truncate 183→23 (Bridge→Guy Wire) in a file that still validates. **Deliverable/working cloud MUST stay LAS 1.4 / PDRF 6+.** Do NOT accept Agisoft's container — **re-wrap**: transplant RGB onto the ORIGINAL header (correct PDRF/offsets/WKT), drop normals. Agisoft reorders AND re-quantizes, so match by **scipy cKDTree nearest-neighbor** on coords (integer offset-shell search is too slow / doesn't scale; re-quant can exceed several key units) — ~2 min for 152 M pts, 100% coverage by construction. Verify raw-int identity of X/Y/Z/class/intensity/gps_time vs original + RGB populated. (`rewrap_rgb_kdt.py`.)
- **Coverage / provenance audit.** Aerial vs mobile vs photogrammetry coverage is NOT recorded anywhere by default — build it from `<raw>\Base_Station_Data\QA_out\<proj>_all_missions.kml` (per-mission Trajectory + **Footprint** placemarks; footprint = actual LiDAR swath). Convert lon/lat → job CRS with pyproj, validate ~1 ft against known control, tabulate per-batch E/N envelope, save a `COVERAGE_TABLE.csv`. Map missions → batches → aerial/mobile from the batch reference (the acquisition date is the tell: e.g. Fergus 7/2 = main corridor, 7/16–17 = taps/west end, 6/30 = mobile). **A different flight day can cover ground the main corridor missed** — filtering the export by one acquisition date makes that area look empty when it isn't.
- **Distinguishing source without provenance fields:** thinning/decimation often **wipes `point_source_id` (→0) and `gps_time` (→constant sentinel)** — you then can't trace a point to its mission. Two fallbacks: (1) **multi-return fraction** — airborne/mobile LiDAR shows a multi-return tail (~10–14% here, returns to 6); **photogrammetry is surface-only ≈0%**, so multi-return present ⇒ real LiDAR (but does NOT separate aerial from mobile). (2) **swath width** — mobile is a narrow road corridor; a 10,000+ ft cross-corridor spread ⇒ areal (aerial/photo), not mobile. To separate aerial-vs-mobile for certain, bucket `gps_time` on a cloud that still has it (the pre-thin classified export).

## GOTCHAS (hard-won)
- **(a) Re-running PPK orphans the CTS reference.** After a re-run/overwrite (esp. to a new `_navlab` folder) the project still points at the old/missing CTS → cloud fuse fails **"no usable trajectories covering interval …" for EVERY interval.** Fix: **manually import the current `.cts` files**; intervals re-link by time (no need to recreate them). Deactivate the real-time `.nav` so only CTS are active.
- **(b) SELECT the base coordinate.** Entering it isn't enough — it won't default-select; unselected → processing runs on the useless RINEX autonomous position. Delete the approximate to make the mistake impossible — but check it against your control first (§0), because some RINEX are written with the *surveyed* coordinate in the header and that's a free typo-check, not garbage.
- **(c) Lever-arm is a property of the rover/aircraft PROFILE**, not a per-run field. The only edit path shown is estimate→save (loosely coupled, "Estimate Primary Antenna Lever-Arm", 1 iter check / 4 production, Save). No manual X/Y/Z entry screen is demonstrated (raw values entered at initial setup off-camera). Read-only in NavLab Trajectory Report → Rover Configuration.
- **(d) Intervals straddling hotswaps / PPK gaps fail to fuse** (no CTS solution there). Delete/trim those intervals — non-productive, zero data lost.
- **(e) QC0 ≈ QC2 with a close base** (within ~5 mi most epochs are QC0/QC1 anyway). Don't bother with QC0 — it can over-reject and drift on long baselines. Standardize on **QC2**.
- **(f) Stock CAD lever-arm is correct for the Astro** — estimating it across 4 flights was a *wash* (same de-biased RMSE), so DON'T adopt an estimate; it just absorbs pitch/attitude artifacts. SOP: "for the Astro, trust the CAD values." (Estimating IS warranted for a new/unknown mount, or to diagnose a uniform vertical bias vs control.)
- **(g) Base measure-up busts** are the classic ~0.1–0.3 m *and* the nasty ~1 ft transposition (a clean digit swap in the entered height, e.g. 1.562→1.256 m ≈ exactly 1 ft). A wrong *measurement-method* only ever costs ≤0.2 m; a bigger uniform vertical offset is a wrong *entered value*. In differential PPK the base error transfers 1:1 into the cloud: base entered **too low → cloud too low**; raise the base to fix. Catch it with independent check-shots + a same-day second base (shorter baseline wins once the height is right). Cross-check every base's TBC entered height vs its RINEX `ANTENNA: DELTA H`.

- **(h) A 3D `PROJCRS` WKT always declares its Z axis "ellipsoidal height" — even when your data is orthometric.** That is not a typo in the file and it cannot be fixed in place: in WKT2 the third axis of a *projected 3D* CRS is ellipsoidal by definition, and declaring gravity-related height requires a separate vertical datum, i.e. `COMPOUNDCRS`. If the tool accepts a compound WKT, use it and the ambiguity disappears. If it only takes the 3D form, the label is wrong-by-construction and the mitigation is procedural: **set height type = orthometric at import** and apply the geoid separately. Taking the axis label literally drops a Montana cloud ~47 ft. Confirm with the §0 separation back-computation, not with the WKT.
- **(i) The unit-of-record is a per-job decision, not a house default.** The four places it must agree: project CRS · control CSV import · base measure-up · export. A wrong foot is 2 ppm — it never looks like a unit bug because the error scales with the coordinate (≈0.40 ft at E 200,000; ≈4 ft at MT State Plane's E 2,000,000-ft range). If a cloud sits *proportionally* off in E and N with a good vertical, suspect the foot before you suspect the base.

- **(j) Big source clouds on Dropbox throw `OSError [Errno 22] Invalid argument` on read** when they're "online-only" placeholders — the file lists a real size but isn't materialized locally. laspy/PDAL fail at the header. Right-click → "Make available offline" before processing. (This is the same online-only-copies-as-zeros trap as convertToRINEX; here it surfaces as a read error, not zero bytes.)
- **(k) The last thing Agisoft, a thinner, or any external tool touched is NOT the deliverable until re-verified.** External tools rewrite containers and drop fields as a side effect (see §7). Always re-wrap/re-verify to the intended LAS 1.4/PDRF 6+ spec and diff against the source; "it opened fine" is not verification.

## SOP gaps
The Stahly Phoenix MiniRANGER-3 SOP covers the workflow conceptually but **lacks button-level UI detail** and several exact strings/fields (which airborne/vehicle profile, where the lever-arm/CRS/base fields live, Align-to-GCPs threshold). When a step is ambiguous, prefer SE's auto-default (it IMU-matches profiles correctly) and confirm against the training recordings / Conrad or Joel at Phoenix. Keep a running gaps list per job (pattern: `<project>\_process\SOP_gaps_TODO.md`).
