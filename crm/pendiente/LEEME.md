# Parches del CRM pendientes de publicar (23-24/11/2026)

Solo código: sin datos de clientes. Se insertan antes del último `</body>` de la página del CRM
(https://claude.ai/artifact/FLgXXtdZnidGLDWrVbPayw), en este orden, sobre la versión publicada 1794418320-25ca.

| Archivo | Qué hace | Estado |
|---|---|---|
| `v47_compras.html` | «Historial de compras» pasa a «Compras» y muestra el ciclo de recompra arriba de los pedidos; el motor de recompra lee la colección `comprasLimpias` + `config/limpia` (sin ellas usa la facturación como antes) | Probado en banco · esperando «publicalo» |
| `v47_avisos_portada.html` | Saca de la portada la línea Stockfish / «Ojo:» y la pasa al desplegable «Avisos» de la ficha | Probado en banco · esperando «publicalo» |
| `prototipo_carriles_chips.html` | Prototipo: carriles Rápidas/Consultivas, chips en la ficha, cuenta compartida, monto fuera del puntaje | No aprobado: referencia |

Con el datacenter (DEC-1124), `comprasLimpias` y `config/limpia` los va a escribir el motor Publicador desde `limpia_compras_firmes`.
