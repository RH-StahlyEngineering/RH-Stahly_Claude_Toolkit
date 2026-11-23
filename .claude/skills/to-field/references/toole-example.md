# Worked example: Toole County Courthouse Retaining Walls (2071-07D26), Nov 2026

Job root: `\\stahly\PROJECTS\2071-Toole County\-07D26_Courthouse_Retaining_Walls\`

| What | Where (under the job root) |
|---|---|
| State, facts, decisions | `Documents\Survey\_AI\STATE.md`, `CONTROL_PLAN.md` |
| Pickup list + exhibit | `Documents\Survey\_AI\site_walk\CONVENTIONAL_PICKUP_LIST.md`, `pickup_exhibit.png`, `exhibit.py` |
| Field card | `Survey_GIS_Data\3-To_Field\FIELD_CARD_TooleCH.html/.pdf` (template copy in this skill) |
| PNEZD points | `Survey_GIS_Data\3-To_Field\TooleCH_field_pts_PNEZD.csv` (from `_AI\scripts\field_points.py`) |
| KML | `Survey_GIS_Data\3-To_Field\TooleCH_field.kml` |
| Targets | `Survey_GIS_Data\3-To_Field\Targets\targets_final.csv/.kml` |
| Prior control (2019) | `Survey_GIS_Data\3-To_Field\Control\shelby2019_pts_thinned_grid.csv` |
| Flight plans | `Survey_GIS_Data\3-To_Field\Flight_Plans\*.plan` |
| Proposal | `\\Stahly\marketing\Scope-Schedule-Budget\Survey - GIS\2026\Great_Falls\018-Toole_County_Courthouse_Retaining_Walls_Survey\` |

Artifacts RH used in the field (pattern to reuse):
- Control checklist with aerial close-up per mark: https://claude.ai/artifact/PFNHhBks87UHQ4KDFmy4Lz
- Target drawing map (saves to the artifact's db): https://claude.ai/artifact/VcavMnkmhEPm4FDJYaj8mU
- Phone field card with KML download: https://claude.ai/artifact/DS1wiuaDFABHf2KLAVewM8

Decisions that recur: low-distortion grid offered (RMTCRS Milk River, EPSG 7094, intl ft); base on a prior MDT aluminum cap with a fallback, checked from MTSRN NWMT VRS; vertical tie to an on-site NGS benchmark (V 425); 5 targets spread in height, one footprint inside coverage; shutter priority 1/1000 s.
