#!/usr/bin/env python3
"""sync_crm.py 0.1 · 28/11/2026 · Loki lleva su CRM (5SPm) a Supabase (Nicolás 28/11: «tu crm vos lo actualizás»).

El CRM es un Artifact: sus fichas se bajan con ArtifactData (query `actualizado >= X`, out_dir a una carpeta) y este script
toma esa carpeta (cotizaciones/, oportunidades/, muestras/ con un JSON por ficha), compara con comercial.crm_ficha y publica
en Supabase SOLO las fichas que cambiaron:
  1. comercial.crm_ficha (data, data_texto, actualizado; el dueño de la fila se conserva, las nuevas van con dueño crm2);
  2. las tablas ordenadas, con el mismo armado que loki_sql.armar_crm: oportunidad (+ contacto e historial de esa ficha),
     cotizacion (+ cotizacion_item) y muestra. Las columnas que agregó otro (por ejemplo vendedor) no se tocan;
  3. una fila por tabla en control.registro (agente loki-sync);
  4. vuelve a leer y compara ficha por ficha; deja el resultado (PASA/FALLA) en control.mudanza, módulo comercial,
     que es lo que mira la línea «fuente CRM» de la apertura.
Sin --escribir solo muestra qué cambiaría. Datos bancarios (config/datosBancarios) nunca se copian (D10).

Uso (python3 -I):
  sync_crm.py correr --crm CARPETA --origen 5SPm4UZTgiF5JXx7GKTybq [--escribir] [--forzar]
  sync_crm.py --autotest
"""
import datetime as D, hashlib, importlib.util, json, os, sys, time

VERSION = 'sync_crm 0.1 · 2026-11-28'
AQUI = os.path.dirname(os.path.abspath(__file__))
COLECCIONES = ('oportunidades', 'cotizaciones', 'muestras')
CRM_OFICIAL = '5SPm4UZTgiF5JXx7GKTybq'
MAX_FICHAS = 150          # más que esto no es un cambio del día (misma idea que INCREMENTAL_MAX de loki_sql)

COT_COLS = ('id', 'numero', 'oportunidad_id', 'cuit', 'cliente', 'estado', 'fecha', 'vence', 'revision', 'fecha_ganada', 'marca',
            'familia', 'cond_pago', 'cond_iva', 'tc', 'neto', 'iva', 'total', 'archivada', 'motivo_perdida', 'domicilio', 'pedido',
            'despacho', 'despacho_at', 'entrega', 'entrega_at', 'pago', 'pago_at', 'factura', 'resultado', 'notas', 'actualizado')
ITEM_COLS = ('cotizacion_id', 'n', 'cuit', 'codigo', 'articulo', 'descripcion', 'marca', 'cantidad', 'precio', 'iva', 'neto')
MUE_COLS = ('id', 'oportunidad_id', 'cuit', 'productos', 'estado', 'envio', 'fecha_pedido', 'fecha_envio', 'devolver',
            'seguimiento', 'notas', 'actualizado')
CON_COLS = ('oportunidad_id', 'n', 'cuit', 'principal', 'nombre', 'cargo', 'celular', 'mail', 'fuente')
HIS_COLS = ('oportunidad_id', 'n', 'cuit', 't', 'txt')


def _mod(nombre):
    sp = importlib.util.spec_from_file_location(nombre[:-3], os.path.join(AQUI, nombre))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


L = _mod('loki_sql.py')          # mismas reglas de armado que la copia en Turso (armar_crm)
_E = []


def espejo():
    if not _E:
        _E.append(_mod('espejo.py'))
    return _E[0]


def supa(sql, ro=True):
    """Supabase con reintento ante 429 (la API de administración limita ráfagas)."""
    for i in range(8):
        try:
            return espejo().supa(sql, solo_lectura=ro)
        except RuntimeError as e:
            if '429' not in str(e):
                raise
            time.sleep(10 * (i + 1))
    raise SystemExit('FALLA: Supabase sigue respondiendo 429 (demasiadas consultas); probar en un rato')


