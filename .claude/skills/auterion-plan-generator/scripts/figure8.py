"""
Gerono-lemniscate figure-8 generator.

Closed 10-vertex figure-8 sized for a given flight speed and target duration.
Returns 11 SimpleItem waypoint dicts (10 unique vertices + 1 return-to-centroid
closer) — drone flies 10 legs and closes the loop.

Geometry:
    x(t) = a · sin(t)
    y(t) = (a/2) · sin(2t)        for t = 2πk/10, k = 0..9
    closed-polyline length = 5.82803 · a

Vertex 0 and vertex 5 both land at the centroid — this IS the figure-8's
self-intersection. The 11th waypoint repeats the centroid to close the path.

Usage:
    from figure8 import fig8_waypoints
    wps = fig8_waypoints(lat=47.153512, lon=-109.461364, alt_amsl=1281.62,
                        speed=8.0, duration=15.0)
    # wps is a list of 11 SimpleItem dicts (cmd 16, frame 0)
"""
import math

GERONO_CLOSED_LENGTH_FACTOR = 5.82803  # closed-polyline length = factor · a


def gerono_a(speed_mps: float, duration_s: float) -> float:
    """Return the 'a' parameter that makes the closed figure-8 take exactly duration_s."""
    return (speed_mps * duration_s) / GERONO_CLOSED_LENGTH_FACTOR


def fig8_vertices_meters(a: float):
    """Return 10 (east, north) vertex offsets in meters, centered at (0,0)."""
    return [(a * math.sin(2 * math.pi * k / 10),
             (a / 2) * math.sin(2 * 2 * math.pi * k / 10))
            for k in range(10)]


def fig8_waypoints(lat, lon, alt_amsl, speed=8.0, duration=15.0, frame=0):
    """Generate 11 waypoints: 10 Gerono vertices + 1 closer at centroid.

    Args:
        lat, lon: centroid (self-intersection point) in degrees
        alt_amsl: altitude (meters; AMSL if frame=0, AGL if frame=10)
        speed: flight speed m/s (only used to size the figure-8)
        duration: target flight time for the closed loop, seconds
        frame: MAV frame for the waypoints (default 0 = GLOBAL/AMSL)

    Returns:
        list of 11 SimpleItem waypoint dicts (`command: 16`).
        doJumpId is 0 — caller must renumber.
    """
    a = gerono_a(speed, duration)
    m_per_deg_lat = 111132.0
    m_per_deg_lon = 111132.0 * math.cos(math.radians(lat))

    pts = []
    for x_m, y_m in fig8_vertices_meters(a):
        pts.append((lat + y_m / m_per_deg_lat, lon + x_m / m_per_deg_lon))
    pts.append((lat, lon))  # closer: return to centroid

    return [{
        'autoContinue': True, 'command': 16, 'doJumpId': 0,
        'frame': frame, 'groupTag': 0,
        'params': [0, 0, 0, None, p[0], p[1], alt_amsl],
        'type': 'SimpleItem',
    } for p in pts]


def closed_polyline_length(a: float) -> float:
    """Total length of the closed Gerono polyline (10 legs)."""
    verts = fig8_vertices_meters(a) + [(0.0, 0.0)]  # add closer
    total = 0.0
    for i in range(10):
        dx = verts[i + 1][0] - verts[i][0]
        dy = verts[i + 1][1] - verts[i][1]
        total += math.hypot(dx, dy)
    return total


if __name__ == '__main__':
    # Self-test
    a = gerono_a(8.0, 15.0)
    L = closed_polyline_length(a)
    print(f"a = {a:.3f} m")
    print(f"closed polyline length = {L:.3f} m (target {8.0*15.0})")
    print(f"bounding box: {2*a:.1f} m wide x {a:.1f} m tall")
    wps = fig8_waypoints(47.15, -109.46, 1281.62)
    print(f"generated {len(wps)} waypoints")
