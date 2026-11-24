#!/usr/bin/env python3
"""memoria.py 0.1 · memoria SQL compartida entre las sesiones de Loki (Turso horizon-nicom90, tabla mem_dia).

Regla de Nicolás (24/11): no hay corrida diaria; cada sesión deja todo anotado al final del día y lo lee al empezar.
«Más simple: en Turso dejen una memoria SQL». Una fila por cosa; cada sesión escribe y cierra solo sus filas.
  sesion  · datacenter | loki-5spm | pm
  tipo    · estado | pendiente | decision (espera a Nicolás) | hallazgo | aviso (para otra sesión)
  para    · a quién va (o NULL)        estado · abierto | cerrado
Uso (python3 -I):
  memoria.py leer [--todas]                         lo abierto de todas las sesiones (o todo con --todas)
  memoria.py anotar SESION TIPO "texto" [--para X] [--ref Y]
  memoria.py cerrar ID SESION "cómo se cerró"      solo cierra filas de esa misma sesión
  memoria.py --autotest
"""
import datetime as D, importlib.util, json, os, sys

VERSION = 'memoria 0.1 · 2026-11-24'
AQUI = os.path.dirname(os.path.abspath(__file__))
TIPOS = {'estado', 'pendiente', 'decision', 'hallazgo', 'aviso'}
CREAR = ('CREATE TABLE IF NOT EXISTS mem_dia(id INTEGER PRIMARY KEY, creado TEXT, sesion TEXT, tipo TEXT, para TEXT, '
         'texto TEXT, ref TEXT, estado TEXT DEFAULT \'abierto\', cerrado TEXT, cierre TEXT)')
ahora = lambda: D.datetime.now(D.timezone.utc).isoformat(timespec='seconds')


def anotar(db, sesion, tipo, texto, para=None, ref=None):
    if tipo not in TIPOS:
        raise ValueError(f'tipo {tipo}: tiene que ser uno de {sorted(TIPOS)}')
    db.run([(CREAR, []), ('INSERT INTO mem_dia(creado, sesion, tipo, para, texto, ref) VALUES(?,?,?,?,?,?)',
                          [ahora(), sesion, tipo, para, texto, ref])])


def cerrar(db, id_, sesion, como):
    cols, filas = db.run([(CREAR, []), ('SELECT sesion, estado FROM mem_dia WHERE id = ?', [id_])])[1]
    if not filas:
        raise ValueError(f'no existe la fila {id_}')
    if filas[0][0] != sesion:
        raise PermissionError(f'la fila {id_} es de {filas[0][0]}: solo la cierra esa sesión')
    db.run([('UPDATE mem_dia SET estado=\'cerrado\', cerrado=?, cierre=? WHERE id=? AND sesion=?', [ahora(), como, id_, sesion])])


def leer(db, todas=False):
    cols, filas = db.run([(CREAR, []), ('SELECT id, creado, sesion, tipo, para, texto, ref, estado, cierre FROM mem_dia'
                                        + ('' if todas else " WHERE estado='abierto'") + ' ORDER BY sesion, tipo, id', [])])[1]
    return [dict(zip(cols, f)) for f in filas]


class _DBPrueba:
    """sqlite en memoria con la misma interfaz run() que loki_sql."""
    def __init__(self):
        import sqlite3
        self.c = sqlite3.connect(':memory:')

    def run(self, lote):
        out = []
        for s, a in lote:
            cur = self.c.execute(s, a)
            out.append(([d[0] for d in cur.description] if cur.description else [], [list(r) for r in cur.fetchall()]))
        self.c.commit()
        return out


def autotest():
    db = _DBPrueba()
    anotar(db, 'datacenter', 'pendiente', 'correr control_biblioteca', para='pm')
    anotar(db, 'pm', 'aviso', 'arreglé los alias', para='datacenter')
    ab = leer(db)
    casos = [('se anota y se lee lo abierto', len(ab) == 2)]
    try:
        cerrar(db, ab[0]['id'] if ab[0]['sesion'] == 'pm' else ab[1]['id'], 'datacenter', 'x'); ok = False
    except PermissionError:
        ok = True
    casos.append(('una sesión no cierra filas de otra', ok))
    cerrar(db, next(x['id'] for x in ab if x['sesion'] == 'datacenter'), 'datacenter', 'C1=0')
    casos.append(('cerrar saca de lo abierto y queda en el historial', len(leer(db)) == 1 and len(leer(db, True)) == 2))
    try:
        anotar(db, 'pm', 'chisme', 'x'); ok = False
    except ValueError:
        ok = True
    casos.append(('tipo desconocido se rechaza', ok))
    for t, k in casos:
        print(('  OK    ' if k else '  FALLA ') + t)
    n = sum(x for _, x in casos)
    print(f'autotest memoria: {n}/{len(casos)}')
    return 0 if n == len(casos) else 1


def loki(ruta):
    sp = importlib.util.spec_from_file_location('loki_sql', ruta)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


if __name__ == '__main__':
    a = sys.argv[1:]
    if '--autotest' in a:
        sys.exit(autotest())
    db = None
    if a[:1] in (['leer'], ['anotar'], ['cerrar']):
        db = loki(os.path.join(AQUI, '..', 'loki', 'loki_sql.py')).conectar()
    if a[:1] == ['leer']:
        for f in leer(db, '--todas' in a):
            print(f"#{f['id']} [{f['sesion']}·{f['tipo']}{'→' + f['para'] if f['para'] else ''}] {f['texto']}" + (f"  ({f['estado']}: {f['cierre']})" if f['estado'] != 'abierto' else ''))
    elif a[:1] == ['anotar'] and len(a) >= 4:
        opt = lambda k: a[a.index(k) + 1] if k in a else None
        anotar(db, a[1], a[2], a[3], opt('--para'), opt('--ref')); print('anotado')
    elif a[:1] == ['cerrar'] and len(a) >= 4:
        cerrar(db, int(a[1]), a[2], a[3]); print('cerrado')
    else:
        print(__doc__)
    if db:
        db.close()
