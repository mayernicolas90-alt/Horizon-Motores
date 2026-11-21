# Loki · capa sobre su base SQL

Desde el 17/11/2026 Loki trabaja sobre **su propia base** (Turso `horizon-nicom90`, cuenta de Loki). Estos scripts vivían solo en la tabla `scripts` de esa base; se mudaron acá el 21/11 **idénticos byte por byte** (sha256 verificado contra la base). Regla: se mudan, no se reescriben; un cambio va de a uno, con comparación antes/después, el «hacelo» de Nicolás y su huella en `loki/huellas.json` en el mismo commit. `python -I -X utf8 loki/verificar.py` controla huellas y autotests (GitHub lo corre en cada cambio).

**Acá no hay datos ni secretos.** Los datos viven en la base de Loki; el token de Turso, en el Administrador de credenciales de Windows de la PC de Nicolás. La otra cuenta tiene su propia base y su propio repositorio: no se mezclan.

| Archivo | Versión | Qué hace | Autotest |
|---|---|---|---|
| `loki_sql.py` | 1.8.0 | Base de Loki: arranque (`abrir`), copia del CRM, cargas de reportes y recompra, cerebro, bitácora vieja, fichas, status | `--autotest` (83/83) |
| `loki.py` | v3 | Números de la apertura y urgentes (lo llama `loki_sql.py abrir`) | — |
| `motor.py` | 1.2.0 | Pedidos de producto: lista del CRM, stock (Hive en vivo o R8), fichas técnicas | `--autotest` (28/28) |
| `motor_regresion.py` | 1.0 | Corre un `motor.py` sobre las cotizaciones del CRM para comparar versiones | — |
| `recompra.py` | v3.1 | Recompra por cliente + SKU desde el R10 | — |
| `auditar.py` | 1.1 | Audita un reporte de Finnegans contra el registro antes de cargarlo | — |
| `memoria_check.py` | 1.0.0 | Aplica la memoria de cuentas (AJUSTAR / AVISO / BOX) a la apertura | `--autotest` (10/10) |
| `bitacora2.py` | 0.1.0 | Bitácora 2: temas + eventos + chequeos contra CRM, R10 y stock | — |
| `conauth.py` | 1.0 | Lanzador en la PC: agrega el token de Turso a los pedidos y corre todo en UTF-8 | — |
| `credencial.py` | 1.0 | Guarda y lee el token en el Administrador de credenciales (solo Windows) | — |

## Uso en la PC

```
python -I -X utf8 %USERPROFILE%\.loki\conauth.py loki_sql.py abrir RAIZ AAAA-MM-DD --crm RAIZ\CRM --reglas
python -I -X utf8 %USERPROFILE%\.loki\conauth.py bitacora2.py chequear turso AAAA-MM-DD
```

En la nube el token lo pone el proxy y no hace falta `conauth.py`.
