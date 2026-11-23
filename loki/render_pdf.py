#!/usr/bin/env python3
"""render_pdf.py 0.1 · 23/11/2026 · imprime en la PC (Windows) las piezas HTML de Horizon con la nitidez del modelo NM53.

Por qué: el cotizador del PM (cot_hz2.py) imprime con Playwright, que en la PC no está. Chrome sin interfaz da el mismo
motor (Skia) y el mismo resultado, pero hay que corregir las rutas de las fuentes (`file://C:\\...` no carga en Windows y
el PDF cae a Arial: caso NM57 de prueba, 23/11).

La nitidez del NM53 (comparado el 23/11) sale de que el PDF es 100 % vectorial: 0 imágenes ráster, logo SVG en curvas,
fuentes Manrope e Inter incrustadas como TrueType, A4. Este script lo controla en cada PDF («control de nitidez»).
La imagen de control se saca a escala 2 para que se lea nítida (el PDF no depende de eso).

Uso:
  python -I -X utf8 loki/render_pdf.py imprimir PIEZA.html --nombre NM57_Cliente [--fuentes Manrope,Inter]
        [--cot PIEZA.cot.json --cotizador <carpeta cotizador del PM>]   (además corre su control_cot.py)
  python -I -X utf8 loki/render_pdf.py nitidez PIEZA.pdf [--fuentes Manrope,Inter]
  python -I -X utf8 loki/render_pdf.py --autotest
Salida 0 = PASA, 1 = FALLA. Solo biblioteca estándar (pdfplumber no hace falta). No escribe en el CRM ni en la base.
"""
import os, pathlib, re, subprocess, sys, zlib

