#!/usr/bin/env python3
"""auditor.py 0.1 · 23/11/2026 · la puerta de entrada de la base de Loki (pedido de Nicolás 23/11: «lo importante es
auditar la info que entra y que cada motor sea independiente»).

Toda información que entra pasa por acá: se RECIBE (con su sha256), se CLASIFICA (qué reporte es), se VERIFICA (controles
de su clase, cada resultado queda guardado) y recién entonces se PUBLICA en las tablas que leen los motores. Lo que falla
queda en CUARENTENA con su motivo, no alimenta a nadie, abre un tema en la bitácora 2 y `abrir` lo muestra hasta resolverlo.

Fase 1: reportes de Finnegans (facturación por renglón, cabecera de comprobantes y pedidos).

Uso (en la PC con conauth.py; en la nube el proxy pone el token):
  python -I -X utf8 loki/auditor.py entrar ARCHIVO [ARCHIVO ...] [--origen finnegans]
        recibe, clasifica y verifica los archivos como un solo lote (la cabecera sirve de control de los renglones)
  python -I -X utf8 loki/auditor.py publicar LOTE --hacelo "texto del hacelo"
        solo entradas verificadas: las carga en la base (archivos, cargas y, para la facturación, la tabla ventas)
  python -I -X utf8 loki/auditor.py estado            cuarentena, último lote y últimas publicaciones
  python -I -X utf8 loki/auditor.py --autotest        con una base SQLite temporal (no toca Turso)
Salida 0 = PASA (todo verificado o publicado) · 1 = algo quedó en cuarentena o se rechazó.
Escribe en la base de Loki: `entrar` solo en sus tablas (entrada, entrada_control) y en la bitácora 2 si hay cuarentena;
`publicar` en archivos/cargas/ventas y requiere el «hacelo» de Nicolás, que queda registrado.
"""
import csv, datetime as D, hashlib, importlib.util, io, json, os, re, sys, tempfile, unicodedata

VERSION = 'auditor 0.2 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))


def _modulo(nombre):
    sp = importlib.util.spec_from_file_location(nombre, os.path.join(AQUI, nombre + '.py'))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


L = _modulo('loki_sql')

DDL = [
    """CREATE TABLE IF NOT EXISTS entrada (id INTEGER PRIMARY KEY AUTOINCREMENT, lote TEXT NOT NULL, recibido TEXT NOT NULL,
       origen TEXT NOT NULL, nombre TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE, bytes INTEGER NOT NULL, texto TEXT,
       clase TEXT, codigo TEXT, filas INTEGER, corte TEXT,
       estado TEXT NOT NULL CHECK (estado IN ('recibida','clasificada','verificada','publicada','cuarentena','reemplazada')),
       motivo TEXT)""",
    """CREATE TABLE IF NOT EXISTS entrada_control (entrada_id INTEGER NOT NULL, control TEXT NOT NULL,
       estado TEXT NOT NULL CHECK (estado IN ('PASA','AVISO','FALLA')), detalle TEXT, fecha TEXT NOT NULL,
       PRIMARY KEY (entrada_id, control))""",
    """CREATE TABLE IF NOT EXISTS entrada_publicacion (entrada_id INTEGER NOT NULL, destino TEXT NOT NULL, filas INTEGER,
       fecha TEXT NOT NULL, hacelo TEXT NOT NULL, PRIMARY KEY (entrada_id, destino))""",
    "CREATE INDEX IF NOT EXISTS ix_entrada_estado ON entrada (estado, codigo)",
]
# Clase de cada reporte del registro (`reportes`). Lo que no está acá es «reporte» a secas (se verifica el formato).
RENGLONES = {'R6', 'R7', 'R10'}            # Análisis de Facturación por renglón (con TransaccionID)
CABECERA = {'R23', 'R4', 'R15'}           # comprobantes de venta, cabecera
ALIAS = {'indentificaciontributaria': 'identificaciontributaria'}   # error de tipeo de Finnegans en un formato
MAX_FALTAN = 0.02
EMPRESA = 'HORIZON TRADING'   # 0.2: la tabla ventas (R10) se arma solo con los renglones de esta empresa


