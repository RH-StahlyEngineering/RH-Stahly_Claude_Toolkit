# Gotchas (learned on Toole, job 2071-07D26)

- **Aerial imagery extent.** The ArcGIS World_Imagery export stretches the image to the requested size. Request `size` with the same aspect as the bbox in degrees (`h = w * dlat / dlon`) so the returned extent equals the request, and cap resolution at about 2.5e-6 deg/px (finer returns HTTP 500). Python urllib sometimes gets 500 where curl succeeds; use curl.
- **Ground-scaled projects.** Prior TBC jobs may be scaled to ground about a point (Shelby 2019: about CP1 by 1.0004209515). Unscale before converting to lat/lon; check one point against an OPUS or known value.
- **Heights.** Lidar/DTM elevations are NAVD88 GEOID18 orthometric and approximate (~0.5 ft): label them "approx". Older Stahly elevations may be on GEOID12B; convert with the NGS geoid API (`geodesy.noaa.gov/api/geoid/ght?lat=&lon=&model=14` for GEOID18, 13 for GEOID12B).
- **Flight plan home.** The plan's HOME must be where the pilot takes off; a lower launch flew the Toole plans low.
- **UNC paths.** Run share commands from PowerShell. Git Bash rewrites `\\server\share` arguments and cannot mkdir on a share.
- **Open PDF.** A PDF open in a viewer silently blocks regeneration; `render_card.ps1` renders to temp then copies and fails loudly.
- **Email attachments.** The Outlook connector only attaches files under `C:\Users\<user>`; copy from shares first. Sending to RH himself needs his "send" / "no draft" in the conversation.
- **Street View.** The built-in browser renders Street View black; use Claude in Chrome. Never open Google API/service URLs (they download files). Pano GPS is offset 5-10 m: identify features in Street View, place them from the aerial.
- **811 ticket numbers** arrive in the Outlook folder "811 Locates" from mt@occinc.com, not the Inbox.
- **Targets** at the edge of the flight are seen in few photos; keep them at least one image footprint inside photo coverage.
- **Grid not in PROJ.** RMTCRS zones (e.g. Milk River EPSG 7094) may be missing from the local PROJ database. Give `proj4` in points.json instead: Milk River intl ft = `+proj=lcc +lat_1=48.5 +lat_0=48.5 +lon_0=-111 +k_0=1.000145 +x_0=150000 +y_0=200000 +ellps=GRS80 +towgs84=0,0,0 +units=ft +no_defs` (checked: pt 60 -> N 659169.578 E 284797.944).
