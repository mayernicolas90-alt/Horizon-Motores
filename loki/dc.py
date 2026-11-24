#!/usr/bin/env python3
"""dc.py 0.1 · Orquestador del datacenter de Loki en Turso (24/11/2026, DEC-1124a/b/c).

Cada motor es un archivo independiente con tres entradas:
  motor.py --contrato   → JSON {id, nombre, version, disparo, lee, escribe, que_hace}
  motor.py --autotest   → casos sin datos reales
  motor.py correr       → lee sus tablas de Turso y escribe solo en las suyas; última línea «RESUMEN {...}»
Los motores no se llaman entre sí: se comunican solo por tablas de Turso.

El orquestador:
  1. lee el contrato de cada motor y lo guarda en dc_motores;
  2. corre solo los motores del disparo pedido (finnegans: al subir reportes · loki: al escribir «Loki»);
  3. saltea un motor si sus tablas de entrada no cambiaron desde su última corrida buena (salvo --forzar);
  4. antes y después de cada motor cuenta las filas de todas las tablas: si cambió una que no está en su contrato,
     la corrida queda FUERA DE CONTRATO;
  5. después de cada motor corre el auditor (auditor_dc.py), que deja sus controles en aud_resultados;
  6. registra todo en dc_corridas.
Solo el orquestador escribe dc_motores y dc_corridas.

Uso (python3 -I):
  dc.py motores                         contratos registrados
  dc.py correr --disparo finnegans|loki [--forzar] [--solo ID]
  dc.py estado [N]                      últimas corridas
  dc.py --autotest
"""
import datetime as D, hashlib, importlib.util, json, os, subprocess, sys

VERSION = 'dc 0.6 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
MOTORES = ['importar.py', 'recompra.py', 'cuentas.py', 'puntaje.py', 'portada.py']   # en orden: un motor solo lee lo que dejaron los anteriores
AUDITOR = 'auditor_dc.py'
PROPIAS = ('dc_motores', 'dc_corridas')
DDL = ["CREATE TABLE IF NOT EXISTS dc_motores(id TEXT PRIMARY KEY, nombre TEXT, version TEXT, disparo TEXT, lee TEXT, escribe TEXT, "
       "archivo TEXT, que_hace TEXT, actualizado TEXT)",
       "CREATE TABLE IF NOT EXISTS dc_corridas(id INTEGER PRIMARY KEY AUTOINCREMENT, motor TEXT, disparo TEXT, inicio TEXT, fin TEXT, "
       "estado TEXT, huella_entrada TEXT, resumen TEXT, fuera_contrato TEXT, auditor TEXT)"]


def ahora():
    return D.datetime.now(D.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def loki(ruta=None):
    ruta = ruta or os.path.join(AQUI, 'loki_sql.py')
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m, ruta


def q(db, sql, args=()):
    cols, filas = db.run([(sql, list(args))])[0]
    return [dict(zip(cols, f)) for f in filas]


def contrato(archivo):
    r = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(AQUI, archivo), '--contrato'], capture_output=True, text=True, cwd=AQUI)
    if r.returncode:
        raise RuntimeError(f'{archivo}: --contrato falló: {r.stderr[-300:]}')
    c = json.loads(r.stdout.strip().splitlines()[-1])
    for k in ('id', 'version', 'disparo', 'lee', 'escribe'):
        if k not in c:
            raise RuntimeError(f'{archivo}: al contrato le falta «{k}»')
    c['archivo'] = archivo
    return c