def lit(s):
    tag = 'j' + hashlib.sha1(s.encode()).hexdigest()[:8]
    return f'${tag}${s}${tag}$'


# ------------------------------------------------------------------ lectura de la carpeta de ArtifactData
def leer_carpeta(crm_dir):
    docs = {}
    for c in COLECCIONES:
        p = os.path.join(crm_dir, c)
        if not os.path.isdir(p):
            continue
        for f in sorted(os.listdir(p)):        # solo *.json (ArtifactData deja ocultos .x.json)
            if not f.endswith('.json') or f.startswith('.') or (c, f[:-5]) in L.CRM_PRIVADO:
                continue
            d = L.leer_json(os.path.join(p, f))
            if not isinstance(d, dict):
                raise ValueError(f'{c}/{f}: no es objeto')
            docs[(c, f[:-5])] = d
    return docs


# ------------------------------------------------------------------ armado (igual que loki_sql.armar_crm, por ficha)
def filas_oportunidad(oid, d):
    c = L.cuit_ok(d.get('cuit')) or (L.cuits_ficha(None, d) or [None])[0]
    o = {'id': oid}
    for col, k in L.OPO_COLS:
        v = c if col == 'cuit' else d.get(k)
        if col == 'monto':
            v = v if isinstance(v, (int, float)) and not isinstance(v, bool) else L.num(v)
        elif col in ('archivada', 'no_prospectar', 'otro_vendedor'):
            v = L._si(v)
        else:
            v = L._txt(v)
        o[col] = v
    extra = {k: v for k, v in d.items() if k not in L.OPO_USADAS and v not in (None, '', [], {})}
    o['extra'] = L.jdump(extra) if extra else None
    cont = []
    if L._txt(d.get('contacto')) or L._txt(d.get('telefono')) or L._txt(d.get('email')):
        cont.append((1, L._txt(d.get('contacto')), None, L._txt(d.get('telefono')), L._txt(d.get('email')), 'ficha'))
    for e in d.get('contactosAdicionales') or []:
        if isinstance(e, dict) and any(L._txt(e.get(x)) for x in ('nombre', 'celular', 'mail')):
            cont.append((0, L._txt(e.get('nombre')), L._txt(e.get('cargo')), L._txt(e.get('celular')), L._txt(e.get('mail')),
                         L._txt(e.get('fuente'))))
    contactos = [dict(zip(CON_COLS, (oid, i, c) + ct)) for i, ct in enumerate(cont)]
    hist = [dict(zip(HIS_COLS, (oid, i, c, L._txt(h.get('t')), L._txt(h.get('txt')))))
            for i, h in enumerate(e for e in (d.get('historial') or []) if isinstance(e, dict))]
    return o, contactos, hist


def filas_cotizacion(cid, d, opo_cuit):
    op_id = L._txt(d.get('oportunidadId'))
    c = L.cuit_ok(d.get('cuit')) or opo_cuit.get(op_id)
    o = d.get('hz_operacion') if isinstance(d.get('hz_operacion'), dict) else {}
    res = d.get('hz_resultado') if isinstance(d.get('hz_resultado'), dict) else {}
    rev = L._txt(d.get('revisionFecha')) or L._txt(res.get('fechaSeguimiento')) or L._txt(d.get('vence'))
    t = L._txt
    vals = (cid, t(d.get('numero')), op_id, c, t(d.get('cliente')), t(d.get('estado')), t(d.get('fecha')), t(d.get('vence')), rev,
            t(d.get('fechaGanada')), t(d.get('marca')), t(d.get('familia')), t(d.get('condPago')), t(d.get('condIva')),
            L.num(d.get('tc')), L.num(d.get('neto')), L.num(d.get('ivaTotal')), L.num(d.get('total')), L._si(d.get('archivada')),
            t(d.get('motivoPerdida')), t(d.get('domicilio')), t(o.get('pedidoConfirmado')), t(o.get('despacho')),
            t(o.get('despachoAt')), t(o.get('entrega')), t(o.get('entregaAt')), t(o.get('pago')), t(o.get('pagoAt')),
            t(o.get('factura')), t(res.get('estado')), t(d.get('notas')), t(d.get('actualizado')))
    items = [dict(zip(ITEM_COLS, (cid, i, c, t(it.get('codigo')), t(it.get('articulo')), t(it.get('descripcion')), t(it.get('marca')),
                                  L.num(it.get('cantidad')), L.num(it.get('precio')), L.num(it.get('iva')), L.num(it.get('neto')))))
             for i, it in enumerate(e for e in (d.get('items') or []) if isinstance(e, dict))]
    return dict(zip(COT_COLS, vals)), items


