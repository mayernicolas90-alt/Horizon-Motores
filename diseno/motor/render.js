const {chromium}=require('playwright');const fs=require('fs');
const PJ='/opt/npm-tools/node_modules/pdfjs-dist/build/';const qa=fs.readFileSync(__dirname+'/qa_scene.js','utf8');const F=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const tag=process.argv[3]||F.pid;
let r_last=null;var c0;(async()=>{const b=await chromium.launch();const pg=await b.newPage({viewport:{width:1200,height:900}});const errs=[];pg.on('pageerror',e=>errs.push(e.message));
await pg.route('**/*',r=>{const u=r.request().url();
 if(u==='http://pm.test/')return r.fulfill({body:fs.readFileSync(__dirname+'/plantilla_horizon.html','utf8'),contentType:'text/html'});
 if(u.includes('pdf.js/3.11.174/pdf.min.js'))return r.fulfill({contentType:'text/javascript',body:"window.__pdf=import('http://pm.test/pj/pdf.min.mjs').then(m=>{window.pdfjsLib=m;m.GlobalWorkerOptions.workerSrc='http://pm.test/pj/pdf.worker.min.mjs'})"});
 if(u.startsWith('http://pm.test/pj/')){const p=PJ+u.split('/pj/')[1];return fs.existsSync(p)?r.fulfill({contentType:'text/javascript',body:fs.readFileSync(p)}):r.fulfill({contentType:'text/javascript',body:''})}
 if(u.startsWith('http://pm.test/_blob/')){const f=__dirname+'/../fotos/'+u.split('/_blob/')[1]+'.png';return fs.existsSync(f)?r.fulfill({contentType:'image/png',body:fs.readFileSync(f)}):r.abort()}
 return r.abort()});
await pg.goto('http://pm.test/');await pg.waitForTimeout(1500);await pg.evaluate(()=>Promise.race([window.__pdf,new Promise(r=>setTimeout(r,1500))]));await pg.addScriptTag({content:qa});if(F.composicion)await pg.addScriptTag({content:fs.readFileSync(__dirname+'/composicion_v8.js','utf8')});if(F.pulido)await pg.addScriptTag({content:fs.readFileSync(__dirname+'/pulido_v9.js','utf8')});
const P=JSON.parse(fs.readFileSync(__dirname+'/prods.json','utf8'));await pg.evaluate(P=>{st.prods=P},P);
for(const fmt of (F.formatos||['chat'])){
const r=await pg.evaluate(async({fmt,F})=>{st.dz.f=DZDEF();st.dz.pid=F.pid;const o=dzV2Build(pById(F.pid),'');dzVolcar(o);const f=st.dz.f;
 f.foto={id:F.foto,url:'/_blob/'+F.foto};
 for(const k of ['titulo','chips','datos','atr','fuerte','tabla','modelos'])if(F[k]!==undefined)f[k]=F[k];
 const sc=await dzEscenas(f,fmt),res={ficha:JSON.parse(JSON.stringify({...f,foto:null,logo:null}))};
 if(F.composicion&&window.compV8)for(const k of ['portada','detalle'])res['comp_'+k]=await compV8(sc[k],fmt,k,F.composicion);
 if(F.pulido&&window.pulirV9)for(const k of ['portada','detalle'])sc[k]=pulirV9(sc[k],fmt,k,F);res.pulido=window.__pulido||null;
 for(const k of ['portada','detalle']){const {w,h}=FMT[fmt];const cv=document.createElement('canvas');cv.width=w;cv.height=h;await pintar(cv,sc[k]);res[k]=cv.toDataURL();res['qa_'+k]=pmQA(sc[k],fmt,f);
  res['esc_'+k]=sc[k].map(e=>{const o={...e};if(o.src)o.src='img';delete o.d;if(o.t==='text'&&o.txt){c0=document.createElement('canvas').getContext('2d');o.tw=mw(o.txt,o.w,o.s,o.ls||0)}return o});
  const E=F.escala||1;if(E>1){const SH=F.foto_hd?sc[k].map(e=>e.t==='img'&&typeof e.src==='string'&&e.src.includes('/_blob/'+F.foto)?{...e,src:e.src.replace('/_blob/'+F.foto,'/_blob/'+F.foto_hd)}:e):sc[k];const hd=document.createElement('canvas');hd.width=w*E;hd.height=h*E;const cx=hd.getContext('2d');cx.imageSmoothingEnabled=true;cx.imageSmoothingQuality='high';cx.setTransform(E,0,0,E,0,0);
   const orig=hd.getContext.bind(hd);hd.getContext=t=>{const c=orig(t);c.imageSmoothingQuality='high';return c};await pintar(hd,SH);res['hd_'+k]=hd.toDataURL('image/png')}}return res},{fmt,F});
if(r.comp_portada&&r.comp_detalle){const a=r.comp_portada.medidas,d=r.comp_detalle.medidas;r.comp_detalle.par={misma_mirada:a.mira===d.mira,misma_escala:(a.escala||{}).modo===(d.escala||{}).modo&&(a.escala||{}).area_objetivo===(d.escala||{}).area_objetivo,mismo_color:JSON.stringify(a.luz||{})===JSON.stringify(d.luz||{})};r.comp_detalle.pruebas.par_portada_ficha=Object.values(r.comp_detalle.par).every(Boolean);r.comp_detalle.aprobado=r.comp_detalle.aprobado&&r.comp_detalle.pruebas.par_portada_ficha}
for(const k of ['portada','detalle']){const O=process.argv[4]||'.';fs.writeFileSync(`${O}/${tag}_${fmt}_${k}.png`,Buffer.from(r[k].split(',')[1],'base64'));fs.writeFileSync(`${O}/${tag}_${fmt}_${k}.escena.json`,JSON.stringify(r['esc_'+k]));if(r['hd_'+k])fs.writeFileSync(`${O}/${tag}_${fmt}_${k}_hd.png`,Buffer.from(r['hd_'+k].split(',')[1],'base64'));
 if(r['comp_'+k]){fs.writeFileSync(`${process.argv[4]||'.'}/${tag}_${fmt}_${k}.composicion.json`,JSON.stringify(r['comp_'+k],null,1));console.log(fmt,k,'composicion',r['comp_'+k].aprobado,JSON.stringify(r['comp_'+k].pruebas))}}
r_last=r;console.log(fmt,'QA',JSON.stringify(r.qa_portada),JSON.stringify(r.qa_detalle));if(fmt==='chat')console.log(JSON.stringify(r.ficha).slice(0,900))}
if(r_last&&r_last.pulido)console.log('pulido',JSON.stringify(r_last.pulido));console.log('errs',errs);await b.close()})();