def tablas(db):
    return [r['name'] for r in q(db, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def conteos(db, excluir=()):
    ts = [t for t in tablas(db) if t not in excluir]
    if not ts:
        return {}
    res = db.run([(f'SELECT count(*) FROM "{t}"', []) for t in ts])
    return {t: r[1][0][0] for t, r in zip(ts, res)}


def huella(db, lee, version=''):
    """Huella de las tablas de entrada de un motor (sha256 de los archivos crudos o filas + último rowid de cada tabla) y de su versión."""
    partes = ['version=' + version]
    for e in lee:
        if e.startswith('archivos:'):
            f = q(db, 'SELECT sha256 FROM archivos WHERE nombre=?', [e.split(':', 1)[1]])
            partes.append(e + '=' + (f[0]['sha256'] if f else 'falta'))
        else:
            try:
                f = q(db, f'SELECT count(*) n, max(rowid) m FROM "{e}"')[0]
                if (f['n'] or 0) <= 5000:   # 0.4: tablas chicas por contenido completo (detecta cambios en filas existentes, ej. una regla editada)
                    filas = db.run([(f'SELECT * FROM "{e}" ORDER BY rowid', [])])[0][1]
                    partes.append(e + '=' + hashlib.sha256(json.dumps(filas, default=str).encode()).hexdigest()[:16])
                else:
                    partes.append(f"{e}={f['n']}/{f['m']}")
            except RuntimeError:
                partes.append(e + '=falta')
    return hashlib.sha256('|'.join(partes).encode()).hexdigest()[:16]


def registrar(db, cs):
    db.run([(s, []) for s in DDL])
    db.run([('INSERT OR REPLACE INTO dc_motores VALUES(?,?,?,?,?,?,?,?,?)',
             [c['id'], c.get('nombre', c['id']), c['version'], c['disparo'], json.dumps(c['lee']), json.dumps(c['escribe']), c['archivo'],
              c.get('que_hace', ''), ahora()]) for c in cs])


def correr(disparo, forzar=False, solo=None, loki_ruta=None):
    L, ruta = loki(loki_ruta)
    db = L.conectar()
    cs = [contrato(a) for a in MOTORES]
    registrar(db, cs)
    salida = []
    for c in cs:
        if solo and c['id'] != solo:
            continue
        if disparo != 'todos' and c['disparo'] != disparo and not solo:
            continue
        h = huella(db, c['lee'], c['version'])   # 0.2: una versión nueva del motor también lo vuelve a correr
        ult = q(db, "SELECT huella_entrada FROM dc_corridas WHERE motor=? AND estado='OK' AND auditor IN ('PASA','AVISO') ORDER BY id DESC LIMIT 1", [c['id']])
        if ult and ult[0]['huella_entrada'] == h and not forzar:
            salida.append((c['id'], 'SIN CAMBIOS', 'sus datos de entrada no cambiaron desde la última corrida buena'))
            continue
        ini = ahora()
        cid = db.run([('INSERT INTO dc_corridas(motor,disparo,inicio,estado,huella_entrada) VALUES(?,?,?,?,?) RETURNING id',
                       [c['id'], disparo, ini, 'CORRIENDO', h])])[0][1][0][0]
        antes = conteos(db, excluir=PROPIAS + tuple(c['escribe']))
        r = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(AQUI, c['archivo']), 'correr', '--loki', ruta],
                           capture_output=True, text=True, cwd=AQUI)
        res = next((l[8:] for l in reversed(r.stdout.splitlines()) if l.startswith('RESUMEN ')), '')
        despues = conteos(db, excluir=PROPIAS + tuple(c['escribe']))
        fuera = sorted(t for t in set(antes) | set(despues) if t not in ('aud_resultados',) and antes.get(t) != despues.get(t))
        est = 'OK' if r.returncode == 0 else 'ERROR'
        db.run([('UPDATE dc_corridas SET fin=?, estado=?, resumen=?, fuera_contrato=? WHERE id=?',
                 [ahora(), est, res or (r.stderr or r.stdout)[-500:], json.dumps(fuera), cid])])
        a = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(AQUI, AUDITOR), 'correr', '--corrida', str(cid), '--loki', ruta],
                           capture_output=True, text=True, cwd=AQUI)
        veredicto = next((l.split()[1] for l in reversed(a.stdout.splitlines()) if l.startswith('AUDITOR ')), 'ERROR')
        db.run([('UPDATE dc_corridas SET auditor=? WHERE id=?', [veredicto, cid])])
        salida.append((c['id'], est + (' · FUERA DE CONTRATO: ' + ', '.join(fuera) if fuera else ''), 'auditor ' + veredicto + ' · ' + a.stdout.strip().splitlines()[-1][:160] if a.stdout.strip() else 'auditor sin salida'))
    db.close()
    print(f'{VERSION} · disparo {disparo}')
    for m, e, d in salida:
        print(f'  {m:10} {e:12} {d}')
    malas = [s for s in salida if s[1].startswith('ERROR') or 'FUERA' in s[1] or 'FALLA' in s[2]]
    print('RESULTADO: ' + ('FALLA' if malas else 'PASA'))
    return 1 if malas else 0


def estado(n=10, loki_ruta=None):
    L, _ = loki(loki_ruta)
    db = L.conectar()
    try:
        for r in q(db, 'SELECT id, motor, disparo, inicio, estado, auditor, fuera_contrato FROM dc_corridas ORDER BY id DESC LIMIT ?', [n]):
            print(f"  #{r['id']} {r['inicio']} {r['motor']:10} {r['disparo']:9} {r['estado']:9} auditor {r['auditor']}"
                  + (' · fuera de contrato ' + r['fuera_contrato'] if r['fuera_contrato'] not in (None, '[]') else ''))
    except RuntimeError:
        print('  todavía no hay corridas')
    db.close()


def motores():
    for a in MOTORES:
        c = contrato(a)
        print(f"  {c['id']:10} {c['version']:28} disparo {c['disparo']:9} lee {', '.join(c['lee'])} → escribe {', '.join(c['escribe'])}")


