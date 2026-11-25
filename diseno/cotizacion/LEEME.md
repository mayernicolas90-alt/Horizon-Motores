# Cotización Horizon · formato NM60

Este es el formato que Nicolás aprobó el 25/11/2026, tomando como modelo la NM60 de Bertone y corrigiéndolo con la NM61 de CEVIC. Reemplaza al NM-50 del cotizador que exportó el PM el 10/11.

## Usar
```
python -I -X utf8 cotizacion_nm.py cot.json SALIDA     # deja SALIDA.pdf, SALIDA.png y SALIDA.html
python -I -X utf8 cotizacion_nm.py --autotest          # 11/11 = PASA
```
- La salida 0 significa «Control PDF: APROBADO».
- El control verifica estas cosas sobre el PDF:
  - El neto, el IVA, el total y cada precio están impresos.
  - Todo entra en una sola hoja.
  - Ningún texto toca el borde.
  - Las fuentes Manrope e Inter quedaron embebidas.
- A Nicolás se le manda siempre también el PNG, porque la vista lateral de la app no abre PDF.

## Contenido (regla de Nicolás, 25/11)
- **Cliente:** el nombre corto (por ejemplo «CEVIC»). En «Atención» va el contacto.
- **Condición de pago:** la de la operación, por ejemplo «Contado (transferencia)» o «30-60-90 días».
- **Artículo:** el nombre comercial, por ejemplo «ONT GPON FiberHome HG6543D». Debajo, una línea con «Cód. · marca · rasgos cortos».
- **Observaciones:**
  - El despacho, con el transporte y el destino.
  - «Los precios no incluyen flete ni seguro.»
  - «Stock sujeto a confirmación al momento de la orden de compra.»
- **No van:**
  - La validez.
  - La financiación (regla L-215).
  - A qué CUIT se factura: eso queda en la ficha del CRM.
- El tipo de cambio va con su fuente y su fecha.

## Requisitos
- Chrome o Edge.
- `pdfplumber`.
- Internet, para bajar Manrope e Inter de fonts.googleapis.com. Si las fuentes no cargan, el control da FALLA, así que el PDF no sale en otra fuente sin que nos enteremos.

## Ejemplo
El archivo `ejemplo_nm61.json` es la NM61 de CEVIC tal cual se aprobó. La regresión del 25/11 dio una imagen idéntica, píxel por píxel, al PDF que vio Nicolás.
