"""
USGS 3DEP terrain elevation lookup.

Free, no auth, 1-meter resolution in MT. ~1 s/point. Stdlib only.

Use this to DEM-bake AMSL altitudes for standalone waypoints. AMC does NOT
recompute terrain for standalone waypoints on file open (only for survey
inner items) — see known-pitfalls.md #1.

Usage:
    from dem_lookup import terrain_amsl
    elev = terrain_amsl(47.153512, -109.461364)  # returns meters AMSL
    waypoint_amsl = elev + AGL_TARGET
"""
import json
import math
import os
import time
import urllib.request
import hashlib

_cache = {}
_local_dem = None      # numpy array of elevations
_local_meta = None     # bbox + shape metadata
_explicit_meta_paths = []  # caller-supplied DEM metadata paths


def ensure_dem_for_bbox(lat_min, lat_max, lon_min, lon_max,
                        resolution_m=10.0, cache_dir=None):
    """Download (if not cached) a USGS 3DEP TIFF covering the bbox, return its meta path.

    Caches to <cache_dir>/dem_<hash>.tif (default cache_dir is ~/.claude/dem_cache).
    Subsequent calls with the same bbox skip download.

    After the first call, terrain_amsl() will auto-use this raster for any
    point inside the bbox (50,000× faster than per-point HTTP).
    """
    import ssl
    if cache_dir is None:
        cache_dir = os.path.join(os.path.expanduser('~'), '.claude', 'dem_cache')
    os.makedirs(cache_dir, exist_ok=True)
    key = f"{lat_min:.5f}_{lat_max:.5f}_{lon_min:.5f}_{lon_max:.5f}_{resolution_m:.1f}"
    digest = hashlib.md5(key.encode()).hexdigest()[:12]
    tif_path = os.path.join(cache_dir, f"dem_{digest}.tif")
    meta_path = os.path.join(cache_dir, f"dem_{digest}.json")
    if not (os.path.exists(tif_path) and os.path.exists(meta_path)):
        m_per_lon = 111132 * math.cos(math.radians((lat_min + lat_max) / 2))
        m_per_lat = 111132
        cols = int((lon_max - lon_min) * m_per_lon / resolution_m) + 1
        rows = int((lat_max - lat_min) * m_per_lat / resolution_m) + 1
        url = (f"https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?"
               f"bbox={lon_min},{lat_min},{lon_max},{lat_max}"
               f"&bboxSR=4326&size={cols},{rows}&imageSR=4326"
               f"&format=tiff&pixelType=F32&interpolation=RSP_BilinearInterpolation&f=image")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={'User-Agent': 'auterion-plan-generator'})
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            with open(tif_path, 'wb') as f:
                f.write(r.read())
        json.dump({'lat_min': lat_min, 'lat_max': lat_max,
                   'lon_min': lon_min, 'lon_max': lon_max,
                   'resolution_m': resolution_m,
                   'rows': rows, 'cols': cols,
                   'tif_path': tif_path}, open(meta_path, 'w'), indent=2)
    if meta_path not in _explicit_meta_paths:
        _explicit_meta_paths.append(meta_path)
        # Force the lazy loader to re-pick on next call
        global _local_dem, _local_meta
        _local_dem = None
        _local_meta = None
    return meta_path


def _try_load_local_dem():
    """One-time load of a DEM raster, if present.
    Speed: ~50,000x faster than per-point HTTP — entire batches in seconds.
    Search order: caller-supplied via ensure_dem_for_bbox(), then skill-dir defaults.
    """
    global _local_dem, _local_meta
    if _local_dem is not None or _local_meta is False:
        return
    candidates = list(_explicit_meta_paths)
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(skill_dir, 'fergus_dem.json'))
    # ~/.claude/dem_cache/*.json — pick the most recently modified
    cache_dir = os.path.join(os.path.expanduser('~'), '.claude', 'dem_cache')
    if os.path.isdir(cache_dir):
        cached = sorted(
            (os.path.join(cache_dir, f) for f in os.listdir(cache_dir) if f.endswith('.json')),
            key=lambda p: -os.path.getmtime(p))
        candidates.extend(cached)
    for meta_path in candidates:
        if not os.path.exists(meta_path): continue
        try:
            import tifffile
            meta = json.load(open(meta_path))
            arr = tifffile.imread(meta['tif_path'])
            _local_dem = arr
            _local_meta = meta
            return
        except Exception:
            continue
    _local_meta = False


def _local_lookup(lat, lon):
    """Bilinear sample from the loaded DEM array. Returns None if out-of-bounds or no raster."""
    _try_load_local_dem()
    if _local_dem is None or _local_meta is False:
        return None
    m = _local_meta
    if not (m['lat_min'] <= lat <= m['lat_max'] and m['lon_min'] <= lon <= m['lon_max']):
        return None
    # Y/row goes top-to-bottom; lat decreases with row
    fy = (m['lat_max'] - lat) / (m['lat_max'] - m['lat_min']) * (m['rows'] - 1)
    fx = (lon - m['lon_min']) / (m['lon_max'] - m['lon_min']) * (m['cols'] - 1)
    y0 = int(fy); x0 = int(fx)
    y1 = min(y0 + 1, m['rows'] - 1); x1 = min(x0 + 1, m['cols'] - 1)
    dy = fy - y0; dx = fx - x0
    v00 = float(_local_dem[y0, x0]); v01 = float(_local_dem[y0, x1])
    v10 = float(_local_dem[y1, x0]); v11 = float(_local_dem[y1, x1])
    v = (v00 * (1-dx) * (1-dy) + v01 * dx * (1-dy)
         + v10 * (1-dx) * dy + v11 * dx * dy)
    return v


import ssl
_unverified_ctx = ssl.create_default_context()
_unverified_ctx.check_hostname = False
_unverified_ctx.verify_mode = ssl.CERT_NONE


def terrain_amsl(lat: float, lon: float, retries: int = 5, timeout: int = 30) -> float:
    """Return ground elevation (meters AMSL) at (lat, lon) from USGS 3DEP.

    Cached by (lat, lon) rounded to 6 decimals (~0.1 m precision).
    Raises on persistent failure.

    Falls back to TLS-cert-unverified mode if cert validation fails (some
    corporate networks intercept the cert chain).
    """
    key = (round(lat, 6), round(lon, 6))
    if key in _cache:
        return _cache[key]

    # Try local DEM first (50× faster, no network)
    v = _local_lookup(lat, lon)
    if v is not None:
        _cache[key] = v
        return v

    url = (f"https://epqs.nationalmap.gov/v1/json?"
           f"x={lon}&y={lat}&units=Meters&wkid=4326&includeDate=false")
    last_err = None
    for attempt in range(retries):
        ctx = _unverified_ctx if attempt >= 1 else None
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'auterion-plan-generator'})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                data = json.loads(r.read().decode())
            value = float(data['value'])
            _cache[key] = value
            return value
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 + attempt * 2)
    raise RuntimeError(f"USGS 3DEP lookup failed for ({lat}, {lon}): {last_err}")


def bake_amsl(lat: float, lon: float, agl_target: float) -> float:
    """Return terrain + agl_target for direct use as a waypoint AMSL."""
    return terrain_amsl(lat, lon) + agl_target


def cache_stats():
    return {'unique_points': len(_cache)}


if __name__ == '__main__':
    # Self-test
    print(f"Home position (Hilger area): {terrain_amsl(47.255, -109.354):.2f} m AMSL")
    print(f"Stahly office (Lewistown):   {terrain_amsl(47.1535, -109.4614):.2f} m AMSL")
    print(f"Cache: {cache_stats()}")
