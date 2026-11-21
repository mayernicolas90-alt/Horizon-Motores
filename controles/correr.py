#!/usr/bin/env python3
"""Corre los controles del registro (controles/registro.json).
  python -I -X utf8 controles/correr.py ci       sin datos reales (GitHub, en cada cambio)
  python -I -X utf8 %USERPROFILE%/.loki/conauth.py controles/correr.py diario --hoy AAAA-MM-DD
        con la base de Loki: guarda el resultado y abre un tema en la bitácora por cada FALLA nueva.
Un error sin control puede repetirse: el registro lista también los que faltan."""
import importlib.util, json, os, sys, datetime as dt

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)


def cargar(ruta):
    s = importlib.util.spec_from_file_location(os.path.basename(ruta)[:-3], os.path.join(RAIZ, ruta))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def main(a):
    modo = a[0] if a else 'ci'
    hoy = a[a.index('--hoy') + 1] if '--hoy' in a else dt.date.today().isoformat()
    reg = json.load(open(os.path.join(AQUI, 'registro.json'), encoding='utf-8'))
    res, hechos = [], set()
    for c in reg['controles']:
        if c['tipo'] in ('instruccion', 'falta') or not c['archivo']:
            res.append((c['id'], 'SIN CODIGO' if c['tipo'] == 'falta' else 'INSTRUCCION', c.get('nota') or c['archivo'] or '', c)); continue
        if c['archivo'] in hechos:
            res.append((c['id'], 'INCLUIDO', f"lo cubre el mismo control ({c['archivo']})", c)); continue
        hechos.add(c['archivo'])
        if modo not in c['corre'] and not (modo == 'diario' and c['tipo'] in ('caso', 'alerta')):
            res.append((c['id'], 'SALTA', f"corre en {', '.join(c['corre'])}", c)); continue
        try:
            est, det = cargar(c['archivo']).correr(modo)
        except Exception as e:  # noqa: BLE001  un control roto es una falla, no se esconde
            est, det = 'FALLA', f'el control no corrió: {type(e).__name__}: {str(e)[:120]}'
        res.append((c['id'], est, det, c))
    for i, est, det, c in res:
        print(f'{est:<11} {i}  {c["error"][:70]:<70} · {det}')
    fallas = [r for r in res if r[1] == 'FALLA']
    if modo == 'diario':
        sys.path.insert(0, os.path.join(RAIZ, 'loki'))
        from bitacora2 import turso
        turso('CREATE TABLE IF NOT EXISTS a_control_resultado (fecha TEXT, control TEXT, estado TEXT, detalle TEXT, PRIMARY KEY (fecha, control))')
        for i, est, det, c in res:
            turso('INSERT OR REPLACE INTO a_control_resultado VALUES (?,?,?,?)', [hoy, i, est, det[:500]])
        for i, est, det, c in fallas:
            tit = f'Control {i} falla'
            if not turso("SELECT 1 FROM tema WHERE titulo=? AND estado='abierto'", [tit]):
                m = max(1000, int(turso('SELECT MAX(id) m FROM tema')[0]['m'] or 0) + 1)
                turso("""INSERT INTO tema (id,titulo,area,estado,espera,proximo,revisar,prioridad,refs,creado,actualizado)
                         VALUES (?,?,'loki','abierto','loki',?,?,'A','[]',?,?)""", [m, tit, f'Corregir: {c["error"][:90]}', hoy, hoy, hoy])
                turso("INSERT INTO tema_evento (tema_id,fecha,tipo,texto,fuente) VALUES (?,?,'auto',?,'controles')", [m, hoy, det[:500]])
    print(f"\nRESULTADO: {'FALLA (' + str(len(fallas)) + ')' if fallas else 'PASA'} · {len(res)} en el registro · "
          f"{sum(1 for r in res if r[1] == 'SIN CODIGO')} sin código")
    return 1 if fallas else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
