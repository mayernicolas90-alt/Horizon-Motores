// QA determinístico de escenas del PM (se evalúa dentro de la página). Devuelve lista de problemas.
window.pmQA=function(S,fmt,f){
  const {w:W,h:H}=FMT[fmt],X0=72,X1=1008,foot=H-(fmt==='estado'?230:164),P=[];
  const boxes=[];
  for(const e of S){
    if(e.t==='text'&&e.txt){const tw=mw(e.txt,e.w,e.s,e.ls||0);let x=e.x;if(e.a==='middle')x-=tw/2;else if(e.a==='end')x-=tw;
      const b={x,y:e.y-e.s*0.78,w:tw,h:e.s*0.98,txt:e.txt,g:e.g};boxes.push(b);
      if(e.g!=='Pie'&&(b.x<X0-1||b.x+b.w>X1+1))P.push(['fuera de columna',e.txt]);
      if(/…|\.\.\.$/.test(e.txt))P.push(['texto con puntos suspensivos',e.txt]);
      if(/^[A-Za-z][^:]{2,30}$/.test(e.txt)&&e.g==='Tabla'&&!e.txt.trim())P.push(['fila vacía',e.txt]);
    }
    if(e.t==='img'&&e.g==='Producto'&&e.w&&e.h&&(e.x<X0-1||e.x+e.w>X1+1))P.push(['imagen fuera de columna',e.g]);
  }
  for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const a=boxes[i],b=boxes[j];
    const ox=Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x),oy=Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y);
    if(ox>4&&oy>4)P.push(['textos superpuestos',a.txt+' ⟂ '+b.txt])}
  // huecos verticales entre bloques de contenido (texto, imágenes de producto, tarjetas de atributos)
  const ys=[];for(const b of boxes)if(b.g!=='Pie')ys.push([b.y,b.y+b.h]);
  for(const e of S)if((e.t==='img'||e.t==='rect'||e.t==='placeholder')&&e.h&&e.h<H*0.8&&e.w<W*0.99&&e.g!=='Fondo'&&e.y>140)ys.push([e.y,e.y+e.h]);
  ys.sort((a,b)=>a[0]-b[0]);let end=ys.length?ys[0][1]:0;
  for(const [a,b] of ys){if(a-end>120&&a<foot)P.push(['hueco vertical de '+Math.round(a-end)+' px',Math.round(end)+'→'+Math.round(a)]);end=Math.max(end,b)}
  if(foot-end>140)P.push(['hueco antes del pie de '+Math.round(foot-end)+' px','']);
  // textos repetidos (mismo dato dos veces)
  const cnt={};for(const b of boxes){const k=norm(b.txt);if(k.length>=4&&b.g!=='Pie')cnt[k]=(cnt[k]||0)+1}
  for(const [k,n] of Object.entries(cnt))if(n>1)P.push(['texto repetido '+n+' veces',k]);
  // afirmaciones que requieren confirmación
  const allT=boxes.map(b=>b.txt).join(' ');
  if(/stock local|entrega inmediata/i.test(allT)&&!f?.stockConfirmado)P.push(['afirma stock sin confirmar','']);
  if(/precios usd/i.test(allT)&&!(f?.modelos||[]).some(m=>m.p))P.push(['leyenda de precios sin precio','']);
  return P;
};
