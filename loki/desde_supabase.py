#!/usr/bin/env python3
"""desde_supabase.py 0.1 · 28/11/2026 · los motores de Loki leen del datacenter (Regla 0 de Nicolás, notas PM-s y PM-t).

Arma una base local (SQLite) SOLO con datos de Supabase, con las tablas y columnas que cada motor espera (mismo nombre que
en Turso), y corre los motores sobre esa base con LOKI_SQL_LOCAL. Los motores no cambian. Al final compara lo calculado con
lo publicado en Supabase y, con --escribir, lo publica con el Espejo (verificado fila por fila, queda en control.registro).

Motores que ya pueden correr desde el datacenter: puntaje y portada (leen crm, rec_cliente, cue_cuentas, pun_fichas).
Cuentas y recompra siguen en Turso hasta que el PM publique su limpieza en Supabase (nota bh).

Uso (python3 -I):  desde_supabase.py correr [--hoy AAAA-MM-DD] [--escribir] [--base RUTA.sqlite] · desde_supabase.py --autotest
"""
import datetime as D, importlib.util, json, os, sqlite3, subprocess, sys, tempfile

VERSION = 'desde_supabase 0.1 · 2026-11-28'
AQUI = os.path.dirname(os.path.abspath(__file__))
EXTRA = {'dueno', 'mudado', 'cuit11', 'foto'}          # columnas que agregó la mudanza: no son del motor
# tabla que espera el motor → origen en Supabase
ORIGEN = {'rec_cliente': 'motores.recompra_cliente', 'cue_cuentas': 'clientes.cuenta', 'pun_fichas': 'motores.puntaje'}
MOTORES = ['puntaje.py', 'portada.py']                  # en orden: portada lee el pun_fichas que deja puntaje
SALIDA = {'puntaje.py': ('pun_fichas', 'motores.puntaje'), 'portada.py': ('por_dia', 'motores.portada')}


def _mod(nombre):
    sp = importlib.util.spec_from_file_location(nombre[:-3], os.path.join(AQUI, nombre))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def armar(base, supa):
    """Base local con crm (fichas crudas del CRM, sin datos bancarios) y las tablas de ORIGEN."""
    c = sqlite3.connect(base)
    c.execute('CREATE TABLE crm (coleccion TEXT, id TEXT, data TEXT, PRIMARY KEY (coleccion, id))')
    filas = supa("SELECT coleccion, id, data::text AS data FROM comercial.crm_ficha "
                 "WHERE coleccion IN ('oportunidades','cotizaciones','muestras')")
    c.executemany('INSERT INTO crm VALUES (?,?,?)', [(f['coleccion'], f['id'], f['data']) for f in filas])
    n = {'crm': len(filas)}
    for t, o in ORIGEN.items():
        esq, tab = o.split('.')
        cols = [r['column_name'] for r in supa(f"SELECT column_name FROM information_schema.columns WHERE table_schema='{esq}' "
                                                f"AND table_name='{tab}' ORDER BY ordinal_position") if r['column_name'] not in EXTRA]
        c.execute(f'CREATE TABLE {t} ({", ".join(chr(34) + x + chr(34) for x in cols)})')
        rows = supa(f'SELECT {", ".join(chr(34) + x + chr(34) for x in cols)} FROM {o}')
        c.executemany(f'INSERT INTO {t} VALUES ({",".join("?" * len(cols))})',
                      [tuple(json.dumps(r[x], ensure_ascii=False) if isinstance(r[x], (dict, list)) else r[x] for x in cols) for r in rows])
        n[t] = len(rows)
    c.commit()
    c.close()
    return n