VERSION = 'render_pdf 0.1 · 2026-11-23'
A4 = (595.28, 841.89)          # puntos
TOL_A4 = 3.0
NAVEGADORES = [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
               r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
               r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']


def corregir_fuentes(html):
    """url('file://C:\\a\\b.ttf') -> url('file:///C:/a/b.ttf'). Devuelve (html, cantidad corregida)."""
    n = [0]

    def f(m):
        n[0] += 1
        return "url('" + pathlib.PureWindowsPath(m.group(1)).as_uri() + "')"
    return re.sub(r"url\('file://([A-Za-z]:\\[^']+)'\)", f, html), n[0]


def navegador():
    for p in NAVEGADORES:
        if os.path.exists(p):
            return p
    raise SystemExit('FALLA · no hay Chrome ni Edge instalados')


def _objetos(raw):
    """Texto de cada objeto del PDF, con los streams Flate descomprimidos cuando se puede."""
    out = []
    for m in re.finditer(rb'(\d+)\s+0\s+obj(.*?)endobj', raw, re.S):
        cuerpo = m.group(2)
        s = re.search(rb'stream\r?\n(.*?)\r?\nendstream', cuerpo, re.S)
        if s and b'/FlateDecode' in cuerpo[:s.start()]:
            try:
                cuerpo = cuerpo[:s.start()] + zlib.decompress(s.group(1))
            except zlib.error:
                pass
        out.append((int(m.group(1)), cuerpo))
    return out


def nitidez(pdf, fuentes=('Manrope', 'Inter')):
    """Control de nitidez: A4, sin imágenes ráster, todas las fuentes incrustadas y las de la marca presentes."""
    raw = open(pdf, 'rb').read()
    numerados = _objetos(raw)
    objs = [o for _, o in numerados]
    # Chrome pasa las OTF (Inter) a fuentes Type3: los glifos van como dibujos vectoriales dentro del PDF; su descriptor
    # no lleva FontFile y eso no es una fuente faltante.
    tipo3 = {int(x) for o in objs if re.search(rb'/Subtype\s*/Type3\b', o)
             for x in re.findall(rb'/FontDescriptor\s+(\d+)\s+0\s+R', o)}
    fallas, datos = [], {}
    cajas = [tuple(float(x) for x in m.groups()) for o in objs for m in
             re.finditer(rb'/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]', o)]
    if not cajas:
        fallas.append('sin tamaño de página')
    for c in cajas:
        w, h = c[2] - c[0], c[3] - c[1]
        if abs(w - A4[0]) > TOL_A4 or abs(h - A4[1]) > TOL_A4:
            fallas.append(f'página {w:.1f} × {h:.1f} pt: no es A4')
    datos['paginas'] = len(cajas)
    imgs = sum(1 for o in objs if re.search(rb'/Subtype\s*/Image\b', o))
    datos['imagenes'] = imgs
    if imgs:
        fallas.append(f'{imgs} imagen(es) ráster: el PDF tiene que ser vectorial')
    desc_n = [(n, o) for n, o in numerados if b'/FontDescriptor' in o and b'/FontName' in o]
    sin = [re.search(rb'/FontName\s*/([^\s/>]+)', o).group(1).decode(errors='replace') for n, o in desc_n
           if not re.search(rb'/FontFile[23]?\b', o) and n not in tipo3]
    desc = [o for _, o in desc_n]
    nombres = sorted({re.search(rb'/FontName\s*/([^\s/>]+)', o).group(1).decode(errors='replace').split('+')[-1] for o in desc})
    datos['fuentes'] = nombres
    if sin:
        fallas.append('fuentes sin incrustar: ' + ', '.join(sin))
    for f in fuentes:
        if f and not any(n.startswith(f) for n in nombres):
            fallas.append(f'falta la fuente {f} (cayó a otra: {", ".join(nombres) or "ninguna"})')
    return (not fallas), fallas, datos


def imprimir(html, nombre, fuentes, cot=None, cotizador=None):
    out = os.path.dirname(os.path.abspath(html))
    t, n = corregir_fuentes(open(html, encoding='utf-8').read())
    win = os.path.join(out, nombre + '_win.html')
    open(win, 'w', encoding='utf-8').write(t)
    ch, u = navegador(), pathlib.Path(win).as_uri()
    base = ['--headless=new', '--disable-gpu', '--allow-file-access-from-files', '--virtual-time-budget=5000']
    pdf, png = os.path.join(out, nombre + '.pdf'), os.path.join(out, nombre + '.png')
    subprocess.run([ch] + base + ['--no-pdf-header-footer', '--print-to-pdf=' + pdf, u], capture_output=True)
    subprocess.run([ch] + base + ['--hide-scrollbars', '--window-size=794,1123', '--force-device-scale-factor=2',
                                  '--screenshot=' + png, u], capture_output=True)
    print(f'{VERSION} · fuentes corregidas {n} · {pdf}')
    if not os.path.exists(pdf):
        print('FALLA · Chrome no generó el PDF'); return 1
    ok, fallas, datos = nitidez(pdf, fuentes)
    print(f"  nitidez: {'PASA' if ok else 'FALLA'} · {datos}")
    for f in fallas:
        print('  ✗ ' + f)
    if cot and cotizador:
        r = subprocess.run([sys.executable, '-X', 'utf8', '-I', os.path.join(cotizador, 'control_cot.py'), pdf, cot],
                           capture_output=True, text=True, encoding='utf-8')
        fin = [l for l in r.stdout.splitlines() if l.strip()]
        print('  control_cot: ' + (fin[-1] if fin else r.stderr[-200:]))
        ok = ok and r.returncode == 0
    print('Render: ' + ('PASA' if ok else 'FALLA'))
    return 0 if ok else 1


def autotest():
    casos = []
    h, n = corregir_fuentes("x{src:url('file://C:\\Users\\a b\\fuentes\\Inter-Bold.otf')} y{src:url('file:///C:/ya/bien.ttf')}")
    casos.append(('ruta de Windows se corrige y la buena no se toca',
                  n == 1 and "file:///C:/Users/a%20b/fuentes/Inter-Bold.otf" in h and 'file:///C:/ya/bien.ttf' in h))
    import tempfile
    d = tempfile.mkdtemp()

    def pdf(nombre, extra=b'', fuente=b'/FontFile2 9 0 R', caja=b'0 0 595.28 841.89', fname=b'ABCDEF+Manrope-Bold'):
        p = os.path.join(d, nombre)
        cuerpo = (b'%PDF-1.4\n1 0 obj << /Type /Page /MediaBox [' + caja + b'] >> endobj\n'
                  b'2 0 obj << /Type /FontDescriptor /FontName /' + fname + b' ' + fuente + b' >> endobj\n'
                  b'3 0 obj << /Type /FontDescriptor /FontName /GHIJKL+Inter-Regular /FontFile2 8 0 R >> endobj\n' + extra +
                  b'%%EOF\n')
        open(p, 'wb').write(cuerpo)
        return p
    casos.append(('PDF vectorial A4 con fuentes incrustadas: PASA', nitidez(pdf('ok.pdf'))[0]))
    casos.append(('imagen ráster: FALLA', not nitidez(pdf('img.pdf', b'4 0 obj << /Type /XObject /Subtype /Image >> endobj\n'))[0]))
    casos.append(('fuente sin incrustar: FALLA', not nitidez(pdf('sinf.pdf', fuente=b''))[0]))
    casos.append(('OTF pasada a Type3 (vectorial, caso Inter): PASA',
                  nitidez(pdf('t3.pdf', b'5 0 obj << /Type /Font /Subtype /Type3 /FontDescriptor 2 0 R >> endobj\n', fuente=b''))[0]))
    casos.append(('cayó a Arial (falta Manrope): FALLA', not nitidez(pdf('arial.pdf', fname=b'ArialMT'))[0]))
    casos.append(('carta en vez de A4: FALLA', not nitidez(pdf('carta.pdf', caja=b'0 0 612 792'))[0]))
    ok = sum(1 for _, c in casos if c)
    for t, c in casos:
        print(('  OK   ' if c else '  FALLA ') + t)
    print(f'autotest render_pdf: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__); return 0
    if a[0] == '--autotest':
        return autotest()
    kv = dict(zip(a[2::2], a[3::2]))
    fuentes = [f for f in kv.get('--fuentes', 'Manrope,Inter').split(',') if f]
    if a[0] == 'imprimir':
        return imprimir(a[1], kv.get('--nombre') or os.path.splitext(os.path.basename(a[1]))[0], fuentes, kv.get('--cot'), kv.get('--cotizador'))
    if a[0] == 'nitidez':
        ok, fallas, datos = nitidez(a[1], fuentes)
        print(f"nitidez {'PASA' if ok else 'FALLA'} · {datos}")
        for f in fallas:
            print('  ✗ ' + f)
        return 0 if ok else 1
    print('comando desconocido: ' + a[0]); return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
