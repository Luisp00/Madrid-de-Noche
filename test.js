const { chromium } = require('playwright');
const fs=require('fs');
(async()=>{
  const html=fs.readFileSync('index.html','utf8');
  const sample=[
   {id:"a",d:{title:"Noche Latina",date:"2026-10-31",start:"23:30",end:"06:00",venue:"Teatro Kapital",zone:"Atocha",type:"club",music:["reggaeton","comercial"],priceMin:15,priceMax:25,priceText:"Anticipada 15€ con copa · Taquilla 25€",free:false,dressCode:"Elegante, no deportivas",ageMin:21,sources:[{name:"Fourvenues",url:"https://x"}],status:"disponible"}},
   {id:"b",d:{title:"Techno Rave",date:"2026-10-30",start:"23:00",venue:"Fabrik",zone:"Fuenlabrada",type:"club",music:["techno"],priceMin:0,priceMax:30,priceText:"Lista gratis hasta 1:00",free:true,dressCode:null,ageMin:18,sources:[{name:"Xceed",url:"https://y"}],status:"ultimas"}}
  ];
  const mock = `<script>window.__sample=${JSON.stringify(sample)}.map(x=>({id:x.id,data:()=>x.d}));
  window.claude={use:async(n)=>{ if(n!=="db") return null; return {
     collection:()=>{const q={where:()=>q,orderBy:()=>q,limit:()=>q,onSnapshot:(cb)=>{cb({docs:window.__sample})}};return q;},
     doc:()=>({onSnapshot:(cb)=>cb({exists:true,data:()=>({lastUpdated:new Date().toISOString()})})})
  }}};</script>`;
  const b=await chromium.launch(); const p=await b.newPage({viewport:{width:390,height:844}});
  const errs=[]; p.on('pageerror',e=>errs.push(e.message)); p.on('console',m=>{if(m.type()==='error')errs.push(m.text())});
  await p.setContent(html.replace('<script>',mock+'<script>'),{waitUntil:'networkidle'});
  await p.waitForTimeout(800);
  await p.screenshot({path:'shot1.png'});
  await p.click('.card'); await p.waitForTimeout(400); await p.screenshot({path:'shot2.png'});
  await p.click('#closeDetail'); await p.click('#filterBtn'); await p.waitForTimeout(400); await p.screenshot({path:'shot3.png'});
  console.log('errors:',errs); console.log(await p.textContent('#status'));
  await b.close();
})();
