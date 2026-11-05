"""Self-contained 3D HTML (plotly inline): terrain, optional lidar, flight paths, every photo footprint
(corner rays cast onto the DEM, clipped at 300 m), and a view cone on every Nth photo.
Embeds <script id="photo-counts" type="application/json">{plan file: photos}</script>."""
import json, os
import numpy as np
import plotly.graph_objects as go
from walls import plan_photos, camera

COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b", "#e377c2", "#17becf"]
TS = np.arange(0.5, 300.01, 0.5)


def _cast(site, pos, dirs):
    dirs = dirs / np.linalg.norm(dirs, axis=1)[:, None]
    P = pos[None, None, :] + dirs[:, None, :] * TS[None, :, None]
    below = P[..., 2] <= site.ground(P[..., 0], P[..., 1])
    i = np.argmax(below, 1)
    return P[np.arange(len(dirs)), np.where(below[np.arange(len(dirs)), i], i, len(TS) - 1)]


def write_3d(site, plan_paths, pl, out_html, L=None, building=None, nth=10, max_lidar=50000, grid=160):
    f, sw, sh = pl["focal_mm"], pl["sensor_w_mm"], pl["sensor_h_mm"]
    hx, hy = site.hx, site.hy
    data, counts, tops = [], {}, []
    for k, p in enumerate(plan_paths):
        ph = plan_photos(site, p)
        name = os.path.basename(p); counts[name] = len(ph)
        wps = np.array([[*site.fw.transform(i["params"][5], i["params"][4]), i["params"][6]]
                        for i in json.load(open(p))["mission"]["items"] if i["command"] == 16])
        tops.append(wps[:, 2].max())
        data.append((name, COLORS[k % len(COLORS)], wps, ph))
    # terrain over paths + limits extent
    allxy = np.vstack([d[2][:, :2] for d in data] + [np.array(site.poly.exterior.coords)])
    x0, y0 = allxy.min(0) - 30; x1, y1 = allxy.max(0) + 30
    gx, gy = np.meshgrid(np.linspace(x0, x1, grid), np.linspace(y0, y1, grid))
    gz = site.ground(gx, gy)
    gz = np.where(site.inside(gx, gy), gz, np.nan)
    tr = [go.Surface(x=gx - hx, y=gy - hy, z=gz, colorscale="Earth", opacity=0.75, showscale=False,
                     name="Terrain (DEM)", showlegend=True, hoverinfo="skip")]
    if L is not None:
        m = (np.abs(L["x"] - (x0 + x1) / 2) < (x1 - x0) / 2) & (np.abs(L["y"] - (y0 + y1) / 2) < (y1 - y0) / 2)
        idx = np.flatnonzero(m)
        idx = np.random.default_rng(0).choice(idx, min(max_lidar, len(idx)), replace=False)
        tr.append(go.Scatter3d(x=np.round(L["x"][idx] - hx, 1), y=np.round(L["y"][idx] - hy, 1),
                               z=np.round(L["z"][idx], 1), mode="markers", marker=dict(size=1.2, color="#888"),
                               name=f"Lidar ({len(idx)} pts)", visible="legendonly", hoverinfo="skip"))
    lim = np.array(site.poly.exterior.coords)
    tr.append(go.Scatter3d(x=lim[:, 0] - hx, y=lim[:, 1] - hy, z=site.ground(lim[:, 0], lim[:, 1]) + 0.5, mode="lines",
                           line=dict(color="black", width=6), name="Survey limits"))
    tr.append(go.Scatter3d(x=[0], y=[0], z=[site.home_ground + 1], mode="markers+text", text=["HOME"],
                           marker=dict(size=7, color="yellow", line=dict(color="black", width=2)), name="HOME"))
    if building is not None:
        C = building["corners"]; Cc = np.r_[C, C[:1]]
        for z in (building["base"], building["roof"]):
            tr.append(go.Scatter3d(x=Cc[:, 0] - hx, y=Cc[:, 1] - hy, z=np.full(5, z), mode="lines",
                                   line=dict(color="orange", width=5), name="Building box", legendgroup="bld",
                                   showlegend=z == building["base"]))
    for name, col, wps, ph in data:
        g = name
        tr.append(go.Scatter3d(x=wps[:, 0] - hx, y=wps[:, 1] - hy, z=wps[:, 2], mode="lines", line=dict(color=col, width=4),
                               name=f"{name}: path", legendgroup=g))
        if not ph: continue
        P = np.array([q[0] for q in ph])
        tr.append(go.Scatter3d(x=P[:, 0] - hx, y=P[:, 1] - hy, z=P[:, 2], mode="markers", marker=dict(size=2.5, color=col),
                               name=f"{name}: {len(ph)} photos", legendgroup=g, hoverinfo="text",
                               text=[f"{name} #{i + 1}" for i in range(len(ph))]))
        ox, oy, oz, fx, fy, fz = [], [], [], [], [], []
        for i, q in enumerate(ph):
            c = camera(*q)
            dirs = np.array([f * c["ax"] + sx * sw / 2 * c["rt"] + sy * sh / 2 * c["uc"]
                             for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1))])
            cp = _cast(site, c["pos"], dirs)
            for j in (0, 1, 2, 3, 0):
                ox.append(round(cp[j, 0] - hx, 1)); oy.append(round(cp[j, 1] - hy, 1)); oz.append(round(cp[j, 2] + 0.3, 1))
            ox.append(None); oy.append(None); oz.append(None)
            if i % nth == 0:
                for j in range(4):
                    fx += [c["pos"][0] - hx, cp[j, 0] - hx, None]; fy += [c["pos"][1] - hy, cp[j, 1] - hy, None]
                    fz += [c["pos"][2], cp[j, 2], None]
        tr.append(go.Scatter3d(x=ox, y=oy, z=oz, mode="lines", line=dict(color=col, width=1.5), opacity=0.6,
                               name=f"{name}: footprints", legendgroup=g, hoverinfo="skip"))
        tr.append(go.Scatter3d(x=fx, y=fy, z=fz, mode="lines", line=dict(color=col, width=1),
                               name=f"{name}: view cones (every {nth}th)", legendgroup=g, hoverinfo="skip"))
    xr, yr = [x0 - hx, x1 - hx], [y0 - hy, y1 - hy]
    zr = [float(np.nanmin(gz)), float(max(np.nanmax(gz), max(tops))) + 5]
    mx = max(xr[1] - xr[0], yr[1] - yr[0])
    asp = lambda ve: dict(x=(xr[1] - xr[0]) / mx, y=(yr[1] - yr[0]) / mx, z=ve * (zr[1] - zr[0]) / mx)
    tot = sum(counts.values())
    fig = go.Figure(tr)
    fig.update_layout(
        title=dict(text=f"Camera plan set: {tot} photos in {len(counts)} flights", font=dict(size=14)), template="plotly_white",
        scene=dict(xaxis=dict(title="East of HOME (m)", range=xr), yaxis=dict(title="North of HOME (m)", range=yr),
                   zaxis=dict(title="AMSL (m)", range=zr), aspectmode="manual", aspectratio=asp(1)),
        legend=dict(groupclick="toggleitem", font=dict(size=10)), margin=dict(l=0, r=0, t=50, b=0),
        updatemenus=[dict(type="buttons", direction="right", x=0, y=1, xanchor="left",
                          buttons=[dict(label=f"Vert {v}x", method="relayout", args=[{"scene.aspectratio": asp(v)}])
                                   for v in (1, 2, 3, 5)])])
    html = fig.to_html(include_plotlyjs=True, full_html=True)
    tag = f'<script id="photo-counts" type="application/json">{json.dumps(counts)}</script>'
    html = html.replace("</body>", tag + "\n</body>", 1)
    with open(out_html, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    return dict(file=os.path.basename(out_html), size_mb=round(os.path.getsize(out_html) / 1e6, 1),
                photos=counts, view_cone_every=nth)