def filas_muestra(mid, d, opo_cuit):
    op_id = L._txt(d.get('oportunidadId'))
    t = L._txt
    return dict(zip(MUE_COLS, (mid, op_id, opo_cuit.get(op_id), t(d.get('productos')), t(d.get('estado')), t(d.get('envio')),
                               t(d.get('fechaPedido')), t(d.get('fechaEnvio')), L._si(d.get('devolver')), t(d.get('seguimiento')),
                               t(d.get('notas')), t(d.get('actualizado')))))


def con_mudanza(filas, hoy):
    for f in filas:
        f['dueno'] = 'loki'
        f['mudado'] = hoy
        f['cuit11'] = L.re.sub(r'\D', '', f['cuit']) if f.get('cuit') else None
    return filas


# ------------------------------------------------------------------ SQL
def sql_upsert(tabla, filas, clave):
    """Actualiza por clave las filas que existen (sin tocar columnas que no vienen) e inserta las que faltan."""
    if not filas:
        return ''
    js = lit(json.dumps(filas, ensure_ascii=False, default=str))
    cols = list(filas[0])
    q = lambda c: '"' + c + '"'
    on = ' AND '.join(f't.{q(k)}=j.{q(k)}' for k in clave)
    sets = ', '.join(f'{q(c)}=j.{q(c)}' for c in cols if c not in clave)
    src = f'json_populate_recordset(NULL::{tabla}, {js}::json) j'
    return (f"UPDATE {tabla} t SET {sets} FROM {src} WHERE {on}; "
            f"INSERT INTO {tabla} ({', '.join(map(q, cols))}) SELECT {', '.join('j.' + q(c) for c in cols)} FROM {src} "
            f"WHERE NOT EXISTS (SELECT 1 FROM {tabla} t WHERE {on}); ")


def sql_hijos(tabla, padre, ids, filas):
    """Hijos de una ficha (contactos, historial, ítems): se borran los de esas fichas y se cargan de nuevo."""
    if not ids:
        return ''
    s = f"DELETE FROM {tabla} WHERE {padre} IN ({', '.join(lit(i) for i in ids)}); "
    if filas:
        cols = list(filas[0])
        s += (f"INSERT INTO {tabla} ({', '.join(cols)}) SELECT {', '.join(cols)} FROM "
              f"json_populate_recordset(NULL::{tabla}, {lit(json.dumps(filas, ensure_ascii=False, default=str))}::json); ")
    return s


def plan(docs, sup, opo_cuit, hoy):
    """Qué fichas cambiaron y las filas de cada tabla. sup: {(col,id): data de Supabase}; opo_cuit: {op_id: cuit}."""
    cambian = {k: d for k, d in docs.items() if sup.get(k) != d}
    oc = dict(opo_cuit)
    t = {x: [] for x in ('ficha', 'oportunidad', 'contacto', 'historial', 'cotizacion', 'cotizacion_item', 'muestra')}
    ids = {'oportunidades': [], 'cotizaciones': [], 'muestras': []}
    for (c, i), d in sorted(cambian.items()):
        ids[c].append(i)
        t['ficha'].append({'coleccion': c, 'id': i, 'actualizado': d.get('actualizado'), 'data': d, 'data_texto': L.jdump(d)})
        if c == 'oportunidades':
            o, con, his = filas_oportunidad(i, d)
            oc[i] = o['cuit']
            t['oportunidad'].append(o)
            t['contacto'] += con
            t['historial'] += his
    for (c, i), d in sorted(cambian.items()):
        if c == 'cotizaciones':
            cot, items = filas_cotizacion(i, d, oc)
            t['cotizacion'].append(cot)
            t['cotizacion_item'] += items
        elif c == 'muestras':
            t['muestra'].append(filas_muestra(i, d, oc))
    for k in t:
        if k != 'ficha':
            con_mudanza(t[k], hoy)
    return cambian, ids, t