def ahora():
    return D.datetime.now(D.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def hoy():
    return D.date.today().isoformat()


def nombre_col(s):
    """Compara columnas sin mayúsculas, acentos, espacios ni puntuación: «Nro de identificación» = «Nrodeidentificacion»."""
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[^a-z0-9]', '', s)
    return ALIAS.get(s, s)


def leer_texto(raw):
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1'), 'latin-1'


def tabla(texto):
    prim = texto.split('\n', 1)[0]
    sep = max(';,\t', key=prim.count)
    r = [f for f in csv.reader(io.StringIO(texto), delimiter=sep) if any(c.strip() for c in f)]
    return (r[0], r[1:], sep) if r else ([], [], sep)


def crear(db):
    L.init(db)
    db.run([(s, []) for s in DDL])


# ------------------------------------------------------------------ 1. recibir
def recibir(db, ruta, lote, origen='finnegans'):
    """Guarda el archivo. Devuelve (id, nuevo). Si la sha256 ya estaba, no lo duplica (se informa)."""
    raw = open(ruta, 'rb').read()
    h = hashlib.sha256(raw).hexdigest()
    ya = L.q(db, 'SELECT id, estado, lote FROM entrada WHERE sha256=?', h)
    if ya:
        return ya[0]['id'], False
    if raw[:2] == b'PK':
        texto, estado, motivo = None, 'cuarentena', 'vino en Excel: exportarlo en CSV desde Finnegans'
    else:
        texto, _ = leer_texto(raw)
        texto = texto.replace('\r\n', '\n')
        estado, motivo = 'recibida', None
    db.run([('INSERT INTO entrada (lote, recibido, origen, nombre, sha256, bytes, texto, estado, motivo) VALUES (?,?,?,?,?,?,?,?,?)',
             [lote, ahora(), origen, os.path.basename(ruta), h, len(raw), texto, estado, motivo])])
    i = L.q(db, 'SELECT id FROM entrada WHERE sha256=?', h)[0]['id']
    if estado == 'cuarentena':
        control(db, i, 'lectura', 'FALLA', motivo)
    return i, True


def control(db, i, nombre, estado, detalle):
    db.run([('INSERT OR REPLACE INTO entrada_control VALUES (?,?,?,?,?)', [i, nombre, estado, str(detalle)[:500], ahora()])])


# ------------------------------------------------------------------ 2. clasificar
def registro(db):
    return {r['codigo']: json.loads(r['columnas']) for r in L.q(db, 'SELECT codigo, columnas FROM reportes')}


def identificar(h, reg):
    """(codigo, parecido): primero por columnas exactas (sin mayúsculas), después normalizadas; mínimo 0,6."""
    ex = {c.strip().lower() for c in h}
    no = {nombre_col(c) for c in h}
    mejor = (None, -1.0, -1.0)
    for cod, cols in sorted(reg.items(), key=lambda x: int(x[0][1:]) if x[0][1:].isdigit() else 999):
        e = {c.strip().lower() for c in cols}
        n = {nombre_col(c) for c in cols}
        je, jn = len(ex & e) / max(len(ex | e), 1), len(no & n) / max(len(no | n), 1)
        if (je, jn) > mejor[1:]:
            mejor = (cod, je, jn)
    return mejor[0], max(mejor[1], mejor[2])


def clasificar(db, i, reg):
    e = L.q(db, 'SELECT nombre, texto, estado FROM entrada WHERE id=?', i)[0]
    if e['estado'] != 'recibida':
        return e['estado']
    h, filas, _ = tabla(e['texto'] or '')
    if not h:
        return cuarentena(db, i, 'clasificar', 'el archivo está vacío')
    cod, par = identificar(h, reg)
    if not cod or par < 0.6:
        return cuarentena(db, i, 'clasificar', f'no coincide con ningún reporte del registro (parecido {par:.0%})')
    ix = {nombre_col(c): k for k, c in enumerate(h)}
    docs = [f[ix['documento']] for f in filas if 'documento' in ix and ix['documento'] < len(f)]
    pedidos = docs and sum('pedido' in d.lower() for d in docs) > len(docs) / 2
    clase = ('pedidos_cabecera' if pedidos else 'facturacion_renglones' if cod in RENGLONES
             else 'comprobantes_cabecera' if cod in CABECERA else 'reporte')
    if pedidos:
        cod = None                        # los pedidos todavía no tienen código propio en el registro: sirven de control
    fk = next((ix[k] for k in ('fechacomprobante', 'fecha') if k in ix), None)
    fechas = [f[fk][:10] for f in filas if fk is not None and fk < len(f) and re.match(r'\d{4}-\d\d-\d\d', f[fk][:10])]
    db.run([("UPDATE entrada SET clase=?, codigo=?, filas=?, corte=?, estado='clasificada' WHERE id=?",
             [clase, cod, len(filas), max(fechas) if fechas else None, i])])
    control(db, i, 'clasificar', 'PASA' if par >= 0.999 else 'AVISO', f'{cod or clase} (parecido {par:.0%})')
    return 'clasificada'


def cuarentena(db, i, ctl, motivo):
    control(db, i, ctl, 'FALLA', motivo)
    db.run([("UPDATE entrada SET estado='cuarentena', motivo=? WHERE id=?", [motivo[:500], i])])
    tema(db, i, motivo)
    return 'cuarentena'


def tema(db, i, motivo):
    """Abre un tema en la bitácora 2 (si la tabla existe), como controles/correr.py: quien espera es Loki."""
    try:
        e = L.q(db, 'SELECT nombre, lote FROM entrada WHERE id=?', i)[0]
        tit = f"Cuarentena: {e['nombre']}"[:60]
        if L.q(db, "SELECT 1 FROM tema WHERE titulo=? AND estado='abierto'", tit):
            return
        m = max(1000, int((L.q(db, 'SELECT MAX(id) m FROM tema')[0]['m'] or 0)) + 1)
        h = hoy()
        db.run([("INSERT INTO tema (id,titulo,area,estado,espera,proximo,revisar,prioridad,refs,creado,actualizado)"
                 " VALUES (?,?,'loki','abierto','nicolas',?,?,'A','[]',?,?)",
                 [m, tit, f'Resolver la entrada {i} (lote {e["lote"]}) y volver a pasarla por el auditor'[:120], h, h, h]),
                ("INSERT INTO tema_evento (tema_id,fecha,tipo,texto,fuente) VALUES (?,?,'auto',?,'auditor')", [m, h, motivo[:500]])])
    except Exception:  # noqa: BLE001  sin bitácora 2 la cuarentena igual queda en la tabla entrada
        pass


# ------------------------------------------------------------------ 3. verificar
def verificar(db, ids, reg):
    ents = {r['id']: r for r in L.q(db, f"SELECT * FROM entrada WHERE id IN ({','.join('?' * len(ids))})", *ids)}
    cabeceras = [e for e in ents.values() if e['clase'] == 'comprobantes_cabecera' and e['estado'] == 'clasificada']
    if not cabeceras:   # la cabecera ya había entrado antes (misma sha256): sirve la última verificada o publicada
        cabeceras = L.q(db, "SELECT * FROM entrada WHERE clase='comprobantes_cabecera' AND estado IN ('verificada','publicada')"
                            " ORDER BY corte DESC, id DESC LIMIT 1")
    for i, e in sorted(ents.items()):
        if e['estado'] != 'clasificada':
            continue
        h, filas, _ = tabla(e['texto'])
        fallas = []
        if e['codigo']:
            esperadas = {nombre_col(c) for c in reg[e['codigo']]}
            faltan = esperadas - {nombre_col(c) for c in h}
            if faltan:
                fallas.append(f'formato: faltan {len(faltan)} columnas del registro {e["codigo"]}')
            control(db, i, 'formato', 'FALLA' if faltan else 'PASA', f'{len(h)} columnas · faltan {len(faltan)}')
        desp = sum(1 for f in filas if len(f) != len(h))
        control(db, i, 'lectura', 'FALLA' if desp else 'PASA', f'{len(filas)} filas · {desp} filas con columnas de más o de menos')
        if desp:
            fallas.append(f'lectura: {desp} filas desparejas')
        if e['codigo']:
            prev = L.q(db, 'SELECT corte, filas FROM cargas WHERE fuente=?', e['codigo'])
            if prev and prev[0]['corte'] and e['corte'] and e['corte'] < prev[0]['corte'][:10]:
                control(db, i, 'corte', 'AVISO', f"corte {e['corte']} anterior al cargado ({prev[0]['corte'][:10]})")
            else:
                control(db, i, 'corte', 'PASA', f"corte {e['corte']}")
        if e['clase'] == 'facturacion_renglones':
            r = completitud(db, e, cabeceras)
            control(db, i, 'completitud', r[0], r[1])
            if r[0] == 'FALLA':
                fallas.append('completitud: ' + r[1])
        if fallas:
            cuarentena(db, i, 'verificar', ' · '.join(fallas))
        else:
            db.run([("UPDATE entrada SET estado='verificada' WHERE id=?", [i])])


def completitud(db, e, cabeceras):
    """La regla del importador 0.3: renglones contra la cabecera de comprobantes hasta su corte (más de 2 % faltante = FALLA)."""
    if not cabeceras:
        return 'FALLA', 'falta la cabecera de comprobantes (Ventas › Transacciones › Facturas de Venta) en el mismo lote'
    imp = _modulo('importar')
    d = tempfile.mkdtemp()
    ren, cab = os.path.join(d, 'renglones.csv'), os.path.join(d, 'cabecera.csv')
    open(ren, 'w', encoding='utf-8').write(e['texto'])
    open(cab, 'w', encoding='utf-8').write(max(cabeceras, key=lambda c: c['filas'] or 0)['texto'])
    crm = os.path.join(d, 'crm')
    os.makedirs(os.path.join(crm, 'oportunidades'))
    for r in L.q(db, "SELECT id, data FROM crm WHERE coleccion='oportunidades'"):
        open(os.path.join(crm, 'oportunidades', r['id'] + '.json'), 'w', encoding='utf-8').write(r['data'])
    out = io.StringIO()
    try:
        from contextlib import redirect_stdout, redirect_stderr
        with redirect_stdout(out), redirect_stderr(out):
            res = imp.main(['--base', os.path.join(d, 'limpia.sqlite'), '--renglones', ren, '--cabecera', cab, '--crm', crm])
    except SystemExit as x:
        return 'FALLA', f'el importador no corrió: {x}'
    falt = sum(v for k, v in res.items() if k.startswith('comprobantes sin renglones'))
    n = sum(v for k, v in res.items() if k.startswith('comprobantes de '))
    if res.get('_falla'):
        linea = next((l.strip(' ✗') for l in out.getvalue().splitlines() if 'faltan' in l), 'reporte incompleto')
        return 'FALLA', linea[:400]
    return 'PASA', f'{n} comprobantes · {falt} sin renglones hasta el corte'


# ------------------------------------------------------------------ 4. publicar
def publicar(db, lote, hacelo):
    if not (hacelo or '').strip():
        raise SystemExit('FALLA · publicar escribe en la base: hace falta --hacelo con el texto de Nicolás')
    ents = L.q(db, 'SELECT * FROM entrada WHERE lote=? ORDER BY id', lote)
    if not ents:
        raise SystemExit(f'FALLA · no hay entradas en el lote {lote}')
    malas = [e for e in ents if e['estado'] not in ('verificada', 'publicada', 'reemplazada') and e['clase'] != 'pedidos_cabecera']
    if malas:
        print('RECHAZADO · el lote tiene entradas sin verificar: ' + ', '.join(f"{e['id']} {e['nombre']} ({e['estado']})" for e in malas))
        return 1
    reg = registro(db)
    d = tempfile.mkdtemp()
    for e in ents:
        if e['estado'] != 'verificada' or not e['codigo']:
            continue
        destinos = [(e['codigo'], e['texto'], e['filas'])]
        if e['clase'] == 'facturacion_renglones' and 'R10' in reg and e['codigo'] != 'R10':
            # la tabla ventas sale del formato R10 y solo con los renglones de Horizon (0.2: como venía cargada, 1.219 al 20/11)
            destinos.append(('R10',) + renombrar(e['texto'], reg['R10'], EMPRESA))
        for cod, texto, nf in destinos:
            p = os.path.join(d, cod + '.csv')
            open(p, 'w', encoding='utf-8', newline='').write(texto)
            meta = dict(archivo=f"{e['nombre']} (auditor, entrada {e['id']}, lote {lote})", corte=e['corte'], fecha=hoy(),
                        filas=nf, sha256=L.sha(texto), auditoria=f'auditor.py {VERSION}: verificada', cargado=hoy())
            mp = os.path.join(d, cod + '.meta.json')
            json.dump(meta, open(mp, 'w', encoding='utf-8'), ensure_ascii=False)
            n = L.cargar_reporte(db, cod, p, mp)
            db.run([('INSERT OR REPLACE INTO entrada_publicacion VALUES (?,?,?,?,?)', [e['id'], cod, n, ahora(), hacelo[:300]])])
        db.run([("UPDATE entrada SET estado='reemplazada' WHERE codigo=? AND estado='publicada' AND id<>?", [e['codigo'], e['id']]),
                ("UPDATE entrada SET estado='publicada' WHERE id=?", [e['id']])])
        print(f"PUBLICADA {e['id']} {e['nombre']} → " + ', '.join(f'{c} ({nf} filas)' for c, _, nf in destinos) + f", corte {e['corte']}")
    L.cadena('todos', 'auditor publicar ' + str(lote))   # loki_sql 1.15.0 · DEC-1124b
    return 0


def renombrar(texto, columnas, empresa=None):
    """Pasa los encabezados al formato del registro (mismas columnas, otro nombre). Falla si alguna columna no tiene par.
    Con `empresa` deja solo los renglones cuya columna Empresa empieza así. Devuelve (texto, filas)."""
    h, filas, sep = tabla(texto)
    por = {nombre_col(c): c for c in columnas}
    nuevo = []
    for c in h:
        if nombre_col(c) not in por:
            raise SystemExit(f'FALLA · la columna «{c}» no tiene par en el formato de destino')
        nuevo.append(por[nombre_col(c)])
    if empresa:
        ix = {nombre_col(c): k for k, c in enumerate(h)}
        if 'empresa' not in ix:
            raise SystemExit('FALLA · el reporte no tiene la columna Empresa: no se puede separar Horizon')
        filas = [f for f in filas if f[ix['empresa']].strip().upper().startswith(empresa)]
    s = io.StringIO()
    w = csv.writer(s, delimiter=';', lineterminator='\n')
    w.writerow(nuevo)
    w.writerows(filas)
    return s.getvalue(), len(filas)


# ------------------------------------------------------------------ entrar y estado
def entrar(db, rutas, origen='finnegans', reg=None):
    crear(db)
    sig = int(L.q(db, 'SELECT COALESCE(MAX(id), 0) m FROM entrada')[0]['m']) + 1
    lote = D.datetime.now().strftime('%Y%m%d-%H%M%S') + f'-{sig}'     # único aunque dos lotes caigan en el mismo segundo
    reg = reg or registro(db)
    ids = []
    for r in rutas:
        i, nuevo = recibir(db, r, lote, origen)
        if not nuevo:
            ya = L.q(db, 'SELECT lote, estado FROM entrada WHERE id=?', i)[0]
            print(f"YA ESTABA {os.path.basename(r)}: entrada {i} (lote {ya['lote']}, {ya['estado']}); no se duplica")
            continue
        ids.append(i)
        clasificar(db, i, reg)
    if ids:
        verificar(db, ids, reg)
    falla = 0
    print(f'{VERSION} · lote {lote}')
    for e in L.q(db, f"SELECT * FROM entrada WHERE id IN ({','.join('?' * len(ids)) or 'NULL'})", *ids):
        print(f"  {e['estado'].upper():<11} {e['id']} {e['nombre'][:30]:30} {e['clase'] or '-':22} {e['codigo'] or '-':4} "
              f"{e['filas'] or 0} filas · corte {e['corte'] or '-'}" + (f" · {e['motivo']}" if e['motivo'] else ''))
        falla |= e['estado'] == 'cuarentena'
    print('Auditor: ' + ('FALLA (hay entradas en cuarentena)' if falla else 'PASA') + (f' · para cargar: publicar {lote} --hacelo "…"' if ids and not falla else ''))
    return lote, (1 if falla else 0)


def estado(db, imprimir=True):
    crear(db)
    cua = L.q(db, "SELECT id, nombre, motivo, recibido FROM entrada WHERE estado='cuarentena' ORDER BY id")
    pub = L.q(db, "SELECT codigo, MAX(corte) corte, MAX(recibido) r FROM entrada WHERE estado='publicada' GROUP BY codigo")
    pend = L.q(db, "SELECT lote, COUNT(*) n FROM entrada WHERE estado='verificada' GROUP BY lote")
    lineas = []
    lineas.append(f'CUARENTENA ({len(cua)})' + (': ' + ' · '.join(f"{c['id']} {c['nombre'][:28]} ({(c['motivo'] or '')[:70]})" for c in cua) if cua else ': -'))
    if pend:
        lineas.append('VERIFICADO SIN PUBLICAR: ' + ' · '.join(f"lote {p['lote']} ({p['n']})" for p in pend))
    if pub:
        lineas.append('PUBLICADO: ' + ' · '.join(f"{p['codigo']} corte {p['corte']}" for p in pub))
    if imprimir:
        print('\n'.join(lineas))
    return lineas, len(cua)


# ------------------------------------------------------------------ autotest (sin datos reales)
def autotest():
    d = tempfile.mkdtemp()
    db = L.Local(os.path.join(d, 'base.sqlite'))
    crear(db)
    bit = _modulo('bitacora2')
    db.run([(s, []) for s in bit.DDL])
    RC = ['TransaccionID', 'Fecha comprobante', 'Documento', 'Comprobante', 'Cliente', 'Nrodeidentificacion', 'Descripción',
          'Motivodeanulacion', 'Producto', 'Cantidad', 'Marca', 'Familia', 'Subfamilia', 'Moneda', 'Empresa']
    R10 = [c.replace('Nrodeidentificacion', 'Nro de identificación').replace('Subfamilia', 'SubFamilia') for c in RC]
    CB = ['TransaccionID', 'Fecha', 'Documento', 'Nro comp', 'Cliente', 'Bruto', 'Descripción', 'Empresa']
    for cod, cols in (('R7', RC), ('R10', R10), ('R23', CB)):
        db.run([('INSERT INTO reportes (codigo, descripcion, clase, privado, columnas, actualizado, meta) VALUES (?,?,?,?,?,?,?)',
                 [cod, 'prueba', 'acumulativo', 0, json.dumps(cols), ahora(), '{}'])])
    db.run([("INSERT INTO crm (coleccion, id, empresa, cuit, data) VALUES ('oportunidades','x','Cliente X','30-11111111-1',?)",
             [json.dumps({'empresa': 'Cliente X', 'cuit': '30-11111111-1'})])])
    H, FA = 'HORIZON TRADING S.A.', 'Factura de Venta Electrónica'

    def esc(nombre, cols, filas):
        p = os.path.join(d, nombre)
        with open(p, 'w', encoding='utf-8', newline='') as fh:
            w = csv.writer(fh, delimiter=';')
            w.writerow(cols)
            w.writerows(filas)
        return p
    ren = [[str(t), f'2026-11-{t:02d}', FA, f'A-00005-0000{1000 + t}', 'Cliente X', '30-11111111-1', '', '', 'Ont A', '10',
            'FH', 'FTTH', 'ONU', 'Dólares', H] for t in range(1, 11)]
    cab = [[str(t), f'2026-11-{t:02d}', FA, f'A-00005-0000{1000 + t}', 'Cliente X', '100', '', H] for t in range(1, 11)]
    otra = ['99', '2026-11-05', FA, 'A-00001-00009999', 'Cliente Y', '30-22222222-2', '', '', 'Ont B', '3', 'FH', 'FTTH', 'ONU',
            'Dólares', 'OTRA EMPRESA S.A.']
    completo = esc('ren_completo.csv', RC, ren + [otra])          # 10 de Horizon + 1 de otra empresa
    cabecera = esc('cabecera.csv', CB, cab)
    recortado = esc('ren_recortado.csv', RC, ren[:3] + ren[6:])     # faltan 3 de 10 antes del corte (el caso del 23/11)
    raro = esc('otra_cosa.csv', ['a', 'b', 'c'], [['1', '2', '3']])
    casos = []
    from contextlib import redirect_stdout
    with redirect_stdout(io.StringIO()):
        lote1, rc1 = entrar(db, [recortado, cabecera])
    e = {r['nombre']: r for r in L.q(db, 'SELECT nombre, estado, motivo FROM entrada')}
    casos.append(('reporte recortado → cuarentena', e['ren_recortado.csv']['estado'] == 'cuarentena' and rc1 == 1))
    casos.append(('la cuarentena abre un tema en la bitácora 2', bool(L.q(db, "SELECT 1 FROM tema WHERE titulo LIKE 'Cuarentena:%'"))))
    with redirect_stdout(io.StringIO()):
        rc_pub = publicar(db, lote1, 'prueba')
    casos.append(('publicar un lote con cuarentena → rechazado', rc_pub == 1 and not L.q(db, 'SELECT 1 FROM entrada_publicacion')))
    with redirect_stdout(io.StringIO()):
        entrar(db, [raro])
        lote2, rc2 = entrar(db, [completo, cabecera])      # la cabecera ya estaba: se usa la verificada
    e2 = {r['nombre']: r for r in L.q(db, 'SELECT nombre, estado, lote FROM entrada')}
    casos.append(('formato desconocido → cuarentena', e2['otra_cosa.csv']['estado'] == 'cuarentena'))
    casos.append(('la misma cabecera no se duplica (sha256)', L.q(db, "SELECT COUNT(*) n FROM entrada WHERE nombre='cabecera.csv'")[0]['n'] == 1))
    casos.append(('renglones completos + cabecera → verificada', e2['ren_completo.csv']['estado'] == 'verificada'))
    try:
        with redirect_stdout(io.StringIO()):
            publicar(db, lote2, '')
        sin_hacelo = False
    except SystemExit:
        sin_hacelo = True
    casos.append(('publicar sin «hacelo» no escribe', sin_hacelo))
    with redirect_stdout(io.StringIO()):
        lote3, _ = entrar(db, [completo])            # ya estaba: no se duplica
    casos.append(('el mismo archivo dos veces no se duplica', L.q(db, "SELECT COUNT(*) n FROM entrada WHERE nombre='ren_completo.csv'")[0]['n'] == 1))
    with redirect_stdout(io.StringIO()):
        rc3 = publicar(db, lote2, 'Nicolás: hacelo (prueba)')
    v = L.q(db, 'SELECT COUNT(*) n FROM ventas')[0]['n']
    casos.append(('verificada + hacelo → publicada (ventas en formato R10)', rc3 == 0 and v == 10 and
                  L.q(db, "SELECT estado FROM entrada WHERE nombre='ren_completo.csv'")[0]['estado'] == 'publicada'))
    cg = {r['fuente']: r['filas'] for r in L.q(db, 'SELECT fuente, filas FROM cargas')}
    casos.append(('ventas solo con Horizon; R7 completo (otra empresa afuera de ventas)',
                  cg.get('R7') == 11 and cg.get('R10') == 10 and not L.q(db, "SELECT 1 FROM ventas WHERE empresa NOT LIKE 'HORIZON%'")))
    casos.append(('el hacelo queda registrado', bool(L.q(db, "SELECT 1 FROM entrada_publicacion WHERE hacelo LIKE 'Nicolás%'"))))
    casos.append(('la cuarentena se ve en estado', estado(db, imprimir=False)[1] == 2))
    casos.append(('columnas iguales con otro nombre (Nrodeidentificacion = Nro de identificación)',
                  nombre_col('Nro de identificación') == nombre_col('Nrodeidentificacion')
                  and nombre_col('Indentificaciontributaria') == nombre_col('Identificacion Tributaria')))
    db.close()
    ok = sum(1 for _, c in casos if c)
    for t, c in casos:
        print(('  OK   ' if c else '  FALLA ') + t)
    print(f'autotest auditor: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__)
        return 0
    if a[0] == '--autotest':
        return autotest()
    db = L.conectar()
    try:
        if a[0] == 'entrar':
            rutas = [x for x in a[1:] if not x.startswith('--') and x != (a[a.index('--origen') + 1] if '--origen' in a else None)]
            return entrar(db, rutas, a[a.index('--origen') + 1] if '--origen' in a else 'finnegans')[1]
        if a[0] == 'publicar':
            return publicar(db, a[1], a[a.index('--hacelo') + 1] if '--hacelo' in a else '')
        if a[0] == 'estado':
            return 1 if estado(db)[1] else 0
        print('comando desconocido: ' + a[0])
        return 2
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
