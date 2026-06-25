"""Round-2 Rylan email — same content as v1, updated fee table to match the
rounded-to-$100 totals, and now attaches both the KML and the branded proposal PDF."""
import win32com.client
import re

outlook = win32com.client.Dispatch("Outlook.Application")
mail = outlook.CreateItem(0)

mail.To = "rstahly@seaeng.com"
mail.Subject = "Hilger-Roy LiDAR proposal - want your eyes before I send"

mail.Display()
sig_html = mail.HTMLBody

body_html = r"""<div style="font-family:Calibri,sans-serif; font-size:11pt; color:#000000;">
<p>Hey Rylan,</p>

<p>Working on the revised Hilger-Roy LiDAR proposal for Fergus and want your eyes on it before I send. Way more meat than the October version &mdash; $85.8K total versus the $55.5K we bid in October. The branded proposal PDF is attached, along with Melanie&rsquo;s KML of the new alignment.</p>

<h3 style="margin-bottom:4px;">Scope Changes Since October</h3>
<p>As you know, the original was an unclassified LAS plus planimetric CAD extraction. HDR now wants a fully classified LAS per their feature codes, an ECW ortho, and an ASPRS accuracy report. That classification work is most of the price jump.</p>
<p>Melanie&rsquo;s KML shows 28.1 miles of new alignment, an asymmetric corridor crossing the highway, and seven &ldquo;Extra Survey&rdquo; polygons HDR wants on top of the standard buffer. Plus ~30 logical taps off the main line where I&rsquo;d assumed 8-10 in October. Total survey footprint is ~1,060 acres.</p>

<h3 style="margin-bottom:4px;">Fee Breakdown ($85,800 total, ~508 hours)</h3>
<p style="margin-bottom:4px;">Each line item rounded to the nearest $100; grand total is computed in code from the rounded rows.</p>
<table style="border-collapse:collapse; font-size:10.5pt; margin-top:4px;">
<tr style="background:#e9eef5;"><td style="padding:4px 10px;border:1px solid #ccc;"><b>Phase</b></td><td style="padding:4px 10px;border:1px solid #ccc;"><b>Hours</b></td><td style="padding:4px 10px;border:1px solid #ccc;"><b>Labor</b></td><td style="padding:4px 10px;border:1px solid #ccc;"><b>Expenses</b></td><td style="padding:4px 10px;border:1px solid #ccc;"><b>Subtotal</b></td></tr>
<tr><td style="padding:4px 10px;border:1px solid #ccc;">1. PM / Admin / QA-QC</td><td style="padding:4px 10px;border:1px solid #ccc;">40</td><td style="padding:4px 10px;border:1px solid #ccc;">$6,700</td><td style="padding:4px 10px;border:1px solid #ccc;">&mdash;</td><td style="padding:4px 10px;border:1px solid #ccc;">$6,700</td></tr>
<tr><td style="padding:4px 10px;border:1px solid #ccc;">2. Pre-field Prep</td><td style="padding:4px 10px;border:1px solid #ccc;">34</td><td style="padding:4px 10px;border:1px solid #ccc;">$5,300</td><td style="padding:4px 10px;border:1px solid #ccc;">&mdash;</td><td style="padding:4px 10px;border:1px solid #ccc;">$5,300</td></tr>
<tr><td style="padding:4px 10px;border:1px solid #ccc;">3. Field Work (acquisition + checkpoints)</td><td style="padding:4px 10px;border:1px solid #ccc;">124</td><td style="padding:4px 10px;border:1px solid #ccc;">$17,600</td><td style="padding:4px 10px;border:1px solid #ccc;">$10,700</td><td style="padding:4px 10px;border:1px solid #ccc;">$28,300</td></tr>
<tr><td style="padding:4px 10px;border:1px solid #ccc;">4. Processing (trajectory, georef, ortho)</td><td style="padding:4px 10px;border:1px solid #ccc;">54</td><td style="padding:4px 10px;border:1px solid #ccc;">$9,100</td><td style="padding:4px 10px;border:1px solid #ccc;">&mdash;</td><td style="padding:4px 10px;border:1px solid #ccc;">$9,100</td></tr>
<tr><td style="padding:4px 10px;border:1px solid #ccc;">5. Classification (the big bucket)</td><td style="padding:4px 10px;border:1px solid #ccc;">201</td><td style="padding:4px 10px;border:1px solid #ccc;">$27,800</td><td style="padding:4px 10px;border:1px solid #ccc;">&mdash;</td><td style="padding:4px 10px;border:1px solid #ccc;">$27,800</td></tr>
<tr><td style="padding:4px 10px;border:1px solid #ccc;">6. Deliverables &amp; client review</td><td style="padding:4px 10px;border:1px solid #ccc;">55</td><td style="padding:4px 10px;border:1px solid #ccc;">$8,600</td><td style="padding:4px 10px;border:1px solid #ccc;">&mdash;</td><td style="padding:4px 10px;border:1px solid #ccc;">$8,600</td></tr>
<tr style="background:#fffae6; font-weight:bold;"><td style="padding:4px 10px;border:1px solid #ccc;">TOTAL</td><td style="padding:4px 10px;border:1px solid #ccc;">508</td><td style="padding:4px 10px;border:1px solid #ccc;">$75,100</td><td style="padding:4px 10px;border:1px solid #ccc;">$10,700</td><td style="padding:4px 10px;border:1px solid #ccc;">$85,800</td></tr>
</table>
<p style="margin-top:8px;">Equivalent unit rate: <b>$3,050 per mile</b> across 28.132 miles. Phase 3 expenses include $9,900 for the MiniRanger-3 Lite equipment fee (built into the total, not on top), 600 mi mileage @ $0.75, and 6 per-diem days @ $54.</p>

<h3 style="margin-bottom:4px;">Staff and Roles</h3>
<ul>
<li><b>Ryan Harbach, P.L.S.</b> (LPS2, $168/hr) &mdash; Project Lead. PM, field crew, trajectory/processing, senior classification, deliverable assembly, client coordination.</li>
<li><b>Taylor Tennant</b> (LST1, $115/hr) &mdash; Field crew (flying alongside me) and production classification work in TBC.</li>
<li><b>Nate Bolton</b> (LSI4, $143/hr) &mdash; Field crew alongside Ryan and Taylor. Base station setup/teardown, aerial targets, ground truthing.</li>
<li><b>Rylan Stahly, P.L.S.</b> (LPS4, $180/hr) &mdash; Project Checker / QA reviewer (you).</li>
</ul>

<h3 style="margin-bottom:4px;">How We&rsquo;re Going to Do the Work (Acquisition)</h3>
<p>Flight plan: Phoenix MiniRanger-3 Lite (Riegl miniVUX-3UAV scanner) at 250 ft AGL / 15 mph, <b>plus DJI Zenmuse P1 camera</b> on the same UAV mission, flown to whatever altitude/speed gives sufficient resolution on the power line structures. The P1 photogrammetry isn&rsquo;t a nice-to-have &mdash; it drives the orthomosaic deliverable and is what we use to place conductor attachment points later.</p>
<p>On density: the test I ran earlier this year on a suburban Montana dataset (195K m&sup2; with 17.6M points = 90 pts/m&sup2;) was enough for reliable TBC distribution wire extraction. Phoenix&rsquo;s published MiniRanger-3 LITE sample at 60 m AGL and 6 m/s yielded 473 pts/m&sup2;. Scaling to our flight (76 m AGL, 6.7 m/s):</p>
<p style="margin-left: 30px;">473 &times; (60/76) &times; (6/6.7) &asymp; <b>~333 pts/m&sup2;</b></p>
<p>That puts us ~3.7&times; over the 90 threshold &mdash; standard single pass clears it.</p>
<p>Two-man flying crew (me and Taylor). Bolton handles base stations, aerial targets, and ground checkpoints. 60 ASPRS-spec ground checkpoints (30 NVA + 30 VVA) tied to Arrow Creek Surveying&rsquo;s control. Not specifying base stations vs MTSRN for the conventional checkpoint work in the proposal &mdash; we&rsquo;ll figure that out later. Also need to verify with Melanie whether there are any shield wires on the existing distribution before we start classifying &mdash; doesn&rsquo;t change the number since we&rsquo;d classify them individually anyway.</p>

<h3 style="margin-bottom:4px;">How We&rsquo;re Going to Classify</h3>
<p>Biggest-paintbrush-to-smallest, where each new classification pulls from a larger bucket so we never overwrite small features with bulk operations. Step by step:</p>
<ol>
<li><b>Starting point: TBC auto-classify, refine on a sample section, then train + apply.</b> Run TBC&rsquo;s auto-classifier on the whole site, hand-clean a representative section, then use the cleaned section as a training set to re-run classification across the rest of the corridor. Cleaner starting point than auto-class alone.</li>

<li><b>Ground (200).</b> TBC auto-class tends to pull vegetation into ground. To handle that, we&rsquo;ll build a LandXML ground surface from the cleaner sections in TBC, then bring the surface into Global Mapper Pro and use its &ldquo;Select Lidar by Distance&rdquo; tool (Search Near Loaded Terrain) to select points within a defined vertical buffer of the surface and reclassify those as ground. Points outside the buffer stay in their pre-classification state until we come back to them. <b>Row 57 = 45 hrs (covers Ground + Water).</b></li>

<li><b>Things that look like ground but aren&rsquo;t.</b> Water (210) and roads (230) get pulled out of the ground class. Road classification uses 2D centerline polylines drawn over the 17 highway tangents I identified in Google Earth, offset both sides, buffer-select, plus manual classification of 5 arterial roads per mile at 10 min each. Cattle guards classified as road per HDR. <b>Row 58 = 25 hrs.</b></li>

<li><b>Buildings, bins, tanks, fences, poles.</b> Buildings (825) + grain bins (885) + storage tanks (880) are 90% auto / 10% manual cleanup; bin/tank separation from generic building is the manual part. Fences (810) are manual centerline trace at top of fence (1.5 mi/hr productivity) plus 3D prism buffer (about 1 ft horizontal, 3 ft vertical). Power poles (710) get a <i>liberal</i> classification &mdash; goal is to capture every pole even if we over-classify, because every powerline-related feature code after this depends on having every pole identified. <b>Row 60 = 6 hrs, Row 61 = 47 hrs.</b></li>

<li><b>Pole extraction.</b> Extract poles as discrete features. From there we can zoom-to from one pole to the next using TBC/Agisoft&rsquo;s zoom-to function and work the corridor pole-by-pole. <b>Included in Row 63.</b></li>

<li><b>Conductor attachments (540) from photogrammetry.</b> Same-side 8 mi only. Manually place attachment points using the P1 photogrammetry imagery alongside the cloud &mdash; ~560 points across the stretch at 1-2 min each. Points in space at each pole. <b>Included in Row 63.</b></li>

<li><b>Attachment structures via buffer.</b> Once attachment points are placed, buffer up or down (depending on whether the line attaches at top or bottom of the hardware) by a fixed distance and classify all points inside the buffer as attachment structure. Assumes uniform structure size, which holds for distribution. <b>Included in Row 63.</b></li>

<li><b>Overhead lines (610/620/640) and guy wires (740).</b> TBC&rsquo;s Extract Powerline tool takes start attachment + end attachment + midpoint and auto-traces the catenary. Wire type comes from which attachment it terminates at (top = shield 620, lower = distribution 610). Guy wires manual identification at angle/dead-end/tap poles + 3D polyline buffer-classify. Don&rsquo;t overwrite the attachment-structure or pole classifications. <b>Row 63 total = 35 hrs, Row 62 (foreign crossings 641/642/643) = 8 hrs.</b></li>

<li><b>Substations (750).</b> Manual classification within fence + 50 ft buffer outside fence, both yards. <b>Row 64 = 4 hrs.</b></li>

<li><b>Vegetation (805) is the leftover bucket.</b> Once ground is classified and every other feature is classified, anything that&rsquo;s left over is either vegetation or stays unclassified (per HDR&rsquo;s preference). No dedicated vegetation pass &mdash; it&rsquo;s defined by exclusion.</li>

<li><b>Manual cleanup and reconciliation.</b> Smaller stuff (signs 831, light poles 850, bridges 895) bundled in Row 61. Traffic signals (840) likely zero on this corridor. Target &lt;5% of the site needing manual touch. <b>Row 66 LAS QA pass = 13 hrs.</b></li>
</ol>

<h3 style="margin-bottom:4px;">What We&rsquo;re Delivering and Software</h3>
<p><b>Deliverables to HDR:</b></p>
<ul>
<li>Classified LAS v1.4 point cloud per HDR&rsquo;s feature codes &mdash; two products: fully classified at native density, plus a thinned ground product at ~1 pt/m&sup2; for clean ground surface and contour generation</li>
<li>Classification Application Notes (PDF) &mdash; project-specific documentation defining how each HDR feature code was applied in this delivery, including any edge-case decisions (cattle guards as Code 230, conductor attachments only on the same-side stretch, vegetation as the leftover class, etc.)</li>
<li>Orthomosaic in ECW format covering the full survey extent</li>
<li>Ground checkpoint report per ASPRS Positional Accuracy Standards Edition 2 v2 (2024)</li>
</ul>
<p><b>Software stack:</b></p>
<ul>
<li>Phoenix Spatial Explorer &mdash; raw point cloud generation</li>
<li>NovAtel Inertial Explorer &mdash; trajectory / SBET processing</li>
<li>Trimble Business Center &mdash; primary classification engine, surface modeling, deliverable assembly</li>
<li>Global Mapper Pro &mdash; LandXML-to-terrain gridding, Select Lidar by Distance for ground reclassification, supplemental buffer-select operations</li>
<li>ArcGIS Pro / Global Mapper Pro &mdash; ECW ortho export (we have licenses for both)</li>
<li>Agisoft Metashape &mdash; P1 photogrammetry orthomosaic generation</li>
</ul>

<p>Workbook is at <code>\\Stahly\marketing\Scope-Schedule-Budget\Survey - GIS\2025\Great Falls\036-Fergus_Electric_Lidar\</code>. Branded proposal PDF and Melanie&rsquo;s KML are attached.</p>

<p>Thanks,<br>
Ryan</p>
</div>
"""

if "<body" in sig_html.lower():
    match = re.search(r"<body[^>]*>", sig_html, re.IGNORECASE)
    if match:
        pos = match.end()
        mail.HTMLBody = sig_html[:pos] + body_html + sig_html[pos:]
    else:
        mail.HTMLBody = body_html + sig_html
else:
    mail.HTMLBody = body_html + sig_html

# Two attachments: branded proposal PDF + Melanie's KML
mail.Attachments.Add(r"\\Stahly\marketing\Scope-Schedule-Budget\Survey - GIS\2025\Great Falls\036-Fergus_Electric_Lidar\20260512_Hilger_to_Roy_LiDAR_Proposal_Branded.pdf")
mail.Attachments.Add(r"\\Stahly\marketing\Scope-Schedule-Budget\Survey - GIS\2025\Great Falls\036-Fergus_Electric_Lidar\Received\Hilger to Roy TD-Line.kml")

print("Draft opened with proposal PDF + KML attached.")