def sql_plan(ids, t, hoy):
    nuevas = [dict(f, dueno='crm2', mudado=hoy) for f in t['ficha']]
    s = 'BEGIN; '
    if nuevas:    # crm_ficha: el dueño de las filas que ya existen no se toca
        js = lit(json.dumps(nuevas, ensure_ascii=False, default=str))
        src = f'json_populate_recordset(NULL::comercial.crm_ficha, {js}::json) j'
        s += (f"UPDATE comercial.crm_ficha t SET data=j.data, data_texto=j.data_texto, actualizado=j.actualizado, mudado=j.mudado "
              f"FROM {src} WHERE t.coleccion=j.coleccion AND t.id=j.id; "
              f"INSERT INTO comercial.crm_ficha (coleccion, id, actualizado, data, data_texto, dueno, mudado) "
              f"SELECT coleccion, id, actualizado, data, data_texto, dueno, mudado FROM {src} "
              f"WHERE NOT EXISTS (SELECT 1 FROM comercial.crm_ficha t WHERE t.coleccion=j.coleccion AND t.id=j.id); ")
    s += sql_upsert('comercial.oportunidad', t['oportunidad'], ['id'])
    s += sql_hijos('comercial.contacto', 'oportunidad_id', ids['oportunidades'], t['contacto'])
    s += sql_hijos('comercial.historial', 'oportunidad_id', ids['oportunidades'], t['historial'])
    s += sql_upsert('comercial.cotizacion', t['cotizacion'], ['id'])
    s += sql_hijos('comercial.cotizacion_item', 'cotizacion_id', ids['cotizaciones'], t['cotizacion_item'])
    s += sql_upsert('comercial.muestra', t['muestra'], ['id'])
    for k, tabla in (('ficha', 'crm_ficha'), ('oportunidad', 'oportunidad'), ('contacto', 'contacto'), ('historial', 'historial'),
                     ('cotizacion', 'cotizacion'), ('cotizacion_item', 'cotizacion_item'), ('muestra', 'muestra')):
        if t[k]:
            det = json.dumps({'origen': 'CRM 5SPm (ArtifactData)', 'fichas': [f.get('id') or f.get('oportunidad_id') or
                              f.get('cotizacion_id') for f in t[k]][:40]}, ensure_ascii=False)
            s += (f"INSERT INTO control.registro(cuando, agente, tabla, operacion, motor, version, hash_entrada, filas, detalle) "
                  f"VALUES (now(), 'loki-sync', 'comercial.{tabla}', 'carga', 'sync_crm.py', {lit(VERSION)}, '', {len(t[k])}, "
                  f"{lit(det)}::jsonb); ")
    return s + 'COMMIT;'


# ------------------------------------------------------------------ corrida
def leer_supa(docs):
    pares = ', '.join(f'({lit(c)}, {lit(i)})' for c, i in docs) or "('', '')"
    r = supa("SELECT json_build_object("
             f"'ficha', (SELECT json_agg(json_build_object('c', coleccion, 'i', id, 'd', data)) FROM comercial.crm_ficha "
             f"WHERE (coleccion, id) IN ({pares})), "
             "'opo', (SELECT json_object_agg(id, cuit) FROM comercial.oportunidad)) r")[0]['r']
    sup = {(x['c'], x['i']): x['d'] for x in r.get('ficha') or []}
    return sup, r.get('opo') or {}


