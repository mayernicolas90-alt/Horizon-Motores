# Motor de diseño V9 (propuesta de Loki nube · 25/11/2026)

Parte del motor V8 del PM (base del PM, `config/motorV8`, versión 2026-10-29) y le suma HD, nitidez, criterios de diseño y composición.
**Sin el campo `pulido` en la ficha, el motor sale idéntico al V8** (regresión AN6000-7 píxel por píxel y banco 8/8).
El motor V8 original sigue siendo del PM: este directorio es la copia de Loki con las mejoras, para que el PM las revise y las pase a su repo.

## Qué agrega
| Archivo | Qué hace |
|---|---|
| `motor/render.js` | Exporta la escena (`*.escena.json`) y, con `"escala": 2`, la pieza en HD (2160×2700) dibujando los vectores al doble. `"foto_hd"` usa una foto realzada solo en la HD. |
| `motor/panal_v8.py` | 4.º argumento opcional: dibuja el mismo panal nativo sobre la pieza HD. |
| `motor/foto_hd.py` | Foto para HD sin IA generativa: Lanczos + máscara de enfoque con umbral sobre el equipo, limpia el halo del alfa; avisa si la foto queda chica. |
| `motor/criterios_v8.py` | 11 criterios medidos: margen seguro, alineación por contenedor, solapamiento, escala tipográfica, legibilidad móvil, contraste WCAG 2, ritmo vertical, espacio en blanco, balance visual, centrado vertical y nitidez HD. |
| `motor/pulido_v9.js` | Con `"pulido": true`: escala tipográfica cerrada (18 · 22 · 34 · 40 · 64+), rótulos ≥ 22 px, contraste ≥ 4,5:1, aire repartido (tabla y portada), CTA centrado con su botón, líneas de base compartidas, cifras y foto en el centro de su tarjeta. Con `"titulo_modelo": true` la ficha usa el modelo como título, la categoría como bajada (`"bajada"`) y el logo de marca grande (`"logo_ancho"`, 230 px). |
| `motor/pieza_auto.py` | Borrador del campo `pieza` desde las specs del PM (sin inventar cifras) + verificador de promesas. |
| `motor/ficha_v8.py` | Elige la foto aprobada de **mayor resolución** (lección L-194). |
| `probar.py` | Banco: regresión AN6000-7, banco de composición y pieza V9 de la HG6145F3. |

## Reglas que no cambian
Plantilla, colores, Poppins, panal, pie y orden de bloques de Horizon. Fotos sin IA generativa. Ninguna cifra sin respaldo en la base del PM (`ficha_v8.py verificar`). Precios solo si Nicolás los pide.

## Probar
1. Exportar `config` y `productos` del PM a `../pm` y bajar fuentes, fotos y referencias (assets del PM, ver `config/motorV8.assets`).
2. `python3 motor/ficha_v8.py prods --pm ../pm --salida motor/prods.json` y `python3 motor/ficha_v8.py ficha --pm ../pm --pid an6000-7 --salida fichas/an6000-7.json`.
3. `python3 motor/foto_hd.py fotos/ont-hg6145f3.png fotos/ont-hg6145f3_hd.png --ancho_mostrado 290`.
4. `python3 probar.py --referencias <dir>` → `RESULTADO: PASA`.

Resultado del 25/11 en la nube: regresión 0 px distintos (portada y ficha) · banco 8/8 · HG6145F3 V9 criterios 11/11 en portada y ficha, nitidez HD 4,7-5,0×.
Panal: pasa en la portada (0,225); la ficha de ONT da 0,251, igual que la ficha de ONT ya aprobada (0,252): mirar a ojo.

## Fuentes de los criterios
O'Donovan et al. 2014 (alineación, solapamiento, espacio en blanco) · SciFig (balance en grilla 8×8) · W3C WCAG 2 G17/G18 (contraste, luminancia) · OpenCV (varianza del Laplaciano, Lanczos, máscara de enfoque) · Adobe y Expert Photography (espacio negativo, peso visual, producto como foco) · principios de composición (OpenText BC) y alineación óptica (Icons8).
