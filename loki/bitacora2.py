"""Bitácora 2 de Loki: temas con estado + eventos + chequeos contra los datos.

Un TEMA es un compromiso abierto con: quién lo tiene (espera), qué sigue (proximo, una línea),
cuándo se mira (revisar) y, si se puede, un CHEQUEO que la máquina verifica contra la base
(CRM, R10, stock). Cada novedad es un EVENTO (no se reescribe el texto).

Uso (en la nube el proxy pone el token de Turso):
  python3 -I -X utf8 bitacora2.py crear  DB
  python3 -I -X utf8 bitacora2.py migrar DB migracion.json bitacora.jsonl
  python3 -I -X utf8 bitacora2.py chequear DB HOY      # corre chequeos, cierra solos, marca conflictos
  python3 -I -X utf8 bitacora2.py hoy DB HOY           # vista corta para la apertura
DB = archivo SQLite local (copia de prueba) o 'turso' (base real; escribe: requiere hacelo).
"""
import json, sqlite3, sys, urllib.request, datetime as dt

TURSO = 'https://horizon-nicom90.aws-sa-east-1.turso.io/v2/pipeline'
VERSION = '0.1.0'

DDL = [
    """CREATE TABLE IF NOT EXISTS tema (
        id INTEGER PRIMARY KEY,
        titulo TEXT NOT NULL CHECK (length(titulo) <= 60),
        area TEXT NOT NULL CHECK (area IN ('cuenta','crm','loki','pm','proveedor','sistema')),
        cuit TEXT, cuenta TEXT,
        estado TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto','cerrado','descartado')),
        espera TEXT NOT NULL CHECK (espera IN ('nicolas','hacelo','jp','cliente','loki','jefe')),
        proximo TEXT NOT NULL CHECK (length(proximo) <= 120),
        revisar TEXT CHECK (revisar IS NULL OR revisar GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
        prioridad TEXT NOT NULL DEFAULT 'B' CHECK (prioridad IN ('A','B','C')),
        refs TEXT NOT NULL DEFAULT '[]',
        chequeo TEXT,
        propuesta TEXT,
        creado TEXT NOT NULL, actualizado TEXT NOT NULL, cerrado TEXT, cierre TEXT)""",
    """CREATE TABLE IF NOT EXISTS tema_evento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tema_id INTEGER NOT NULL REFERENCES tema (id),
        fecha TEXT NOT NULL, chat INTEGER,
        tipo TEXT NOT NULL CHECK (tipo IN ('origen','nota','decision','dato','conflicto','cierre','auto')),
        texto TEXT NOT NULL, fuente TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_tema_abierto ON tema (estado, revisar)",
    "CREATE INDEX IF NOT EXISTS ix_evento_tema ON tema_evento (tema_id, fecha)",
]


# ---------- acceso a datos ----------
def turso(sql, args=()):
    stmt = {'sql': sql, 'args': [{'type': 'null'} if a is None else {'type': 'text', 'value': str(a)} for a in args]}
    body = {'requests': [{'type': 'execute', 'stmt': stmt}, {'type': 'close'}]}
    rq = urllib.request.Request(TURSO, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(rq, timeout=60) as r:
        res = json.load(r)['results'][0]
    if res['type'] != 'ok':
        raise RuntimeError(res.get('error'))
    rs = res['response']['result']
    cols = [c['name'] for c in rs['cols']]
    return [dict(zip(cols, [None if v['type'] == 'null' else v['value'] for v in row])) for row in rs['rows']]


class Local:
    def __init__(self, path):
        self.c = sqlite3.connect(path)
        self.c.row_factory = sqlite3.Row

    def q(self, sql, args=()):
        return [dict(r) for r in self.c.execute(sql, args)]

    def x(self, sql, args=()):
        self.c.execute(sql, args)

    def fin(self):
        self.c.commit()


class Remota:
    def q(self, sql, args=()):
        return turso(sql, args)

    def x(self, sql, args=()):
        turso(sql, args)

    def fin(self):
        pass


def abrir_db(nombre):
    return Remota() if nombre == 'turso' else Local(nombre)


# ---------- chequeos: cada uno devuelve (estado, detalle) ----------
# estado: 'cumplido' (se cierra solo) · 'pendiente' (sigue) · 'conflicto' (las fuentes no coinciden) · 'sin_dato'
CERRADAS = ('aceptada', 'ganada', 'perdida', 'rechazada')


def ch_cot_cerrada(c):
    out = []
    for nm in c['nm'] if isinstance(c['nm'], list) else [c['nm']]:
        r = turso('SELECT numero, estado, archivada, revision FROM crm_cotizacion WHERE numero=?', [nm])
        if not r:
            out.append(('sin_dato', f'{nm} no está en el CRM'))
        elif r[0]['estado'] in CERRADAS or r[0]['archivada'] == '1':
            out.append(('cumplido', f"{nm} {r[0]['estado']}{' archivada' if r[0]['archivada'] == '1' else ''}"))
        else:
            out.append(('pendiente', f"{nm} {r[0]['estado']} · revisión {r[0]['revision'] or 'sin fecha'}"))
    return juntar(out)


def ch_fa_entregada(c):
    r = turso('SELECT SUM(cantidad) cant, SUM(pte_dest) pte FROM ventas WHERE comprobante=?', [c['fa']])
    if not r or r[0]['cant'] is None:
        return 'sin_dato', f"{c['fa']} no está en el R10"
    pte = float(r[0]['pte'] or 0)
    crm = turso('SELECT numero, despacho, entrega FROM crm_cotizacion WHERE replace(factura,\' \',\'-\')=?', [c['fa']])
    dice = crm[0]['entrega'] if crm else None
    if pte == 0:
        return 'cumplido', f"{c['fa']} entregada (R10 sin pendiente)"
    if dice == 'confirmado':
        return 'conflicto', f"{c['fa']}: CRM dice entregado, R10 tiene {pte:g} pendiente"
    return 'pendiente', f"{c['fa']}: {pte:g} sin entregar"


def ch_ficha_campo(c):
    r = turso(f"SELECT {c['campo']} v FROM crm_oportunidad WHERE id=?", [c['id']])
    if not r:
        return 'sin_dato', f"ficha {c['id']} no está"
    ok = (r[0]['v'] or '').lower() == str(c['valor']).lower()
    return ('cumplido' if ok else 'pendiente'), f"{c['id']}.{c['campo']} = {r[0]['v'] or 'vacío'}"


def ch_unificada(c):
    out = []
    for i in c['ids']:
        r = turso('SELECT archivada, unificada_en FROM crm_oportunidad WHERE id=?', [i])
        if not r:
            out.append(('sin_dato', f'{i} no está'))
        else:
            hecho = r[0]['archivada'] == '1' or r[0]['unificada_en']
            out.append(('cumplido' if hecho else 'pendiente', f"{i} {'unificada en ' + r[0]['unificada_en'] if r[0]['unificada_en'] else ('archivada' if hecho else 'activa')}"))
    return juntar(out)


def ch_stock(c):
    r = turso('SELECT SUM(stock) s, SUM(en_transito) t FROM stock WHERE producto LIKE ?', [f"%{c['producto']}%"])
    s = float(r[0]['s'] or 0) if r else 0
    return ('cumplido' if s >= c.get('min', 1) else 'pendiente'), f"{c['producto']}: stock {s:g}"


CHEQUEOS = {'cot_cerrada': ch_cot_cerrada, 'fa_entregada': ch_fa_entregada, 'ficha_campo': ch_ficha_campo,
            'unificada': ch_unificada, 'stock': ch_stock}


def juntar(out):
    est = [e for e, _ in out]
    tot = 'conflicto' if 'conflicto' in est else 'cumplido' if all(e == 'cumplido' for e in est) else 'sin_dato' if all(e == 'sin_dato' for e in est) else 'pendiente'
    return tot, ' · '.join(d for _, d in out)


# ---------- comandos ----------
def crear(db):
    for s in DDL:
        db.x(s)
    db.fin()


def migrar(db, mig_p, bit_p):
    mig = json.load(open(mig_p, encoding='utf-8'))
    viejos = {r['id']: r for r in map(json.loads, (l for l in open(bit_p, encoding='utf-8') if l.startswith('{')))}
    hoy = dt.date.today().isoformat()
    for t in mig:
        v = viejos[t['id']]
        db.x("""INSERT OR REPLACE INTO tema (id,titulo,area,cuit,cuenta,estado,espera,proximo,revisar,prioridad,refs,chequeo,propuesta,creado,actualizado)
                VALUES (?,?,?,?,?,'abierto',?,?,?,?,?,?,?,?,?)""",
             [t['id'], t['titulo'], t['area'], v['cuit'], t.get('cuenta') or v['cuenta'], t['espera'], t['proximo'], t.get('revisar'),
              t.get('prioridad', 'B'), json.dumps(t.get('refs', []), ensure_ascii=False),
              json.dumps(t['chequeo'], ensure_ascii=False) if t.get('chequeo') else None, t.get('propuesta'), v['fecha'], hoy])
        db.x('DELETE FROM tema_evento WHERE tema_id=?', [t['id']])
        db.x("INSERT INTO tema_evento (tema_id,fecha,chat,tipo,texto,fuente) VALUES (?,?,?,'origen',?,?)",
             [t['id'], v['fecha'], v['chat'], v['texto'], f"bitacora #{t['id']}"])
    db.fin()
    return len(mig)


def chequear(db, hoy):
    res = {'cumplido': [], 'conflicto': [], 'pendiente': [], 'sin_dato': []}
    for t in db.q("SELECT id, titulo, chequeo FROM tema WHERE estado='abierto' AND chequeo IS NOT NULL"):
        c = json.loads(t['chequeo'])
        est, det = CHEQUEOS[c['t']](c)
        res[est].append((t['id'], t['titulo'], det))
        if est == 'cumplido':
            db.x("UPDATE tema SET estado='cerrado', cerrado=?, cierre=?, actualizado=? WHERE id=?", [hoy, 'auto: ' + det, hoy, t['id']])
            db.x("INSERT INTO tema_evento (tema_id,fecha,tipo,texto,fuente) VALUES (?,?,'auto',?,'chequeo')", [t['id'], hoy, 'Se cerró solo: ' + det])
        elif est == 'conflicto':
            ya = db.q("SELECT 1 FROM tema_evento WHERE tema_id=? AND tipo='conflicto' AND texto=?", [t['id'], det])
            if not ya:
                db.x("INSERT INTO tema_evento (tema_id,fecha,tipo,texto,fuente) VALUES (?,?,'conflicto',?,'chequeo')", [t['id'], hoy, det])
    db.fin()
    return res


def corta(f):
    return f'{f[8:10]}/{f[5:7]}' if f else 's/f'


def vista_hoy(db, hoy, res=None):
    ab = db.q("SELECT * FROM tema WHERE estado='abierto' ORDER BY prioridad, COALESCE(revisar,'9999'), id")
    conf = {r['tema_id']: r['texto'] for r in db.q("SELECT tema_id, texto FROM tema_evento WHERE tipo='conflicto'")}
    lin = lambda t: f"#{t['id']} {t['prioridad']} · {t['titulo']} · {t['proximo']} · {t['espera']} · {corta(t['revisar'])}"
    out = [f"BITÁCORA {corta(hoy)} · {len(ab)} abiertos"]
    if res:
        if res['cumplido']:
            out.append(f"SE CERRARON SOLOS ({len(res['cumplido'])}): " + ' · '.join(f"#{i} {t}" for i, t, _ in res['cumplido']))
    cf = [t for t in ab if t['id'] in conf]
    if cf:
        out.append(f"CONFLICTOS ({len(cf)}):")
        out += [f"  #{t['id']} {t['titulo']} · {conf[t['id']]}" for t in cf]
    venc = [t for t in ab if t['revisar'] and t['revisar'] <= hoy and t['id'] not in conf]
    semana = (dt.date.fromisoformat(hoy) + dt.timedelta(days=7)).isoformat()
    prox = [t for t in ab if t['revisar'] and hoy < t['revisar'] <= semana and t['id'] not in conf]
    out.append(f"HOY O VENCIDOS ({len(venc)}):")
    out += ['  ' + lin(t) for t in venc]
    out.append(f"ESTA SEMANA ({len(prox)}):")
    out += ['  ' + lin(t) for t in prox]
    resto = [t for t in ab if t not in venc and t not in prox and t not in cf]
    por = {}
    for t in resto:
        por.setdefault(t['espera'], []).append(f"#{t['id']}")
    out.append('SIN FECHA O MÁS ADELANTE: ' + ' · '.join(f"{k} {' '.join(v)}" for k, v in sorted(por.items())))
    props = [t for t in ab if t['propuesta']]
    if props:
        out.append(f"PROPUESTAS DE CIERRE ({len(props)}): " + ' · '.join(f"#{t['id']} {t['propuesta']}" for t in props))
    return '\n'.join(out)


CAMPOS = ('titulo', 'area', 'cuit', 'cuenta', 'espera', 'proximo', 'revisar', 'prioridad', 'refs', 'chequeo', 'propuesta')


def nuevo(db, t, hoy, chat=None):
    m = db.q('SELECT MAX(id) m FROM tema')[0]['m']
    i = max(1000, int(m or 0) + 1)
    if t.get('chequeo') and t['chequeo']['t'] not in CHEQUEOS:
        raise ValueError('chequeo desconocido: ' + t['chequeo']['t'])
    db.x("""INSERT INTO tema (id,titulo,area,cuit,cuenta,estado,espera,proximo,revisar,prioridad,refs,chequeo,propuesta,creado,actualizado)
            VALUES (?,?,?,?,?,'abierto',?,?,?,?,?,?,?,?,?)""",
         [i, t['titulo'], t['area'], t.get('cuit'), t.get('cuenta'), t['espera'], t['proximo'], t.get('revisar'), t.get('prioridad', 'B'),
          json.dumps(t.get('refs', []), ensure_ascii=False), json.dumps(t['chequeo'], ensure_ascii=False) if t.get('chequeo') else None,
          t.get('propuesta'), hoy, hoy])
    if t.get('texto'):
        db.x("INSERT INTO tema_evento (tema_id,fecha,chat,tipo,texto,fuente) VALUES (?,?,?,'origen',?,?)", [i, hoy, chat, t['texto'], t.get('fuente')])
    db.fin()
    return i


def evento(db, i, tipo, texto, hoy, chat=None, cambios=None):
    db.x('INSERT INTO tema_evento (tema_id,fecha,chat,tipo,texto) VALUES (?,?,?,?,?)', [i, hoy, chat, tipo, texto])
    for k, v in (cambios or {}).items():
        if k not in CAMPOS:
            raise ValueError('campo desconocido: ' + k)
        db.x(f'UPDATE tema SET {k}=?, actualizado=? WHERE id=?', [v, hoy, i])
    db.x('UPDATE tema SET actualizado=? WHERE id=?', [hoy, i])
    db.fin()


def cerrar(db, i, como, hoy, chat=None, estado='cerrado'):
    db.x('UPDATE tema SET estado=?, cerrado=?, cierre=?, actualizado=? WHERE id=?', [estado, hoy, como, hoy, i])
    db.x("INSERT INTO tema_evento (tema_id,fecha,chat,tipo,texto) VALUES (?,?,?,'cierre',?)", [i, hoy, chat, como])
    db.fin()


def ver(db, i):
    t = db.q('SELECT * FROM tema WHERE id=?', [i])
    if not t:
        return f'#{i} no existe'
    t = t[0]
    ev = db.q('SELECT fecha, chat, tipo, texto FROM tema_evento WHERE tema_id=? ORDER BY fecha, id', [i])
    out = [f"#{t['id']} {t['estado']} · {t['prioridad']} · {t['titulo']} · {t['cuenta'] or t['area']}",
           f"  próximo: {t['proximo']} · espera {t['espera']} · revisar {corta(t['revisar'])} · refs {t['refs']}"]
    if t['cierre']:
        out.append(f"  cierre {corta(t['cerrado'])}: {t['cierre']}")
    out += [f"  {corta(e['fecha'])} {e['tipo']}: {e['texto']}" for e in ev]
    return '\n'.join(out)


def opcion(a, k):
    return a[a.index(k) + 1] if k in a else None


def main(a):
    op = a[0]
    hoy = opcion(a, '--hoy') or dt.date.today().isoformat()
    chat = opcion(a, '--chat')
    if op == 'nuevo':      # nuevo DB tema.json
        print(f"OK tema #{nuevo(abrir_db(a[1]), json.load(open(a[2], encoding='utf-8')), hoy, chat)}"); return 0
    if op == 'evento':     # evento DB ID TIPO "texto" [--set campo=valor ...]
        cambios = dict(x.split('=', 1) for i, x in enumerate(a) if i > 0 and a[i - 1] == '--set')
        evento(abrir_db(a[1]), int(a[2]), a[3], a[4], hoy, chat, cambios); print(f'OK evento en #{a[2]}'); return 0
    if op in ('cerrar', 'descartar'):   # cerrar DB ID "cómo se cerró"
        cerrar(abrir_db(a[1]), int(a[2]), a[3], hoy, chat, 'cerrado' if op == 'cerrar' else 'descartado'); print(f'OK #{a[2]} {op}'); return 0
    if op == 'ver':        # ver DB ID
        print(ver(abrir_db(a[1]), int(a[2]))); return 0
    if op == 'crear':
        crear(abrir_db(a[1])); print('OK esquema', VERSION)
    elif op == 'migrar':
        print('OK migrados', migrar(abrir_db(a[1]), a[2], a[3]))
    elif op == 'chequear':
        db = abrir_db(a[1]); res = chequear(db, a[2]); print(vista_hoy(db, a[2], res))
        print('\nDETALLE CHEQUEOS:'); [print(f'  {k}: #{i} {d}') for k, v in res.items() for i, _, d in v]
    elif op == 'hoy':
        print(vista_hoy(abrir_db(a[1]), a[2]))
    else:
        print(__doc__); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
