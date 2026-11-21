"""C05 · El top 5 de Loki es solo venta: una entrega abierta (aunque esté pagada, sea grande y esté vencida)
va a la lista posventa y nunca ocupa un lugar del top 5, de siguen ni de cortas (regla N01).
Arma un caso mínimo en una carpeta temporal y corre loki.py urgentes. No usa red ni la base."""
import json, os, subprocess, sys, tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOY = '2026-11-21'


def _caso(d):
    ops = {'o1': {'empresa': 'Cliente Entrega SA', 'proximaFecha': '2026-11-10', 'proximaAccion': 'confirmar entrega NM90', 'ultimoContacto': '2026-11-10'},
           'o2': {'empresa': 'Cliente Venta SA', 'proximaFecha': '2026-11-25', 'ultimoContacto': '2026-11-15'}}
    cots = {'c1': {'numero': 'NM90', 'cliente': 'Cliente Entrega SA', 'oportunidadId': 'o1', 'estado': 'aceptada', 'total': 50000,
                   'hz_operacion': {'pago': 'confirmado', 'despacho': 'pendiente', 'entrega': 'pendiente'}},
            'c2': {'numero': 'NM91', 'cliente': 'Cliente Venta SA', 'oportunidadId': 'o2', 'estado': 'enviada', 'total': 6000,
                   'fecha': '2026-11-10', 'vence': '2026-12-10', 'items': []}}
    w = lambda n, x: json.dump(x, open(os.path.join(d, n), 'w', encoding='utf-8'))
    w('respaldo.json', {'collections': {'oportunidades': ops, 'cotizaciones': cots, 'muestras': {}}})
    w('respaldo_meta.json', {'exportadoEn': HOY, 'colecciones': {}})
    w('continuidad.json', {}); w('recompra.json', []); w('recompra_meta.json', {'corte': HOY})
    w('R10_meta.json', {'corte': HOY, 'filas': 0})
    open(os.path.join(d, 'R10.csv'), 'w', encoding='utf-8').write('Fecha;Comprobante;Cliente;Producto;Marca;Cantidad;Pte Dest.;Empresa\n')


def correr(modo):
    with tempfile.TemporaryDirectory() as d:
        _caso(d)
        p = subprocess.run([sys.executable, '-I', '-X', 'utf8', os.path.join(RAIZ, 'loki', 'loki.py'), 'urgentes', d, HOY],
                           capture_output=True, text=True, encoding='utf-8')
        if p.returncode != 0:
            return 'FALLA', f'loki.py urgentes no corrió: {p.stderr.strip()[-150:]}'
        u = json.loads(p.stdout)
    venta = u.get('top5', []) + u.get('siguen', []) + u.get('cortas', [])
    mal = [x['ref'] for x in venta if x.get('tipo') == 'posventa']
    if mal:
        return 'FALLA', f'entrega abierta dentro del ranking de venta: {", ".join(map(str, mal))}'
    if [x.get('ref') for x in u.get('posventa', [])] != ['NM90']:
        return 'FALLA', 'la entrega abierta NM90 no aparece en la lista posventa'
    if [x.get('ref') for x in u.get('top5', [])] != ['NM91']:
        return 'FALLA', f"el top 5 debería ser solo NM91 y es {[x.get('ref') for x in u.get('top5', [])]}"
    return 'PASA', 'top 5 solo venta; NM90 (pagada, USD 50.000, vencida) va a posventa'
