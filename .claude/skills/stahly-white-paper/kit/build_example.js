const fs = require('fs');
const path = require('path');
const { ExternalHyperlink, Bookmark, InternalHyperlink, Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, Footer, AlignmentType,
  LevelFormat, HeadingLevel, BorderStyle, WidthType, ShadingType, VerticalAlign, PageNumber, HeightRule,
  TableLayoutType } = require('docx');

const BLUE = '00548C', TAN = 'BABAB1', CREAM = 'E9E6E1', NAVY = '043348', GRAY = '787878', LGRAY = 'C7C8CA', WHITE = 'FFFFFF';
const ASSETS = 'C:/Users/rharbach/.claude/skills/stahly-proposal/assets';
const logoBig = fs.readFileSync(path.join(ASSETS, 'StahlyLogo_EO_official.png'));
const logoSmall = fs.readFileSync(path.join(ASSETS, 'StahlyLogo_Artboard1_official.png'));
const offices = JSON.parse(fs.readFileSync('C:/Users/rharbach/.claude/skills/stahly-proposal/references/offices.json', 'utf8')).offices;

const PAGE_W = 12240, SIDE = 1224, BODY_W = PAGE_W - 2 * SIDE; // 9792
const none = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
const noBorders = { top: none, bottom: none, left: none, right: none };
const thin = { style: BorderStyle.SINGLE, size: 4, color: TAN };
const gridBorders = { top: thin, bottom: thin, left: thin, right: thin };

const R = (text, o = {}) => new TextRun({ text, font: 'Arial', size: 21, ...o });
const RK = (text, o = {}) => new TextRun({ text, font: 'Rockwell', ...o });
const P = (children, o = {}) => new Paragraph({ spacing: { after: 120, line: 276 }, ...o, children: Array.isArray(children) ? children : [children] });
const T = (text, o = {}) => P([R(text)], o);
// rich text: **bold** segments
const rich = (s, base = {}) => s.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(x => x.startsWith('**') ? R(x.slice(2, -2), { bold: true, ...base }) : R(x, base));
const TP = (s, o = {}) => P(rich(s), o);
const H1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, keepNext: true, children: [new TextRun(text)] });
const H2 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_2, keepNext: true, children: [new TextRun(text)] });
const B = (s, lvl = 0) => new Paragraph({ numbering: { reference: 'bul', level: lvl }, spacing: { after: 60, line: 264 }, children: rich(s) });
const N = (ref, s) => new Paragraph({ numbering: { reference: ref, level: 0 }, spacing: { after: 80, line: 264 }, children: rich(s) });

function table(widths, header, rows, o = {}) {
  const keep = o.keep;
  const cell = (content, w, isHead, fill, kp) => new TableCell({
    borders: gridBorders, width: { size: w, type: WidthType.DXA },
    shading: { fill: isHead ? BLUE : (fill || WHITE), type: ShadingType.CLEAR, color: 'auto' },
    verticalAlign: VerticalAlign.TOP,
    children: (Array.isArray(content) ? content : [content]).map((c, i, arr) => new Paragraph({ keepNext: !!keep || !!kp, spacing: { after: arr.length > 1 ? 40 : 0, line: 252 },
      ...(arr.length > 1 ? { numbering: { reference: 'bul', level: 0 } } : {}),
      children: isHead ? [R(c, { bold: true, color: WHITE, size: 19 })] : (c && c.runs ? c.runs : rich(c, { size: 19 })) }))
  });
  return new Table({
    columnWidths: widths, width: { size: widths.reduce((a, b) => a + b), type: WidthType.DXA },
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    rows: [new TableRow({ tableHeader: true, cantSplit: true, children: header.map((h, i) => cell(h, widths[i], true)) }),
      ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, widths[i], false, (o.zebra && ri % 2) ? CREAM : null, o.keepFirst && ri === 0)) }))]
  });
}