def correr(crm_dir, origen, escribir=False, forzar=False):
    if L.origen_crm(origen) != CRM_OFICIAL:
        raise SystemExit(f'RECHAZADO: el origen tiene que ser el CRM oficial {CRM_OFICIAL} (5SPm); FLgX está congelado.')
    docs = leer_carpeta(crm_dir)
    if not docs:
        raise SystemExit(f'FALLA: no hay fichas en {crm_dir} (oportunidades/, cotizaciones/, muestras/)')
    if len(docs) > MAX_FICHAS and not forzar:
        raise SystemExit(f'RECHAZADO: {len(docs)} fichas (> {MAX_FICHAS}) no es un cambio del día; con --forzar si es correcto.')
    hoy = D.date.today().isoformat()
    sup, opo_cuit = leer_supa(docs)
    cambian, ids, t = plan(docs, sup, opo_cuit, hoy)
    print(f'{VERSION} · {len(docs)} fichas leídas · {len(cambian)} cambian · ' +
          ' · '.join(f'{k} {len(v)}' for k, v in t.items() if v))
    for c, i in sorted(cambian):
        print(f'  {c[:3]} {i} · CRM {cambian[(c, i)].get("actualizado")} · ' + ('nueva' if (c, i) not in sup else 'cambió'))
    if not escribir:
        print('Sin --escribir: no se tocó nada.')
        return 0
    if cambian:
        supa(sql_plan(ids, t, hoy), ro=False)
    sup2, _ = leer_supa(docs)
    iguales = sum(1 for k, d in docs.items() if sup2.get(k) == d)
    res = 'PASA' if iguales == len(docs) else 'FALLA'
    dif = [f'{c}/{i}' for (c, i), d in docs.items() if sup2.get((c, i)) != d][:40]
    supa("INSERT INTO control.mudanza(cuando, agente, modulo, tabla, origen, filas_origen, filas_destino, filas_iguales, diferencias, "
         f"resultado, hash_script) VALUES (now(), 'loki-sync', 'comercial', 'comercial.crm_ficha', "
         f"{lit('CRM 5SPm ArtifactData · ' + os.path.basename(os.path.normpath(crm_dir)))}, {len(docs)}, {len(sup2)}, {iguales}, "
         f"{lit(json.dumps(dif, ensure_ascii=False)) + '::jsonb' if dif else 'NULL'}, '{res}', {lit(VERSION)})", ro=False)
    print(f'{res}: {iguales}/{len(docs)} fichas iguales en Supabase después de publicar' + (f' · distintas: {", ".join(dif)}' if dif else ''))
    return 0 if res == 'PASA' else 1


