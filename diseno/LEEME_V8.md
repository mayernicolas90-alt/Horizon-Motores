# Diseñador de piezas Horizon · motor V8 (versión 2026-10-29, guardado en el PM)

El motor ya no viaja en un zip: vive en la base del PM FiberHome (`config/motorV8`). Las fotos, las fuentes y las piezas de referencia son assets del PM. Los datos de cada pieza salen del campo `pieza` de la ficha del producto y pasan por un verificador antes de dibujarse.

## Qué hay
- `motor/plantilla_horizon.html`: plantilla aprobada de WhatsApp (chat 1080×1350 y estado 1080×1920; portada y ficha). **No se modifica.**
- `motor/render.js`: arma las 4 piezas a partir de una ficha JSON (playwright + Chromium).
- `motor/panal_v8.py`: panal de hexágonos y las 5 pruebas del panal.
- `motor/composicion_v8.js`: composición fotográfica; se activa con `composicion` en la ficha. Equipo centrado en su tarjeta (decisión de Nicolás 29/10; `centrado: false` vuelve a tercios + aire de mirada), mirada por las líneas del chasis, escala física con las medidas del PM (`medidas_mm`, la pone ficha_v8.py), control de calidad de la foto (ampliación y nitidez), color parejo por material (oscuro 64 / claro 220, LEDs sin tocar), sombra de apoyo y control del par portada-ficha.
- `motor/banco_v8.py` + `motor/banco_esperado.json`: banco de la composición con OLT (AN6000-7), ONT (HG6145F3), ONT con foto chica (HG6543D) y switch sin medidas (S5735-L).
- `motor/qa_scene.js`: control de la escena.
- `motor/ficha_v8.py`: genera `prods.json` y la ficha de la pieza desde la base del PM, y verifica las promesas.
- Fuentes Poppins y referencias aprobadas: assets del PM (ids en `config/motorV8.assets`).

## Pasos
1. **Instalar** (una vez por chat): exportar `config` y `productos` del PM con ArtifactData (`out_dir` = `<dir>/pm`), escribir los archivos de `config/motorV8.archivos` y bajar los assets (Artifact `read` con `path` = id). Si `fc-list | grep Poppins` no muestra nada, copiar las fuentes a `~/.local/share/fonts` y correr `fc-cache`.
2. **prods.json**: `python3 motor/ficha_v8.py prods --pm <dir>/pm --salida motor/prods.json` (siempre desde la base, nunca a mano).
3. **Ficha**: `python3 motor/ficha_v8.py ficha --pm <dir>/pm --pid <id> --salida fichas/<id>.json`. Sale el id del asset de la foto aprobada: bajarlo a `fotos/<id>.png`. Si la ficha del PM no tiene `pieza` o foto aprobada, se carga primero en el PM.
4. **Verificar**: `python3 motor/ficha_v8.py verificar --pm <dir>/pm --ficha fichas/<id>.json`. Tiene que dar `"aprobado": true`. Controla que cada cifra y cada tecnología estén en la base del producto, que no prometa más puertos PON de los que deja el kit (reglas del PM), que no use palabras sin respaldo (licencia, stock, entrega inmediata, garantía, homologado) y las promesas prohibidas de la ficha (`pieza.prohibido`).
5. **Render**: `NODE_PATH=/opt/npm-tools/node_modules node motor/render.js fichas/<id>.json <nombre> <salida>` → 2 PNG: portada y ficha (detalle) en formato chat 1080×1350. Para estado 1080×1920, agregar `"formatos": ["chat", "estado"]` en la ficha.
6. **Panal**: `python3 motor/panal_v8.py <entrada.png> <salida.png> <familia>` (olt, ont o pasivo; la ficha lo trae en `familia_panal`).
7. **Control**: 5 pruebas del panal con `"aprobado": true` (y 13 de composición si se usó: suma calidad_foto, sombra_apoyo y par_portada_ficha). Si falla, no se entrega. Avisos de calidad (foto ampliada o blanda): pedir foto mejor.
8. **Entrega**: 2 PNG por producto, portada y ficha, en chat 1080×1350 (decisión de Nicolás 29/10).

## Reglas
- No mover ni redimensionar nada de la plantilla.
- Textos cortos; 3 atributos de unas 2 palabras, parejos en largo.
- Nada inventado: si el verificador marca una cifra, se corrige la pieza o se carga el dato en el PM con su fuente.
- Prueba de regresión: la ficha `an6000-7` del PM tiene que reproducir píxel por píxel las referencias AN6000-7 (sin composición). Si se toca la composición: `python3 motor/banco_v8.py <salida>` tiene que dar 8 de 8 iguales al esperado.
