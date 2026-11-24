#!/usr/bin/env python3
"""publicador.py 0.1 · Publicador del datacenter (24/11/2026, DEC-1124c/f). Solo biblioteca estándar.

Copia al CRM lo que calcularon los motores, solo si el auditor lo aprobó (PASA o AVISO; con FALLA no se copia nada).
El CRM solo se escribe desde una sesión de Claude (herramienta ArtifactData), así que el Publicador trabaja en dos pasos:
  1. preparar: revisa las últimas corridas de los motores en dc_corridas; arma los documentos (comprasLimpias por CUIT,
     config/limpia, config/portada, config/puntajes), los compara con lo que hoy tiene el CRM y deja solo lo que cambió,
     en lotes de hasta 50 escrituras, con un manifiesto (huella de cada documento). La guardia G02 deja pasar esas escrituras
     solo si coinciden con el manifiesto.
  2. verificar: con el CRM releído después de escribir, compara cada documento con su huella, registra el envío en pub_envios
     y la corrida en dc_corridas (motor «publicador»).
Nunca toca fichas, cotizaciones, muestras ni notas. Nunca copia precios: solo cantidades, puntajes y fechas.

Uso (python3 -I):
  publicador.py preparar --crm DIR_CRM --salida DIR [--versiones versiones.json] [--loki ruta]
  publicador.py verificar --crm DIR_CRM --salida DIR [--loki ruta]
  publicador.py --contrato · publicador.py --autotest
DIR_CRM = salida de ArtifactData list (out_dir) de las colecciones comprasLimpias y config.
"""
import datetime as D, glob, hashlib, importlib.util, json, os, sys

VERSION = 'publicador 0.1 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
MOTORES = ['limpieza', 'recompra', 'cuentas', 'puntaje', 'portada']
OK_AUDITOR = {'PASA', 'AVISO'}                     # DEC-1124f: con AVISO también se publica (y se avisa)
MANIFIESTO_GUARDIA = os.path.expanduser('~/.cache/loki-publicador/manifiesto.json')
CONTRATO = {'id': 'publicador', 'nombre': 'Publicador', 'disparo': 'después de cada corrida',
            'lee': ['limpia_renglones', 'limpia_comprobantes', 'limpia_fuentes', 'limpia_pedidos', 'por_dia', 'pun_fichas', 'dc_corridas'],
            'escribe': ['pub_envios', 'CRM: comprasLimpias, config/limpia, config/portada, config/puntajes'],
            'que_hace': 'Copia al CRM solo lo que cambió y solo si el auditor aprobó; después verifica lo escrito.'}
VOLATIL = {'actualizado', 'generado'}               # no cuentan para decidir si un documento cambió


