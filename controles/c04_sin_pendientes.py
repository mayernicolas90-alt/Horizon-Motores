"""C04 · alerta diaria: no puede haber reglas en estado pendiente (N05: se resuelven cuando surgen)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'loki'))


def correr(modo):
    if modo == 'ci':
        return 'SALTA', 'solo con datos (diario)'
    from bitacora2 import turso
    r = turso("SELECT id, titulo FROM k_regla WHERE estado='pendiente'")
    return ('PASA', '0 reglas pendientes') if not r else ('FALLA', 'pendientes: ' + ', '.join(x['id'] for x in r))
