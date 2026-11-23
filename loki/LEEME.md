# Loki · capa sobre su base SQL

Desde el 17/11/2026 Loki trabaja sobre **su propia base** (Turso `horizon-nicom90`, cuenta de Loki). Estos scripts vivían solo en la tabla `scripts` de esa base; se mudaron acá el 21/11 **idénticos byte por byte** (sha256 verificado contra la base). Regla: se mudan, no se reescriben; un cambio va de a uno, con comparación antes/después, el «hacelo» de Nicolás y su huella en `loki/huellas.json` en el mismo commit. `python -I -X utf8 loki/verificar.py` controla huellas y autotests (GitHub lo corre en cada cambio). La guardia G02 (escribir en el CRM sin «hacelo») corre como hook de Claude Code desde `.claude/settings.json` de este repositorio.

**Acá no hay datos ni secretos.** Los datos viven en la base de Loki; el token de Turso, como secreto del entorno de la nube (lo pone el proxy). La otra cuenta tiene su propia base y su propio repositorio: no se mezclan.

| Archivo | Versión | Qué hace | Autotest |
|---|---|---|---|
| `loki_sql.py` | 1.10.0 | Base de Loki: arranque (`abrir`), copia del CRM, cargas de reportes y recompra, cerebro, bitácora vieja, fichas, status | `--autotest` (91/91) |
| `loki.py` | v3 | Números de la apertura y urgentes (lo llama `loki_sql.py abrir`) | — |
| `motor.py` | 1.2.0 | Pedidos de producto: lista del CRM, stock (Hive en vivo o R8), fichas técnicas | `--autotest` (28/28) |
| `motor_regresion.py` | 1.0 | Corre un `motor.py` sobre las cotizaciones del CRM para comparar versiones | — |
| `recompra.py` | v3.1 | Recompra por cliente + SKU desde el R10 | — |
| `auditar.py` | 1.1 | Audita un reporte de Finnegans contra el registro antes de cargarlo | — |
| `memoria_check.py` | 1.0.0 | Aplica la memoria de cuentas (AJUSTAR / AVISO / BOX) a la apertura | `--autotest` (10/10) |
| `bitacora2.py` | 0.1.0 | Bitácora 2: temas + eventos + chequeos contra CRM, R10 y stock | — |
| `importar.py` | 0.3 | Filtro de limpieza de Finnegans: comprobante por TransaccionID, NC vinculadas a su factura (referencia, producto y cantidad, facturas idénticas), anticipos y diferencias de cambio fuera, faltantes contra la cabecera, pedidos sin factura (con tolerancia por descuento contado). Cuentas ajenas (otro vendedor, no prospectar, cuentas fuera) desde el CRM (`--crm`, obligatorio); reporte incompleto (más del 2 % de la cabecera sin renglones hasta el corte) = FALLA y no se sube. Deja `limpia_*` en la base con `--subir-turso` (solo con hacelo) | `--autotest` (18/18) |

## Dónde corre (desde el 22/11)

Loki vive **solo en la nube** (claude.ai/code): el token de Turso lo pone el proxy del entorno. Finnegans se adjunta en el chat; los cambios de motores van por rama + PR en este repositorio y, aprobados, se cargan con la misma huella a la tabla `scripts` de la base.

```
python3 -I loki_sql.py abrir RAIZ AAAA-MM-DD --crm RAIZ/CRM --reglas
python3 -I RAIZ/SCRIPTS/bitacora2.py chequear turso AAAA-MM-DD
```
