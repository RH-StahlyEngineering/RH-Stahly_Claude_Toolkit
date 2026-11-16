// add-line-v2.js — reliable +Add Line. Input add2.json: [{"s":"<project search>","phase":"<phase text>","task":"<task text, omit if the phase has none>"}]. Output {allAdded, missing, res}; allAdded comes from a reload, so trust it over res. Reloads per row; clicks lookup TDs with mousedown/up; Select; Save.
const tabs = await browser.listPages();
const page = await browser.getPage(tabs.find(t=>t.url&&t.url.includes('deltekfirst.com')).id);
const rows = JSON.parse(await readFile("add2.json"));const res=[];
const cen=(sel)=>page.evaluate(sel);
for (const q of rows){
  await page.reload();await page.waitForTimeout(6000);
  const add=await page.evaluate(()=>{const b=[...document.querySelectorAll('button')].find(e=>e.textContent.trim()==='+Add Line'&&e.offsetParent);const r=b.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
  await page.mouse.click(add.x,add.y);await page.waitForTimeout(1500);
  const pi=await page.evaluate(()=>{const i=[...document.querySelectorAll('input.input-element.search-input.searchCol')].find(i=>i.offsetParent&&!i.className.includes('locked'));const r=i.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
  await page.mouse.click(pi.x,pi.y);await page.waitForTimeout(400);
  await page.keyboard.type(q.s,{delay:80});await page.waitForTimeout(4000);
  let has=await page.evaluate(()=>!![...document.querySelectorAll('.ui-dialog,[role=dialog]')].find(d=>d.offsetParent));
  if(!has){await page.keyboard.press('F2');await page.waitForTimeout(500);
    const mg=await page.evaluate(()=>{const i=[...document.querySelectorAll('.search-icon,.icon-search,[class*=search][class*=btn],button[class*=search]')].filter(e=>e.offsetParent);const e=i[0];if(!e)return null;const r=e.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
    if(mg){await page.mouse.click(mg.x,mg.y);await page.waitForTimeout(3000);}
    has=await page.evaluate(()=>!![...document.querySelectorAll('.ui-dialog,[role=dialog]')].find(d=>d.offsetParent));}
  if(!has){res.push({q,err:'no dialog'});continue;}
  const f=await page.evaluate((s)=>{const d=[...document.querySelectorAll('.ui-dialog,[role=dialog]')].find(d=>d.offsetParent);const fi=d.querySelector('input[placeholder="Find Project"]');if(fi&&fi.value!==s){const r=fi.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}}return null},q.s);
  if(f){await page.mouse.click(f.x,f.y,{clickCount:3});await page.keyboard.press('Delete');await page.keyboard.type(q.s,{delay:80});await page.waitForTimeout(2500);}
  for (const t of [q.s,q.phase].concat(q.task?[q.task]:[])){
    const c=await page.evaluate((t)=>{const d=[...document.querySelectorAll('.ui-dialog,[role=dialog]')].find(d=>d.offsetParent);const r=[...d.querySelectorAll('tr')].filter(r=>r.offsetParent&&r.textContent.includes(t)).sort((a,b)=>a.textContent.length-b.textContent.length)[0];if(!r)return null;const b=r.querySelector('td').getBoundingClientRect();return{x:b.x+b.width/2,y:b.y+b.height/2}},t);
    if(!c){res.push({q,err:'miss '+t});break;}
    await page.mouse.move(c.x,c.y);await page.mouse.down();await page.mouse.up();await page.waitForTimeout(1500);
  }
  await page.evaluate(()=>{const b=[...document.querySelectorAll('span,button')].find(e=>e.offsetParent&&e.textContent.trim()==='Select');b&&b.click()});await page.waitForTimeout(2000);
  await page.evaluate(()=>{const b=[...document.querySelectorAll('span,button')].find(e=>e.offsetParent&&e.textContent.trim()==='Save');b&&b.click()});await page.waitForTimeout(4000);
  res.push({q,ok:await page.evaluate((a)=>[...document.querySelectorAll('.gridBody.absolute')[0].querySelectorAll('tr')].some(r=>r.textContent.includes(a.s)&&(!a.task||r.textContent.includes(a.task))),{s:q.s,task:q.task})});
}
// Final check after a fresh reload: a row counts only if its project AND task are on the saved sheet.
await page.reload();await page.waitForTimeout(6000);
const missing=await page.evaluate((qs)=>{const rows=[...document.querySelectorAll('.gridBody.absolute')[0].querySelectorAll('tr')].map(r=>r.textContent);return qs.filter(q=>!rows.some(t=>t.includes(q.s)&&t.includes(q.phase)&&(!q.task||t.includes(q.task))))},rows);
console.log(JSON.stringify({allAdded:missing.length===0,missing,res}));