function callout(title, lines) {
  return new Table({
    columnWidths: [BODY_W], width: { size: BODY_W, type: WidthType.DXA },
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({
      width: { size: BODY_W, type: WidthType.DXA },
      borders: { top: none, bottom: none, right: none, left: { style: BorderStyle.SINGLE, size: 24, color: BLUE } },
      shading: { fill: CREAM, type: ShadingType.CLEAR, color: 'auto' },
      margins: { top: 120, bottom: 120, left: 220, right: 180 },
      children: [new Paragraph({ spacing: { after: 80 }, children: [RK(title, { bold: true, color: BLUE, size: 22 })] }),
        ...lines.map(l => new Paragraph({ spacing: { after: 60, line: 264 }, children: Array.isArray(l) ? l : rich(l, { size: 20 }) }))]
    })] })]
  });
}
const RED = 'C00000';
function caution(text) {
  return new Table({ columnWidths: [BODY_W], width: { size: BODY_W, type: WidthType.DXA },
    rows: [new TableRow({ cantSplit: true, children: [new TableCell({ width: { size: BODY_W, type: WidthType.DXA },
      borders: { top: none, bottom: none, right: none, left: { style: BorderStyle.SINGLE, size: 24, color: RED } },
      shading: { fill: 'FFFFFF', type: ShadingType.CLEAR, color: 'auto' }, margins: { top: 100, bottom: 100, left: 220, right: 180 },
      children: [new Paragraph({ spacing: { after: 0, line: 264 }, children: [R('CAUTION  ', { bold: true, color: RED, size: 20 }), ...rich(text, { size: 20 })] })] })] })] });
}
const pngSize = f => { const b = fs.readFileSync(path.join(__dirname, f)); return [b.readUInt32BE(16), b.readUInt32BE(20)]; };
const fig = (file, w, h0, alt) => { const [pw, ph] = pngSize(file); const h = Math.round(w * ph / pw); return figP(file, w, h, alt); };
const figP = (file, w, h, alt) => new Paragraph({ alignment: AlignmentType.CENTER, keepNext: false, spacing: { before: 60, after: 120 },
  children: [new ImageRun({ type: 'png', data: fs.readFileSync(path.join(__dirname, file)), transformation: { width: w, height: h },
    altText: { title: alt, description: alt, name: file } })] });
const gap = (after = 120) => new Paragraph({ spacing: { after }, children: [] });

// ---------------- COVER ----------------
const officeList = Object.entries(offices).sort((a, b) => a[1].address_band_order - b[1].address_band_order);
const fullCell = (h, fill, children, o = {}) => new TableRow({ height: { value: h, rule: HeightRule.EXACT }, cantSplit: true, children: [new TableCell({
  width: { size: PAGE_W, type: WidthType.DXA }, borders: o.borders || noBorders, shading: { fill, type: ShadingType.CLEAR, color: 'auto' },
  verticalAlign: o.v || VerticalAlign.CENTER, margins: o.margins || { top: 0, bottom: 0, left: 0, right: 0 }, children })] });

const addressBand = new Table({
  columnWidths: Array(officeList.length).fill(Math.floor((PAGE_W - 1200) / officeList.length)), width: { size: PAGE_W - 1200, type: WidthType.DXA },
  rows: [new TableRow({ children: officeList.map(([name, o]) => new TableCell({
    borders: noBorders, width: { size: Math.floor((PAGE_W - 1200) / officeList.length), type: WidthType.DXA },
    children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [R(name.toUpperCase(), { bold: true, color: TAN, size: 18 })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [R(o.street, { color: TAN, size: 17 })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [R(o.city_state_zip, { color: TAN, size: 17 })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [R(o.phone, { color: TAN, size: 17 })] })]
  })) })]
});

const firmBand = new Table({
  columnWidths: [7600, 3640], width: { size: 11240, type: WidthType.DXA },
  rows: [new TableRow({ children: [
    new TableCell({ borders: noBorders, width: { size: 7600, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER, margins: { left: 300 },
      children: [new Paragraph({ spacing: { after: 0 }, children: [RK('STAHLY', { bold: true, color: BLUE, size: 64 })] }),
        new Paragraph({ spacing: { after: 0 }, children: [RK('ENGINEERING & ASSOCIATES', { color: BLUE, size: 30 })] })] }),
    new TableCell({ borders: noBorders, width: { size: 3640, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [new ImageRun({ type: 'png', data: logoBig,
        transformation: { width: 152, height: 144 }, altText: { title: 'Stahly logo', description: 'Stahly Engineering & Associates logo', name: 'logo' } })] })] })
  ] })]
});

