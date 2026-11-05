---
name: auterion-plan-generator
description: Generate and modify Auterion Mission Control / QGroundControl .plan files for drone LiDAR surveys and camera photogrammetry missions. Use when the user asks to create a flight plan, build a .plan file, design a LiDAR or photogrammetry (mapping camera) survey, add figure-8 calibration patterns, convert a KML to a flight plan, fix a plan that won't load on the RC controller, estimate flight duration, or work with terrain-following missions in Auterion.
when_to_use: "Create flight plan; generate .plan; Auterion mission; QGroundControl; LiDAR survey; photogrammetry survey; camera mapping mission; figure-8 calibration; terrain follow; KML to plan; mission duration estimate; controller-loadable plan; fix plan format"
---

# Auterion / QGroundControl .plan generator

Builds, modifies, and validates `.plan` files for Ryan's PX4-multirotor (Freefly Astro) survey workflow. Read [constants-and-variables.md](constants-and-variables.md) **and** [known-pitfalls.md](known-pitfalls.md) before generating or editing any plan — both hold hard-won knowledge the file format alone does not reveal.

## When to invoke

- "Generate a flight plan for ..." / "Build a .plan from this KML"
- "Plan a photogrammetry / camera mapping flight over ..."
- "Add figure-8s to this mission"
- "This .plan won't load on the controller — fix it"
- "How long will this mission take?"
- "Tweak the cross-line / trailing leg / home position in this plan"
- "Why is my mission flying at MSL instead of terrain-following?"

## First: LiDAR or camera?

Settle the payload before anything else; it decides the workflow, the flight-time limit, and the checks.

- **LiDAR (MiniRanger-3)** → follow [references/lidar.md](references/lidar.md): canonical mission structure, session model, Q&A, workflow, scripts, corridor missions, lessons learned, final checklist.
- **Camera photogrammetry (Sony ILX-LR1)** → follow [references/photogrammetry.md](references/photogrammetry.md): defaults Q&A, trade-off sweep before any build, gimbal rule, Toole lessons. Offer every camera default and build only on RH's confirmation.
- Payload specs, per-flight time limits, and the flight-time model → [references/payloads.md](references/payloads.md).

When the user's request leaves the payload open, ask.

## Standing rules (current — override older lessons in the references)

- **Per-flight time limit: 15 min** for LiDAR (RH 2026-10-06; was 10); camera limits in [references/payloads.md](references/payloads.md). Check every plan's estimated duration against its payload's limit. Lessons that cite a 10-min battery are historical records of those projects. Plans RH accepted before this change are exempt even if they violate it.
- **Criss-cross surveys drop the cross-line** (RH 2026-10-06). The perpendicular grid ties the lines for the LiDAR INS. See *Criss-cross (double-grid) surveys* in [references/lidar.md](references/lidar.md). Plans RH already built with a cross-line keep it.
- **Line angle follows the dominant power line** when one crosses or borders the site (RH 2026-10-06). Lines parallel to the wires give the best wire returns. Use the length-weighted bearing of power-line segments within ~200 m of the survey polygon (OSM `power=line|minor_line`, or the client's line KML). Otherwise, use the polygon's long axis.
- **Every generated plan gets a photo-overlap report** from `scripts/photo_overlap.py` (see *Photogrammetry overlap* in [references/lidar.md](references/lidar.md)).
