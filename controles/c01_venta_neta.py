"""C01/C02 · venta neta y entregas, contra los datos reales de la base de Loki (diario) o con datos inventados (ci).
Casos aprendidos: NM07 y NM09 (ONU devueltas) dan venta neta 0; NM53 (Contratista) no tiene nada por entregar."""
import os, sys, sqlite3, subprocess
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, '..', 'loki'))

CASOS = [('NM07', lambda t: t['neta'] == 0 and t['por_entregar'] == 0 and t['dudoso'] == 0, 'venta neta 0, nada por entregar, no dudosa'),
         ('NM09', lambda t: t['neta'] == 0 and t['por_entregar'] == 0 and t['dudoso'] == 0, 'venta neta 0, nada por entregar, no dudosa'),
         ('NM53', lambda t: t['por_entregar'] == 0, 'nada por entregar (remito 0007-87)')]


def correr(modo):
    if modo == 'ci':
        r = subprocess.run([sys.executable, '-X', 'utf8', '-I', os.path.join(AQUI, '..', 'loki', 'enlace.py'), '--autotest'], capture_output=True, text=True, encoding='utf-8')
        return ('PASA' if r.returncode == 0 else 'FALLA'), (r.stdout.strip().splitlines() or ['sin salida'])[-1]
    import enlace
    db = sqlite3.connect(':memory:')
    enlace.importar(db)
    lin, cots = enlace.enlazar(db)
    mal = []
    for nm, ok, esperado in CASOS:
        cid = next((k for k, c in cots.items() if c['numero'] == nm), None)
        if cid is None:
            mal.append(f'{nm}: no está en el CRM'); continue
        t = enlace.totales(db, cid)
        if not ok(t):
            mal.append(f"{nm}: esperaba {esperado}; dio neta {t['neta']:g}, por entregar {t['por_entregar']:g}, dudosos {int(t['dudoso'])}")
    return ('FALLA', ' · '.join(mal)) if mal else ('PASA', f'{len(CASOS)} casos')