const coverTitle = [
  new Paragraph({ spacing: { before: 1300, after: 120 }, indent: { left: 1000, right: 1000 }, children: [RK('WHITE PAPER', { color: GRAY, size: 24, bold: true })] }),
  new Paragraph({ spacing: { after: 200 }, indent: { left: 1000, right: 1000 }, children: [RK('UAV Project Folder Standard', { bold: true, color: BLUE, size: 56 })] }),
  new Paragraph({ spacing: { after: 360 }, indent: { left: 1000, right: 1000 }, children: [RK('Where every drone file goes, why, and the tools that put it there', { italics: true, color: NAVY, size: 28 })] }),
  new Paragraph({ border: { top: { style: BorderStyle.SINGLE, size: 6, color: BLUE, space: 8 } }, spacing: { after: 60 }, indent: { left: 1000, right: 6000 }, children: [] }),
  new Paragraph({ spacing: { after: 40 }, indent: { left: 1000 }, children: [R('Survey / GIS — Remote Sensing', { color: NAVY, size: 22, bold: true })] }),
  new Paragraph({ spacing: { after: 40 }, indent: { left: 1000 }, children: [R('Ryan Harbach, P.L.S., Remote Sensing Category Lead', { color: NAVY, size: 22 })] }),
  new Paragraph({ spacing: { after: 40 }, indent: { left: 1000 }, children: [RK('October 2026  |  Version 1.008', { italics: true, color: NAVY, size: 22 })] }),
];

const H_TOTAL = 15840 - 6;
const H_BLUE = 170, H_TAN = 90, H_CREAM = 3024, H_ADDR = 1296, H_TAG = 792;
const H_TOP = H_TOTAL - H_BLUE - H_TAN - H_CREAM - H_ADDR - H_TAG;
const cover = new Table({
  columnWidths: [PAGE_W], width: { size: PAGE_W, type: WidthType.DXA }, layout: TableLayoutType.FIXED,
  rows: [
    fullCell(H_BLUE, BLUE, [new Paragraph({ children: [] })]),
    fullCell(H_TAN, TAN, [new Paragraph({ children: [] })]),
    fullCell(H_TOP, WHITE, coverTitle, { v: VerticalAlign.TOP }),
    fullCell(H_CREAM, CREAM, [firmBand], { borders: { top: { style: BorderStyle.SINGLE, size: 12, color: BLUE }, bottom: none, left: none, right: none }, margins: { left: 500, right: 500 } }),
    fullCell(H_ADDR, BLUE, [addressBand], { margins: { left: 600, right: 600 } }),
    fullCell(H_TAG, TAN, [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [RK('Engineering Excellence for More Than 50 Years', { italics: true, color: WHITE, size: 28 })] })]),
  ]
});

// ---------------- FOOTER ----------------
const footer = new Footer({ children: [new Table({
  columnWidths: [1600, 9040, 1600], width: { size: PAGE_W, type: WidthType.DXA }, indent: { size: -SIDE, type: WidthType.DXA },
  rows: [new TableRow({ height: { value: 792, rule: HeightRule.EXACT }, children: [
    new TableCell({ borders: noBorders, width: { size: 1600, type: WidthType.DXA }, shading: { fill: TAN, type: ShadingType.CLEAR, color: 'auto' }, verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [new ImageRun({ type: 'png', data: logoSmall, transformation: { width: 50, height: 38 },
        altText: { title: 'Stahly logo', description: 'Stahly logo', name: 'logo-small' } })] })] }),
    new TableCell({ borders: noBorders, width: { size: 9040, type: WidthType.DXA }, shading: { fill: TAN, type: ShadingType.CLEAR, color: 'auto' }, verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 0 }, children: [
        new TextRun({ children: ['UAV Project Folder Standard  ·  Page ', PageNumber.CURRENT, ' of ', PageNumber.TOTAL_PAGES], font: 'Rockwell', italics: true, color: WHITE, size: 22 })] })] }),
    new TableCell({ borders: noBorders, width: { size: 1600, type: WidthType.DXA }, shading: { fill: TAN, type: ShadingType.CLEAR, color: 'auto' }, children: [new Paragraph({ children: [] })] }),
  ] })]
})] });

