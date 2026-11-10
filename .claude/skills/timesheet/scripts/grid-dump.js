// grid-dump.js — reload, print every grid-0 row with its grid-3 hours plus grid-5 daily totals (fast hours check, ignores selection state).
const tabs = await browser.listPages();const page = await browser.getPage(tabs.find(t=>t.url&&t.url.includes('deltekfirst.com')).id);
await page.reload();await page.waitForTimeout(6000);
const r=await page.evaluate(()=>{const g=document.querySelectorAll('.gridBody.absolute');const L=[...g[0].querySelectorAll('tr')],R=[...g[3].querySelectorAll('tr')];return L.map((l,i)=>[l.textContent.replace(/\s+/g,' ').trim().slice(0,60),R[i]?[...R[i].querySelectorAll('td')].map(t=>t.textContent.trim()).filter((v,j)=>true):[]]).filter(x=>x[0])});
const tot=await page.evaluate(()=>[...document.querySelectorAll('.gridBody.absolute')[5].querySelectorAll('td')].map(t=>t.textContent.trim()).filter(Boolean));
console.log(JSON.stringify({r,tot}));
