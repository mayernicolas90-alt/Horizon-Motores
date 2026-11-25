"""C08 · la copia del CRM en la base de Loki viene solo del CRM oficial 5SPm (paso 4 del datacenter, 24/11).
Error que lo originó: el 24/11 18:16 UTC una sesión cargó un incremental de FLgX (CRM congelado, 458 fichas) sobre la
copia de 5SPm y puntaje, portada y status leyeron datos viejos unas 3 h; cargar-crm lo rotulaba «CRM FLgX» siempre.
ci: en una base SQLite temporal, cargar-crm rechaza sin --origen, con FLgX y un incremental masivo, y acepta 5SPm.
diario: cada copia crm:* registrada en `cargas` dice origen 5SPm (FALLA si dice otro; AVISO si no lo registró)."""
import importlib.util, json, os, sys, tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
LOKI = os.path.join(AQUI, '..', 'loki')


def _loki_sql():
    sp = importlib.util.spec_from_file_location('loki_sql_c08', os.path.join(LOKI, 'loki_sql.py'))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m


def _prueba():
    with tempfile.TemporaryDirectory() as d:
        os.environ['LOKI_SQL_LOCAL'] = os.path.join(d, 'b.db')
        try:
            L = _loki_sql(); db = L.conectar(); L.init(db)
            for c, i, x in (('oportunidades', 'o1', {'empresa': 'A', 'cuit': '30-1'}), ('cotizaciones', 'c1', {'numero': 'NM1'})):
                os.makedirs(os.path.join(d, 'CRM', c)); open(os.path.join(d, 'CRM', c, i + '.json'), 'w').write(json.dumps(x))
            for i in range(L.INCREMENTAL_MAX + 1):
                os.makedirs(os.path.join(d, 'INC', 'oportunidades'), exist_ok=True)
                open(os.path.join(d, 'INC', 'oportunidades', f'x{i}.json'), 'w').write('{}')
            mal = []
            for nombre, args in (('sin origen', dict(origen=None)), ('FLgX', dict(origen='https://claude.ai/artifact/FLgXcongelado')),
                                 ('incremental masivo', dict(origen=L.CRM_OFICIAL, incremental=True, dir='INC'))):
                try:
                    L.cargar_crm(db, os.path.join(d, args.pop('dir', 'CRM')), '2026-11-24', **args); mal.append(nombre + ' entró')
                except ValueError:
                    pass
            L.cargar_crm(db, os.path.join(d, 'CRM'), '2026-11-24', origen=L.CRM_OFICIAL)
            meta = json.loads(L.q(db, "SELECT meta FROM cargas WHERE fuente='crm:oportunidades'")[0]['meta'])
            if meta.get('origen') != L.CRM_OFICIAL:
                mal.append('5SPm no quedó registrado')
            db.close()
        finally:
            os.environ.pop('LOKI_SQL_LOCAL', None)
    return ('FALLA', '; '.join(mal)) if mal else ('PASA', '4 casos: rechaza sin origen, FLgX e incremental masivo; 5SPm entra con origen')


def correr(modo):
    if modo == 'ci':
        return _prueba()
    sys.path.insert(0, LOKI)
    from bitacora2 import turso
    oficial = _loki_sql().CRM_OFICIAL
    otro, sin = [], []
    for r in turso("SELECT fuente, meta FROM cargas WHERE fuente LIKE 'crm:%'"):
        o = json.loads(r['meta'] or '{}').get('origen')
        (otro if o and o != oficial else sin if not o else []).append(f"{r['fuente']}={o}" if o else r['fuente'])
    if otro:
        return 'FALLA', 'copia del CRM de otro origen: ' + ', '.join(otro)
    return ('AVISO', 'sin origen registrado (anterior a 1.13.0): ' + ', '.join(sin)) if sin else ('PASA', 'toda la copia del CRM viene de 5SPm')
