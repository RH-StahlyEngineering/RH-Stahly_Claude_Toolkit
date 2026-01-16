# Civil 3D Layer Naming Conventions

Standard layer prefixes for Civil 3D survey drawings:

## V-* (Survey/Civil)

| Pattern | Description | Common Codes |
|---------|-------------|--------------|
| `V-NODE-*` | Survey nodes/control points | |
| `V-STRM-*` | Storm drain | SDI=inlet, MHSD=manhole, SDM=structure |
| `V-SSWR-*` | Sanitary sewer | CO=cleanout, MHSS=manhole, SSM=structure |
| `V-WATR-*` | Water utilities | FFH=fire hydrant |
| `V-POWR-*` | Power/electrical | PP=pole, EM=meter, LP=light, OHE=overhead |
| `V-GAS-*` | Gas utilities | PRO=riser(?), GM=meter |
| `V-TINN` | TIN surface/contours | |
| `V-TOPO-*` | Topography | |

## Other Common Layers

| Layer | Description |
|-------|-------------|
| `G-ANNO` | Annotations/labels |
| `0` | Default layer |

## Usage Examples

```python
# Find all storm drain points
extract_cogo_points(filepath, 'V-STRM-*')

# Find all utility points
extract_cogo_points(filepath, 'V-*')

# Flatten contour lines
flatten_entities(filepath, output, layer_pattern='V-TINN')
```
