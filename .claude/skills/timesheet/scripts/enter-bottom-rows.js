// enter-bottom-rows.js — enter cells enter-timesheet.js reports popup_not_open/row_not_found (rows near grid bottom). Reads entries.json; tall viewport + real mouse click on the day input.
const tabs = await browser.listPages();const page = await browser.getPage(tabs.find(t=>t.url&&t.url.includes('deltekfirst.com')).id);
await page.setViewportSize({width:1900,height:1600});
const E=JSON.parse(await readFile("entries.json")).entries;const D={Sun:0,Mon:1,Tue:2,Wed:3,Thu:4,Fri:5,Sat:6};const res=[];
for(const e of E){
  await page.reload();await page.waitForTimeout(6000);
  const rc=await page.evaluate((a)=>{const rows=[...document.querySelectorAll('.gridBody.absolute')[0].querySelectorAll('tr')];const r=rows.find(r=>r.offsetParent&&r.textContent.includes(a.p)&&r.textContent.includes(a.t));if(!r)return null;r.scrollIntoView({block:'center'});const b=r.querySelectorAll('td')[1].getBoundingClientRect();return{x:b.x+b.width/2,y:b.y+b.height/2}},{p:e.project_number,t:e.task_name});
  if(!rc){res.push([e.src,'row']);continue;}
  await page.waitForTimeout(500);
  const rc2=await page.evaluate((a)=>{const r=[...document.querySelectorAll('.gridBody.absolute')[0].querySelectorAll('tr')].find(r=>r.offsetParent&&r.textContent.includes(a.p)&&r.textContent.includes(a.t));const b=r.querySelectorAll('td')[1].getBoundingClientRect();return{x:b.x+b.width/2,y:b.y+b.height/2}},{p:e.project_number,t:e.task_name});
  await page.mouse.click(rc2.x,rc2.y);await page.waitForTimeout(1000);
  const ip=await page.evaluate((di)=>{const ins=[...document.querySelectorAll('input.input-element.number_input')].filter(i=>i.offsetParent).sort((a,b)=>a.getBoundingClientRect().x-b.getBoundingClientRect().x);const r=ins[di].getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}},D[e.day]);await page.mouse.click(ip.x,ip.y);
  await page.waitForTimeout(1000);
  const open=await page.evaluate(()=>{const r=document.getElementById('regHrs');return !!(r&&r.offsetParent)});
  if(!open){res.push([e.src,'nopopup',rc2.y]);continue;}
  await page.evaluate((a)=>{const reg=document.getElementById('regHrs');reg.focus();reg.select();reg.value=String(a.h);['input','change','blur'].forEach(t=>reg.dispatchEvent(new Event(t,{bubbles:true})));const ce=document.getElementById('commentEntry');ce.focus();ce.textContent=a.c;ce.dispatchEvent(new InputEvent('input',{bubbles:true,data:a.c,inputType:'insertText'}));['change','blur'].forEach(t=>ce.dispatchEvent(new Event(t,{bubbles:true})));const f=document.querySelector('input[name="commentDdwn"]');if(f){f.value=a.c;f.dispatchEvent(new Event('input',{bubbles:true}))}},{h:e.hours,c:e.comment});
  const ok=await page.evaluate((c)=>document.getElementById('commentEntry').textContent===c,e.comment);
  await page.evaluate(()=>{const s=[...document.querySelectorAll('span')].find(el=>el.textContent.trim()==='Save'&&el.offsetParent);s&&s.click()});await page.waitForTimeout(2500);
  res.push([e.src,ok?'entered':'comment_fail']);
}
console.log(JSON.stringify(res));
