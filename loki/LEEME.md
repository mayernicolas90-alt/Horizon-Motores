# Loki · capa sobre su base SQL

Desde el 17/11/2026 Loki trabaja sobre **su propia base** (Turso `horizon-nicom90`, cuenta de Loki). Estos scripts vivían solo en la tabla `scripts` de esa base; se mudaron acá el 21/11 **idénticos byte por byte** (sha256 verificado contra la base). Regla: se mudan, no se reescriben; un cambio va de a uno, con comparación antes/después, el «hacelo» de Nicolás y su huella en `loki/huellas.json` en el mismo commit. `python -I -X utf8 loki/verificar.py` controla huellas y autotests (GitHub lo corre en cada cambio). La guardia G02 (escribir en el CRM sin «hacelo») corre como hook de Claude Code desde `.claude/settings.json` de este repositorio.

**Acá no hay datos ni secretos.** Los datos viven en la base de Loki; el token de Turso, como secreto del entorno de la nube (lo pone el proxy). La otra cuenta tiene su propia base y su propio repositorio: no se mezclan.

| Archivo | Versión | Qué hace | Autotest |
|---|---|---|---|
| `loki_sql.py` | 1.10.0 | Base de Loki: arranque (`abrir`), copia del CRM, cargas de reportes y recompra, cerebro, bitácora vieja, fichas, status | `--autotest` (91/91) |
| `loki.py` | v3 | Números de la apertura y urgentes (lo llama `loki_sql.py abrir`) | — |
| `motor.py` | 1.2.0 | Pedidos de producto: lista del CRM, stock (Hive en vivo o R8), fichas técnicas | `--autotest` (28/28) |
| `motor_regresion.py` | 1.0 | Corre un `motor.py` sobre las cotizaciones del CRM para comparar versiones | — |
| `recompra.py` | 4.1 | Motor **Recompra** del datacenter: ciclo por cliente (CUIT) + SKU sobre las compras limpias (reglas de la v3.1: ONT FH juntas, ONU Huawei → reemplazo / ya migró, switches fuera, discontinuados, 15 días = una compra). Suma el ciclo global del cliente (patrón de compra del CRM, sin equipos de inversión). Escribe `rec_sku` y `rec_cliente` | `--autotest` (15/15) |
| `cuentas.py` | 0.1 | Motor **Cuentas** del datacenter: qué cuentas se trabajan según la regla D07 (leída de `k_regla`) y la copia del CRM (otro vendedor, no prospectar, compartida, archivada, unificada); CUIT ↔ ficha; deja los conflictos entre fuentes para definir. Escribe `cue_cuentas` | `--autotest` (11/11) |
| `puntaje.py` | 0.2 | Motor **Puntaje** del datacenter: puntaje de cierre 0-100 por ficha con las reglas V143 del CRM, sobre la copia del CRM en Turso; recompra desde `rec_cliente` y exclusiones desde `cue_cuentas`; guarda `s` y `s_sin_monto` (monto aparte) y si es elegible hoy. Escribe `pun_fichas` | `--autotest` (10/10) |
| `portada.py` | 0.1 | Motor **Portada** del datacenter: los 10 del día en una sola lista por puntaje con monto (decisión 24/11), con los dos tipos de venta (rápida: ONT/ONU y recompras · consultiva: cable, OLT, proyectos; mínimo 3 de cada uno si existen). Escribe `por_dia` | `--autotest` (7/7) |
| `publicador.py` | 0.2 | **Publicador**: si el auditor dio PASA o AVISO (DEC-1124f), arma los documentos del CRM (`comprasLimpias`, `config/limpia`, `config/portada`, `config/puntajes`), deja solo lo que cambió en lotes de 50 con manifiesto (la guardia G02 deja pasar solo eso) y después verifica lo escrito contra Turso (`pub_envios`). Nunca toca fichas ni copia precios | `--autotest` (8/8) |
| `auditar.py` | 1.1 | Audita un reporte de Finnegans contra el registro antes de cargarlo | — |
| `memoria_check.py` | 1.0.0 | Aplica la memoria de cuentas (AJUSTAR / AVISO / BOX) a la apertura | `--autotest` (10/10) |
| `bitacora2.py` | 0.1.0 | Bitácora 2: temas + eventos + chequeos contra CRM, R10 y stock | — |
| `auditor.py` | 0.1 | **Puerta de entrada** de reportes de Finnegans (PR #12): recibir, clasificar, verificar contra la cabecera y publicar solo lo verificado; lo que falla va a cuarentena | `--autotest` |
| `importar.py` | 0.5 | Motor **Limpieza** del datacenter: comprobante por TransaccionID, NC vinculadas a su factura (referencia primero, producto y cantidad, facturas idénticas, cantidad exacta), anticipos y diferencias de cambio fuera, pedidos sin factura con tolerancia por descuento contado; cuentas ajenas desde el CRM (`--crm`); **FALLA si a los renglones les falta más del 2 % de la cabecera**; sinónimos de columnas; `correr` lee R10/R23/R24 de `archivos` y deja `limpia_*` | `--autotest` (23/23) |
| `dc.py` | 0.6 | **Orquestador del datacenter** (DEC-1124): lee el contrato de cada motor, lo corre solo si cambiaron sus tablas de entrada o su versión, verifica que no escriba fuera de su contrato, llama al auditor y registra todo en `dc_motores` / `dc_corridas` | `--autotest` (6/6) |
| `auditor_dc.py` | 0.5 | **Auditor de corridas** (antes `auditor.py`): controles generales (terminó bien, contrato) de Limpieza, Recompra, Cuentas, Puntaje y Portada (lista ordenada, sin excluidas, los dos tipos de venta; puntaje en rango, topes, excluidas sin puntaje; regla D07 legible, conflictos, cobertura de CUIT; una fila por SKU, cobertura, ciclo coherente, última compra firme; entrada = salida contra R10, NC sueltas, cantidades, sin precios, frescura, pendientes propios). Solo escribe `aud_resultados` | `--autotest` (7/7) |

## Datacenter (desde el 24/11, DEC-1124a/b/c)

Turso es el datacenter: cada motor es un archivo independiente (`--contrato`, `--autotest`, `correr`) que lee tablas de Turso y escribe solo en las suyas.
`dc.py correr --disparo finnegans` (al subir reportes) o `--disparo loki` (al escribir «Loki») corre los motores que correspondan; el auditor revisa cada corrida
y, si da FALLA, no se publica nada. Motores: Limpieza (`importar.py`) y Recompra (`recompra.py`) con disparo finnegans; Cuentas (`cuentas.py`), Puntaje (`puntaje.py`) y Portada (`portada.py`) con disparo loki; después, el Publicador (`publicador.py preparar` → Claude escribe los lotes con ArtifactData → `publicador.py verificar`).

## Dónde corre (desde el 22/11)

Loki vive **solo en la nube** (claude.ai/code): el token de Turso lo pone el proxy del entorno. Finnegans se adjunta en el chat; los cambios de motores van por rama + PR en este repositorio y, aprobados, se cargan con la misma huella a la tabla `scripts` de la base.

```
python3 -I loki_sql.py abrir RAIZ AAAA-MM-DD --crm RAIZ/CRM --reglas
python3 -I RAIZ/SCRIPTS/bitacora2.py chequear turso AAAA-MM-DD
```