def correr(hoy, escribir=False, base=None):
    E = _mod('espejo.py')
    base = base or os.path.join(tempfile.mkdtemp(prefix='loki_dc_'), 'datacenter.sqlite')
    n = armar(base, E.supa)
    env = dict(os.environ, LOKI_SQL_LOCAL=base)
    print(f'{VERSION} · base armada solo desde Supabase: ' + ' · '.join(f'{k} {v}' for k, v in n.items()))
    malas = 0
    for m in MOTORES:
        r = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(AQUI, m), 'correr', '--hoy', hoy,
                            '--loki', os.path.join(AQUI, 'loki_sql.py')], capture_output=True, text=True, cwd=AQUI, env=env)
        if r.returncode:
            print(f'  {m:11} FALLA · {(r.stderr or r.stdout)[-300:]}')
            return 1
        t, dest = SALIDA[m]
        c = sqlite3.connect(base)
        cur = c.execute(f'SELECT * FROM {t}')
        cols = [d[0] for d in cur.description]
        filas = [dict(zip(cols, x)) for x in cur.fetchall()]
        c.close()
        comunes = [x for x in cols if x in E.columnas_supa(dest)]
        actual = E.supa(f'SELECT {", ".join(chr(34) + x + chr(34) for x in comunes)} FROM {dest}')
        ig, a, b = E.comparar(filas, actual, comunes)
        estado = 'IGUAL A SUPABASE' if not a and not b else f'CAMBIA ({a} nuevas/cambiadas, {b} salen)'
        if escribir and (a or b):
            h, sql = E.sql_publicar(dest, filas, E.columnas_supa(dest), m[:-3], f'{m[:-3]} desde Supabase · {VERSION}', hoy)
            E.supa(sql, solo_lectura=False)
            despues = E.supa(f'SELECT {", ".join(chr(34) + x + chr(34) for x in comunes)} FROM {dest}')
            _, a2, b2 = E.comparar(filas, despues, comunes)
            estado = 'PUBLICADO PASA' if not a2 and not b2 else 'PUBLICADO FALLA'
            malas += bool(a2 or b2)
        print(f'  {m:11} → {t:11} {len(filas):4} filas · {estado} · {r.stdout.strip().splitlines()[-1][:120]}')
    print('RESUMEN ' + json.dumps({'base': base, 'falla': malas}))
    return 1 if malas else 0


def autotest():
    d = tempfile.mkdtemp(prefix='loki_dc_test_')
    base = os.path.join(d, 'b.sqlite')
    datos = {
        "comercial.crm_ficha": [{'coleccion': 'oportunidades', 'id': 'o1', 'data': '{"empresa": "X"}'}],
        'motores.recompra_cliente': [{'cuit': '30', 'estado': 'Le toca', 'mudado': '2026-11-28', 'dueno': 'loki'}],
        'clientes.cuenta': [{'clave': 'k', 'cuit': '30', 'trabajar': 1, 'cuit11': '30', 'dueno': 'loki'}],
        'motores.puntaje': [{'crm_id': 'o1', 's': 50, 'foto': 'x'}],
    }

    def supa(sql):
        if 'information_schema' in sql:
            t = [k for k in datos if f"table_name='{k.split('.')[1]}'" in sql][0]
            return [{'column_name': c} for c in datos[t][0]]
        if 'crm_ficha' in sql:
            if 'bancarios' in sql:
                return []
            return datos['comercial.crm_ficha']
        t = [k for k in datos if k in sql][0]
        return datos[t]
    n = armar(base, supa)
    c = sqlite3.connect(base)
    casos = [('crm armado', n['crm'] == 1 and c.execute('SELECT data FROM crm').fetchone()[0] == '{"empresa": "X"}'),
             ('columnas de la mudanza fuera', [x[1] for x in c.execute('PRAGMA table_info(rec_cliente)')] == ['cuit', 'estado']),
             ('cuentas sin cuit11 ni dueño', 'cuit11' not in [x[1] for x in c.execute('PRAGMA table_info(cue_cuentas)')]),
             ('pun_fichas para la portada', c.execute('SELECT s FROM pun_fichas').fetchone()[0] == 50),
             ('solo oportunidades, cotizaciones y muestras (sin config bancaria)', 'config' not in json.dumps(datos['comercial.crm_ficha']))]
    c.close()
    ok = sum(b for _, b in casos)
    for x, b in casos:
        print(('  OK    ' if b else '  FALLA ') + x)
    print(f'autotest desde_supabase: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    arg = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
    if '--autotest' in a:
        sys.exit(autotest())
    if a[:1] == ['correr']:
        hoy = arg('--hoy') or D.datetime.now(D.timezone(D.timedelta(hours=-3))).date().isoformat()
        sys.exit(correr(hoy, '--escribir' in a, arg('--base')))
    print(__doc__)
