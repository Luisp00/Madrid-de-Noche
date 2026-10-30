#!/usr/bin/env node
// Descarga una página con Chromium headless (a través del proxy del entorno) y devuelve su texto visible
// más la lista de enlaces. Sustituto de WebFetch cuando este no está disponible o la web lo bloquea.
// Uso: node tools/fetch.js URL [--wait ms] [--max chars] [--links N] [--raw] [--mobile]
//   --raw   imprime el cuerpo de la respuesta tal cual (JSON/HTML) en vez del texto visible
//   --links N  número máximo de enlaces a listar (por defecto 250; 0 = ninguno)
const { chromium } = require('playwright');
const args=process.argv.slice(2); const url=args.find(a=>!a.startsWith('--'));
const opt=(k,d)=>{const i=args.indexOf(k); return i>=0? args[i+1] : d;};
const wait=+opt('--wait',2500), max=+opt('--max',45000), nlinks=+opt('--links',250), raw=args.includes('--raw'), mobile=args.includes('--mobile');
if(!url){ console.error('uso: node tools/fetch.js URL [--wait ms] [--max chars] [--links N] [--raw]'); process.exit(2); }
(async()=>{
  const b=await chromium.launch({proxy: process.env.HTTPS_PROXY? {server:process.env.HTTPS_PROXY} : undefined});
  const ctx=await b.newContext({
    userAgent: mobile? 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
                     : 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    locale:'es-ES', timezoneId:'Europe/Madrid', viewport: mobile? {width:390,height:844}:{width:1280,height:900}});
  await ctx.route('**/*',r=>{ const t=r.request().resourceType(); if(['image','media','font'].includes(t)) r.abort(); else r.continue(); });
  const p=await ctx.newPage(); let status=0, body='';
  try{
    const r=await p.goto(url,{waitUntil:'domcontentloaded',timeout:45000}); status=r? r.status():0;
    if(raw){ body=await r.text(); }
    else {
      await p.waitForTimeout(wait);
      // cerrar avisos de cookies habituales
      for (const sel of ['button:has-text("Aceptar")','button:has-text("Accept")','button:has-text("GOT IT")','button:has-text("Acepto")','#onetrust-accept-btn-handler']) { try{ const el=await p.$(sel); if(el){ await el.click({timeout:1000}); await p.waitForTimeout(400); break; } }catch(e){} }
      // desplazar para cargar listados perezosos
      for(let i=0;i<4;i++){ await p.mouse.wheel(0,2500); await p.waitForTimeout(400); }
      const res=await p.evaluate((n)=>{
        const text=document.body? document.body.innerText : '';
        const seen=new Set(); const links=[];
        for (const a of document.querySelectorAll('a[href]')){ const h=a.href; if(!h||h.startsWith('javascript')||seen.has(h)) continue; seen.add(h); const t=(a.innerText||a.getAttribute('aria-label')||'').trim().replace(/\s+/g,' ').slice(0,80); links.push((t?t+' | ':'')+h); if(links.length>=n) break; }
        return {title:document.title, text, links};
      }, nlinks);
      body=`TITLE: ${res.title}\nSTATUS: ${status}\n\n${res.text}`;
      if (nlinks>0) body+=`\n\nLINKS (${res.links.length}):\n`+res.links.join('\n');
    }
  }catch(e){ body=`ERROR: ${e.message.split('\n')[0]} (status ${status})`; }
  await b.close();
  body=body.replace(/\n{3,}/g,'\n\n');
  if(body.length>max) body=body.slice(0,max)+`\n…[recortado a ${max} caracteres de ${body.length}]`;
  process.stdout.write(body+'\n');
})();
