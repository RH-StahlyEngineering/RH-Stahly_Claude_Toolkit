"""Phone page for the field: the card's content as a single Artifact page, images embedded, plus a KML
download button (publish with capabilities {"downloads": true}).

Usage:  py phone_page.py card.html field.kml [out.html]
Writes <card>_phone.html unless out.html is given. Images referenced by the card (relative paths) are embedded.
"""
import base64, json, os, re, sys

def main(card, kml, out=None):
    base = os.path.dirname(os.path.abspath(card))
    s = open(card, encoding="utf8").read()
    css = re.search(r"<style>(.*?)</style>", s, re.S).group(1).replace("@page{size:letter;margin:0.45in}", "")
    body = re.search(r"<body>(.*)</body>", s, re.S).group(1)
    def embed(m):
        p = os.path.join(base, m.group(1))
        return f'src="data:image/png;base64,{base64.b64encode(open(p, "rb").read()).decode()}"' if os.path.exists(p) else m.group(0)
    body = re.sub(r'src="([^":]+\.png)"', embed, body)
    body = re.sub(r"(<table>.*?</table>)", r'<div class="tw">\1</div>', body, flags=re.S)
    title = re.search(r"<title>(.*?)</title>", s).group(1)
    css += """
:root{color-scheme:light}
body{background:#fff;color:#000;font-size:15px;line-height:1.4}
.wrap{max-width:860px;margin:0 auto;padding-block:12px 32px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.tw{overflow-x:auto}.tw table{min-width:560px}img{max-width:100%;height:auto}.pb{break-before:auto}
@media (max-width:600px){.cols{grid-template-columns:1fr}h1{font-size:18px}}
"""
    kname = os.path.basename(kml)
    btn = ('<div><button type="button" id="kmlbtn" style="font:600 15px Arial;padding:8px 14px;border:2px solid #000;'
           f'background:#fff">Download KML</button> <span id="kmlmsg"></span></div>')
    js = ("<script>const KML=" + json.dumps(open(kml, encoding="utf8").read()) + ";const KN=" + json.dumps(kname) + ";"
          "(async()=>{const b=document.getElementById('kmlbtn'),m=document.getElementById('kmlmsg');let dl=null;"
          "try{dl=await window.claude?.use?.('downloads')}catch(e){}if(!dl){b.disabled=true;m.textContent='Download not available here.';return}"
          "b.onclick=async()=>{try{await dl.save({filename:KN,data:new Blob([KML])});m.textContent='Saved.'}"
          "catch(e){m.textContent='Not saved ('+(e&&e.code||'error')+').'}}})();</script>")
    page = (f'<title>{title}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n<style>{css}</style>\n'
            f'<div class="wrap">{btn}{body}</div>\n{js}\n')
    out = out or os.path.splitext(card)[0] + "_phone.html"
    open(out, "w", encoding="utf8").write(page)
    print(out)

if __name__ == "__main__":
    main(*sys.argv[1:4])
