// copy-row.js — copies the 0000-00826 6.07 row twice via row Options > Copy (separate line per proposal). Edit loop count/match as needed.
const tabs = await browser.listPages();
const page = await browser.getPage(tabs.find(t=>t.url&&t.url.includes('deltekfirst.com')).id);
const out=[];
for (let k=0;k<2;k++){
  await page.reload();await page.waitForTimeout(6000);
  const idx=await page.evaluate(()=>[...document.querySelectorAll('.gridBody.absolute')[0].querySelectorAll('tr')].findIndex(r=>r.textContent.includes('0000-00826')));
  // select row
  const rc=await page.evaluate((i)=>{const r=document.querySelectorAll('.gridBody.absolute')[0].querySelectorAll('tr')[i];r.scrollIntoView({block:'center'});const b=r.querySelectorAll('td')[1].getBoundingClientRect();return{x:b.x+b.width/2,y:b.y+b.height/2}},idx);
  await page.mouse.click(rc.x,rc.y);await page.waitForTimeout(800);
  const btns=await page.evaluate((y)=>[...document.querySelectorAll('button.rowTools_menuBtn')].filter(b=>b.offsetParent).map(b=>{const r=b.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}}),rc.y);
  const b=btns.sort((a,b)=>Math.abs(a.y-rc.y)-Math.abs(b.y-rc.y))[0];
  if(!b){out.push('no menu btn');break;}
  await page.mouse.click(b.x,b.y);await page.waitForTimeout(800);
  const ok=await page.evaluate(()=>{const m=[...document.querySelectorAll('li,a,span,div')].filter(e=>e.offsetParent&&e.textContent.trim()==='Copy');if(!m.length)return false;m[m.length-1].click();return true});
  await page.waitForTimeout(1500);
  await page.evaluate(()=>{const s=[...document.querySelectorAll('span,button')].find(e=>e.offsetParent&&e.textContent.trim()==='Save');s&&s.click()});await page.waitForTimeout(4000);
  out.push(ok);
}
await page.reload();await page.waitForTimeout(6000);
const rows=await page.evaluate(()=>[...document.querySelectorAll('.gridBody.absolute')[0].querySelectorAll('tr')].map((r,i)=>i+':'+r.textContent.replace(/\s+/g,' ').trim().slice(0,90)).filter(x=>x.length>4));
console.log(JSON.stringify(out));console.log(rows.join('\n'));
