# Blind-locator test prompt (fill the <> slots, give the subagent nothing else)

You are a utility locator in Montana. You received the 811 ticket text below; the map
attachment did NOT come through. Draw the area you must mark onto the blank aerial, from
the ticket text alone.

Aerial (north up, <town>, <W>x<H> px; roughly <scale>): <path>/blind/aerial.png
(view with Read; zoomed/gridded crops via PIL are fine).

Rules: use ONLY the ticket text and that image. Open no other files, no web.

Outputs in <path>/blind/r<N>/ (create it):
- area.json: the marking area as ONE polygon, JSON list of [x,y] pixel vertices in order (concave OK).
- drawing.png: aerial with the polygon and identified streets labeled ("?" on guesses).
- your script.

Report: each boundary, where you put it, confidence; anything ambiguous or that would make
you call the contact.

TICKET TEXT:
---
<one ticket's full description, exactly as entered>
---
