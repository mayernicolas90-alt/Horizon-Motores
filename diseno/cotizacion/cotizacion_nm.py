"""Cotización Horizon en el formato de la NM60 (modelo aprobado por Nicolás el 25/11/2026 con la NM61 CEVIC).
HTML -> PDF y PNG con Chrome (o Edge) sin cabecera, y control del PDF con pdfplumber.
Uso: python -I -X utf8 cotizacion_nm.py cot.json SALIDA_SIN_EXTENSION   -> SALIDA.pdf, SALIDA.png, SALIDA.html
     python -I -X utf8 cotizacion_nm.py --autotest
cot.json: {numero, fecha (dd/mm/aaaa), cliente, cuit, atencion, condIva, condPago,
           items [{articulo, sub, cant, precio, iva}], observaciones [..], tc, tc_fuente}
Fuentes: Manrope e Inter desde fonts.googleapis.com (necesita internet; si no cargan, el control FALLA).
Salida 0 = «Control PDF: APROBADO». Contenido según la NM61: sin validez, sin financiación (L-215) y sin a qué CUIT
se factura (eso va en la ficha del CRM).
"""
import json, sys, subprocess, pathlib, html, os
VERSION = 'cotizacion_nm 1.0 · 2026-11-25'
NAVEGADORES = (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
               r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
               r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
               "/usr/bin/google-chrome", "/usr/bin/chromium")


def navegador():
    for p in NAVEGADORES:
        if os.path.exists(p):
            return p
    sys.exit('FALLA: no encuentro Chrome ni Edge')


def ar(v, d=2):
    return f"{v:,.{d}f}".replace(',', 'X').replace('.', ',').replace('X', '.')


def pu(v):
    s = f"{v:.4f}".rstrip('0')
    ent, dec = s.split('.')
    return ar(int(ent), 0) + ',' + dec.ljust(2, '0')


def pct(v):
    return f"{v:g}".replace('.', ',') + ' %'


U = ['', 'uno', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve', 'diez', 'once', 'doce', 'trece', 'catorce',
     'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve', 'veinte', 'veintiuno', 'veintidós', 'veintitrés',
     'veinticuatro', 'veinticinco', 'veintiséis', 'veintisiete', 'veintiocho', 'veintinueve']
D = ['', '', '', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
CE = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos', 'ochocientos',
      'novecientos']


