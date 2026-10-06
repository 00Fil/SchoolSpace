const { chromium } = require('/data/pg-qa/node_modules/playwright');
const fs=require('fs'),cp=require('child_process');
const B='http://127.0.0.1:5175', EV='/data/gestionale-ripetizioni/docs/evidence', AXE='/data/pg-qa/node_modules/axe-core/axe.min.js';
const log=[];const step=(s)=>{log.push(s);console.error('· '+s);};
const axeReport=[];
async function audit(page,label){
 await page.addScriptTag({path:AXE}).catch(()=>{});
 const r=await page.evaluate(async()=>{const x=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']},resultTypes:['violations']});return x.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.length,targets:v.nodes.slice(0,4).map(n=>n.target.join(' '))}));});
 axeReport.push({page:label,violations:r});if(r.length)console.error('  axe '+label+': '+r.map(v=>v.id+'×'+v.nodes).join(', '));
 return r;
}
(async()=>{
 const cred=JSON.parse(fs.readFileSync('/data/v07-ui-credentials.json','utf8'));
 const browser=await chromium.launch({headless:true,executablePath:cp.execSync('which chromium').toString().trim(),args:['--no-sandbox']});
 const mk=async()=>{const ctx=await browser.newContext({viewport:{width:1440,height:1000},locale:'it-IT',timezoneId:'Europe/Rome'});const page=await ctx.newPage();return {ctx,page};};
 const {ctx,page}=await mk();globalThis.__page=page;const errors=[];
 const watch=(p,who)=>{p.on('pageerror',e=>errors.push(who+': '+e.message));p.on('response',r=>{const u=r.url();if(r.status()>=400&&!(u.endsWith('/api/v1/me')&&r.status()===403)&&!r.request().headers()['x-expect-error'])errors.push(`${who}: HTTP ${r.status()} ${u}`)});};
 watch(page,'centro');
 const toast=(t,p=page)=>p.locator('.toast',{hasText:t}).first().waitFor({timeout:20000});
 const modal=(p=page)=>p.locator('.modal.show');
 const api=(p,pg=page)=>pg.evaluate(async(p)=>(await fetch('/api/v1'+p,{credentials:'same-origin'})).json(),p);
 const login=async(p,u,pw)=>{await p.goto(B);await p.getByLabel('Nome utente').fill(u);await p.getByLabel('Password',{exact:true}).fill(pw);await p.getByRole('button',{name:'Accedi'}).click();await p.getByRole('heading',{level:1}).filter({hasText:/^Buon/}).waitFor();};
 await login(page,cred.username,cred.password);step('login centro');

 // 1. proposta
 await page.goto(B+'/#/proposte');await page.getByRole('button',{name:'Verifica i dati'}).click();
 await page.locator('.notice.ok',{hasText:'Dati pronti'}).waitFor();step('verifica dati: pronti (seed lun/mer/gio)');
 await page.getByRole('button',{name:'Genera la proposta'}).click();await toast('Calcolo avviato');
 await page.locator('.mini',{hasText:'Calcolo concluso'}).first().waitFor({timeout:90000});step('calcolo concluso dal worker');

 // 2. pubblica
 await page.goto(B+'/#/agenda?d=2026-10-05');
 await page.locator('button.mini',{hasText:'Pronta da rivedere'}).first().click();
 await page.locator('.sheet.show').getByRole('button',{name:'Pubblica nel calendario'}).click();
 await modal().getByText('Confermo che sono dati sintetici di prova').click();
 await modal().getByRole('button',{name:'Pubblica',exact:true}).click();
 await toast('lezioni pubblicate');
 const week=await api('/calendar/?from=2026-10-05&until=2026-10-12');const pub=week.results.filter(l=>l.state==='PUBLISHED');
 if(pub.length!==6)throw Error('attese 6 lezioni, trovate '+pub.length);
 const days=[...new Set(pub.map(l=>l.start_at.slice(0,10)))].sort();step('pubblicate 6 lezioni nei giorni '+days.join(', '));
 fs.writeFileSync('/data/v07-published.json',JSON.stringify(pub,null,1));

 // 3. motivo puntuale via API (rifiuto) e opzioni
 const lone=(()=>{const byT={};pub.forEach(l=>(byT[l.tutor]=byT[l.tutor]||[]).push(l));return Object.values(byT).sort((a,b)=>a.length-b.length)[0][0];})();
 const tue=new Date(new Date(lone.start_at).getTime()); // stesso orario, martedì della settimana
 const d0=new Date(lone.start_at);const shift=(2-((d0.getUTCDay()+6)%7)-1)*86400000; // verso martedì (indice 1)
 const tueISO=new Date(d0.getTime()+((1-((d0.getUTCDay()+6)%7))*86400000)).toISOString();
 const rej=await page.evaluate(async([id,v,s])=>{const tok=document.cookie.split('; ').find(c=>c.startsWith('csrftoken='))?.split('=')[1]||'';const r=await fetch(`/api/v1/occurrences/${id}/reschedule/`,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':tok,'Idempotency-Key':crypto.randomUUID(),'X-Expect-Error':'1'},body:JSON.stringify({expected_version:v,reason:'Prova rifiuto',start_at:s})});return {status:r.status,body:await r.json()};},[lone.id,lone.version,tueISO]);
 if(rej.status!==422||!(rej.body.violations||[]).includes('TUTOR_AVAILABILITY'))throw Error('rifiuto senza motivo puntuale: '+JSON.stringify(rej));
 step('rifiuto con motivi: '+rej.body.violations.join(', '));
 const opt=await api(`/occurrences/${lone.id}/reschedule-options/?date=${lone.start_at.slice(0,10)}`);
 step(`opzioni server: ${opt.options.filter(o=>o.ok).length}/${opt.options.length} orari validi nel giorno della lezione`);

 // 4. sposta da modale: martedì bloccato con motivo, poi mercoledì
 await page.goto(B+'/#/agenda?d='+lone.start_at.slice(0,10)+'&l='+lone.id);
 const sheet=page.locator('.sheet.show');await sheet.waitFor();
 await sheet.getByRole('button',{name:'Sposta'}).click();
 const m=modal();await m.getByRole('heading',{name:'Sposta la lezione'}).waitFor();
 await m.locator('.mv-hint',{hasText:'Orario compatibile'}).waitFor({timeout:15000}).catch(()=>{});
 const wheel=m.getByRole('spinbutton',{name:'Inizio'});const v0=Number(await wheel.getAttribute('aria-valuenow'));await wheel.focus();
 for(let i=0;i<4;i++)await page.keyboard.press('ArrowDown');await page.waitForTimeout(1200);
 const v1=Number(await wheel.getAttribute('aria-valuenow'));if(v1!==v0+4)throw Error(`ruota: attesi ${v0+4}, ottenuti ${v1}`);step('ruota da tastiera: +1 h');
 for(let i=0;i<4;i++)await page.keyboard.press('ArrowUp');await page.waitForTimeout(1200);
 await m.getByText(/^Mar/).click();await page.waitForTimeout(800);
 const why=await m.locator('.conflict.show').textContent();
 if(!/tutor non è disponibile/.test(why||''))throw Error('motivo non mostrato: '+why);
 if(!await m.getByRole('button',{name:/Sposta la lezione/}).isDisabled())throw Error('martedì non bloccato');
 const tueLabel=await m.locator('.choice',{hasText:/^Mar/}).textContent();
 step('modale: martedì bloccato con motivo «'+why.trim().slice(0,80)+'…» ('+tueLabel.trim()+')');
 await page.screenshot({path:EV+'/v0.7-sposta-motivo-1440.png'});
 await audit(page,'modale sposta (chiaro)');
 await m.getByText(/^Mer/).click();await page.waitForTimeout(800);
 const submit=m.getByRole('button',{name:/Sposta la lezione/});
 if(await submit.isDisabled()){const alt=m.locator('.conflict button');if(await alt.count()){await alt.first().click();await page.waitForTimeout(900);}}
 await m.getByLabel('Motivo dello spostamento').fill('Collaudo UI v0.7');
 await submit.click();await toast('Lezione spostata').catch(async e=>{throw Error('spostamento rifiutato: '+(await m.locator('.notice.bad').textContent().catch(()=>'?')))});step('spostamento a mercoledì salvato (nessuna disponibilità creata dal test)');
 await page.locator('.toast',{hasText:'Lezione spostata'}).getByRole('button',{name:'Annulla'}).click();
 await toast('Spostamento annullato');step('annulla spostamento eseguito');
 const after=await api('/calendar/?from=2026-10-05&until=2026-10-12');
 if(!after.results.some(l=>l.id===lone.id&&l.start_at===lone.start_at&&l.state==='PUBLISHED'))throw Error('annullamento non ha ripristinato l’orario');

 // 5. trascinamento con il mouse
 await page.waitForTimeout(1500);
 const dragDay=lone.start_at.slice(0,10);
 await page.goto(B+'/#/agenda?d='+dragDay);await page.waitForTimeout(1500);
 const card=page.locator(`.les[data-movable][data-id="${lone.id}"]`);await card.waitFor();await card.scrollIntoViewIfNeeded();
 const bb=await card.boundingBox();const heads=await page.locator('.c-head').evaluateAll(h=>h.slice(0,2).map(x=>x.getBoundingClientRect().left));const per30=heads[1]-heads[0];
 const x0=bb.x+12,y0=bb.y+bb.height/2;await page.mouse.move(x0,y0);await page.mouse.down();await page.mouse.move(x0+10,y0,{steps:3});
 let picked=null;
 for(const k of [2,4,-2,-4,6,-6,8]){await page.mouse.move(x0+k*per30/2,y0,{steps:6});await page.waitForTimeout(250);
  const st=await page.locator('.zone').getAttribute('data-state').catch(()=>null);if(st==='ok'){picked=await page.locator('.zone .zl').textContent();break;}}
 await page.mouse.up();
 if(!picked)throw Error('trascinamento: nessun orario libero trovato');
 await m.getByRole('heading',{name:'Sposta la lezione'}).waitFor();
 const when=(await m.locator('#mv-when').textContent()).trim();
 if(!picked.startsWith(when))throw Error(`modale non precompilato: zona ${picked}, modale ${when}`);
 step('trascinamento: rilascio a '+when+' apre il modale precompilato');
 await page.waitForTimeout(1200);
 const dsub=m.getByRole('button',{name:/Sposta la lezione/});
 if(await dsub.isDisabled()){const alt=m.locator('.conflict button');if(await alt.count()){await alt.first().click();await page.waitForTimeout(900);}}
 await m.getByLabel('Motivo dello spostamento').fill('Trascinamento in collaudo');await dsub.click();await toast('Lezione spostata');
 await page.locator('.toast',{hasText:'Lezione spostata'}).getByRole('button',{name:'Annulla'}).click();await toast('Spostamento annullato');step('spostamento da trascinamento salvato e annullato');

 // 6. cancella (lezione dell'altro tutor, così il portale tutor-1 resta con lezioni attive)
 await page.waitForTimeout(800);
 await page.goto(B+'/#/agenda?d=2026-10-05');await page.waitForTimeout(1200);
 const victim=pub.filter(l=>l.start_at.slice(0,10)===pub.map(x=>x.start_at).sort()[0].slice(0,10)).sort((a,b)=>b.start_at.localeCompare(a.start_at))[0];
 await page.goto(B+'/#/agenda?d='+victim.start_at.slice(0,10)+'&l='+victim.id);await page.locator('.sheet.show').getByRole('button',{name:'Cancella lezione'}).click();
 await modal().getByLabel('Motivo della cancellazione').fill('Collaudo UI v0.7');
 await modal().getByRole('button',{name:'Cancella lezione'}).click();await toast('Lezione cancellata');
 const c=await api('/calendar/?from=2026-10-05&until=2026-10-12');if(c.results.filter(l=>l.state==='CANCELLED').length!==1)throw Error('cancellazione non registrata');step('cancellazione registrata');

 // 7. configurazione con modulo strutturato
 await page.waitForTimeout(61000);
 await page.goto(B+'/#/proposte');await page.getByRole('button',{name:'Aperture',exact:true}).click();await page.locator('.mini-list .mini').first().waitFor();
 const sw0=(await api('/service-windows/')).count;
 await page.getByRole('button',{name:'Nuovo',exact:true}).click();await modal().getByRole('heading',{name:/Nuovo: aperture/}).waitFor();
 await modal().getByRole('button',{name:'Ven',exact:true}).click();
 await modal().getByRole('button',{name:'JSON avanzato'}).click();const js=await modal().locator('#js-text').inputValue();if(!/"weekday": 4/.test(js))throw Error('JSON non sincronizzato col modulo');
 await modal().getByRole('button',{name:'Modulo',exact:true}).click();
 await page.screenshot({path:EV+'/v0.7-config-modulo-1440.png'});await audit(page,'modulo configurazione (chiaro)');
 await modal().getByRole('button',{name:'Salva'}).click();await toast('Configurazione salvata');
 if((await api('/service-windows/')).count!==sw0+1)throw Error('apertura non salvata');step('apertura del venerdì creata dal modulo (JSON sincronizzato)');
 await page.getByRole('button',{name:'Competenze',exact:true}).click();const skill=page.locator('.mini-list .mini',{hasText:/approvata|da approvare/}).first();await skill.waitFor();
 const skillTxt=await skill.textContent();if(/[0-9a-f]{8}-[0-9a-f]{4}/.test(skillTxt))throw Error('UUID visibile nell’elenco: '+skillTxt);
 await skill.click();await modal().getByRole('heading',{name:/Modifica: competenze/}).waitFor();const combo=modal().locator('#cf-tutor');if(!/Tutor/.test(await combo.inputValue()))throw Error('riferimento tutor non risolto');
 await modal().getByRole('button',{name:'Chiudi'}).click();step('competenze: nomi al posto degli identificativi');

 // 8. laboratorio leggibile
 await page.goto(B+'/#/laboratorio');await page.getByRole('button',{name:'Carica lo scenario di prova'}).click();await toast('Scenario di prova caricato');
 await page.getByRole('heading',{name:/Richieste da collocare/}).waitFor();
 await page.locator('.lab-unit .check').first().click();
 await page.getByRole('button',{name:'Calcola la proposta'}).click();await page.getByRole('heading',{name:/Risultato/}).waitFor({timeout:30000});
 const placed=await page.locator('.stat',{hasText:'Lezioni collocate'}).textContent();
 if(!/5/.test(placed))throw Error('esclusione non applicata: '+placed);step('laboratorio: riepilogo, esclusione di una richiesta, 5 lezioni collocate');
 await page.screenshot({path:EV+'/v0.7-laboratorio-1440.png'});

 // 9. portali
 const people=[['tutor-planning-demo-1','tutor'],['portale-famiglia-demo','famiglia'],['portale-studente-demo','studente']];
 const portal={};
 for(const [u,who] of people){
  const P=await mk();watch(P.page,who);await login(P.page,u,cred.portal[u]);
  const nav=await P.page.locator('.rail a, .rail button').allTextContents();
  if(nav.join('|').includes('Agenda'))throw Error(who+': agenda del centro visibile');
  const cal=await P.page.evaluate(async()=>(await fetch('/api/v1/calendar/?from=2026-10-05&until=2026-10-12',{headers:{'X-Expect-Error':'1'}})).status);
  if(cal!==403)throw Error(who+': calendario del centro accessibile ('+cal+')');
  const mine=(await api('/my/lessons?from=2026-10-05&until=2026-10-12',P.page)).results;
  const vis=(await api('/students/',P.page)).results.map(s=>s.display_name);
  const allNames=[...new Set(pub.flatMap(l=>l.participants.map(p=>p.name)))];
  const shownNames=[...new Set(mine.flatMap(l=>l.participants.map(p=>p.name)))];
  if(who!=='tutor'&&shownNames.some(n=>!vis.includes(n)))throw Error(who+': nomi non autorizzati '+shownNames);
  await P.page.getByRole('heading',{name:'Prossime lezioni'}).waitFor();
  await P.page.goto(B+'/#/settimana?d='+(mine[0]?.start_at.slice(0,10)||'2026-10-05'));await P.page.locator('.event').first().waitFor();
  const cards=await P.page.locator('.event').count();
  const body=await P.page.locator('main').textContent();const leaked=who==='tutor'?[]:allNames.filter(n=>!vis.includes(n)&&body.includes(n));
  if(leaked.length)throw Error(who+': nomi trapelati '+leaked);
  portal[who]={lessons:mine.length,day_cards:cards,visible_students:vis.length,hidden_participants:mine.reduce((a,l)=>a+l.other_participants,0)};
  step(`portale ${who}: ${mine.length} lezioni, ${vis.length} studenti visibili (perimetro), ${portal[who].hidden_participants} partecipanti anonimizzati`);
  for(const theme of ['light','dark']){await P.page.evaluate(t=>{localStorage.setItem('ripetizioni-ui',JSON.stringify({theme:t,motion:'reduce'}));},theme);await P.page.reload();await P.page.locator('.event').first().waitFor();
   await audit(P.page,`portale ${who} settimana (${theme})`);
   for(const [w,h] of [[1440,1000],[390,844]]){await P.page.setViewportSize({width:w,height:h});await P.page.waitForTimeout(500);
    const d=await P.page.evaluate(()=>({sw:document.documentElement.scrollWidth,vw:innerWidth}));if(d.sw>d.vw)errors.push(`overflow portale ${who} ${w} ${theme}`);
    if(who!=='studente')await P.page.screenshot({path:`${EV}/v0.7-portale-${who}-${w}-${theme}.png`});}
   await P.page.setViewportSize({width:1440,height:1000});await P.page.goto(B+'/#/panoramica');await P.page.getByRole('heading',{name:'Prossime lezioni'}).waitFor();await P.page.waitForTimeout(600);
   await audit(P.page,`portale ${who} panoramica (${theme})`);
   if(theme==='light'&&who==='famiglia')await P.page.screenshot({path:`${EV}/v0.7-portale-${who}-panoramica-1440-light.png`});
   await P.page.goto(B+'/#/settimana?d='+(mine[0]?.start_at.slice(0,10)||'2026-10-05'));}
  await P.ctx.close();
 }
 fs.writeFileSync('/data/v07-portal.json',JSON.stringify(portal,null,1));

 // 10. palette comandi
 await page.keyboard.press('Control+k');await page.locator('.cmd.show').waitFor();await page.keyboard.type('agenda');await page.keyboard.press('Enter');
 await page.waitForURL(/#\/agenda/);step('palette comandi');

 // 11. screenshot, overflow e audit axe per tutte le schermate del centro
 let dialogs=0;page.on('dialog',d=>{dialogs++;d.dismiss();});
 const shots=[['panoramica',''],['agenda','?d=2026-10-05'],['studenti',''],['disponibilita',''],['richieste',''],['percorsi',''],['proposte',''],['laboratorio',''],['decisioni',''],['impostazioni','']];
 const dims={};
 for(const theme of ['light','dark']){
  await page.waitForTimeout(61000);
  await page.evaluate(t=>{localStorage.setItem('ripetizioni-ui',JSON.stringify({theme:t,motion:'reduce'}));},theme);await page.reload();await page.locator('.rail').waitFor({state:'attached'});
  for(const [w,h] of [[1440,1000],[1280,900],[390,844]]){await page.setViewportSize({width:w,height:h});
   for(const [r,q] of shots){await page.goto(B+'/#/'+r+q);await page.waitForTimeout(1100);
    const d=await page.evaluate(()=>({sw:document.documentElement.scrollWidth,vw:innerWidth}));dims[`${r}-${w}-${theme}`]=d;if(d.sw>d.vw)errors.push(`overflow ${r} ${w} ${theme}: ${d.sw}`);
    if(w!==1280)await audit(page,`${r} ${w} ${theme}`);
    if(['panoramica','agenda','proposte','laboratorio'].includes(r)&&(theme==='light'||w!==1280))await page.screenshot({path:`${EV}/v0.7-${r}-${w}-${theme}.png`});}}}
 if(dialogs)errors.push('dialoghi nativi: '+dialogs);
 await browser.close();
 const axeTotal=axeReport.reduce((a,x)=>a+x.violations.length,0);
 fs.writeFileSync(EV+'/v0.7-axe.json',JSON.stringify({tool:'axe-core '+require('/data/pg-qa/node_modules/axe-core/package.json').version,tags:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'],pages:axeReport.length,violations_total:axeTotal,report:axeReport},null,1));
 console.log(JSON.stringify({steps:log,errors,dims_checked:Object.keys(dims).length,axe_pages:axeReport.length,axe_violations:axeTotal,portal},null,1));process.exit(errors.length||axeTotal?2:0);
})().catch(async e=>{try{await globalThis.__page.screenshot({path:'/data/v07-fail.png'})}catch{};console.error('FAIL',e.message);console.log(JSON.stringify({steps:log,axe:axeReport.filter(x=>x.violations.length)}));process.exit(1)});