# ---------------------------------------------------------------- autotest (base local, motores de juguete)
def autotest():
    import tempfile, shutil, sqlite3
    d = tempfile.mkdtemp()
    shutil.copy(os.path.join(AQUI, 'loki_sql.py'), d)
    base = os.path.join(d, 'base.sqlite')
    c = sqlite3.connect(base)
    c.executescript("CREATE TABLE archivos(nombre TEXT, sha256 TEXT, bytes INTEGER, texto TEXT); INSERT INTO archivos VALUES('X.csv','h1',1,'a');"
                    "CREATE TABLE ajena(x); INSERT INTO ajena VALUES(1);")
    c.commit(); c.close()
    bueno = "import sys,json,os,importlib.util\nsp=importlib.util.spec_from_file_location('L',os.path.join(os.path.dirname(__file__),'loki_sql.py'));L=importlib.util.module_from_spec(sp);sp.loader.exec_module(L)\n" \
            "C={'id':'%s','version':'1','disparo':'finnegans','lee':['archivos:X.csv'],'escribe':['%s']}\n" \
            "if '--contrato' in sys.argv: print(json.dumps(C)); sys.exit(0)\n" \
            "db=L.conectar(); db.run([('CREATE TABLE IF NOT EXISTS %s(x)',[]),('INSERT INTO %s VALUES(1)',[])%s]); print('RESUMEN {\"ok\":1}')\n"
    open(os.path.join(d, 'm_bueno.py'), 'w').write(bueno % ('bueno', 'sal_bueno', 'sal_bueno', 'sal_bueno', ''))
    open(os.path.join(d, 'm_malo.py'), 'w').write(bueno % ('malo', 'sal_malo', 'sal_malo', 'sal_malo', ",('INSERT INTO ajena VALUES(2)',[])"))
    open(os.path.join(d, 'auditor_dc.py'), 'w').write("import sys\nprint('AUDITOR PASA · juguete')\n")
    shutil.copy(os.path.abspath(__file__), os.path.join(d, 'dc.py'))
    env = dict(os.environ, LOKI_SQL_LOCAL=base)
    def dc(*a, motores=('m_bueno.py',)):
        src = open(os.path.join(d, 'dc.py')).read().replace("MOTORES = ['importar.py', 'recompra.py', 'cuentas.py', 'puntaje.py', 'portada.py']", 'MOTORES = ' + repr(list(motores)), 1)
        open(os.path.join(d, 'dc_t.py'), 'w').write(src)
        return subprocess.run([sys.executable, '-X', 'utf8', os.path.join(d, 'dc_t.py'), *a], capture_output=True, text=True, env=env, cwd=d)
    r1 = dc('correr', '--disparo', 'finnegans')
    r2 = dc('correr', '--disparo', 'finnegans')
    r3 = dc('correr', '--disparo', 'loki')
    c = sqlite3.connect(base); c.execute("UPDATE archivos SET sha256='h2'"); c.commit(); c.close()
    r4 = dc('correr', '--disparo', 'finnegans')
    r5 = dc('correr', '--disparo', 'finnegans', motores=('m_malo.py',))
    c = sqlite3.connect(base)
    corr = c.execute('SELECT motor, estado, auditor, fuera_contrato FROM dc_corridas ORDER BY id').fetchall()
    casos = [
        ('corre el motor del disparo y registra la corrida', 'PASA' in r1.stdout and corr[0][:3] == ('bueno', 'OK', 'PASA')),
        ('sin cambios en la entrada no vuelve a correr', 'SIN CAMBIOS' in r2.stdout and len([x for x in corr if x[0] == 'bueno']) == 2),
        ('otro disparo no corre motores de Finnegans', 'bueno' not in r3.stdout),
        ('si cambia el archivo crudo vuelve a correr', 'SIN CAMBIOS' not in r4.stdout and r4.returncode == 0),
        ('escribir fuera del contrato queda marcado y da FALLA', 'FUERA DE CONTRATO: ajena' in r5.stdout and r5.returncode == 1 and corr[-1][3] == '["ajena"]'),
        ('el contrato queda registrado', c.execute("SELECT count(*) FROM dc_motores WHERE id IN ('bueno','malo')").fetchone()[0] == 2),
    ]
    c.close()
    for t, ok in casos:
        print(('  OK    ' if ok else '  FALLA ') + t)
    ok = sum(1 for _, x in casos if x)
    print(f'autotest dc: {ok}/{len(casos)}')
    return 0 if ok == len(casos) else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    arg = lambda k, dflt=None: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else dflt
    if a[:1] == ['motores']:
        motores()
    elif a[:1] == ['correr']:
        sys.exit(correr(arg('--disparo', 'todos'), '--forzar' in a, arg('--solo'), arg('--loki')))
    elif a[:1] == ['estado']:
        estado(int(a[1]) if len(a) > 1 and a[1].isdigit() else 10, arg('--loki'))
    else:
        print(__doc__)