def ahora():
    return D.datetime.now(D.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def huella(doc):
    limpio = {k: v for k, v in doc.items() if k not in VOLATIL}
    return hashlib.sha256(json.dumps(limpio, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()[:16]


def loki(ruta=None):
    ruta = ruta or os.path.join(AQUI, 'loki_sql.py')
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def q(db, sql, args=()):
    cols, filas = db.run([(sql, list(args))])[0]
    return [dict(zip(cols, f)) for f in filas]


def compuerta(db):
    """Última corrida de cada motor: tiene que haber terminado bien y el auditor dar PASA o AVISO."""
    estado, malos = {}, []
    for m in MOTORES:
        r = q(db, 'SELECT id, estado, auditor FROM dc_corridas WHERE motor=? ORDER BY id DESC LIMIT 1', [m])
        if not r:
            malos.append(f'{m}: nunca corrió'); continue
        r = r[0]
        estado[m] = {'corrida': r['id'], 'auditor': r['auditor']}
        if r['estado'] != 'OK' or r['auditor'] not in OK_AUDITOR:
            malos.append(f"{m}: corrida {r['id']} {r['estado']} · auditor {r['auditor']}")
    return estado, malos


def armar(db):
    """Documentos del CRM a partir de las tablas de Turso. Devuelve {(coleccion, doc_id): doc}."""
    hoy = ahora()
    docs = {}
    filas = q(db, "SELECT c.cuit, c.cliente, c.fecha, c.comprobante, r.producto, r.cantidad_neta, r.familia, r.subfamilia, r.marca "
                  "FROM limpia_renglones r JOIN limpia_comprobantes c ON c.tid = r.tid WHERE c.tipo = 'FA' AND r.clase = 'producto' "
                  "AND r.cantidad_neta > 0.0001 AND c.cuit <> '' ORDER BY c.fecha, c.comprobante, r.producto")
    for f in filas:
        d = docs.setdefault(('comprasLimpias', f['cuit']), {'cliente': '', 'cuit': f['cuit'], 'lineas': [], 'fuente': 'datacenter', 'actualizado': hoy})
        d['cliente'] = (f['cliente'] or '').strip()
        d['lineas'].append({'fecha': f['fecha'], 'comprobante': f['comprobante'], 'producto': (f['producto'] or '').strip(),
                            'cantidad': round(float(f['cantidad_neta']), 2), 'familia': f['familia'] or '', 'subfamilia': f['subfamilia'] or '',
                            'marca': f['marca'] or ''})
    fuentes = q(db, 'SELECT fuente, archivo, corte FROM limpia_fuentes')
    anul = [r['nro'] for r in q(db, "SELECT p.nro FROM limpia_pedidos p WHERE p.factura_tid IS NOT NULL AND NOT EXISTS (SELECT 1 FROM limpia_renglones r "
                                    "WHERE r.tid = p.factura_tid AND r.clase IN ('producto','anticipo') AND r.cantidad_neta > 0.0001) "
                                    "AND EXISTS (SELECT 1 FROM limpia_renglones r WHERE r.tid = p.factura_tid AND r.clase IN ('producto','anticipo')) ORDER BY p.nro")]
    corte = q(db, 'SELECT max(fecha) m FROM limpia_comprobantes')[0]['m']
    docs[('config', 'limpia')] = {'version': VERSION, 'corte': corte, 'fuentes': fuentes, 'pedidosAnulados': anul, 'generado': hoy,
                                  'nota': 'Compras netas de notas de crédito, sin anticipos ni diferencias de cambio. Solo cantidades, sin precios.'}
    lista = q(db, 'SELECT puesto, crm_id, empresa, tipo, s, s_sin_monto, valor_en_juego, motivo, calculado FROM por_dia ORDER BY puesto')
    docs[('config', 'portada')] = {'version': VERSION, 'fecha': lista[0]['calculado'] if lista else None, 'generado': hoy,
                                   'criterio': 'una sola lista por puntaje con monto; rápidas y consultivas (DEC-1124e)',
                                   'lista': [{k: v for k, v in x.items() if k != 'calculado'} for x in lista]}
    pun = q(db, 'SELECT crm_id, s, s_sin_monto, valor_en_juego, nivel, elegible, excluida, calculado FROM pun_fichas ORDER BY crm_id')
    docs[('config', 'puntajes')] = {'version': VERSION, 'fecha': pun[0]['calculado'] if pun else None, 'generado': hoy,
                                    'fichas': {p['crm_id']: {'s': p['s'], 's0': p['s_sin_monto'], 'v': p['valor_en_juego'], 'nivel': p['nivel'],
                                                             'elegible': p['elegible'], 'excluida': p['excluida']} for p in pun}}
    return docs


def leer_crm(dir_crm):
    out = {}
    for col in ('comprasLimpias', 'config'):
        for p in glob.glob(os.path.join(dir_crm, col, '*.json')):
            d = json.load(open(p, encoding='utf-8'))
            out[(col, os.path.basename(p)[:-5])] = d.get('data', d) if isinstance(d.get('data'), dict) else d
    return out


def preparar(dir_crm, salida, versiones=None, loki_ruta=None):
    db = loki(loki_ruta).conectar()
    estado, malos = compuerta(db)
    if malos:
        db.close()
        print('BLOQUEADO · no se publica nada: ' + ' · '.join(malos))
        return 3
    docs = armar(db)
    db.close()
    actual = leer_crm(dir_crm)
    vers = json.load(open(versiones, encoding='utf-8')) if versiones else {}
    os.makedirs(salida, exist_ok=True)
    cambios = []
    for (col, i), d in sorted(docs.items()):
        if (col, i) in actual and huella(actual[(col, i)]) == huella(d):
            continue
        p = os.path.join(salida, 'docs', col, i + '.json')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
        e = {'op': 'set', 'collection': col, 'doc_id': i, 'file_path': p, 'sha': huella(d), 'nuevo': (col, i) not in actual}
        v = vers.get(f'{col}/{i}')
        if v:
            e['if_version'] = int(v)
        cambios.append(e)
    lotes = [cambios[k:k + 50] for k in range(0, len(cambios), 50)]
    for n, lote in enumerate(lotes, 1):
        json.dump([{k: e[k] for k in ('op', 'collection', 'doc_id', 'file_path', 'if_version') if k in e} for e in lote],
                  open(os.path.join(salida, f'lote_{n}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    auditor = 'AVISO' if any(x['auditor'] == 'AVISO' for x in estado.values()) else 'PASA'
    man = {'version': VERSION, 'creado': ahora(), 'auditor': auditor, 'corridas': estado, 'total': len(docs),
           'cambios': [{k: e[k] for k in ('collection', 'doc_id', 'file_path', 'sha', 'nuevo')} for e in cambios], 'lotes': len(lotes)}
    json.dump(man, open(os.path.join(salida, 'manifiesto.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(MANIFIESTO_GUARDIA), exist_ok=True)
    json.dump(man, open(MANIFIESTO_GUARDIA, 'w', encoding='utf-8'), ensure_ascii=False)
    nuevos = sum(e['nuevo'] for e in cambios)
    print(f'PREPARADO · auditor {auditor} · {len(docs)} documentos · {len(cambios)} cambian ({nuevos} nuevos) · {len(lotes)} lotes en {salida}')
    return 0


def verificar(dir_crm, salida, loki_ruta=None):
    man = json.load(open(os.path.join(salida, 'manifiesto.json'), encoding='utf-8'))
    actual = leer_crm(dir_crm)
    ok, mal = [], []
    for c in man['cambios']:
        d = actual.get((c['collection'], c['doc_id']))
        (ok if d is not None and huella(d) == c['sha'] else mal).append(c)
    db = loki(loki_ruta).conectar()
    t = ahora()
    db.run([('CREATE TABLE IF NOT EXISTS pub_envios(fecha TEXT, coleccion TEXT, doc_id TEXT, sha TEXT, estado TEXT, auditor TEXT)', [])]
           + [('INSERT INTO pub_envios VALUES(?,?,?,?,?,?)', [t, c['collection'], c['doc_id'], c['sha'], 'verificado' if c in ok else 'distinto', man['auditor']])
              for c in man['cambios']])
    est = 'OK' if not mal else 'ERROR'
    db.run([('INSERT INTO dc_corridas(motor,disparo,inicio,fin,estado,huella_entrada,resumen,fuera_contrato,auditor) VALUES(?,?,?,?,?,?,?,?,?)',
             ['publicador', 'publicación', man['creado'], t, est, hashlib.sha256(json.dumps(man['cambios'], sort_keys=True).encode()).hexdigest()[:16],
              json.dumps({'cambios': len(man['cambios']), 'verificados': len(ok), 'distintos': len(mal)}), '[]', 'PASA' if not mal else 'FALLA'])])
    db.close()
    try:
        os.remove(MANIFIESTO_GUARDIA)     # el permiso de la guardia vale para un solo envío
    except OSError:
        pass
    print(f"{'VERIFICADO' if not mal else 'FALLA'} · {len(ok)}/{len(man['cambios'])} documentos iguales a Turso"
          + (' · distintos: ' + ', '.join(f"{c['collection']}/{c['doc_id']}" for c in mal[:8]) if mal else ''))
    return 0 if not mal else 1


# ---------------------------------------------------------------- autotest (base local, sin datos reales)
def autotest():
    import sqlite3, tempfile, shutil, io, contextlib
    global MANIFIESTO_GUARDIA
    d = tempfile.mkdtemp()
    MANIFIESTO_GUARDIA = os.path.join(d, 'guardia', 'manifiesto.json')
    shutil.copy(os.path.join(AQUI, 'loki_sql.py'), d)
    base = os.path.join(d, 'b.sqlite')
    c = sqlite3.connect(base)
    c.executescript("""
     CREATE TABLE dc_corridas(id INTEGER PRIMARY KEY AUTOINCREMENT, motor, disparo, inicio, fin, estado, huella_entrada, resumen, fuera_contrato, auditor);
     INSERT INTO dc_corridas(motor,estado,auditor) VALUES('limpieza','OK','PASA'),('recompra','OK','PASA'),('cuentas','OK','AVISO'),('puntaje','OK','PASA'),('portada','OK','PASA');
     CREATE TABLE limpia_comprobantes(tid, fecha, tipo, comprobante, cliente, cuit);
     INSERT INTO limpia_comprobantes VALUES('1','2026-10-01','FA','A-1','Cliente X','301'),('2','2026-11-01','FA','A-2','Cliente Y','302');
     CREATE TABLE limpia_renglones(tid, producto, clase, cantidad, cantidad_neta, familia, subfamilia, marca);
     INSERT INTO limpia_renglones VALUES('1','Ont','producto',10,10,'FTTH','ONU','FiberHome'),('2','Caja','producto',5,0,'ODN','CTO','FiberHome');
     CREATE TABLE limpia_fuentes(fuente, archivo, corte); INSERT INTO limpia_fuentes VALUES('renglones','R10.csv','2026-11-20');
     CREATE TABLE limpia_pedidos(nro, fecha, cliente, factura_tid, estado, usuario); INSERT INTO limpia_pedidos VALUES('P-2','2026-11-01','Cliente Y','2','facturado','x');
     CREATE TABLE por_dia(puesto, crm_id, empresa, tipo, s, s_sin_monto, valor_en_juego, motivo, accion, proxima_fecha, calculado);
     INSERT INTO por_dia VALUES(1,'f1','Cliente X','rapida',50,50,0,'Recompra','Llamar',NULL,'2026-11-24');
     CREATE TABLE pun_fichas(crm_id, cuit, empresa, etapa, elegible, s, s_sin_monto, valor_en_juego, nivel, objetivo, funding, evidencia, recompra, razones, excluida, motivo_exclusion, calculado);
     INSERT INTO pun_fichas VALUES('f1','301','Cliente X','ganado',1,50,50,0,'media','recompra','sin_definir',1,'Le toca','[]',0,NULL,'2026-11-24');
    """)
    c.commit(); c.close()
    os.environ['LOKI_SQL_LOCAL'] = base
    crm, sal = os.path.join(d, 'crm'), os.path.join(d, 'sal')
    os.makedirs(os.path.join(crm, 'config'))
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        r1 = preparar(crm, sal, loki_ruta=os.path.join(d, 'loki_sql.py'))
    man = json.load(open(os.path.join(sal, 'manifiesto.json')))
    docs = {(x['collection'], x['doc_id']) for x in man['cambios']}
    x = json.load(open(os.path.join(sal, 'docs', 'comprasLimpias', '301.json')))
    # «escribir» en el CRM simulado copiando los documentos preparados, y verificar
    for ch in man['cambios']:
        p = os.path.join(crm, ch['collection'], ch['doc_id'] + '.json'); os.makedirs(os.path.dirname(p), exist_ok=True); shutil.copy(ch['file_path'], p)
    with contextlib.redirect_stdout(io.StringIO()) as o2:
        r2 = verificar(crm, sal, loki_ruta=os.path.join(d, 'loki_sql.py'))
    sal2 = os.path.join(d, 'sal2')
    with contextlib.redirect_stdout(io.StringIO()) as o3:
        preparar(crm, sal2, loki_ruta=os.path.join(d, 'loki_sql.py'))
    man2 = json.load(open(os.path.join(sal2, 'manifiesto.json')))
    c = sqlite3.connect(base); c.execute("INSERT INTO dc_corridas(motor,estado,auditor) VALUES('portada','OK','FALLA')"); c.commit()
    with contextlib.redirect_stdout(io.StringIO()) as o4:
        r4 = preparar(crm, os.path.join(d, 'sal3'), loki_ruta=os.path.join(d, 'loki_sql.py'))
    envios = c.execute("SELECT count(*) FROM pub_envios WHERE estado='verificado'").fetchone()[0]
    c.close()
    texto = json.dumps(x)
    casos = [
        ('arma compras por CUIT, configuración y portada', r1 == 0 and docs == {('comprasLimpias', '301'), ('config', 'limpia'), ('config', 'portada'), ('config', 'puntajes')}),
        ('solo compras firmes: la compra anulada no va', ('comprasLimpias', '302') not in docs),
        ('nunca copia precios ni importes', not any(k in texto.lower() for k in ('precio', 'importe', 'bruto', 'neto'))),
        ('pedido con factura anulada queda informado', json.load(open(os.path.join(sal, 'docs', 'config', 'limpia.json')))['pedidosAnulados'] == ['P-2']),
        ('con AVISO del auditor publica y lo dice', man['auditor'] == 'AVISO'),
        ('verifica lo escrito y registra el envío', r2 == 0 and 'VERIFICADO · 4/4' in o2.getvalue() and envios == 4),
        ('si nada cambió no escribe nada', man2['cambios'] == []),
        ('con FALLA del auditor no publica nada', r4 == 3 and 'BLOQUEADO' in o4.getvalue()),
    ]
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    ok = sum(1 for _, y in casos if y)
    print(f'autotest publicador: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    arg = lambda k: a[a.index(k) + 1] if k in a else None
    if '--autotest' in a:
        sys.exit(autotest())
    if '--contrato' in a:
        print(json.dumps(dict(CONTRATO, version=VERSION), ensure_ascii=False))
        sys.exit(0)
    if a[:1] == ['preparar']:
        sys.exit(preparar(arg('--crm'), arg('--salida'), arg('--versiones'), arg('--loki')))
    if a[:1] == ['verificar']:
        sys.exit(verificar(arg('--crm'), arg('--salida'), arg('--loki')))
    print(__doc__)
