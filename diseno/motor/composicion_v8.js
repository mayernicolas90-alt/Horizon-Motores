// Composición fotográfica V8 (determinística, sin IA).
// Se evalúa dentro de la página después de dzEscenas() y antes de pintar().
// No toca la plantilla: solo reubica y re-escala la foto DENTRO de su tarjeta y suma capas
// (brillo de marca, sombra de apoyo y reflejo opcional) entre la tarjeta y la foto. La tarjeta, los textos,
// la marca y el pie quedan exactamente donde los pone la plantilla.
//
// cfg (en la ficha, clave "composicion"):
//   familia: 'olt' | 'ont' | 'pasivo'      (escala por familia si no hay medidas)
//   medidas_mm: {ancho, alto, prof}        (medidas reales del PM: escala física entre productos)
//   mira:    'auto' | 'der' | 'izq' | 'centro'  (hacia dónde mira el frente del equipo)
//   reflejo: false | true                  (reflejo opcional, con tope de opacidad)
//   luz:     true | false                  (luz y color parejos entre fotos)
window.compV8 = async function (S, fmt, kind, cfg) {
  cfg = Object.assign({ familia: 'olt', mira: 'auto', reflejo: false, luz: true }, cfg || {});
  const CW = 936, PHI = (1 + Math.sqrt(5)) / 2, G8 = v => Math.round(v / 8) * 8;
  const R = { pieza: kind, formato: fmt, cfg, medidas: {}, pruebas: {}, avisos: [] };
  const iCard = S.findIndex(e => e.g === 'Producto' && e.t === 'img' && Math.round(e.w) === CW && !e.shadow);
  const iFoto = S.findIndex(e => e.g === 'Producto' && e.t === 'img' && e.shadow);
  if (iCard < 0 || iFoto < 0) { R.aprobado = false; R.avisos.push('sin tarjeta o sin foto'); return R; }
  const card = S[iCard], foto = S[iFoto];
  const im = await dzImg(foto.src); if (!im) { R.aprobado = false; R.avisos.push('foto no carga'); return R; }

  // ---------- análisis de la foto (máscara alfa) ----------
  const nw = im.naturalWidth || im.width, nh = im.naturalHeight || im.height;
  const cv = document.createElement('canvas'); cv.width = nw; cv.height = nh;
  const cx = cv.getContext('2d', { willReadFrequently: true }); cx.drawImage(im, 0, 0);
  const D = cx.getImageData(0, 0, nw, nh), px = D.data;
  let sa = 0, sx = 0, sy = 0; const colTop = new Array(nw).fill(-1), colBot = new Array(nw).fill(-1);
  const lum = []; let sr = 0, sg = 0, sb = 0, nOp = 0;
  for (let y = 0; y < nh; y++) for (let x = 0; x < nw; x++) {
    const i = (y * nw + x) * 4, a = px[i + 3] / 255; if (a <= .5) continue;
    sa += a; sx += a * x; sy += a * y; if (colTop[x] < 0) colTop[x] = y; colBot[x] = y;
    sr += px[i]; sg += px[i + 1]; sb += px[i + 2]; nOp++;
    if (((x + y) & 3) === 0) lum.push(.2126 * px[i] + .7152 * px[i + 1] + .0722 * px[i + 2]);
  }
  const vcx = sx / sa / nw, vcy = sy / sa / nh;           // centro visual (centroide alfa), normalizado
  const colH = x => colTop[x] < 0 ? 0 : colBot[x] - colTop[x];
  const band = (a, b) => { let s = 0, n = 0; for (let x = Math.floor(a * nw); x < Math.floor(b * nw); x++) { const h = colH(x); if (h > 0) { s += h; n++ } } return n ? s / n : 0 };
  const hL = band(.04, .14), hR = band(.86, .96), persp = hL / Math.max(1, hR);
  // Mirada por las líneas del chasis: ajuste lineal de la altura de cada columna (20 franjas)
  // y de los bordes superior e inferior. Un equipo en perspectiva achica su altura hacia el lado
  // que se aleja; el frente mira hacia ese lado. Si el ajuste no es claro, se usa la regla vieja.
  const xs0 = colTop.findIndex(v => v >= 0), xs1 = nw - 1 - [...colTop].reverse().findIndex(v => v >= 0);
  const fit = (f) => { const P = []; const W = xs1 - xs0; for (let k = 0; k < 20; k++) { const a = xs0 + W * (.05 + .9 * k / 20), b = xs0 + W * (.05 + .9 * (k + 1) / 20); const v = []; for (let x = Math.floor(a); x < Math.floor(b); x++) { if (colTop[x] >= 0) v.push(f(x)) } if (v.length) { v.sort((p, q) => p - q); P.push([(a + b) / 2, v[v.length >> 1]]) } }
    const n = P.length; if (n < 6) return { m: 0, r2: 0, mean: 1 }; const mx = P.reduce((t, p) => t + p[0], 0) / n, my = P.reduce((t, p) => t + p[1], 0) / n;
    let sxy = 0, sxx = 0, syy = 0; for (const [x, y] of P) { sxy += (x - mx) * (y - my); sxx += (x - mx) ** 2; syy += (y - my) ** 2 } const m = sxy / Math.max(1e-9, sxx); return { m, r2: syy ? (sxy * sxy) / (sxx * syy) : 0, mean: my } };
  const fH = fit(x => colH(x)), fT = fit(x => colTop[x]), fB = fit(x => colBot[x]);
  const cambio = fH.m * (xs1 - xs0) / Math.max(1, fH.mean);          // variación total de altura de izq a der (relativa)
  const converge = Math.sign(fT.m) !== Math.sign(fB.m) || Math.abs(fT.m - fB.m) * (xs1 - xs0) / Math.max(1, fH.mean) > .03;
  let mira = cfg.mira, miraFuente = 'ficha';
  if (mira === 'auto') {
    if (fH.r2 >= .6 && Math.abs(cambio) >= .035 && converge) { mira = cambio < 0 ? 'der' : 'izq'; miraFuente = 'lineas'; }
    else if (fH.r2 < .6 && (persp > 1.08 || persp < 1 / 1.08)) { mira = persp > 1 ? 'der' : 'izq'; miraFuente = 'franjas'; }
    else { mira = 'centro'; miraFuente = Math.abs(cambio) < .035 ? 'lineas (frontal)' : 'sin convergencia'; }
  }
  R.medidas.mirada = { cambio_altura: +cambio.toFixed(3), r2: +fH.r2.toFixed(2), bordes_convergen: converge, fuente: miraFuente };
  R.medidas.perspectiva_izq_der = +persp.toFixed(3); R.medidas.mira = mira;

  // ---------- luz y color parejos ----------
  let src = foto.src;
  if (cfg.luz && nOp > 100) {
    // Color parejo entre fotos de distinto origen: balance de blancos sobre los grises del equipo
    // (no sobre LEDs ni logos), niveles sin empastar ni quemar, y tono medio del material llevado
    // a la referencia aprobada: chasis oscuro (AN6000-7: 64) o plástico claro (ONT: 220).
    let nr = 0, ng = 0, nb = 0, nn = 0; const lumN = [];
    for (let i = 0; i < px.length; i += 16) {
      if (px[i + 3] < 128) continue; const r = px[i], g = px[i + 1], b = px[i + 2], mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = .2126 * r + .7152 * g + .0722 * b;
      if (mx - mn < 28 && l > 20 && l < 235) { nr += r; ng += g; nb += b; nn++; lumN.push(l) }
    }
    lum.sort((a, b) => a - b); lumN.sort((a, b) => a - b);
    const q = (A, p) => A[Math.min(A.length - 1, Math.floor(p * A.length))];
    const p05 = q(lum, .05), p50 = q(lum, .5), p95 = q(lum, .95);
    const lo = Math.max(0, Math.min(p05, 14)), hi = Math.max(p95, 200), gain = 235 / Math.max(1, hi - lo);
    const base = nn > 50 ? [nr / nn, ng / nn, nb / nn] : [sr / nOp, sg / nOp, sb / nOp], mm = (base[0] + base[1] + base[2]) / 3;
    const wb = base.map(v => 1 + .9 * (mm / Math.max(1, v) - 1));
    const med = nn > 50 ? q(lumN, .5) : p50, claro = med >= 128, T = claro ? 220 : 64;
    const medN = Math.max(1, Math.min(254, (med - lo) * gain)), gam = Math.max(.8, Math.min(1.25, Math.log(T / 255) / Math.log(medN / 255)));
    const LUT = new Uint8ClampedArray(256); for (let v = 0; v < 256; v++) LUT[v] = 255 * Math.pow(Math.max(0, Math.min(255, (v - lo) * gain)) / 255, gam);
    for (let i = 0; i < px.length; i += 4) {
      if (!px[i + 3]) continue; const r = px[i], g = px[i + 1], b = px[i + 2], ch = Math.max(r, g, b) - Math.min(r, g, b);
      const k = ch > 60 ? .3 : ch > 28 ? .3 + .7 * (60 - ch) / 32 : 1;   // LEDs y logos casi sin tocar el tinte
      px[i] = LUT[Math.max(0, Math.min(255, Math.round(r * (1 + k * (wb[0] - 1)))))];
      px[i + 1] = LUT[Math.max(0, Math.min(255, Math.round(g * (1 + k * (wb[1] - 1)))))];
      px[i + 2] = LUT[Math.max(0, Math.min(255, Math.round(b * (1 + k * (wb[2] - 1)))))];
    }
    cx.putImageData(D, 0, 0); src = cv.toDataURL('image/png');
    R.medidas.luz = { p05: Math.round(p05), p50: Math.round(p50), p95: Math.round(p95), material: claro ? 'claro' : 'oscuro', tono_medio: Math.round(med), objetivo: T, gamma: +gam.toFixed(3), balance_rgb: wb.map(v => +v.toFixed(3)), ganancia: +gain.toFixed(3), negro: Math.round(lo) };
  }

  // ---------- marco donde vive la foto ----------
  const statsIn = S.some(e => e.g === 'Datos' && e.t === 'text' && e.y > card.y && e.y < card.y + card.h && e.x > card.x + CW * .5);
  const fr0 = { x: card.x, y: card.y, w: statsIn ? CW * .55 : CW, h: card.h };
  const contentSide = statsIn ? 'der' : (S.some(e => e.g === 'Datos' && e.a === 'end') ? 'der' : 'centro');
  const mT = Math.max(24, .08 * card.h), mB = Math.max(32, .1 * card.h), mH = Math.max(32, .04 * fr0.w);
  // escala por familia: tope de área de la foto sobre la tarjeta (OLT pesa más que una ONT)
  // escala: con medidas reales (mm) del PM, área relativa = 0,50 × (L/480)^0,75 (L = lado mayor; 480 = OLT de 19");
  // así una ONT de 185 mm y una OLT de 480 mm quedan en proporción en todo el catálogo. Sin medidas: tope por familia.
  const CAPF = { olt: .50, ont: .30, pasivo: .40 }[cfg.familia] || .50;
  const Lmm = cfg.medidas_mm ? Math.max(...Object.values(cfg.medidas_mm).map(Number).filter(v => v > 0)) : 0;
  const CAP = Lmm ? Math.max(.18, Math.min(.55, .50 * Math.pow(Lmm / 480, .75))) : CAPF;
  R.medidas.escala = Lmm ? { modo: 'fisica', lado_mayor_mm: Lmm, area_objetivo: +CAP.toFixed(3) } : { modo: 'familia', familia: cfg.familia, area_objetivo: CAP };
  const capW = fr0.w - 2 * mH, capH = card.h - mT - mB, w0 = foto.w;
  const ar = foto.w / foto.h;
  // Nicolás (29/10): el equipo va centrado en su tarjeta. Con centrado:false vuelve a tercios + aire de mirada.
  const centrar = cfg.centrado !== false;
  const lines = centrar ? [.5] : mira === 'der' ? [1 / 3, 1 - 1 / PHI] : mira === 'izq' ? [2 / 3, 1 / PHI] : [.5];

  // ---------- búsqueda: escala máxima que cumple tercios + mirada + márgenes ----------
  let best = null; const s0 = Math.min(capW / foto.w, capH / foto.h, Math.sqrt(CAP * fr0.w * fr0.h / (foto.w * foto.h)), 1.25);
  for (let s = s0; s >= .85 && !best; s -= .005) {   // tercios solo si el equipo no pierde más del 15 % de tamaño
    const pw = foto.w * s, ph = pw / ar;
    for (const L of lines) {
      const c = fr0.x + L * fr0.w, x0 = c - vcx * pw, airL = x0 - fr0.x, airR = fr0.x + fr0.w - (x0 + pw);
      if (airL < mH || airR < mH) continue;
      const fac = mira === 'der' ? airR / airL : mira === 'izq' ? airL / airR : 1;
      if (!centrar && mira !== 'centro' && (fac < 1.25 || fac > 4.5)) continue;
      best = { s, pw, ph, x0, L, airL, airR, fac }; break;
    }
  }
  if (!best) { // equipo dominante (ocupa casi todo el ancho): los tercios no aplican.
    // Se mantiene el tamaño y se corre hacia atrás para dar aire del lado al que mira (1,4 : 1).
    const pw = foto.w * Math.min(s0, 1), free = fr0.w - pw, lead = (centrar || mira === 'centro') ? .5 : 1.4 / 2.4;
    const airMin = Math.min(mH, free / 2.4);
    let aL = centrar ? free / 2 : mira === 'der' ? free * (1 - lead) : mira === 'izq' ? free * lead : free / 2; aL = Math.max(airMin, Math.min(free - airMin, aL));
    best = { s: pw / foto.w, pw, ph: pw / ar, x0: fr0.x + aL, L: null, modo: 'dominante' };
    R.avisos.push('equipo dominante: tercios no aplican, se aplica aire de mirada 1,4 : 1');
  }
  // vertical: apoyo sobre el piso de la tarjeta, deja aire para sombra (y reflejo)
  // tarjeta baja: apoyada sobre el piso; tarjeta alta: centro visual en el centro óptico (apenas arriba del centro)
  let y0 = card.h < 1.5 * best.ph ? card.y + card.h - mB - best.ph : card.y + card.h * .48 - vcy * best.ph;
  if (y0 < card.y + mT) y0 = card.y + (card.h - best.ph) / 2;
  // grilla de 8 px (sin romper los márgenes)
  let gx = G8(best.x0), gy = G8(y0);
  if (gx - fr0.x < mH) gx += 8; if (fr0.x + fr0.w - (gx + best.pw) < mH) gx -= 8;
  if (gy - card.y < mT) gy += 8; if (card.y + card.h - (gy + best.ph) < 32) gy -= 8;
  Object.assign(foto, { src, x: gx, y: gy, w: best.pw, h: best.ph });

  // ---------- calidad de la foto ----------
  // ampliación = píxeles mostrados / píxeles de origen. En el celular la pieza se ve 1:1 (1080 px).
  const ampl = best.pw / nw;
  let nit = null;
  { const W2 = Math.min(nw, 700), sc = W2 / nw, H2 = Math.round(nh * sc), c2 = document.createElement('canvas'); c2.width = W2; c2.height = H2;
    const g2 = c2.getContext('2d', { willReadFrequently: true }); g2.drawImage(im, 0, 0, W2, H2); const d2 = g2.getImageData(0, 0, W2, H2).data;
    const L = new Float32Array(W2 * H2), A = new Uint8Array(W2 * H2);
    for (let i = 0; i < W2 * H2; i++) { L[i] = .299 * d2[i * 4] + .587 * d2[i * 4 + 1] + .114 * d2[i * 4 + 2]; A[i] = d2[i * 4 + 3] > 127 ? 1 : 0 }
    const box = (S0) => { const T = new Float32Array(S0.length), O = new Float32Array(S0.length); for (let y = 0; y < H2; y++) for (let x = 1; x < W2 - 1; x++) { const i = y * W2 + x; T[i] = (S0[i - 1] + S0[i] + S0[i + 1]) / 3 } for (let y = 1; y < H2 - 1; y++) for (let x = 0; x < W2; x++) { const i = y * W2 + x; O[i] = (T[i - W2] + T[i] + T[i + W2]) / 3 } return O };
    const B = box(box(L));
    const lv = (S0) => { let s = 0, s2 = 0, n = 0; for (let y = 3; y < H2 - 3; y++) for (let x = 3; x < W2 - 3; x++) { const i = y * W2 + x; if (!(A[i] && A[i - 3] && A[i + 3] && A[i - 3 * W2] && A[i + 3 * W2])) continue; const v = S0[i - 1] + S0[i + 1] + S0[i - W2] + S0[i + W2] - 4 * S0[i]; s += v; s2 += v * v; n++ } return n ? s2 / n - (s / n) ** 2 : 0 };
    const vb = lv(B); nit = vb > 0 ? lv(L) / vb : null; }
  R.medidas.calidad = { ampliacion: +ampl.toFixed(2), px_origen: [nw, nh], nitidez: nit === null ? null : +nit.toFixed(2) };
  if (ampl > 1.25 && ampl <= 1.8) R.avisos.push(`foto ampliada ${ampl.toFixed(2)}×: se puede ver blanda; pedir una de mayor resolución`);
  if (ampl > 1.8) R.avisos.push(`foto ampliada ${ampl.toFixed(2)}×: muy chica para esta pieza, pedir una de al menos ${Math.ceil(best.pw / 1.25)} px de ancho`);
  if (nit !== null && nit < 2.4 && ampl > .9) R.avisos.push(`foto blanda (nitidez ${nit.toFixed(2)}): pedir una más nítida`);

  // ---------- capas: brillo de marca (plano medio), sombra de apoyo y reflejo opcional ----------
  const vx = gx + vcx * best.pw - card.x, vy = gy + vcy * best.ph - card.y;
  const glow = (() => {
    const c = document.createElement('canvas'); c.width = card.w; c.height = card.h; const g = c.getContext('2d');
    g.beginPath(); g.roundRect(.5, .5, card.w - 1, card.h - 1, 28); g.clip();
    g.save(); g.translate(vx, vy + best.ph * .18); g.scale(1, .62);
    const rr = best.pw * .62, gr = g.createRadialGradient(0, 0, 4, 0, 0, rr);
    gr.addColorStop(0, 'rgba(92,118,186,.30)'); gr.addColorStop(.55, 'rgba(92,118,186,.10)'); gr.addColorStop(1, 'rgba(92,118,186,0)');
    g.fillStyle = gr; g.beginPath(); g.arc(0, 0, rr, 0, Math.PI * 2); g.fill();
    const gg = g.createRadialGradient(0, best.ph * .35, 2, 0, best.ph * .35, rr * .7);
    gg.addColorStop(0, 'rgba(47,224,138,.07)'); gg.addColorStop(1, 'rgba(47,224,138,0)');
    g.fillStyle = gg; g.beginPath(); g.arc(0, best.ph * .35, rr * .7, 0, Math.PI * 2); g.fill(); g.restore();
    return c.toDataURL('image/png');
  })();
  // sombra de apoyo: elipse suave bajo la base del equipo (más tenue si el equipo flota en el centro de la tarjeta)
  const apoyado = (card.y + card.h) - (gy + best.ph) < .18 * card.h;
  // base: mediana del borde inferior en el 50 % central del equipo; ancho: 88 % del equipo
  const maxB = Math.max(...colBot.filter(v => v >= 0));
  const mid = []; for (let x = Math.floor(xs0 + .25 * (xs1 - xs0)); x <= Math.floor(xs0 + .75 * (xs1 - xs0)); x++) if (colBot[x] >= 0) mid.push(colBot[x]);
  mid.sort((a, b) => a - b); const bMed = mid.length ? mid[mid.length >> 1] : maxB;
  const sW = (xs1 - xs0) / nw * best.pw * .88, sCx = gx + (xs0 + xs1) / 2 / nw * best.pw, sH = Math.max(10, Math.min(best.ph * .07, 34));
  const baseY = gy + (bMed + maxB) / 2 / nh * best.ph, opS = apoyado ? .42 : .24;
  const shadow = (() => {
    const c = document.createElement('canvas'); c.width = card.w; c.height = card.h; const g = c.getContext('2d');
    g.beginPath(); g.roundRect(.5, .5, card.w - 1, card.h - 1, 28); g.clip();
    g.save(); g.translate(sCx - card.x, baseY - card.y + (apoyado ? 2 : sH * .8)); g.scale(1, sH / (sW / 2));
    const gr = g.createRadialGradient(0, 0, 0, 0, 0, sW / 2); gr.addColorStop(0, `rgba(6,5,16,${opS})`); gr.addColorStop(.6, `rgba(6,5,16,${opS * .45})`); gr.addColorStop(1, 'rgba(6,5,16,0)');
    g.fillStyle = gr; g.beginPath(); g.arc(0, 0, sW / 2, 0, Math.PI * 2); g.fill(); g.restore(); return c.toDataURL('image/png');
  })();
  R.medidas.sombra = { apoyado, opacidad: opS, ancho: Math.round(sW), alto: Math.round(sH) };
  const layers = [{ g: 'Producto', t: 'img', src: glow, x: card.x, y: card.y, w: card.w, h: card.h, capa: 'brillo' },
                  { g: 'Producto', t: 'img', src: shadow, x: card.x, y: card.y, w: card.w, h: card.h, capa: 'sombra' }];
  let reflOp = 0;
  if (cfg.reflejo) {
    const rh = Math.min(best.ph * .3, card.y + card.h - (gy + best.ph) - 10);
    if (rh > 8) {
      reflOp = .12; const fim = await dzImg(src), c = document.createElement('canvas');
      c.width = Math.ceil(best.pw); c.height = Math.ceil(rh); const g = c.getContext('2d');
      g.save(); g.translate(0, rh); g.scale(1, -1); g.drawImage(fim, 0, rh - best.ph, best.pw, best.ph); g.restore();
      g.globalCompositeOperation = 'destination-in'; const gr = g.createLinearGradient(0, 0, 0, rh);
      gr.addColorStop(0, `rgba(255,255,255,${reflOp})`); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, c.width, c.height);
      S.splice(iFoto + 1, 0, { g: 'Producto', t: 'img', src: c.toDataURL('image/png'), x: gx, y: gy + best.ph + 2, w: best.pw, h: rh, capa: 'reflejo' });
    }
  }
  S.splice(iFoto, 0, ...layers);

  // ---------- informe ----------
  const vcxAbs = gx + vcx * best.pw, frLines = ((centrar || mira === 'centro') ? [.5] : [1 / 3, 2 / 3, 1 / PHI, 1 - 1 / PHI]).map(L => fr0.x + L * fr0.w);   // frontal: eje central
  const dTer = Math.min(...frLines.map(l => Math.abs(l - vcxAbs)));
  const airL = gx - fr0.x, airR = fr0.x + fr0.w - (gx + best.pw), airT = gy - card.y, airB = card.y + card.h - (gy + best.ph);
  const fac = mira === 'der' ? airR / airL : mira === 'izq' ? airL / airR : 1;
  const visTxt = S.filter(e => e.t === 'text' && e.g !== 'Pie' && e.txt);
  const chicos = visTxt.filter(e => e.s < 22).map(e => `${e.txt.slice(0, 28)} (${e.s}px)`);
  const nAtr = S.filter(e => e.g === 'Atributos' && e.t === 'icon').length;
  const nDat = S.filter(e => e.g === 'Datos' && e.t === 'text' && e.s >= 28).length;
  Object.assign(R.medidas, {
    marco: [Math.round(fr0.x), Math.round(fr0.y), Math.round(fr0.w), Math.round(fr0.h)],
    foto: [gx, gy, Math.round(best.pw), Math.round(best.ph)], escala_vs_plantilla: +(best.pw / w0).toFixed(3),
    centro_visual: [Math.round(vcxAbs), Math.round(gy + vcy * best.ph)], dist_tercio_px: Math.round(dTer),
    aire_izq_der_arr_aba: [airL, airR, airT, airB].map(Math.round), aire_mirada: +fac.toFixed(2),
    ancho_rel_marco: +(best.pw / fr0.w).toFixed(3), modo: best.modo || (centrar ? 'centrado' : 'tercios'), lado_contenido: contentSide,
    atributos: nAtr, cifras: nDat, textos_menores_22: chicos.length
  });
  if (chicos.length) R.avisos.push('textos de plantilla < 22 px (no se tocan): ' + chicos.slice(0, 4).join(' · '));
  R.pruebas = {
    tercios: best.modo === 'dominante' ? true : dTer <= .025 * fr0.w,
    mirada: (centrar || mira === 'centro') ? true : fac >= (best.modo === 'dominante' ? 1.15 : 1.25) && fac <= 4.5,
    lineas_guia: centrar || mira === 'centro' || mira === contentSide,
    espacio_negativo: Math.min(airL, airR) >= (best.modo === 'dominante' ? 24 : mH - 8) && airT >= mT - 8 && airB >= 32,
    profundidad: S.indexOf(card) < S.findIndex(e => e.capa === 'brillo') && S.findIndex(e => e.capa === 'brillo') < S.indexOf(foto) && foto.shadow === true,
    reflejo_tope: reflOp <= .14,
    enmarcado: gx >= card.x && gy >= card.y && gx + best.pw <= card.x + card.w && gy + best.ph <= card.y + card.h,
    impares: (nAtr === 0 || nAtr % 2 === 1) && (nDat === 0 || nDat % 2 === 1),
    escala: best.pw * best.ph / (fr0.w * fr0.h) <= CAP + .01,
    calidad_foto: ampl <= 1.8,
    sombra_apoyo: S.findIndex(e => e.capa === 'brillo') < S.findIndex(e => e.capa === 'sombra') && S.findIndex(e => e.capa === 'sombra') < S.indexOf(foto),
    grilla_8px: gx % 8 === 0 && gy % 8 === 0
  };
  R.aprobado = Object.values(R.pruebas).every(Boolean);
  return R;
};
