// Prueba de la app con Playwright y una base de datos simulada.
// Uso: node test.js [directorio con events/*.json tal como los guarda ArtifactData out_dir]
// Sin argumento usa dos eventos de ejemplo. Escribe shot1-3.png y falla (exit 1) si algo no cuadra.
const { chromium } = require('playwright');
const fs=require('fs'); const path=require('path');
(async()=>{
  const frag=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
  const today=new Date(); if(today.getHours()<6) today.setDate(today.getDate()-1);
  const iso=d=>d.toISOString().slice(0,10); const addD=(d,n)=>{const x=new Date(d);x.setDate(x.getDate()+n);return x;};
  const T=iso(today), T1=iso(addD(today,1)), T2=iso(addD(today,2));
  let sample=[
   {id:"a",d:{title:"Noche Latina",date:T1,start:"23:30",end:"06:00",venue:"Teatro Kapital",zone:"Atocha",type:"club",music:["reggaeton","comercial"],priceMin:15,priceMax:25,priceText:"Anticipada 15€ con copa · Taquilla 25€",free:false,dressCode:"Elegante, no deportivas",ageMin:21,sources:[{name:"Fourvenues",url:"https://x.example/a"},{name:"Fever",url:"https://fever.example/a"}],ticketUrl:"https://fever.example/a",status:"disponible"}},
   {id:"b",d:{title:"Techno Rave de madrugada",date:T,start:"00:30",venue:"Fabrik",zone:"Humanes (Fabrik)",type:"club",music:["techno"],priceMin:0,priceMax:30,priceText:"Lista gratis hasta 1:00 y luego 30 € con dos copas de marca",free:true,dressCode:null,ageMin:18,sources:[{name:"Xceed",url:"https://y.example/b"}],ticketUrl:"https://y.example/b",status:"ultimas"}},
   {id:"c",d:{title:"Reggaetón Night",date:T,start:"23:00",venue:"Shoko",zone:"La Latina",type:"club",music:["reggaeton"],priceMin:12,free:false,sources:[{name:"Shoko",url:"https://s.example/c"}],ticketUrl:"https://s.example/c",status:"desconocido"}},
   {id:"d",d:{title:"Tardeo Sunset con un título larguísimo que debería partirse en varias líneas sin romper nada",date:T2,start:"18:00",venue:"Café Berlín",zone:"Centro / Sol",type:"tardeo",music:["house"],free:true,priceText:"Gratis con reserva hasta completar aforo, después 10 € con consumición",sources:[{name:"Tardeo Madrid",url:"https://t.example/d"}],ticketUrl:"https://t.example/d",status:"disponible"}},
  ];
  const dir=process.argv[2];
  if (dir){ sample=fs.readdirSync(path.join(dir,'events')).filter(f=>f.endsWith('.json')).map(f=>({id:f.slice(0,-5),d:JSON.parse(fs.readFileSync(path.join(dir,'events',f),'utf8'))})); }
  const mock = `<script>window.__sample=${JSON.stringify(sample)};
  window.__fired=[]; window.__favWrites=[];
  window.claude={use:async(n)=>{
    if(n==="db") return {
      collection:(c)=>{const w=[];const q={where:(f,op,v)=>{w.push([f,op,v]);return q},orderBy:()=>q,limit:()=>q,onSnapshot:(cb)=>{
        const docs=window.__sample.filter(x=>w.every(([f,op,v])=> op===">="? x.d[f]>=v : op==="<" ? x.d[f]<v : true)).map(x=>({id:x.id,data:()=>x.d}));
        setTimeout(()=>cb({docs}),50); return ()=>{};}};return q;},
      doc:(p)=>({onSnapshot:(cb)=>cb({exists:true,data:()=>({lastUpdated:new Date().toISOString(),running:false})}), get:async()=>({exists:true,data:()=>({favs:["c"]})}), set:async(d)=>{window.__favWrites.push(d)}})
    };
    if(n==="user") return {id:async()=>"u_test", isOwner:async()=>true, canEdit:async()=>true};
    if(n==="mcp") return {callTool:async(s,t,i)=>{window.__fired.push([s,t,i]);return {payload:{ok:true}}}};
    return null;
  }};</script>`;
  const html=`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style></head><body>${mock}${frag}</body></html>`;
  const b=await chromium.launch(); const errs=[]; const fails=[];
  const check=(ok,msg)=>{ if(!ok) fails.push(msg); console.log((ok?'OK  ':'FAIL')+' '+msg); };
  for (const vp of [{width:390,height:844},{width:1200,height:900}]){
    const p=await b.newPage({viewport:vp}); p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
    await p.setContent(html,{waitUntil:'networkidle'}); await p.waitForTimeout(600);
    check(await p.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1), `${vp.width}px: sin scroll horizontal`);
    if (vp.width===390){
      await p.screenshot({path:'shot1.png'});
      check(await p.locator('#refreshBtn').isVisible(), 'botón actualizar visible para el propietario');
      // favoritos remotos fusionados
      check(await p.evaluate(()=>document.querySelector('.fav.on')!==null) || !!dir, 'favorito remoto "c" cargado');
      // "7 días": orden dentro de la noche (23:00 antes que 00:30)
      await p.click('text=7 días');
      const titles=await p.$$eval('.card h3',els=>els.map(e=>e.textContent));
      if(!dir){ check(titles.indexOf('Reggaetón Night')<titles.indexOf('Techno Rave de madrugada'), 'orden: 23:00 antes que 00:30 dentro de la misma noche'); }
      // finde
      await p.click('text=/finde/i'); const nFinde=await p.$$eval('.card',e=>e.length);
      const w=today.getDay(); const expectFinde = !dir ? sample.filter(x=>{const d=x.d.date; let fri=new Date(today); if(w===6)fri=addD(today,-1); else if(w===0)fri=addD(today,-2); else fri=addD(today,(5-w+7)%7); const from=iso(fri)>T?iso(fri):T; const sun=iso(addD(fri,2)); return d>=from&&d<=sun;}).length : null;
      if(!dir) check(nFinde===expectFinde, `finde muestra ${nFinde} (esperado ${expectFinde})`); else check(nFinde>0,'finde muestra eventos: '+nFinde);
      // búsqueda sin tildes
      await p.click('text=Todo'); await p.fill('#q','reggaeton'); await p.waitForTimeout(100); const n1=await p.$$eval('.card',e=>e.length);
      await p.fill('#q','reggaetón'); await p.waitForTimeout(100); const n2=await p.$$eval('.card',e=>e.length);
      check(n1===n2 && n1>0, `búsqueda insensible a tildes (${n1} = ${n2})`);
      await p.fill('#q',''); await p.waitForTimeout(100);
      // ficha: botón principal = ticketUrl
      await p.click('.card'); await p.waitForTimeout(350); await p.screenshot({path:'shot2.png'});
      const first=await p.$eval('.card',c=>c.dataset.id); const ev=sample.find(x=>x.id===first).d;
      const href=await p.$eval('#detailSheet .btn.primary',a=>a.getAttribute('href'));
      check(href===(ev.ticketUrl||ev.sources[0].url), 'botón principal apunta a ticketUrl');
      check(await p.evaluate(()=>document.activeElement&&document.activeElement.id==='closeDetail'), 'foco en "Cerrar" al abrir la ficha');
      await p.keyboard.press('Escape'); await p.waitForTimeout(300);
      check(!(await p.$eval('#detailSheet',s=>s.classList.contains('show'))), 'Escape cierra la ficha');
      // teclado: Enter abre la ficha
      await p.focus('.card'); await p.keyboard.press('Enter'); await p.waitForTimeout(300);
      check(await p.$eval('#detailSheet',s=>s.classList.contains('show')), 'Enter abre la ficha desde la tarjeta');
      await p.click('#closeDetail'); await p.waitForTimeout(300);
      // filtros: cerrar tocando fuera aplica el filtro
      const before=await p.$$eval('.card',e=>e.length);
      await p.click('#filterBtn'); await p.waitForTimeout(300); await p.screenshot({path:'shot3.png'});
      await p.click('#swFree'); await p.mouse.click(10,10); await p.waitForTimeout(300);
      const after=await p.$$eval('.card',e=>e.length);
      check(after<before, `cerrar filtros tocando fuera aplica el filtro (${before} → ${after})`);
      check(await p.$eval('#filterCount',e=>e.textContent==='1'), 'contador de filtros = 1');
      // cabecera de día pegajosa justo bajo la cabecera
      const topH=await p.$eval('#top',e=>e.getBoundingClientRect().height); const dh=await p.$eval('.dayhead',e=>parseFloat(getComputedStyle(e).top));
      check(Math.abs(dh-(topH-1))<2, `dayhead top (${dh}) = cabecera (${topH}) - 1`);
      // actualizar ahora
      await p.click('#refreshBtn'); await p.waitForTimeout(200); await p.click('#toastAct'); await p.waitForTimeout(200);
      check(await p.evaluate(()=>window.__fired.length===1 && window.__fired[0][1]==='fire_trigger'), 'botón actualizar llama a fire_trigger');
      console.log('status:', await p.textContent('#status'));
    }
    await p.close();
  }
  console.log('errores de página:',errs);
  if (errs.length) fails.push('errores en consola');
  await b.close();
  if (fails.length){ console.log('\nFALLOS:', fails); process.exit(1); }
  console.log('\nTodo correcto');
})();
