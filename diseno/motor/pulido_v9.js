// Pulido V9 (opcional, "pulido": true en la ficha): criterios de diagramación sobre la escena ya armada.
// No toca la plantilla ni la foto; solo ajusta tamaños, colores de texto y espacios entre bloques.
// 1 escala tipográfica cerrada: 18 · 22 · 24 · 34 · 40 · 64+ (sin tamaños vecinos casi iguales)
// 2 legibilidad en celular: nada por debajo de 22 px, salvo mayúsculas espaciadas y el legal (18 px)
// 3 contraste WCAG 2: texto chico ≥ 4,5:1 contra el fondo de su tarjeta (aclara el gris si hace falta)
// 4 espacio en blanco repartido: el hueco grande antes del pie se reparte entre los bloques (ritmo de 4 px)
(function () {
  const lin = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4) };
  const hex = h => { h = String(h || '').replace('#', ''); if (h.length !== 6) return null; return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)) };
  const L = rgb => 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2]);
  const cr = (a, b) => { const x = L(a), y = L(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) };
  const toHex = rgb => '#' + rgb.map(v => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('');
  const BG = [33, 30, 54];                       // fondo de la pieza
  function fondoDe(S, e) {                        // tarjeta (rect opaco) que contiene al texto
    let f = BG;
    for (const r of S) if (r.t === 'rect' && hex(r.fill) && e.x >= r.x && e.x <= r.x + r.w && e.y >= r.y && e.y <= r.y + r.h) f = hex(r.fill);
    return f;
  }
  function escala(e) {
    const s = e.s, caps = (e.ls || 0) > 0 && e.txt === (e.txt || '').toUpperCase();
    const legal = /Sujeto a disponibilidad/.test(e.txt || '');
    if (s >= 60) return s;
    if (s >= 36) return 40;
    if (s >= 30) return 34;
    if (caps || legal) return 18;
    return 22;
  }
  window.pulirV9 = function (S, fmt, k, opc) {
    opc = opc || {};
    const H = fmt === 'estado' ? 1920 : 1350, pie = S.find(e => e.t === 'rect' && e.x === 0 && e.w >= 1080 && e.y > H * 0.8);
    const log = [];
    // pilas cifra + rótulo (tarjeta de la ficha): la cifra baja a 34 para que el rótulo de 22 respire (≥ 12 px libres)
    for (const e of S) {
      if (e.t !== 'text' || !(e.s >= 36 && e.s < 60)) continue;
      const rot = S.find(o => o !== e && o.t === 'text' && o.x === e.x && o.s < 22 && o.y - e.y > 0 && o.y - e.y < 30);
      if (rot) { log.push(`${(e.txt || '').slice(0, 12)} ${e.s}→34 (pila con rótulo)`); e.s = 34; e._pila = true }
    }
    // 1-2 tamaños; si un rótulo crece, se baja lo justo para no pisar al valor de arriba
    for (const e of S) {
      if (e.t !== 'text' || !e.s) continue;
      const n = escala(e);
      if (n !== e.s) {
        const arriba = S.find(o => o !== e && o.t === 'text' && o.x === e.x && o.s >= 34 && e.y - o.y > 0 && e.y - o.y < 30);
        if (arriba && n > e.s) e.y += arriba._pila ? Math.round((n - e.s) * 0.6) : Math.round((n - e.s) * 0.9);
        log.push(`${(e.txt || '').slice(0, 18)} ${e.s}→${n}`); e.s = n;
      }
    }
    // 3 contraste
    for (const e of S) {
      if (e.t !== 'text') continue;
      const c = hex(e.fill); if (!c) continue;
      const f = fondoDe(S, e).map(v => v + 8), min = (e.s >= 30 ? 3 : 4.5) + 0.3;   // +8: velos claros sobre la tarjeta
      let x = c.slice(), i = 0;
      while (cr(x, f) < min && i++ < 40) x = x.map(v => v + (255 - v) * 0.06);
      if (i) { log.push(`${(e.txt || '').slice(0, 18)} contraste ${cr(c, f).toFixed(1)}→${cr(x, f).toFixed(1)}`); e.fill = toHex(x) }
    }
    // 4 espacio: bloques = tarjetas (rect/img anchos) entre el título y el pie
    if (pie && k === 'detalle') {
      const tarjetas = S.filter(e => (e.t === 'rect' || e.t === 'img') && e.w >= 900 && e.y > 340 && e.y < pie.y)
        .map(e => [e.y, e.y + e.h]).sort((a, b) => a[0] - b[0]);
      const bloques = [];
      for (const [a, b] of tarjetas) { const u = bloques[bloques.length - 1]; if (u && a <= u[1] + 2) u[1] = Math.max(u[1], b); else bloques.push([a, b]) }
      if (bloques.length >= 2) {
        // aire dentro de la tabla (no entre bloques): la tarjeta de la foto y su separación quedan igual, así el panal no cambia;
        // cada fila de la tabla gana 'paso' px y lo que está debajo baja lo mismo; el hueco final queda ≤ 7 % del alto.
        const tabla = S.filter(e => e.t === 'rect' && e.w >= 900 && e.y > bloques[0][1] && e.y < pie.y).sort((x, y) => y.h - x.h)[0];
        if (tabla) {
          const filas = S.filter(e => e.t === 'text' && e.x < tabla.x + 60 && e.y > tabla.y + 60 && e.y < tabla.y + tabla.h).sort((x, y) => x.y - y.y);
          const hueco = pie.y - bloques[bloques.length - 1][1], meta = Math.round(0.07 * H);
          const paso = filas.length ? Math.max(0, Math.min(24, Math.floor((hueco - meta) / (filas.length + 1) / 4) * 4)) : 0;
          if (paso > 0) {
            const ys = filas.map(f => f.y);
            const ya = new Set();
            for (const e of S) {
              if (ya.has(e)) continue; ya.add(e);
              if (e === pie || e === tabla || e.y === undefined || (e.t === 'img' && e.w >= 1080) || e.y >= pie.y || e.y < tabla.y + 60) continue;
              let n = 0; ys.forEach(y => { if (e.y >= y - 4) n++ });
              if (e.y > tabla.y + tabla.h) n = filas.length + 1;
              if (n) { e.y += paso * n; if (e.y1 !== undefined) { e.y1 += paso * n; e.y2 += paso * n } }
            }
            tabla.h += paso * (filas.length + 1);
            log.push(`tabla con más aire: +${paso} px por fila; hueco antes del pie ${Math.round(hueco)} → ${Math.round(hueco - paso * (filas.length + 1))} px`);
          }
        }
      }
    }
    // portada: si sobra aire antes del pie, la foto y lo que sigue bajan la mitad (contenido centrado entre título y pie)
    if (pie && k === 'portada') {
      const card = S.filter(e => (e.t === 'img' || e.t === 'rect') && e.w >= 900 && e.y > 300 && e.y < pie.y).sort((a, b) => a.y - b.y)[0];
      const fondo = Math.max(...S.filter(e => e.y !== undefined && e.y < pie.y && !(e.t === 'img' && e.w >= 1080)).map(e => e.t === 'text' ? e.y + 8 : e.y + (e.h || 0)));
      const hueco = pie.y - fondo, meta = Math.round(0.07 * H);
      const d = card && hueco > meta ? Math.floor((hueco - 24) / 2 / 4) * 4 : 0;
      if (d > 0) {
        const y0 = card.y, movidos = new Set();
        for (const e of S) { if (movidos.has(e) || e === pie || e.y === undefined || (e.t === 'img' && e.w >= 1080) || e.y >= pie.y || e.y < y0 - 1) continue; movidos.add(e); e.y += d; if (e.y1 !== undefined) { e.y1 += d; e.y2 += d } }
        log.push(`portada: foto y datos bajan ${d} px (hueco antes del pie ${hueco} → ${hueco - d} px)`);
      }
    }
    // ficha con el modelo como título (pedido de Nicolás 25/11): título = modelo, bajada = categoría, logo de marca grande
    if (k === 'detalle' && opc.titulo_modelo) {
      const tit = S.find(e => e.t === 'text' && e.s >= 60), sub = tit && S.find(e => e.t === 'text' && e.x === tit.x && e.y > tit.y && e.y - tit.y < 70);
      if (tit && sub) {
        const modelo = sub.txt; tit.txt = modelo; sub.txt = opc.bajada || tit.txt; sub.w = 500; sub.fill = '#c9c5de';
        log.push(`título = ${modelo} · bajada = ${sub.txt}`);
        const logo = S.find(e => e.t === 'img' && e.w < 200 && e.x > 700 && Math.abs(e.y - (tit.y - tit.s * 0.4)) < 60);
        if (logo) {
          const w = opc.logo_ancho || 230, h = logo.h * w / logo.w;
          logo.x = 1008 - w; logo.y = Math.round(tit.y - tit.s * 0.36 - h / 2); logo.w = w; logo.h = h;
          log.push(`logo de marca ${Math.round(w)} px de ancho, alineado con el modelo`);
        }
      }
    }
    // composición (checklist de diseñador): centrado óptico y líneas de base compartidas, sin mover la marca ni la plantilla
    if (k === 'detalle') {
      const capC = e => e.y - e.s * 0.36;                       // centro visual de la línea (altura de mayúscula ≈ 0,72 em)
      // a) texto del CTA centrado con su botón y su banda (antes quedaba alto)
      const boton = S.find(e => e.t === 'rect' && e.fill === '#2fe08a' && e.w < 200 && e.h < 70);
      if (boton) {
        const cta = S.find(e => e.t === 'text' && e.x < 200 && e.y > boton.y - 40 && e.y < boton.y + boton.h + 20 && e.s >= 20);
        const c = boton.y + boton.h / 2;
        if (cta && Math.abs(capC(cta) - c) > 2) { const d = Math.round(c - capC(cta)); cta.y += d; log.push(`CTA centrado con el botón (${d > 0 ? '+' : ''}${d} px)`) }
      }
      // b) rótulo y valor de cada fila de la tabla sobre la misma línea de base
      const vals = S.filter(e => e.t === 'text' && e.x > 300 && e.x < 400);
      let nb = 0;
      for (const v of vals) { const l = S.find(e => e.t === 'text' && e.x < 140 && Math.abs(e.y - v.y) < 4 && e !== v); if (l && l.y !== v.y) { v.y = l.y; nb++ } }
      if (nb) log.push(`tabla: ${nb} filas con línea de base compartida`);
      // c) columna de cifras centrada en su tarjeta (centro óptico: 2 % por encima del geométrico)
      const card = S.filter(e => e.t === 'img' && e.w >= 900 && e.y > 340 && e.y < 700).sort((a, b) => a.y - b.y)[0];
      if (card) {
        const col = S.filter(e => e.t === 'text' && e.x > 560 && e.y > card.y && e.y < card.y + card.h);
        if (col.length) {
          const top = Math.min(...col.map(e => e.y - e.s * 0.72)), bot = Math.max(...col.map(e => e.y));   // de la altura de mayúscula a la línea de base (lo que el ojo ve)
          const meta = card.y + card.h / 2, d = Math.round(meta - (top + bot) / 2);
          if (Math.abs(d) > 2) { col.forEach(e => e.y += d); log.push(`cifras centradas en la tarjeta (${d > 0 ? '+' : ''}${d} px)`) }
        }
        // d) foto centrada en su zona (entre el borde de la tarjeta y la columna de cifras), con el mismo centro óptico
        const foto = S.filter(e => e.t === 'img' && e.w < 700 && e.w > 60 && e.y >= card.y - 2 && e.y + e.h <= card.y + card.h + 2).sort((a, b) => b.w * b.h - a.w * a.h)[0];
        if (foto && col.length) {
          const x0 = card.x + 32, x1 = Math.min(...col.map(e => e.x)) - 48, cx = (x0 + x1) / 2;
          const dx = Math.round(cx - (foto.x + foto.w / 2)), dy = Math.round(card.y + card.h / 2 - card.h * 0.02 - (foto.y + foto.h / 2));
          if (Math.abs(dx) > 3 || Math.abs(dy) > 3) { foto.x += dx; foto.y += dy; log.push(`foto en el centro óptico de su zona (${dx}, ${dy} px)`) }
        }
      }
    }
    window.__pulido = (window.__pulido || {}); window.__pulido[fmt + '_' + k] = log;
    return S;
  };
})();
