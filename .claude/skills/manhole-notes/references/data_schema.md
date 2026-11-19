# job.json

One file per job and field day. It is the record of what the field crew said, so put in what they gave and leave out everything else. `mh_sheet.py` works out invert and size from the raw measurements, and `--final` prints NOT RECORDED for anything left out.

```json
{
  "job": "2071-07D26",
  "date": "2026-11-12",
  "out_dir": "P:/2071-Toole County/-07D26_Courthouse_Retaining_Walls/Survey_GIS_Data/5-Field_Notes/<folder>",
  "field_north_az": 28.2,
  "field_north_ref": "perpendicular to 1st St S",
  "measure_from": "rim",
  "default_wall_ft": null,
  "measure_downs": {"sanitary_mh": false},
  "structures": [
    {
      "point": "12141",
      "kind": "storm_mh",
      "desc": "Storm MH",
      "dia_ft": 5.5,
      "lid": "Eccentric W",
      "type": null,
      "grade": null,
      "cntr": "6.84",
      "notes": "W is the trunk toward the drain to the west.",
      "streets": [{"name": "1st St S", "bearing": 298.2}, {"name": "4th Ave S", "bearing": 28.2}],
      "photo": {"path": "C:/.../photo.jpg", "orientation": "field_north_up"},
      "pipes": [
        {"dir": "W", "invert": "6.86", "top": "3.83", "size": "36", "drop": "No", "proj": 14},
        {"dir": "N", "invert": "5.63", "top": "4.16", "drop": "Yes", "note": "to drain"}
      ]
    }
  ]
}
```

## Job fields

| Field | Meaning |
|---|---|
| `field_north_az` | The crew's "north" as a true azimuth. They often call north square to the main street. Measure that street's bearing from OSM (geodesic, true north, not grid) and add or subtract 90°. 0 if they used true north. |
| `field_north_ref` | How the crew defined north, for the sheet note. |
| `measure_from` | What measure-downs start from. Default `rim`; set it only if the crew says otherwise (e.g. `top of grate`). |
| `default_wall_ft` | Pipe wall thickness, only if the crew gave a job-wide estimate. Each pipe's `wall` overrides it. |
| `measure_downs` | Per kind: `false` if the engineer said not to measure that kind. Its blanks then stay empty instead of reading NOT RECORDED. |
| `out_dir` | `<job>\Survey_GIS_Data\5-Field_Notes\YYYY-MM-DD_Storm_Measure-Downs` (field date). |

## Structure fields

- `kind`: `storm_mh`, `sanitary_mh`, `curb_inlet`, `grate_inlet` or `combo_inlet`.
- Manholes: `dia_ft` (number) and `lid` (`Concentric`, or `Eccentric <dir>`).
- Inlets: `box_l_ft` and `box_w_ft` (L runs along field E-W) and `opening_side`.
- `type`: structure material, if the crew gave it. A photo is not a source; leave it out.
- `grade`: as given, e.g. `5 rings, equal size, 0.18 ft (2.2 in) each, 0.90 ft total`.
- `cntr`: measure-down to the center of the structure. Add `(top of sediment)` when the crew says so.
- `streets`: 0 to 3 labels. Each has a `name` and a true `bearing`, plus `side` (the true azimuth from the structure to the street centerline) when the structure sits beside the street rather than in it. Only label streets the structure is in or at the intersection of; no distance text.
- `photo.orientation`:
  - `field_north_up`
  - a number: degrees field north sits clockwise of photo-up (e.g. after turning the photo so the rungs sit where the crew said)
  - `unknown`
  
  Never assume north up. With `unknown`, a draft shows the photo unrotated; the final sheet leaves it off, so every page shares one north. Ask the crew instead.

## Pipe fields

| Field | Meaning |
|---|---|
| `dir` | Field direction, 8 or 16 points (`NE`, `WNW`). |
| `invert` | Measure-down to the inside bottom. |
| `top` | Measure-down to the outside top of pipe. Invert = top + wall + ID. |
| `wall` | Wall thickness in ft, from the crew. |
| `size` | Inside diameter in inches. If the crew states it, it wins over any calculation. |
| `slant` | `{"s": 3.9, "h": 2.7}` when the tape ran at an angle. Vertical = √(s² − h²). |
| `type` | Pipe material (`Concrete`, `PVC`), only as given. |
| `drop` | `Yes` or `No`, only as given. |
| `proj` | Inches the pipe sticks into the structure. If the crew didn't measure it, estimate it from the photo. |
| `note` | Free text, e.g. `to MH 12217`. |

The calculation runs only when the inputs exist. With no wall, a top-only pipe gets no invert, and an invert plus top gets no size: ask the crew for the wall.

## From the field form

The form page keeps one record per structure in its database (collection `manholes`). Pull it with `ArtifactData` `list` and `out_dir`. That writes one JSON per structure in the same shape as a `structures[]` entry. Then add the job fields and run.