def l99(n):
    return U[n] if n < 30 else D[n // 10] + ('' if n % 10 == 0 else ' y ' + U[n % 10])


def l999(n):
    if n == 100:
        return 'cien'
    return ' '.join(x for x in (CE[n // 100], l99(n % 100)) if x)


def letras(n):
    if n == 0:
        return 'cero'
    m, r = divmod(n, 1000)
    mil = '' if m == 0 else ('mil' if m == 1 else l999(m) + ' mil')
    return ' '.join(x for x in (mil, l999(r)) if x)


def armar(C, out):
    out = pathlib.Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    CH = navegador()
    neto = round(sum(round(i['precio'] * i['cant'], 2) for i in C['items']), 2)
    ivas = {}
    for i in C['items']:
        ivas[i['iva']] = ivas.get(i['iva'], 0) + round(i['precio'] * i['cant'], 2)
    iva = round(sum(round(b * p / 100, 2) for p, b in ivas.items()), 2)
    total = round(neto + iva, 2)
    ent, cen = int(total), round((total - int(total)) * 100)
    e = html.escape
    
    filas = ''.join(
        f"<tr><td class='art'><div class='an'>{e(i['articulo'])}</div><div class='sub'>{e(i['sub'])}</div></td>"
        f"<td class='n'>{ar(i['cant'], 0)}</td><td class='n'>{pu(i['precio'])}</td><td class='n'>{pct(i['iva'])}</td>"
        f"<td class='n b'>{ar(round(i['precio'] * i['cant'], 2))}</td></tr>" for i in C['items'])
    obs = ''.join(f"<li>{e(o)}</li>" for o in C['observaciones'])
    
    CSS = """@page{size:A4;margin:0}*{box-sizing:border-box;margin:0;padding:0}
    body{width:210mm;height:297mm;font-family:Inter,sans-serif;color:#1a1a2e;position:relative;-webkit-print-color-adjust:exact;print-color-adjust:exact}
    .top{background:#2e6cd4;height:31mm;display:flex;color:#fff}
    .logo{flex:1;display:flex;align-items:center;padding-left:20mm;font-family:Manrope;font-weight:400;font-size:22pt;letter-spacing:.42em}
    .nro{width:50mm;border-left:.6pt solid rgba(255,255,255,.55);display:flex;flex-direction:column;justify-content:center;align-items:flex-end;padding-right:7mm}
    .nro .k{font-size:6.5pt;letter-spacing:.3em}.nro .v{font-family:Manrope;font-weight:800;font-size:21pt;line-height:1.05}.nro .f{font-size:8pt}
    .wrap{padding:9mm 13mm 0 13mm}
    .lab{font-size:6.5pt;letter-spacing:.32em;color:#64748b;text-transform:uppercase}
    .sec{margin-bottom:3mm}.cli{border-top:.9pt solid #2e6cd4}
    .cli .r{display:flex;border-bottom:.5pt solid #dbe3ee;height:8.3mm;align-items:center}
    .cli .c{display:flex;align-items:center;width:56%;white-space:nowrap;overflow:hidden}.cli .c.d{width:44%;padding-left:4mm}.cli .c .lab{width:27mm;flex-shrink:0}.cli .c.d .lab{width:25mm}.cli .val{font-size:10.5pt}
    table{width:100%;border-collapse:collapse;margin-top:6mm}
    th{font-weight:400;font-size:6.5pt;letter-spacing:.2em;color:#64748b;text-align:right;padding:0 0 3mm;border-bottom:1pt solid #1a1a2e}
    th:first-child{text-align:left}td{padding:4mm 0;border-bottom:.5pt solid #dbe3ee;vertical-align:middle;font-size:10.5pt}
    td.n{text-align:right}td.b{font-weight:600}.an{font-size:11pt}.sub{font-size:7pt;color:#64748b;margin-top:1mm}
    .tot{margin-left:auto;width:85mm;margin-top:5mm}.tl{display:flex;justify-content:space-between;font-size:10.5pt;padding:2mm 0}
    .tb{background:#2e6cd4;color:#fff;border-radius:2mm;display:flex;justify-content:space-between;align-items:center;padding:3.5mm 5mm;margin-top:2mm}
    .tb .k{font-size:6.5pt;letter-spacing:.3em}.tb .v{font-family:Manrope;font-weight:700;font-size:18pt}
    .son{text-align:right;font-style:italic;font-size:7.5pt;color:#64748b;margin-top:3mm;padding-bottom:5mm;border-bottom:.5pt solid #dbe3ee}
    .obs{margin-top:12mm}.obs .t{font-size:6.5pt;letter-spacing:.3em;color:#2e6cd4;font-weight:600;margin-bottom:3mm}
    .obs ul{list-style:none}.obs li{font-size:8.8pt;margin:2.3mm 0;padding-left:5mm;position:relative}
    .obs li:before{content:'';position:absolute;left:0;top:1mm;width:2.4mm;height:2.4mm;background:#2e6cd4}
    .tc{display:flex;justify-content:space-between;font-size:8pt;color:#64748b;margin-top:3mm}.tc b{color:#1a1a2e}
    .pie{position:absolute;bottom:0;left:0;right:0;height:26mm;background:#2e6cd4;color:#fff;display:flex;justify-content:space-between;padding:7mm 13mm 0;font-size:7pt;line-height:1.8}
    .pie .d{text-align:right}"""
    
    H = f"""<!doctype html><html><head><meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Manrope:wght@300;400;500;600;700;800&display=block" rel="stylesheet">
    <style>{CSS}</style></head><body>
    <div class="top"><div class="logo">HORIZON</div><div class="nro"><div class="k">COTIZACIÓN</div><div class="v">{e(C['numero'])}</div><div class="f">{e(C['fecha'])}</div></div></div>
    <div class="wrap"><div class="lab sec">Datos del cliente</div><div class="cli">
    <div class="r"><div class="c"><span class="lab">Cliente</span><span class="val">{e(C['cliente'])}</span></div><div class="c d"><span class="lab">C.U.I.T.</span><span class="val">{e(C['cuit'])}</span></div></div>
    <div class="r"><div class="c"><span class="lab">Atención</span><span class="val">{e(C.get('atencion') or '—')}</span></div><div class="c d"><span class="lab">Cond. IVA</span><span class="val">{e(C['condIva'])}</span></div></div>
    <div class="r"><div class="c"><span class="lab">Cond. pago</span><span class="val">{e(C['condPago'])}</span></div><div class="c d"><span class="lab">Moneda</span><span class="val">Dólares estadounidenses</span></div></div></div>
    <table><tr><th>ARTÍCULO</th><th style="width:22mm">CANT.</th><th style="width:26mm">PRECIO U.</th><th style="width:19mm">IVA</th><th style="width:26mm">NETO USD</th></tr>{filas}</table>
    <div class="tot"><div class="tl"><span>Neto</span><span>USD {ar(neto)}</span></div><div class="tl"><span>IVA</span><span>USD {ar(iva)}</span></div>
    <div class="tb"><span class="k">TOTAL USD</span><span class="v">{ar(total)}</span></div></div>
    <div class="son">Son dólares estadounidenses {letras(ent)} con {cen:02d}/100</div>
    <div class="obs"><div class="t">OBSERVACIONES</div><ul>{obs}</ul>
    <div class="tc"><span>Tipo de cambio de referencia: <b>ARS {ar(C['tc'])} / USD</b> ({e(C['tc_fuente'])})</span><span>Equivalente en pesos: <b>ARS {ar(round(total * C['tc'], 2))}</b></span></div></div></div>
    <div class="pie"><div><b>HORIZON TRADING S.A.</b> · Responsable Inscripto<br>Ciudad de la Paz 2846, Piso 3, Dep. A · Belgrano (1428), CABA, Argentina<br>C.U.I.T.: 30-71493161-6 · Ing. Brutos: 30-71493161-6 · Inicio de actividades: 16/07/2015</div>
    <div class="d"><b>www.horizon-trd.com</b><br>Tel: 2113-9433<br>Mikrotik · FiberHome · Furukawa/Lightera · UNIRIM</div></div></body></html>"""
    
    hp = out.with_suffix('.html')
    hp.write_text(H, encoding='utf-8')
    base = [CH, '--headless=new', '--disable-gpu', '--virtual-time-budget=8000']
    subprocess.run(base + ['--no-pdf-header-footer', f'--print-to-pdf={out.with_suffix(".pdf")}', hp.as_uri()],
                   check=True, capture_output=True, timeout=120)
    subprocess.run(base + ['--window-size=794,1123', '--hide-scrollbars', f'--screenshot={out.with_suffix(".png")}', hp.as_uri()],
                   check=True, capture_output=True, timeout=120)
    
    import pdfplumber
    p = pdfplumber.open(str(out.with_suffix('.pdf')))
    t = '\n'.join(x.extract_text() or '' for x in p.pages)
    f = [f'{k} {v} no aparece' for k, v in (('neto', ar(neto)), ('iva', ar(iva)), ('total', ar(total))) if v not in t]
    f += [f"precio {pu(i['precio'])} no aparece" for i in C['items'] if pu(i['precio']) not in t]
    if len(p.pages) != 1:
        f.append(f'{len(p.pages)} páginas')
    for pg in p.pages:
        for w in pg.extract_words():
            if w['x1'] > pg.width - 5 or w['x0'] < 5:
                f.append(f"«{w['text']}» toca el borde")
    fn = {ch.get('fontname', '') for pg in p.pages for ch in pg.chars}
    p.close()
    if not any('Manrope' in x for x in fn) or not any('Inter' in x for x in fn):
        f.append('fuentes: ' + ', '.join(sorted(fn)))
    print(f"NETO {ar(neto)} · IVA {ar(iva)} · TOTAL {ar(total)}")
    print('Control PDF: APROBADO' if not f else 'Control PDF: FALLA · ' + ' · '.join(f))
    return 1 if f else 0


def autotest():
    mal = []
    casos = [(ar(1105), '1.105,00'), (ar(1790100), '1.790.100,00'), (pu(25), '25,00'), (pu(0.0995), '0,0995'),
             (pu(0.96), '0,96'), (pct(10.5), '10,5 %'), (letras(1105), 'mil ciento cinco'),
             (letras(562), 'quinientos sesenta y dos'), (letras(100), 'cien'), (letras(21000), 'veintiuno mil')]
    for got, exp in casos:
        if got != exp:
            mal.append(f'{got!r} != {exp!r}')
    aqui = pathlib.Path(__file__).resolve().parent
    import tempfile
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        rc = armar(json.load(open(aqui / 'ejemplo_nm61.json', encoding='utf-8')), pathlib.Path(d) / 'NM61')
        if rc:
            mal.append('ejemplo NM61: control FALLA')
    print(f'{VERSION} · autotest {len(casos) + 1 - len(mal)}/{len(casos) + 1}' + ('' if not mal else ' · ' + ' · '.join(mal)))
    return 1 if mal else 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--autotest':
        sys.exit(autotest())
    if len(sys.argv) != 3:
        print(__doc__); sys.exit(2)
    sys.exit(armar(json.load(open(sys.argv[1], encoding='utf-8')), sys.argv[2]))