# ------------------------------------------------------------------ autotest (sin red)
def autotest():
    ok = []

    def chk(n, c):
        ok.append(bool(c))
        print(('PASA ' if c else 'FALLA ') + n)

    opo = {'empresa': 'Net SA', 'cuit': '30-70000000-1', 'etapa': 'ganado', 'monto': '1.5', 'contacto': 'Pablo', 'archivada': 'si',
           'historial': [{'t': '2026-11-01', 'txt': 'hola'}, 'basura', {'t': '2026-11-02', 'txt': 'chau'}],
           'contactosAdicionales': [{'nombre': 'Ana', 'mail': 'a@x'}, {'nombre': ''}], 'raro': 'x', 'actualizado': '2026-11-28'}
    cot = {'numero': 'NM1', 'oportunidadId': 'o1', 'estado': 'aceptada', 'total': '10', 'ivaTotal': 2.1, 'actualizado': '2026-11-28',
           'hz_operacion': {'despacho': 'si'}, 'hz_resultado': {'estado': 'ganada', 'fechaSeguimiento': '2026-12-01'},
           'items': [{'codigo': '1115', 'cantidad': '50', 'precio': 38}]}
    mue = {'oportunidadId': 'o1', 'estado': 'enviada', 'devolver': True}
    docs = {('oportunidades', 'o1'): opo, ('cotizaciones', 'k1'): cot, ('muestras', 'm1'): mue, ('oportunidades', 'o2'): {'x': 1}}
    sup = {('oportunidades', 'o2'): {'x': 1}, ('cotizaciones', 'k1'): dict(cot, total='9')}
    cambian, ids, t = plan(docs, sup, {}, '2026-11-28')
    chk('solo publica lo que cambió (o2 igual queda afuera)', set(cambian) == {('oportunidades', 'o1'), ('cotizaciones', 'k1'), ('muestras', 'm1')})
    o = t['oportunidad'][0]
    chk('oportunidad: monto a número, archivada 0/1, extra con lo no mapeado',
        o['monto'] == 1.5 and o['archivada'] == 1 and json.loads(o['extra']) == {'raro': 'x'} and o['cuit'] == '30-70000000-1')
    chk('contactos: principal de la ficha + adicional con datos', [(c['principal'], c['nombre']) for c in t['contacto']] == [(1, 'Pablo'), (0, 'Ana')])
    chk('historial: solo entradas válidas, numeradas', [(h['n'], h['txt']) for h in t['historial']] == [(0, 'hola'), (1, 'chau')])
    k = t['cotizacion'][0]
    chk('cotización hereda el CUIT de su oportunidad y mapea operación/resultado',
        k['cuit'] == '30-70000000-1' and k['despacho'] == 'si' and k['resultado'] == 'ganada' and k['revision'] == '2026-12-01'
        and k['iva'] == 2.1 and k['total'] == 10.0)
    chk('ítems con CUIT y cantidad', t['cotizacion_item'][0]['cuit'] == '30-70000000-1' and t['cotizacion_item'][0]['cantidad'] == 50.0)
    chk('muestra con CUIT y devolver=1', t['muestra'][0]['cuit'] == '30-70000000-1' and t['muestra'][0]['devolver'] == 1)
    chk('columnas de la mudanza (dueño loki, cuit11)', o['dueno'] == 'loki' and o['cuit11'] == '30700000001')
    s = sql_plan(ids, t, '2026-11-28')
    chk('SQL en una transacción, con registro y sin borrar tablas enteras',
        s.startswith('BEGIN;') and s.endswith('COMMIT;') and "'loki-sync'" in s and 'DELETE FROM comercial.oportunidad' not in s
        and 'DELETE FROM comercial.historial WHERE oportunidad_id IN' in s)
    chk('crm_ficha: no pisa el dueño de filas existentes', 'SET data=j.data, data_texto=j.data_texto, actualizado=j.actualizado, mudado=j.mudado ' in s)
    chk('literal seguro ante $ y comillas', lit("a'$b$") .count("a'$b$") == 1)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, 'oportunidades'))
        json.dump({'id': 'o9', 'version': 3, 'data': {'a': 1}}, open(os.path.join(tmp, 'oportunidades', 'o9.json'), 'w'))
        open(os.path.join(tmp, 'oportunidades', '.o9.x.json'), 'w').write('{}')
        chk('carpeta de ArtifactData: desenvuelve data y saltea ocultos', leer_carpeta(tmp) == {('oportunidades', 'o9'): {'a': 1}})
    try:
        correr('.', 'FLgX123')
        chk('rechaza otro CRM', False)
    except SystemExit as e:
        chk('rechaza otro CRM', 'RECHAZADO' in str(e))
    print(f'{VERSION} · autotest {sum(ok)}/{len(ok)}')
    return 0 if all(ok) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['--autotest']:
        sys.exit(autotest())
    if a[:1] == ['correr'] and '--crm' in a and '--origen' in a:
        sys.exit(correr(a[a.index('--crm') + 1], a[a.index('--origen') + 1], '--escribir' in a, '--forzar' in a))
    print(__doc__)
    sys.exit(2)