// ---------------- BODY ----------------
const figN = (n, file, w, cap) => [fig(file, w, 0, cap), new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 0, after: 140 },
  children: [new Bookmark({ id: 'fig' + n, children: [R('Figure ' + n + '. ' + cap, { italics: true, size: 18, color: GRAY })] })] })];
const link = (anchor, text) => new InternalHyperlink({ anchor, children: [R(text, { color: BLUE, underline: {} })] });
const H1b = (id, text) => new Paragraph({ heading: HeadingLevel.HEADING_1, keepNext: true, children: [new Bookmark({ id, children: [new TextRun(text)] })] });

const body = [
  H1('1. Overview'),
  new Paragraph({ spacing: { after: 100, line: 276 }, children: [...rich('Every new UAV job (created from the project template on or after **October 15, 2026**) uses these folders and names. Read Figure 1 top to bottom; the numbers are the steps, in order. '), link('sec_rules', 'Section 2'), R(' onward is the detail.')] }),
  ...figN(1, 'fig17_master.png', 653, 'The whole story: where each file comes from, which step puts it there, who makes the folder, how long it stays.'),
  ...figN(2, 'fig13_anatomy.png', 600, 'Every file name: Flight first, then what it is, then the type.'),
  ...figN(3, 'fig17_label.png', 653, 'Need a label? Only if the datasets will be processed separately.'),

  H1b('sec_rules', '2. Rules to follow'),
  callout('The standard in one minute', [
    '**Checkin\\<flight> is where everything from the field goes.** Images from the lidar unit go in Lidar, never in Photos.',
    '**Flight = the date you flew (261015).** If the datasets will be processed separately, give the Flight a label of up to 8 letters/digits (261015_B): type it in the label box when New_Flight asks (it suggests the next free letter and checks it). The processor decides; if you are not sure, add one.',
    '**Photos from several cards or folders, one Flight?** Pick them all in the same New_Flight run. They land in one Photos folder; folders after the first get C2_, C3_.',
    '**Every file name we give starts with the Flight:** 261015_Ortho_Full.tif. Photos and base logs keep their own names.',
    '**Raw, processing and deliverables are separate,** so raw data goes to cold storage in one move.',
    '**The tools only add.** Nothing is deleted, moved, renamed or overwritten.',
  ]),
  gap(60),
  callout('Old job, new Flight?', ['If the job already has a 2-UAV folder, move its old contents into an _Archive_yymmdd folder inside it first.', [R('Then copy in the template\u2019s 2-UAV folders (location in ', { size: 20 }), link('sec_more', 'section 6'), R(').', { size: 20 })]]),
  gap(60),

  H1b('sec_names', '3. File names'),
  new Paragraph({ keepNext: true, spacing: { after: 120, line: 276 }, children: [R('The pattern is in '), link('fig2', 'Figure 2'), R('. Import_DroneMapper names the deliverables for you.')] }),
  table([9792], ['File name: what it is'], [
    ['**261015_UAV_Targets.jxl**  —  Aerial targets (AT, GCP or CP codes) for the Flight. Targets only. Lives in Ground_Control, never in 1-TBC\\Export to CAD.'],
    ['**261015_Ground_Truth.csv**  —  Independent ground truth points: PNEZD, comma separated, **no header row**.'],
    ['**261015_Ground_Truth_VS.csv**  —  Virtual Surveyor copy (header P,Y,X,Z,D), made by Make_VS_Ground_Truth.'],
    ['**261015_Camera_Positions_<vendor>.csv**  \u2014  Per-photo positions. **RTK** (from the field): New_Flight writes it from the fixed-RTK photos (header name,lat,lon,ellipsoid_height,h_acc,v_acc; decimal degrees to 9 places; ellipsoid height in metres). **PPK** (in the office): you export it from KLAU PPK, or from the lidar software (Spatial Explorer for Phoenix), into that software\u2019s Processing folder.'],
    ['**261015_Ortho_Full.tif / .png**  —  Full-resolution ortho, GeoTIFF (.tfw) and PNG (.pgw); large GeoTIFFs may come as tiles.'],
    ['**261015_Ortho_50pct.png / _10pct.png**  —  Half and one-tenth resolution ortho, PNG with .pgw. Pixel sizes in 261015_Ortho_GSD.txt.'],
    ['**261015_DEM.tif**  —  Elevation model.'],
    ['**261015_PointCloud.las / 261015_PointCloud_HighConf.las**  \u2014  Point cloud, and the high-confidence subset.'],
    ['**261015_Processing_Report.pdf**  —  Processing report.'],
  ], { zebra: true, keepFirst: true }),
  gap(60),
  B('**You export the targets JXL and ground truth CSV from TBC (or straight from the data collector) into Checkin\\<flight>\\Ground_Control.** Ground truth is always PNEZD with no header row.'),
  B('**Targets file: point codes start with AT, GCP or CP** (e.g. AT1, GCP12, CP3).'),
  B('**Your accuracy check shots are ground truth, not targets.** Never give them AT, GCP or CP codes. CP-coded points are targets.'),
  B('**Targets: at least 3 inside the photographed area, each visible in at least 5 photos.**'),
  B('**A targets CSV for CAD may sit in 1-TBC\\Export to CAD.** The targets JXL never goes there.'),
  B('**One flat Photos folder per Flight, unique names.** No card subfolders; New_Flight copies cards 2, 3 ... with C2_, C3_.'),
  B('**After a re-run, whoever re-processes moves the old results into _Archive_yymmdd** (dated the day they were replaced).'),
  B('**Cold storage is offline,** so nothing links to it. Ryan sends a yearly reminder of what is due; the job owner moves it.'),

  new Paragraph({ heading: HeadingLevel.HEADING_1, keepNext: true, pageBreakBefore: true, children: [new TextRun('4. The tools')] }),
  TP('Double-click the tools in **2-UAV\\Planning** (Import_DroneMapper is in **2-UAV\\Deliverables**). Each one\u2019s step number matches Figure 1:'),
  table([9792], ['Tool (where to double-click it): when to run it \u2014 what it does'], [
    ['**New_Flight** (2-UAV\\Planning), step 1: with the USB/SD Card plugged in (or a copy of it on your PC) \u2014 you pick the card folder(s), more than one allowed; it reads the date from the photos and asks you to confirm it, suggests the next free label if the date already has a Flight, makes the Checkin and Deliverables folders, and copies card 1 as-is and cards 2, 3 ... with C2_, C3_, and writes the RTK camera positions file from fixed-RTK photos (it warns if any photo is not fixed). The cards are not changed.'],
    [{ runs: [R('CAUTION  ', { bold: true, color: RED, size: 19 }), ...rich('**The folder date is the day you FLEW.** Example: flew 10/15, copying 10/16 \u2192 folder 261015. New_Flight reads it from the photos; check it before you continue (nothing is created until you do). Wrong date afterwards? Delete what it made (the Flight folders with any copied photos, and its RTK file in Processing\\RTK) and run it again.', { size: 19 })] }],
    ['**Make_VS_Ground_Truth** (2-UAV\\Planning), step 4: after you export ground truth into Ground_Control \u2014 makes the Virtual Surveyor copy (header P,Y,X,Z,D) in Processing\\Virtual_Surveyor, and tells you what to fix if the file is wrong.'],
    [{ runs: [...rich('**Import_DroneMapper** (2-UAV\\Deliverables), step 5: after you download the DroneMapper results \u2014 copies them from Downloads into Deliverables\\<flight> with the names in ', { size: 19 }), new InternalHyperlink({ anchor: 'sec_names', children: [R('section 3', { color: BLUE, underline: {}, size: 19 })] }), ...rich(', shows a preview first, and won\u2019t mix with existing deliverables unless you say so.', { size: 19 })] }],
    [{ runs: [R('CAUTION  ', { bold: true, color: RED, size: 19 }), ...rich('**Download DroneMapper results within 90 days.** The download link expires; the project copy is the record.', { size: 19 })] }],
  ], { zebra: true, keepFirst: true }),

  H1('5. Aerials in CAD (for drafters)'),
  TP('**MAPIINSERT the orthos into the _AP.dwg, unload all but the small one, then save.** Tested: unloaded images are not downloaded when the drawing opens (see CAD_Test_Finding.pdf in 2-UAV\\Planning).'),
  table([4400, 5392], ['Do', 'Why'], [
    ['Keep the low-resolution ortho in DWG\\Backgrounds, loaded', 'Small, fast, travels with the drawing.'],
    ['Link full and 50% from Deliverables, unloaded', 'No duplicate multi-GB copies.'],
    ['Detach images you no longer need', 'Removes even the file check on open.'],
  ], { zebra: true }),

  new Paragraph({ heading: HeadingLevel.HEADING_1, keepNext: true, pageBreakBefore: false, children: [new Bookmark({ id: 'sec_more', children: [new TextRun('6. Where to find more')] })] }),
  TP('Why: in October 2026 we found 1,510 UAV folders across 667 jobs, in three different layouts, with roughly 120 GB of duplicate copies. One standard layout stops that from growing.'),
  TP('**Project template:**', { spacing: { after: 20 }, keepNext: true }),
  new Paragraph({ spacing: { after: 0 }, indent: { left: 360 }, children: [new ExternalHyperlink({ link: 'file://FS01.Stahly.local/PROJECTS/0000-Template/-00000-Project/Survey_GIS_Data/2-UAV', children: [R('\\\\FS01.Stahly.local\\PROJECTS\\0000-Template\\', { color: BLUE, underline: {} })] })] }),
  new Paragraph({ spacing: { after: 120 }, indent: { left: 360 }, children: [new ExternalHyperlink({ link: 'file://FS01.Stahly.local/PROJECTS/0000-Template/-00000-Project/Survey_GIS_Data/2-UAV', children: [R('-00000-Project\\Survey_GIS_Data\\2-UAV', { color: BLUE, underline: {} })] })] }),
  TP('**Master copy** (tools, tests, decision log, glossary, CAD test finding):', { spacing: { after: 20 }, keepNext: true }),
  new Paragraph({ keepNext: true, spacing: { after: 0 }, indent: { left: 360 }, children: [new ExternalHyperlink({ link: 'file://STAHLY/resource%20library/2%20Department%20Resources/SURVEY_GIS/UAV/Standards%20of%20Practice/UAV_Folder_Standard', children: [R('\\\\STAHLY\\resource library\\2 Department Resources\\SURVEY_GIS\\', { color: BLUE, underline: {} })] })] }),
  new Paragraph({ spacing: { after: 120 }, indent: { left: 360 }, children: [new ExternalHyperlink({ link: 'file://STAHLY/resource%20library/2%20Department%20Resources/SURVEY_GIS/UAV/Standards%20of%20Practice/UAV_Folder_Standard', children: [R('UAV\\Standards of Practice\\UAV_Folder_Standard', { color: BLUE, underline: {} })] })] }),
  TP('**Author:** Ryan Harbach, P.L.S., Remote Sensing Category Lead (rharbach@seaeng.com). Tell the author about problems or ideas; fixes go into the master copy first, then the template.'),
];

const doc = new Document({
  creator: 'Ryan Harbach', title: 'UAV Project Folder Standard', description: 'Stahly white paper',
  styles: {
    default: { document: { run: { font: 'Arial', size: 21 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: 'Rockwell', bold: true, size: 32, color: BLUE },
        paragraph: { spacing: { before: 440, after: 160 }, outlineLevel: 0, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: BLUE, space: 4 } } } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: 'Arial', bold: true, size: 23, color: NAVY },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 1 } },
    ]
  },
  numbering: { config: [
    { reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 300 } }, run: { color: BLUE } } }] },
    { reference: 'steps', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } }, run: { color: BLUE, bold: true, font: 'Rockwell' } } }] },
  ] },
  sections: [
    { properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 0, bottom: 0, left: 0, right: 0, header: 0, footer: 0 } } }, children: [cover] },
    { properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1300, bottom: 1250, left: SIDE, right: SIDE, header: 500, footer: 0 } } },
      footers: { default: footer }, children: body },
  ]
});

Packer.toBuffer(doc).then(b => { fs.writeFileSync(path.join(__dirname, 'UAV_Folder_Standard_WhitePaper.docx'), b); console.log('ok'); });
