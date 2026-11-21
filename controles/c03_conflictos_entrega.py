"""C03 · alerta diaria: cotizaciones donde las fuentes no coinciden sobre la entrega (R10 vs R26, o lo facturado sin remito)."""
import os, sys, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'loki'))


def correr(modo):
    if modo == 'ci':
        return 'SALTA', 'solo con datos (diario)'
    import enlace
    db = sqlite3.connect(':memory:')
    enlace.importar(db)
    lin, cots = enlace.enlazar(db)
    conf, porent = [], []
    for cid, c in cots.items():
        t = enlace.totales(db, cid)
        if not t.get('factura'):
            continue
        pend = db.execute("SELECT SUM(c.pendiente) FROM comprobante c JOIN vinculo v ON v.tipo=c.tipo AND v.numero=c.numero AND v.cod=c.cod WHERE v.cotizacion=? AND c.tipo='factura'", (cid,)).fetchone()[0] or 0
        if pend and t['por_entregar'] == 0:
            conf.append(f"{c['numero']} (R10 dice {pend:g} sin entregar, R26 ya remitió)")
        elif t['por_entregar'] > 0:
            porent.append(f"{c['numero']} {t['por_entregar']:g}")
    if not conf and not porent:
        return 'PASA', 'sin conflictos ni entregas abiertas'
    return 'AVISO', f"conflictos: {', '.join(conf) or 'ninguno'} · por entregar (Posventa): {', '.join(porent) or 'nada'}"
