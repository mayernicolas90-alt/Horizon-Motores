# Loki · motor de coincidencias (`motor.py` 1.0.0)

Toma un pedido en texto libre y lo cruza con lo que vende Horizon.
Ejemplos de pedido: «20 onus wifi 5», «botellas de 48», «4 km de drop», «1186».

## De dónde saca los datos

Todo sale de la base SQL de Loki (Turso), en el momento en que corre:
- **Precios:** lista del CRM (precio ISP) y productos Huawei/ZTT.
- **Stock:** reporte R8 de Finnegans, por código.
- **Alias:** tabla `motor_alias`.

En este repositorio no hay datos, precios ni credenciales: el token lo pone el proxy del entorno.

## Qué devuelve por renglón

- **CUMPLE:** producto, precio ISP, IVA, total con IVA y stock con su código.
- **OPCIONES:** el pedido es ambiguo y hay que elegir.
- **SIN PRECIO:** está en Finnegans pero no en la lista; el precio queda a confirmar.
- **NO TENEMOS:** no hay nada en la lista que sirva.

Al final da el total con IVA y la lista de lo que hay que revisar antes de enviar.

## Uso

Necesita `loki_sql.py` en la misma carpeta (se baja de la base).

```bash
python3 -I motor.py responder "20 onus wifi 5; 10 botellas de 48; 4 km de drop"
```

```bash
python3 -I motor.py buscar "splitter 1x8"
```

```bash
python3 -I motor.py --autotest
```

## Pruebas (18/11/2026)

- Autotest: 17/17.
- Contra los renglones de las 63 cotizaciones del CRM: 96/96 escritos tal cual. Escritos "sueltos", como los pondría un cliente: 94/96; los 2 restantes dan opciones que incluyen el correcto.

## Reglas

- Precio ISP de la lista; sin precio = «a confirmar».
- Stock sujeto a confirmación con JP.
- Montos con IVA. Huawei: 4 % de descuento pagando contado o por transferencia.
- Nada se inventa.
- Sumar un alias escribe en la base, así que solo se hace con el «hacelo» de Nicolás.
