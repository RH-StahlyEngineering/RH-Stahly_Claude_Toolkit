# Rebuild the footer page-number run as separate, fully formatted runs (LibreOffice ignores
# formatting on fields that share a run and have no cached result).
import re, sys, zipfile, shutil

src = sys.argv[1]
TITLE = sys.argv[2] if len(sys.argv) > 2 else 'UAV Project Folder Standard'  # footer title
tmp = src + '.tmp'
RPR = ('<w:rPr><w:rFonts w:ascii="Rockwell" w:cs="Rockwell" w:eastAsia="Rockwell" w:hAnsi="Rockwell"/>'
       '<w:i/><w:iCs/><w:color w:val="FFFFFF"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>')

def run(inner): return f'<w:r>{RPR}{inner}</w:r>'
def field(code, cached):
    return (run('<w:fldChar w:fldCharType="begin"/>') + run(f'<w:instrText xml:space="preserve"> {code} </w:instrText>') +
            run('<w:fldChar w:fldCharType="separate"/>') + run(f'<w:t>{cached}</w:t>') + run('<w:fldChar w:fldCharType="end"/>'))

with zipfile.ZipFile(src) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if re.match(r'word/footer\d*\.xml', item.filename):
            x = data.decode('utf-8')
            m = re.search(r'<w:r><w:rPr>(?:(?!</w:r>).)*?PAGE</w:instrText>.*?NUMPAGES</w:instrText>.*?</w:r>', x, re.S)
            if not m: sys.exit('footer page run not found')
            new = (run('<w:t xml:space="preserve">' + TITLE + '  |  Page </w:t>') + field('PAGE', '1') +
                   run('<w:t xml:space="preserve"> of </w:t>') + field('NUMPAGES', '1'))
            x = x[:m.start()] + new + x[m.end():]
            data = x.encode('utf-8')
        zout.writestr(item, data)
shutil.move(tmp, src)
print('footer fixed')
