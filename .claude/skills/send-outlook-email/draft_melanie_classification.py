"""Create an Outlook draft for Melanie Foran re: existing-line classification scope."""
import win32com.client
import re

outlook = win32com.client.Dispatch("Outlook.Application")
mail = outlook.CreateItem(0)

mail.To = "mforan@ferguselectric.coop"
mail.Subject = "Hilger-Roy Lidar - quick question on existing-line classification"

# STEP 1: Display first to load the user's default signature
mail.Display()

# STEP 2: Capture the signature HTML
sig_html = mail.HTMLBody

# STEP 3: Build the body HTML
body_html = r"""<div style="font-family:Calibri,sans-serif; font-size:11pt; color:#000000;">
<p>Hi Melanie,</p>

<p>One follow-up as I finalize the proposal. Our deliverable is a classified LAS, so every point in the survey area needs a class code (conductor, pole, ground, vegetation, etc.).</p>

<p>The 8-mile same-side stretch is straightforward: the existing line is a design constraint there (construction sequencing, clearance with the energized line), so we&rsquo;ll classify it fully alongside the new line.</p>

<p>The question is the 20-mile opposite-side stretch. Parts of the existing line will fall inside our survey corridor on those miles, but the line itself isn&rsquo;t a design constraint. Two options:</p>

<ul>
<li><b>Classify it the same as the rest of the corridor.</b> Every point on the existing line gets its proper class &mdash; consistent, complete dataset.</li>
<li><b>Leave those points unclassified.</b> Lower cost to Fergus &mdash; the existing line shows up in the LAS as raw unclassified points if anyone goes looking later.</li>
</ul>

<p>My instinct is to classify everything for consistency, but I want to make sure you&rsquo;re not paying for work HDR doesn&rsquo;t need. Happy either way &mdash; what&rsquo;s your preference?</p>

<p>Once you send the Google Earth file with the new route, I&rsquo;ll get the proposal updated.</p>

<p>Thanks,<br>
Ryan</p>
</div>
"""

# STEP 4: Insert body before the signature using string slicing (not re.sub)
if "<body" in sig_html.lower():
    match = re.search(r"<body[^>]*>", sig_html, re.IGNORECASE)
    if match:
        pos = match.end()
        mail.HTMLBody = sig_html[:pos] + body_html + sig_html[pos:]
    else:
        mail.HTMLBody = body_html + sig_html
else:
    mail.HTMLBody = body_html + sig_html

print("Draft opened in Outlook.")
