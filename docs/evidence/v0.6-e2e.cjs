const { chromium } = require('/data/pg-qa/node_modules/playwright');
const fs=require('fs'),cp=require('child_process');
const B='http://127.0.0.1:5175', EV='/data/gestionale-ripetizioni/docs/evidence';
const log=[];const step=(s)=>{log.push(s);console.error('· '+s);};
(async()=>{
 const cred=JSON.parse(fs.readFileSync('/data/v06-ui-credentials.json','utf8'));
 const browser=await chromium.launch({headless:true,executablePath:cp.execSync('which chromium').toString().trim(),args:['--no-sandbox']});
 const ctx=await browser.newContext({viewport:{width:1440,height:1000},locale:'it-IT',timezoneId:'Europe/Rome'});
 const page=await ctx.newPage();globalThis.__page=page;const errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',r=>{const u=r.url();if(r.status()>=400&&!(u.endsWith('/api/v1/me')&&r.status()===403))errors.push(`HTTP ${r.status()} ${u}`)});
 const toast=(t)=>page.locator('.toast',{hasText:t}).first().waitFor({timeout:20000});
 const modal=()=>page.locator('.modal.show');
 const api=(p)=>page.evaluate(async(p)=>(await fetch('/api/v1'+p,{credentials:'same-origin'})).json(),p);

 await page.goto(B);await page.getByLabel('Nome utente').fill(cred.username);await page.getByLabel('Password',{exact:true}).fill(cred.password);
 await page.getByRole('button',{name:'Accedi'}).click();await page.getByRole('heading',{level:1}).filter({hasText:/^Buon/}).waitFor();step('login');

 if(!process.env.SKIP){
 // 1. genera la proposta
 await page.goto(B+'/#/proposte');await page.getByRole('button',{name:'Verifica i dati'}).click();
 await page.locator('.notice.ok',{hasText:'Dati pronti'}).waitFor();step('verifica dati: pronti');
 await page.getByRole('button',{name:'Genera la proposta'}).click();await toast('Calcolo avviato');
 await page.locator('.mini',{hasText:'Calcolo concluso'}).first().waitFor({timeout:60000});step('calcolo concluso dal worker');
 await page.screenshot({path:EV+'/v0.6-proposte-1440.png',fullPage:true});

 // 2. pubblica dall'agenda
 await page.goto(B+'/#/agenda?d=2026-10-05');
 await page.locator('button.mini',{hasText:'Pronta da rivedere'}).first().click();
 await page.locator('.sheet.show').getByRole('button',{name:'Pubblica nel calendario'}).click();
 await modal().getByText('Confermo che sono dati sintetici di prova').click();
 await modal().getByRole('button',{name:'Pubblica',exact:true}).click();
 await toast('lezioni pubblicate');
 const week=await api('/calendar/?from=2026-10-05&until=2026-10-12');const pub=week.results.filter(l=>l.state==='PUBLISHED');
 if(pub.length!==6)throw Error('attese 6 lezioni, trovate '+pub.length);step('pubblicate 6 lezioni');
 const first=pub.map(l=>l.start_at).sort()[0];
 await page.waitForTimeout(800);
 await page.locator('.les').first().waitFor();
 await page.screenshot({path:EV+'/v0.6-agenda-1440.png'});

 // 3. sposta + annulla
 const before=await page.locator('.les').count();
 // stesso allestimento del collaudo v0.5: mercoledì disponibile per tutti e finestra di servizio
 await page.evaluate(async()=>{
  const tok=document.cookie.split('; ').find(c=>c.startsWith('csrftoken='))?.split('=')[1]||'';
  const post=(p,b)=>fetch('/api/v1'+p,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':tok},body:JSON.stringify(b)}).then(r=>r.json());
  const rules=(await (await fetch('/api/v1/availability-rules/')).json()).results;
  for(const r of rules){const b={};for(const k of ['student','tutor','start_time','end_time','period_start','period_end','timezone','mode','location'])b[k]=r[k];b.weekday=2;const n=await post('/availability-rules/',b);await post(`/availability-rules/${n.id}/approve/`,{expected_version:n.version,reason:'Mercoledì sintetico'});}
  const w=(await (await fetch('/api/v1/service-windows/')).json()).results[0];const b={};for(const k of ['mode','location','start_time','end_time','period_start','period_end','resource'])b[k]=w[k];b.weekday=2;await post('/service-windows/',b);
 });
 const byT={};pub.forEach(l=>(byT[l.tutor]=byT[l.tutor]||[]).push(l));const lone=Object.values(byT).sort((a,b)=>a.length-b.length)[0][0];
 await page.goto(B+'/#/agenda?d=2026-10-05&l='+lone.id);
 const sheet=page.locator('.sheet.show');await sheet.waitFor();
 await sheet.getByRole('button',{name:'Sposta'}).click();
 const m=modal();await m.getByRole('heading',{name:'Sposta la lezione'}).waitFor();
 const wheel=m.getByRole('spinbutton',{name:'Inizio'});const v0=Number(await wheel.getAttribute('aria-valuenow'));await wheel.focus();
 for(let i=0;i<4;i++)await page.keyboard.press('ArrowDown');await page.waitForTimeout(1200);
 const v1=Number(await wheel.getAttribute('aria-valuenow'));if(v1!==v0+4)throw Error(`ruota: attesi ${v0+4}, ottenuti ${v1}`);step('ruota da tastiera: +1 h');
 for(let i=0;i<4;i++)await page.keyboard.press('ArrowUp');await page.waitForTimeout(1200);
 await m.getByText(/^Mer /).click();await page.waitForTimeout(500);
 const submit=m.getByRole('button',{name:/Sposta la lezione/});
 if(await submit.isDisabled()){const alt=m.locator('.conflict button');if(await alt.count()){await alt.click();await page.waitForTimeout(900);}}
 await m.getByLabel('Motivo dello spostamento').fill('Collaudo UI v0.6');
 await page.screenshot({path:EV+'/v0.6-sposta-1440.png'});
 await submit.click();await toast('Lezione spostata').catch(async e=>{throw Error('spostamento rifiutato: '+(await m.locator('.notice.bad').textContent().catch(()=>'?')))});step('spostamento salvato');
 await page.locator('.toast',{hasText:'Lezione spostata'}).getByRole('button',{name:'Annulla'}).click();
 await toast('Spostamento annullato');step('annulla spostamento eseguito');
 const after=await api('/calendar/?from=2026-10-05&until=2026-10-12');
 if(!after.results.some(l=>l.id===lone.id&&l.start_at===lone.start_at&&l.state==='PUBLISHED'))throw Error('annullamento non ha ripristinato l’orario');

 // 4. cancella
 await page.waitForTimeout(600);
 await page.locator('.les:not(.cancelled)').first().click();await page.locator('.sheet.show').getByRole('button',{name:'Cancella lezione'}).click();
 await modal().getByLabel('Motivo della cancellazione').fill('Collaudo UI v0.6');
 await modal().getByRole('button',{name:'Cancella lezione'}).click();await toast('Lezione cancellata');
 const c=await api('/calendar/?from=2026-10-05&until=2026-10-12');if(c.results.filter(l=>l.state==='CANCELLED').length!==1)throw Error('cancellazione non registrata');step('cancellazione registrata');

 }
 // 5. disponibilità: crea e approva con motivo (nessun window.prompt)
 let dialogs=0;page.on('dialog',d=>{dialogs++;d.dismiss();});
 await page.goto(B+'/#/disponibilita');await page.getByRole('button',{name:'Nuova disponibilità'}).first().click();
 await modal().getByRole('combobox').fill('Studente sintetico 1');await page.locator('.suggest [role=option]').first().click();
 await modal().getByRole('button',{name:'Mer',exact:true}).click();
 await page.screenshot({path:EV+'/v0.6-disponibilita-modal-1440.png'});
 await modal().getByRole('button',{name:'Salva in bozza'}).click();await toast('Disponibilità salvata in bozza');
 await page.getByRole('button',{name:'Approva',exact:true}).first().click();
 await modal().getByLabel('Motivo').fill('Confermata in collaudo');await modal().getByRole('button',{name:'Approva',exact:true}).click();
 await toast('Disponibilità approvata');step('disponibilità creata e approvata con motivo');

 // 6. percorsi: nuova materia
 await page.goto(B+'/#/percorsi');await page.getByRole('button',{name:'Nuova materia'}).click();
 await modal().getByLabel('Nome').fill('Storia dell’arte '+Date.now().toString().slice(-4));await modal().getByRole('button',{name:'Aggiungi materia'}).click();await toast('Materia aggiunta');step('materia creata');
 await page.getByRole('button',{name:'Nuovo percorso'}).click();await modal().getByLabel('Nome del percorso').fill('Bozza');
 await page.keyboard.press('Escape');await modal().getByText('Hai modifiche non salvate.').waitFor();
 await modal().getByRole('button',{name:'Chiudi senza salvare'}).click();await page.waitForTimeout(600);step('guardia modifiche non salvate');
 const p=await page.locator('button.mini').count();if(p){await page.locator('button.mini').first().click();await page.getByRole('button',{name:'Tutti i percorsi'}).waitFor();await page.screenshot({path:EV+'/v0.6-percorso-1440.png',fullPage:true});step('dettaglio percorso');}

 // 7. laboratorio
 await page.goto(B+'/#/laboratorio');await page.getByRole('button',{name:'Carica lo scenario di prova'}).click();await toast('Scenario di prova caricato');
 await page.getByRole('button',{name:'Calcola la proposta'}).click();await page.getByRole('heading',{name:/Risultato/}).waitFor({timeout:30000});step('simulazione laboratorio');
 await page.screenshot({path:EV+'/v0.6-laboratorio-1440.png',fullPage:true});

 // 8. palette comandi
 await page.keyboard.press('Control+k');await page.locator('.cmd.show').waitFor();await page.keyboard.type('agenda');await page.keyboard.press('Enter');
 await page.waitForURL(/#\/agenda/);step('palette comandi');

 // 9. screenshot e overflow
 const shots=[['panoramica',''],['agenda','?d=2026-10-05'],['studenti',''],['disponibilita',''],['richieste',''],['percorsi',''],['proposte',''],['laboratorio',''],['decisioni',''],['impostazioni','']];
 const dims={};
 for(const theme of ['light','dark']){
  await page.waitForTimeout(61000); // limite API 120 richieste/minuto per utente
  await page.evaluate(t=>{localStorage.setItem('ripetizioni-ui',JSON.stringify({theme:t,motion:'reduce'}));},theme);await page.reload();await page.locator('.rail').waitFor({state:'attached'});
  for(const [w,h] of [[1440,1000],[1280,900],[390,844]]){await page.setViewportSize({width:w,height:h});
   for(const [r,q] of shots){await page.goto(B+'/#/'+r+q);await page.waitForTimeout(1100);
    const d=await page.evaluate(()=>({sw:document.documentElement.scrollWidth,vw:innerWidth}));dims[`${r}-${w}-${theme}`]=d;if(d.sw>d.vw)errors.push(`overflow ${r} ${w} ${theme}: ${d.sw}`);
    if(['panoramica','agenda','proposte','percorsi','laboratorio','disponibilita'].includes(r)&&(theme==='light'||w!==1280))await page.screenshot({path:`${EV}/v0.6-${r}-${w}-${theme}.png`});}}}
 if(dialogs)errors.push('dialoghi nativi: '+dialogs);
 await browser.close();
 console.log(JSON.stringify({steps:log,errors,dims_checked:Object.keys(dims).length},null,1));process.exit(errors.length?2:0);
})().catch(async e=>{try{await globalThis.__page.screenshot({path:'/data/v06-shots/fail.png'})}catch{};console.error('FAIL',e.message);console.log(JSON.stringify({steps:log}));process.exit(1)});
