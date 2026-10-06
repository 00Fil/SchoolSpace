const { chromium } = require('/data/pg-qa/node_modules/playwright');
const fs=require('fs'),cp=require('child_process');
const B='http://127.0.0.1:5175',AXE='/data/pg-qa/node_modules/axe-core/axe.min.js';
(async()=>{
 const cred=JSON.parse(fs.readFileSync('/data/v07-ui-credentials.json','utf8'));
 const user=process.env.U||cred.username, pw=process.env.U?cred.portal[process.env.U]:cred.password;
 const browser=await chromium.launch({headless:true,executablePath:cp.execSync('which chromium').toString().trim(),args:['--no-sandbox']});
 const ctx=await browser.newContext({viewport:{width:+(process.env.W||1440),height:1000},locale:'it-IT',timezoneId:'Europe/Rome'});const page=await ctx.newPage();
 await page.goto(B);await page.evaluate(t=>localStorage.setItem('ripetizioni-ui',JSON.stringify({theme:t,motion:'reduce'})),process.env.T||'light');
 await page.goto(B);await page.getByLabel('Nome utente').fill(user);await page.getByLabel('Password',{exact:true}).fill(pw);await page.getByRole('button',{name:'Accedi'}).click();await page.getByRole('heading',{level:1}).waitFor();
 const seen={};
 for(const r of (process.env.R||'panoramica').split(',')){await page.goto(B+'/#/'+r);await page.waitForTimeout(1500);
  if(process.env.CLICK){await page.getByRole('button',{name:process.env.CLICK,exact:true}).first().click();await page.waitForTimeout(900);}
  await page.addScriptTag({path:AXE});
  const v=await page.evaluate(async()=>(await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}})).violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({t:n.target.join(' '),d:n.any[0]?.data?{fg:n.any[0].data.fgColor,bg:n.any[0].data.bgColor,ratio:n.any[0].data.contrastRatio,size:n.any[0].data.fontSize,exp:n.any[0].data.expectedContrastRatio}:n.failureSummary?.slice(0,160)}))})));
  for(const x of v)for(const n of x.nodes){const k=x.id+JSON.stringify(n.d);if(seen[k])continue;seen[k]=1;console.log(r,x.id,n.t.slice(0,90),JSON.stringify(n.d));}}
 await browser.close();process.exit(0);
})();
