#!/usr/bin/env python3
"""loki_sql.py v1.10.1 · la base SQL propia de Loki (Turso horizon-nicom90) · 22/11/2026

Loki es independiente: su estado vive en SU base SQL. El CRM FLgX se LEE (ArtifactData) y se copia acá.
1.10.1 (22/11): cargar-continuidad exige `importante` no vacío y abrir no se cae si falta (una sesión la dejó en null).
1.10.0 (22/11): conocimiento-cargar ARCHIVO.json: alta o cambio de filas de las tablas k_* (decisiones, reglas,
  procedimientos, fuentes, documentos) con columnas validadas, todo o nada. Antes no había cómo escribirlas desde Loki.
1.9.1 (22/11): bajar/abrir bajan también bitacora2.py (antes el chequeo de la bitácora se hacía a mano). Loki vive en la nube.
1.9.0 (22/11): el arranque lee el conocimiento en tablas (capa 1, k_*; tema #1002). `abrir --reglas` imprime reglas duras
  enteras, el resto de las vigentes en una línea, preferencias, decisiones vigentes y motores por pestaña, todo desde
  k_regla / k_preferencia / k_decision / k_motor (antes: prosa de reglas § Parte 0 + preferencias). `regla ID` y `reglas`
  leen k_regla (estados vigente | historica; --tipo dura). Si la base no tiene k_regla, vuelve al cerebro en prosa.
1.8.0 (18/11): orden y velocidad. Consultas del arranque agrupadas en lotes (qs: varias SELECT en un solo viaje a Turso;
  bajar, controles, clientes, crm_*, calidad, status y reglas). Esquema 6: stock guarda TODAS las columnas del R8
  (orden, partida, fechas, en_produccion: antes se perdía "En producción"). bajar/abrir bajan también motor.py.
  VERSION alineada con el encabezado (abrir decía 1.6.0).
1.7.1 (18/11): abrir recalcula status_cliente solo si llegó CRM, R10 o R8 después del último cálculo (línea STATUS).
1.7.0 (18/11): status del cliente como el PM (diseño 18/11): status-calcular precalcula la tarjeta diseño A de TODAS las fichas
  vivas (tabla status_cliente, con control propio, historial de comprobantes, fecha del CRM y versión del motor); `status X`
  lee la fila, saca 4 PNG (sin estirar) y arma la página del panel lateral (2 columnas, Ver historial y Evaluar cotización).
1.6.0 (18/11): copia del CRM en tablas ordenadas (DERIVADAS de `crm`, se rearman en cada abrir; nunca se editan):
  crm_oportunidad · crm_contacto · crm_historial · crm_cotizacion · crm_cotizacion_item · crm_muestra, todas con CUIT
  resuelto; vistas v_despacho y v_ganadas_sin_despacho. Lo que falta acá falta en el CRM: se carga en el CRM.
1.5.0 (17/11): registro de reportes (tabla `reportes`, R4-R26) · cargar-reporte acepta cualquier código registrado
  (R10/R8 siguen llenando ventas/stock; el resto queda como archivo <código>.csv) · bajar-reportes para auditar.py ·
  bajar/abrir solo bajan R10.csv, R8.csv y recompra.json.
1.4.0 (17/11): bitácora (el hilo en filas), clientes por CUIT + alias, vistas 360 / seguimientos / revisar hoy (R-VIVA), L8 calidad.
1.3.0 (17/11): cerebro estructurado (cerebro_seccion / cerebro_regla / cerebro_router, derivadas de los documentos);
  doc --seccion ahora respeta bloques ``` (antes cortaba en un ## dentro de código) y acepta claves D06 / §2 / P01.
Solo biblioteca estándar. Correr siempre con python3 -I. El token lo pone el proxy (nunca en el código).

ARRANQUE (lo único que hace la skill):
  loki_sql.py crm-desde [HOY]               qué traer del CRM: COMPLETA (list de todo) o DESDE AAAA-MM-DD (query actualizado >=)
  loki_sql.py abrir RAIZ HOY [--crm CRM_DIR [--incremental]] [--reglas]
      CRM_DIR = salida de ArtifactData (oportunidades, cotizaciones, muestras): se copia a la base. --incremental si fue
      un query DESDE (solo cambios; las colecciones vacías no dejan carpeta y está bien).
      Baja de la base a RAIZ/DATOS y RAIZ/SCRIPTS solo lo que usan loki.py y memoria_check.py (sha256 verificado),
      corre los controles (L1-L6), loki.py y memoria_check.py, e imprime la apertura corta. --reglas suma
      reglas § Parte 0, preferencias y respuestas § 1 (del cerebro de la base).
      Exit 0 LISTO · 2 AVISO_FORMATO · 1 NO_LISTO_DATOS.
CONSULTA:
  loki_sql.py estado                      fuentes, edad, filas y control de conteos
  loki_sql.py sql "SELECT ..."             solo lectura (SELECT/WITH/PRAGMA)
  loki_sql.py doc ID [--seccion TEXTO]     un documento del cerebro o una sección (clave D06 / §2 / P01 / Parte 0, o título)
  loki_sql.py regla ID                     una regla (D01-D17, P01-P15, R-xxx de reglas.json) con estado y origen
  loki_sql.py reglas [--tipo dura|pendiente|json] [--estado VIGENTE|...]   lista de reglas
  loki_sql.py pendientes                   P01-P15 abiertos (lo que espera decisión de Nicolás)
  loki_sql.py intencion NOMBRE [--texto]   router: documentos, secciones y fuentes de un pedido (--texto imprime las secciones §)
  loki_sql.py bajar RAIZ                   solo baja (sin correr nada)
  loki_sql.py ficha [TEXTO]                ficha técnica corta + lista, stock y ventas (sin TEXTO: lista los modelos)
  loki_sql.py bitacora [--abiertos] [--cuit CUIT|NOMBRE] [--tipo T] [--buscar TXT] [-n N]   el hilo (lo último primero)
  loki_sql.py status-calcular [--hoy AAAA-MM-DD]   precalcula el status de todas las fichas vivas (al llegar CRM o R10)
  loki_sql.py status CUIT|NOMBRE [--salida DIR]   lee la fila precalculada → 4 PNG + página del panel lateral (exit 0 PASA · 1 FALLA/no está · 2 ambiguo)
  loki_sql.py status-vivo CUIT|NOMBRE [--salida DIR] [--hoy F] [--sin-png]   calcula una sola ficha en el momento (prueba)
  loki_sql.py status-url CUIT URL           guarda el enlace del Artifact del cliente (se republica en el mismo)
  loki_sql.py cliente CUIT|NOMBRE          vista 360: ficha, quién lo lleva, cotizaciones, ventas R10 y bitácora (ambiguo → pregunta)
  loki_sql.py calidad                      L8: oportunidades sin CUIT con venta/cotización (con CUIT candidato), cotizaciones
                                           abiertas sin fecha de revisión, CUIT duplicados → lista para corregir el CRM (con hacelo)
BITÁCORA (escribe sin hacelo: aprobado por Nicolás 17/11; una fila por hecho, corta):
  loki_sql.py anotar TIPO "TEMA" "TEXTO" [--cuit C] [--cuenta X] [--fuente F] [--chat N] [--cierra ID]
      TIPO = decision | hecho | pendiente (queda abierto) | error | aprendizaje | carga | cierre
  loki_sql.py cerrar ID "cómo se cerró" [--chat N]
CARGA (escribe en la base: solo con hacelo, salvo crm/continuidad que son parte del arranque y del cierre):
  loki_sql.py init
  loki_sql.py cargar-reporte CODIGO ARCHIVO.csv META.json   (CODIGO registrado en `reportes`; el CSV en UTF-8)
  loki_sql.py registrar-reporte META.json  alta o cambio de un código (codigo, descripcion, clase, privado, columnas)
  loki_sql.py bajar-reportes DIR           definiciones (Rnn.json) + último CSV de cada código + auditar.py, para auditar
  loki_sql.py reportes                     lista del registro con su última carga
  loki_sql.py cargar-recompra recompra.json META.json
  loki_sql.py cargar-crm CRM_DIR [--fecha AAAA-MM-DD]
  loki_sql.py cargar-memoria DIR            (DIR/cuentas/*.json, DIR/aprendizajes/*.json)
  loki_sql.py cargar-continuidad continuidad.json
  loki_sql.py cargar-cerebro DIR            (DIR/**/<id>.json; rearma las tablas derivadas del cerebro)
  loki_sql.py indexar-cerebro               rearma cerebro_seccion / cerebro_regla / cerebro_router desde la tabla cerebro
  loki_sql.py cargar-fichas fichas.json [FECHA]
  loki_sql.py cargar-script NOMBRE ARCHIVO VERSION
  loki_sql.py conocimiento-cargar ARCHIVO.json   {"k_decision": [{"id": .., campo: valor}], ...}: alta o cambio por id en las
                                           tablas k_* (solo columnas que existen; todo o nada). Con hacelo.
  loki_sql.py armar-clientes                rearma clientes / cliente_alias (derivadas; también corre en cada abrir)
  loki_sql.py armar-crm                     rearma las tablas ordenadas crm_* desde la copia `crm` (también corre en cada abrir)
  loki_sql.py migrar-continuidad            una vez: `abiertos` de la continuidad → bitácora (idempotente)
  loki_sql.py --autotest                    contra una base SQLite temporal (no toca Turso)
"""
import base64
import csv
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date

VERSION = "1.10.1"
TURSO = 'https://horizon-nicom90.aws-sa-east-1.turso.io'
ESQUEMA = 6
CRM_ARRANQUE = ('oportunidades', 'cotizaciones', 'muestras')
CRM_PRIVADO = {('config', 'datosBancarios')}          # D10: datos bancarios no se copian
TOPE_APERTURA = 3200

DDL = [
    "CREATE TABLE IF NOT EXISTS esquema (version INTEGER NOT NULL, creado TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cargas (fuente TEXT PRIMARY KEY, corte TEXT, cargado TEXT NOT NULL, filas INTEGER NOT NULL,"
    " sha256 TEXT, origen TEXT, meta TEXT)",
    "CREATE TABLE IF NOT EXISTS archivos (nombre TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, texto TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS scripts (nombre TEXT PRIMARY KEY, version TEXT NOT NULL, sha256 TEXT NOT NULL, texto TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cerebro (id TEXT PRIMARY KEY, titulo TEXT, version TEXT, fecha TEXT, sha256 TEXT NOT NULL,"
    " texto TEXT NOT NULL, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS continuidad (id TEXT PRIMARY KEY, actualizado TEXT, importante TEXT, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cuentas (id TEXT PRIMARY KEY, empresa TEXT, cuit TEXT, lleva TEXT, actualizado TEXT, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS aprendizajes (id TEXT PRIMARY KEY, tipo TEXT, estado TEXT, regla TEXT, fecha TEXT, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS ventas (n INTEGER PRIMARY KEY, fecha TEXT, comprobante TEXT, documento TEXT, cliente TEXT, cuit TEXT,"
    " producto TEXT, cod_producto TEXT, marca TEXT, familia TEXT, subfamilia TEXT, cantidad REAL, precio REAL, importe REAL,"
    " moneda TEXT, cotizacion REAL, total REAL, tasa_iva REAL, estado TEXT, empresa TEXT, condicion_pago TEXT, pte_dest REAL)",
    "CREATE INDEX IF NOT EXISTS ventas_cuit ON ventas (cuit)",
    "CREATE INDEX IF NOT EXISTS ventas_fecha ON ventas (fecha)",
    "CREATE TABLE IF NOT EXISTS stock (n INTEGER PRIMARY KEY, productoid TEXT, producto TEXT, familia TEXT, subfamilia TEXT,"
    " stock REAL, pedidos_sf REAL, facturas_sr REAL, en_transito REAL, total REAL, orden INTEGER, partida TEXT,"
    " fecha_pedidos TEXT, fecha_facturas TEXT, en_produccion REAL, fecha_produccion TEXT, fecha_transito TEXT)",
    "CREATE TABLE IF NOT EXISTS recompra (n INTEGER PRIMARY KEY, cliente TEXT, sku TEXT, ultimo_modelo TEXT, linea TEXT,"
    " compras INTEGER, primera TEXT, ultima TEXT, ciclo_dias REAL, proxima TEXT, estado TEXT, data TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS crm (coleccion TEXT NOT NULL, id TEXT NOT NULL, empresa TEXT, cuit TEXT, estado TEXT, numero TEXT,"
    " monto REAL, fecha TEXT, vence TEXT, proxima_fecha TEXT, actualizado TEXT, data TEXT NOT NULL, PRIMARY KEY (coleccion, id))",
    "CREATE INDEX IF NOT EXISTS crm_cuit ON crm (cuit)",
    "CREATE VIEW IF NOT EXISTS v_cotizaciones_abiertas AS SELECT id, numero, empresa, cuit, estado, monto, fecha, vence,"
    " json_extract(data,'$.revisionFecha') AS revision FROM crm WHERE coleccion='cotizaciones'"
    " AND estado IN ('enviada','espera_aprobacion') AND COALESCE(json_extract(data,'$.archivada'),0)=0",
    "CREATE VIEW IF NOT EXISTS v_ventas_cliente AS SELECT cuit, MAX(cliente) AS cliente, COUNT(DISTINCT comprobante) AS comprobantes,"
    " ROUND(SUM(importe),2) AS importe, MIN(fecha) AS primera, MAX(fecha) AS ultima FROM ventas"
    " WHERE empresa LIKE 'HORIZON TRADING%' GROUP BY cuit",
    "CREATE TABLE IF NOT EXISTS fichas (modelo TEXT PRIMARY KEY, familia TEXT, resumen TEXT, specs TEXT NOT NULL, venta TEXT,"
    " ojo TEXT, buscar TEXT, fuente TEXT, pdf TEXT, actualizado TEXT)",
    "CREATE TABLE IF NOT EXISTS cerebro_seccion (doc TEXT NOT NULL, orden INTEGER NOT NULL, nivel INTEGER NOT NULL, titulo TEXT,"
    " clave TEXT, texto TEXT NOT NULL, sha256 TEXT NOT NULL, doc_sha256 TEXT NOT NULL, PRIMARY KEY (doc, orden))",
    "CREATE INDEX IF NOT EXISTS cerebro_seccion_clave ON cerebro_seccion (doc, clave)",
    "CREATE TABLE IF NOT EXISTS cerebro_regla (id TEXT PRIMARY KEY, tipo TEXT NOT NULL, titulo TEXT, resumen TEXT, texto TEXT,"
    " estado TEXT, destino TEXT, etiqueta TEXT, origen TEXT, bloqueante INTEGER, orden INTEGER, doc_sha256 TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cerebro_router (intencion TEXT PRIMARY KEY, orden INTEGER, ejemplos TEXT, documentos TEXT, fuentes TEXT,"
    " doc_sha256 TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS cerebro_router_doc (intencion TEXT NOT NULL, n INTEGER NOT NULL, doc TEXT NOT NULL, seccion TEXT,"
    " PRIMARY KEY (intencion, n))",
    "CREATE VIEW IF NOT EXISTS v_pendientes AS SELECT id, titulo, texto, destino FROM cerebro_regla WHERE tipo='pendiente' ORDER BY orden",
    "CREATE VIEW IF NOT EXISTS v_fuentes AS SELECT fuente, corte, cargado, filas, CAST(julianday('now') - julianday(corte) AS INTEGER)"
    " AS edad_dias FROM cargas",
    "CREATE TABLE IF NOT EXISTS bitacora (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, chat INTEGER,"
    " tipo TEXT NOT NULL CHECK (tipo IN ('decision','hecho','pendiente','error','aprendizaje','carga','cierre')), cuit TEXT,"
    " cuenta TEXT, tema TEXT NOT NULL, texto TEXT NOT NULL, fuente TEXT,"
    " estado TEXT NOT NULL DEFAULT 'info' CHECK (estado IN ('abierto','cerrado','info')), cierra INTEGER REFERENCES bitacora (id),"
    " creado TEXT NOT NULL, origen TEXT)",
    "CREATE INDEX IF NOT EXISTS bitacora_fecha ON bitacora (fecha)",
    "CREATE INDEX IF NOT EXISTS bitacora_cuit ON bitacora (cuit)",
    "CREATE INDEX IF NOT EXISTS bitacora_estado ON bitacora (estado, tipo)",
    "CREATE TABLE IF NOT EXISTS clientes (cuit TEXT PRIMARY KEY, razon_social TEXT, crm_id TEXT, fichas INTEGER, lleva TEXT,"
    " otro_vendedor TEXT, no_prospectar INTEGER, archivada INTEGER, unificada_en TEXT, fuentes TEXT, armado TEXT)",
    "CREATE TABLE IF NOT EXISTS cliente_alias (alias_norm TEXT NOT NULL, alias TEXT, cuit TEXT NOT NULL, fuente TEXT,"
    " PRIMARY KEY (alias_norm, cuit, fuente))",
    "CREATE VIEW IF NOT EXISTS v_bitacora_abierta AS SELECT id, fecha, tipo, cuit, cuenta, tema, texto FROM bitacora"
    " WHERE estado='abierto' ORDER BY fecha DESC, id DESC",
    "CREATE VIEW IF NOT EXISTS v_seguimientos_hoy AS SELECT id, empresa, cuit, estado AS etapa, proxima_fecha, monto,"
    " json_extract(data,'$.proximaAccion') AS accion FROM crm WHERE coleccion='oportunidades'"
    " AND COALESCE(json_extract(data,'$.archivada'),0)=0 AND json_extract(data,'$.unificadaEn') IS NULL"
    " AND proxima_fecha <> '' AND substr(proxima_fecha,1,10) <= date('now','-3 hours') ORDER BY proxima_fecha",
    # R-VIVA: ninguna cotización "vence"; se revisa por revisionFecha → hz_resultado.fechaSeguimiento → vence
    "CREATE VIEW IF NOT EXISTS v_para_revisar AS SELECT id, numero, empresa, cuit, estado, monto, vence,"
    " COALESCE(NULLIF(json_extract(data,'$.revisionFecha'),''), NULLIF(json_extract(data,'$.hz_resultado.fechaSeguimiento'),''),"
    " NULLIF(vence,'')) AS revision FROM crm WHERE coleccion='cotizaciones' AND estado IN ('enviada','espera_aprobacion','espera_decision')"
    " AND COALESCE(json_extract(data,'$.archivada'),0)=0",
    "DROP VIEW IF EXISTS v_vencidas",
    "CREATE VIEW IF NOT EXISTS v_revisar_hoy AS SELECT * FROM v_para_revisar"
    " WHERE revision IS NULL OR substr(revision,1,10) <= date('now','-3 hours') ORDER BY revision",
    "CREATE VIEW IF NOT EXISTS v_cliente_360 AS SELECT c.*, o.estado AS etapa, o.proxima_fecha AS proxima,"
    " (SELECT COUNT(*) FROM v_cotizaciones_abiertas v WHERE v.cuit=c.cuit) AS cot_abiertas,"
    " (SELECT ROUND(SUM(monto),2) FROM v_cotizaciones_abiertas v WHERE v.cuit=c.cuit) AS cot_monto,"
    " w.comprobantes, w.importe AS ventas_importe, w.ultima AS ultima_compra,"
    " (SELECT COUNT(*) FROM bitacora b WHERE b.cuit=c.cuit AND b.estado='abierto') AS bitacora_abiertos"
    " FROM clientes c LEFT JOIN crm o ON o.coleccion='oportunidades' AND o.id=c.crm_id LEFT JOIN v_ventas_cliente w ON w.cuit=c.cuit",
    # 1.5.0: registro de reportes de Finnegans (definición + última carga). privado=1: trae costos (no sale de la base).
    "CREATE TABLE IF NOT EXISTS reportes (codigo TEXT PRIMARY KEY, descripcion TEXT, clase TEXT, privado INTEGER DEFAULT 0,"
    " columnas TEXT NOT NULL, actualizado TEXT, meta TEXT)",
    # 1.6.0: copia del CRM en tablas ordenadas. DERIVADAS de `crm` (se rearman en cada abrir con armar_crm; nunca a mano).
    "CREATE TABLE IF NOT EXISTS crm_oportunidad (id TEXT PRIMARY KEY, cuit TEXT, empresa TEXT, etapa TEXT, tipo TEXT, zona TEXT,"
    " prioridad TEXT, monto REAL, contacto TEXT, telefono TEXT, email TEXT, domicilio TEXT, transporte TEXT, cond_iva TEXT, pago TEXT,"
    " tecnologia TEXT, abonados TEXT, marca_olt TEXT, modelo_olt TEXT, olt_fh TEXT, usa_fh TEXT, cliente_horizon TEXT, productos TEXT,"
    " competidor TEXT, proxima_accion TEXT, proxima_fecha TEXT, ultimo_contacto TEXT, fecha_ganado TEXT, motivo_perdida TEXT,"
    " archivada INTEGER, unificada_en TEXT, no_prospectar INTEGER, otro_vendedor INTEGER, cuenta_compartida TEXT, notas TEXT,"
    " creado TEXT, actualizado TEXT, extra TEXT)",
    "CREATE INDEX IF NOT EXISTS crm_oportunidad_cuit ON crm_oportunidad (cuit)",
    "CREATE TABLE IF NOT EXISTS crm_contacto (oportunidad_id TEXT NOT NULL, n INTEGER NOT NULL, cuit TEXT, principal INTEGER,"
    " nombre TEXT, cargo TEXT, celular TEXT, mail TEXT, fuente TEXT, PRIMARY KEY (oportunidad_id, n))",
    "CREATE INDEX IF NOT EXISTS crm_contacto_cuit ON crm_contacto (cuit)",
    "CREATE TABLE IF NOT EXISTS crm_historial (oportunidad_id TEXT NOT NULL, n INTEGER NOT NULL, cuit TEXT, t TEXT, txt TEXT,"
    " PRIMARY KEY (oportunidad_id, n))",
    "CREATE INDEX IF NOT EXISTS crm_historial_cuit ON crm_historial (cuit, t)",
    "CREATE TABLE IF NOT EXISTS crm_cotizacion (id TEXT PRIMARY KEY, numero TEXT, oportunidad_id TEXT, cuit TEXT, cliente TEXT,"
    " estado TEXT, fecha TEXT, vence TEXT, revision TEXT, fecha_ganada TEXT, marca TEXT, familia TEXT, cond_pago TEXT, cond_iva TEXT,"
    " tc REAL, neto REAL, iva REAL, total REAL, archivada INTEGER, motivo_perdida TEXT, domicilio TEXT, pedido TEXT, despacho TEXT,"
    " despacho_at TEXT, entrega TEXT, entrega_at TEXT, pago TEXT, pago_at TEXT, factura TEXT, resultado TEXT, notas TEXT,"
    " actualizado TEXT)",
    "CREATE INDEX IF NOT EXISTS crm_cotizacion_cuit ON crm_cotizacion (cuit)",
    "CREATE TABLE IF NOT EXISTS crm_cotizacion_item (cotizacion_id TEXT NOT NULL, n INTEGER NOT NULL, cuit TEXT, codigo TEXT,"
    " articulo TEXT, descripcion TEXT, marca TEXT, cantidad REAL, precio REAL, iva REAL, neto REAL, PRIMARY KEY (cotizacion_id, n))",
    "CREATE TABLE IF NOT EXISTS crm_muestra (id TEXT PRIMARY KEY, oportunidad_id TEXT, cuit TEXT, productos TEXT, estado TEXT,"
    " envio TEXT, fecha_pedido TEXT, fecha_envio TEXT, devolver INTEGER, seguimiento TEXT, notas TEXT, actualizado TEXT)",
    # despacho: una fila por cuenta activa con lo que hay para despachar (transporte / domicilio) y su última cotización aceptada
    "DROP VIEW IF EXISTS v_despacho",
    "CREATE VIEW v_despacho AS SELECT o.id, o.cuit, o.empresa, o.etapa, NULLIF(TRIM(o.transporte),'') AS transporte,"
    " NULLIF(TRIM(o.domicilio),'') AS domicilio, (SELECT c.numero FROM crm_cotizacion c WHERE c.oportunidad_id=o.id AND c.estado='aceptada'"
    " ORDER BY COALESCE(c.fecha_ganada,c.fecha) DESC LIMIT 1) AS ultima_aceptada, o.actualizado FROM crm_oportunidad o"
    " WHERE COALESCE(o.archivada,0)=0 AND o.unificada_en IS NULL",
    "DROP VIEW IF EXISTS v_ganadas_sin_despacho",
    "CREATE VIEW v_ganadas_sin_despacho AS SELECT c.numero, c.cliente, c.cuit, COALESCE(c.fecha_ganada,c.fecha) AS ganada, c.despacho,"
    " c.entrega, o.id AS oportunidad_id, CASE WHEN NULLIF(TRIM(o.transporte),'') IS NULL THEN 'falta transporte' ELSE '' END"
    " || CASE WHEN NULLIF(TRIM(o.transporte),'') IS NULL AND NULLIF(TRIM(COALESCE(o.domicilio,c.domicilio)),'') IS NULL THEN ' · ' ELSE '' END"
    " || CASE WHEN NULLIF(TRIM(COALESCE(o.domicilio,c.domicilio)),'') IS NULL THEN 'falta domicilio' ELSE '' END AS falta"
    " FROM crm_cotizacion c LEFT JOIN crm_oportunidad o ON o.id=c.oportunidad_id WHERE c.estado='aceptada' AND COALESCE(c.archivada,0)=0"
    " AND COALESCE(c.entrega,'') NOT IN ('confirmado','entregado') AND (NULLIF(TRIM(o.transporte),'') IS NULL"
    " OR NULLIF(TRIM(COALESCE(o.domicilio,c.domicilio)),'') IS NULL) ORDER BY ganada DESC",
]
BAJAR_ARCHIVOS = ('R10.csv', 'R8.csv', 'recompra.json')
BAJAR_SCRIPTS = ('loki.py', 'memoria_check.py', 'motor.py', 'bitacora2.py')    # 1.8.0: motor.py (#65) · 1.9.1: bitacora2.py (chequear al abrir)
TABLA_DE = {'R10': 'ventas', 'R8': 'stock', 'recompra': 'recompra', 'cuentas': 'cuentas', 'aprendizajes': 'aprendizajes'}


# ------------------------------------------------------------------ conexión
class Turso:
    def __init__(self, url=TURSO):
        self.url, self.baton = url, None

    def _post(self, reqs):
        body = {'requests': reqs}
        if self.baton:
            body['baton'] = self.baton
        rq = urllib.request.Request(self.url + '/v2/pipeline', data=json.dumps(body).encode(),
                                    headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(rq, timeout=120) as r:
            out = json.load(r)
        self.baton = out.get('baton')
        if out.get('base_url'):
            self.url = out['base_url'].rstrip('/')
        return out['results']

    @staticmethod
    def _arg(v):
        if v is None:
            return {'type': 'null'}
        if isinstance(v, bool):
            return {'type': 'integer', 'value': str(int(v))}
        if isinstance(v, int):
            return {'type': 'integer', 'value': str(v)}
        if isinstance(v, float):
            return {'type': 'float', 'value': v}
        return {'type': 'text', 'value': str(v)}

    @staticmethod
    def _val(c):
        t = c.get('type')
        if t == 'null':
            return None
        if t == 'integer':
            return int(c['value'])
        if t == 'float':
            return float(c['value'])
        if t == 'blob':
            return base64.b64decode(c.get('base64', ''))
        return c.get('value')

    def run(self, stmts, max_bytes=3_000_000):
        """stmts = [(sql, args)]; devuelve [(columnas, filas)]. Corta en pedidos de ~3 MB (misma sesión, con baton)."""
        res, lote, tam = [], [], 0
        def mandar(l):
            if not l:
                return
            out = self._post([{'type': 'execute', 'stmt': {'sql': s, 'args': [self._arg(a) for a in args]}} for s, args in l])
            for r in out:
                if r['type'] == 'error':
                    raise RuntimeError('SQL: ' + r['error'].get('message', str(r['error'])))
                x = r['response']['result']
                res.append(([c['name'] for c in x['cols']], [[self._val(c) for c in fila] for fila in x['rows']]))
        for s, args in stmts:
            n = len(s) + sum(len(str(a)) for a in args)
            if lote and tam + n > max_bytes:
                mandar(lote)
                lote, tam = [], 0
            lote.append((s, args))
            tam += n
        mandar(lote)
        return res

    def close(self):
        if self.baton:
            try:
                self._post([{'type': 'close'}])
            except Exception:  # noqa: BLE001
                pass
            self.baton = None


class Local:
    def __init__(self, ruta):
        self.c = sqlite3.connect(ruta, isolation_level=None)

    def run(self, stmts, **_):
        res = []
        for s, args in stmts:
            cur = self.c.execute(s, args)
            res.append(([d[0] for d in cur.description] if cur.description else [], [list(r) for r in cur.fetchall()]))
        return res

    def close(self):
        self.c.close()


def conectar():
    ruta = os.environ.get('LOKI_SQL_LOCAL')          # solo para pruebas
    return Local(ruta) if ruta else Turso()


def q(db, sql, *args):
    cols, filas = db.run([(sql, list(args))])[0]
    return [dict(zip(cols, f)) for f in filas]


def qs(db, consultas):
    """Varias lecturas en UN viaje a Turso (1.8.0). consultas = [sql | (sql, [args])] → [[dict, ...], ...] en el mismo orden."""
    st = [(c, []) if isinstance(c, str) else (c[0], list(c[1])) for c in consultas]
    return [[dict(zip(cols, f)) for f in filas] for cols, filas in db.run(st)]


def conocimiento_cargar(db, cambios):
    """1.10.0: alta o cambio por id en tablas k_*. cambios = {tabla: [fila, ...]}; cada fila trae id y solo columnas existentes."""
    if not isinstance(cambios, dict) or not cambios:
        raise ValueError('conocimiento-cargar: se espera {tabla: [filas]}')
    st, n = [], {}
    for t, filas in cambios.items():
        if not re.match(r'^k_[a-z_]+$', t):
            raise ValueError(f'conocimiento-cargar: {t} no es una tabla k_*')
        cols = [r['name'] for r in q(db, f'PRAGMA table_info({t})')]
        if not cols:
            raise ValueError(f'conocimiento-cargar: la tabla {t} no existe')
        ids = {r['id'] for r in q(db, f'SELECT id FROM {t}')}
        for f in filas:
            if not isinstance(f, dict) or not f.get('id'):
                raise ValueError(f'conocimiento-cargar: {t}: fila sin id')
            otras = sorted(set(f) - set(cols))
            if otras:
                raise ValueError(f"conocimiento-cargar: {t}/{f['id']}: columnas que no existen: {', '.join(otras)}")
            ks = [k for k in f if k != 'id']
            if f['id'] in ids:
                if ks:
                    st.append((f"UPDATE {t} SET {', '.join(k + '=?' for k in ks)} WHERE id=?", [f[k] for k in ks] + [f['id']]))
            else:
                st.append((f"INSERT INTO {t} ({', '.join(['id'] + ks)}) VALUES ({', '.join('?' * (len(ks) + 1))})", [f['id']] + [f[k] for k in ks]))
            n[t] = n.get(t, 0) + 1
    transaccion(db, st)
    return n


def transaccion(db, stmts):
    """Todo o nada: si una sentencia falla no se manda COMMIT, se hace ROLLBACK y se relanza el error."""
    try:
        db.run([('BEGIN', [])] + stmts)
    except Exception:
        try:
            db.run([('ROLLBACK', [])])
        finally:
            raise
    db.run([('COMMIT', [])])


# ------------------------------------------------------------------ utilidades
sha = lambda b: hashlib.sha256(b if isinstance(b, bytes) else b.encode('utf-8')).hexdigest()
ahora = lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def leer_json(p):
    with open(p, encoding='utf-8') as f:
        d = json.load(f)
    if isinstance(d, dict) and set(d) <= {'id', 'data', 'version', 'collection'} and isinstance(d.get('data'), dict):
        return d['data']
    return d


def num(x):
    try:
        return float(str(x).replace(',', '.')) if str(x).strip() != '' else None
    except ValueError:
        return None


def jdump(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True)


STOCK_NUEVAS = (('orden', 'INTEGER'), ('partida', 'TEXT'), ('fecha_pedidos', 'TEXT'), ('fecha_facturas', 'TEXT'),
                ('en_produccion', 'REAL'), ('fecha_produccion', 'TEXT'), ('fecha_transito', 'TEXT'))


def init(db):
    db.run([(s, []) for s in DDL])
    hay = {r['name'] for r in q(db, 'PRAGMA table_info(stock)')}          # esquema 6: migra una base vieja sin perder filas
    falta = [(c, t) for c, t in STOCK_NUEVAS if c not in hay]
    if falta:
        db.run([(f'ALTER TABLE stock ADD COLUMN {c} {t}', []) for c, t in falta])
    if not q(db, 'SELECT version FROM esquema'):
        db.run([('INSERT INTO esquema VALUES (?, ?)', [ESQUEMA, ahora()])])
    elif q(db, 'SELECT MAX(version) v FROM esquema')[0]['v'] < ESQUEMA:
        db.run([('UPDATE esquema SET version=?', [ESQUEMA])])


def carga_stmt(fuente, corte, filas, sha256, origen, meta):
    return ('INSERT OR REPLACE INTO cargas VALUES (?,?,?,?,?,?,?)', [fuente, corte, ahora(), filas, sha256, origen, jdump(meta)])


# ------------------------------------------------------------------ cargas
def cargar_reporte(db, codigo, archivo, meta_p):
    texto = open(archivo, encoding='utf-8').read()
    meta = leer_json(meta_p)
    if meta.get('sha256') and meta['sha256'] != sha(texto):
        raise ValueError(f'{codigo}: sha256 del archivo ≠ registro ({sha(texto)[:12]} vs {meta["sha256"][:12]})')
    filas = list(csv.reader(io.StringIO(texto), delimiter=';'))
    h, filas = filas[0], [f for f in filas[1:] if f]
    ix = {}
    for i, c in enumerate(h):
        ix.setdefault(c, i)
    g = lambda f, c: f[ix[c]] if c in ix and ix[c] < len(f) else None
    if codigo == 'R10':
        st = [('DELETE FROM ventas', [])] + [(
            'INSERT INTO ventas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            [n, g(f, 'Fecha'), g(f, 'Comprobante'), g(f, 'Documento'), g(f, 'Cliente'), g(f, 'Nro de identificación'),
             g(f, 'Producto'), g(f, 'Cod. Producto'), g(f, 'Marca'), g(f, 'Familia'), g(f, 'SubFamilia'), num(g(f, 'Cantidad')),
             num(g(f, 'Precio')), num(g(f, 'Importe')), g(f, 'Moneda'), num(g(f, 'Cotización')), num(g(f, 'Total')),
             num(g(f, 'Tasa impositiva')), g(f, 'Estado'), g(f, 'Empresa'), g(f, 'Condición pago'), num(g(f, 'Pte Dest.'))])
            for n, f in enumerate(filas, 1)]
    elif codigo == 'R8':
        init(db)                                   # asegura las columnas del esquema 6
        ent = lambda v: int(num(v)) if num(v) is not None else None
        st = [('DELETE FROM stock', [])] + [(
            'INSERT INTO stock (n, productoid, producto, familia, subfamilia, stock, pedidos_sf, facturas_sr, en_transito, total,'
            ' orden, partida, fecha_pedidos, fecha_facturas, en_produccion, fecha_produccion, fecha_transito)'
            ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            [n, g(f, 'Productoid'), g(f, 'Producto'), g(f, 'Familia'), g(f, 'Subfamilia'), num(g(f, 'Stock')),
             num(g(f, 'Pedidos de venta s/f')), num(g(f, 'Facturas de venta s/r')), num(g(f, 'En tránsito')), num(g(f, 'Total')),
             ent(g(f, 'Orden')), g(f, 'Stock partida') or None, g(f, 'Fecha pedidos de venta s/f') or None,
             g(f, 'Fecha facturas de venta s/r') or None, num(g(f, 'En producción')), g(f, 'Fecha en producción') or None,
             g(f, 'Fecha en tránsito') or None])
            for n, f in enumerate(filas, 1)]
    else:
        reg = q(db, 'SELECT columnas FROM reportes WHERE codigo=?', codigo)
        if not reg:
            raise ValueError('código de reporte desconocido (registrarlo antes): ' + codigo)
        esperadas = {c.strip().lower() for c in json.loads(reg[0]['columnas'])}
        faltan = esperadas - {c.strip().lower() for c in h}
        if faltan:
            raise ValueError(f'{codigo}: faltan columnas del registro: ' + ', '.join(sorted(faltan)[:5]))
        st = []
    nombre = codigo + '.csv'
    st.append(('INSERT OR REPLACE INTO archivos VALUES (?,?,?,?)', [nombre, sha(texto), len(texto.encode()), texto]))
    st.append(carga_stmt(codigo, meta.get('corte'), len(filas), sha(texto), meta.get('archivo'), meta))
    st.append(('UPDATE reportes SET meta=?, actualizado=? WHERE codigo=?', [jdump(meta), ahora(), codigo]))
    transaccion(db, st)
    return len(filas)


def registrar_reporte(db, meta_p):
    init(db)
    m = leer_json(meta_p)
    m = m.get('data', m)
    if not re.match(r'^R\d+$', m.get('codigo') or '') or not m.get('columnas'):
        raise ValueError('registro de reporte: hace falta codigo (Rnn) y columnas')
    transaccion(db, [('INSERT INTO reportes (codigo, descripcion, clase, privado, columnas, actualizado, meta) VALUES (?,?,?,?,?,?,?)'
                      ' ON CONFLICT(codigo) DO UPDATE SET descripcion=excluded.descripcion, clase=excluded.clase,'
                      ' privado=excluded.privado, columnas=excluded.columnas',
                      [m['codigo'], m.get('descripcion'), m.get('clase'), 1 if m.get('privado') else 0,
                       jdump(m['columnas']), ahora(), jdump({k: v for k, v in m.items() if k not in ('columnas',)})])])
    return m['codigo']


def bajar_reportes(db, d):
    """Deja en d lo que pide auditar.py: Rnn.json (codigo + columnas) y el último Rnn.csv cargado, más auditar.py."""
    os.makedirs(d, exist_ok=True)
    n = 0
    for r in q(db, 'SELECT codigo, descripcion, clase, privado, columnas, meta FROM reportes'):
        m = json.loads(r['meta'] or '{}')
        m.update(codigo=r['codigo'], descripcion=r['descripcion'], clase=r['clase'], privado=bool(r['privado']),
                 columnas=json.loads(r['columnas']))
        json.dump(m, open(os.path.join(d, r['codigo'] + '.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        n += 1
    fallas = []
    for a in q(db, "SELECT nombre, sha256, texto FROM archivos WHERE nombre GLOB 'R[0-9]*.csv'"):
        if sha(a['texto']) != a['sha256']:
            fallas.append(f"L2 archivo {a['nombre']}: sha256 no coincide")
        open(os.path.join(d, a['nombre']), 'w', encoding='utf-8', newline='').write(a['texto'])
    for s in q(db, "SELECT nombre, sha256, texto FROM scripts WHERE nombre='auditar.py'"):
        if sha(s['texto']) != s['sha256']:
            fallas.append('L2 script auditar.py: sha256 no coincide')
        open(os.path.join(d, 'auditar.py'), 'w', encoding='utf-8').write(s['texto'])
    return n, fallas


def reportes_lista(db):
    cg = {c['fuente']: c for c in q(db, "SELECT fuente, corte, filas FROM cargas WHERE fuente GLOB 'R[0-9]*'")}
    out = []
    for r in q(db, 'SELECT codigo, descripcion, clase, privado FROM reportes'):
        c = cg.get(r['codigo'])
        out.append((int(r['codigo'][1:]), f"{r['codigo']:<4} {r['clase'] or '-':<11} {'PRIVADO ' if r['privado'] else ''}"
                    f"{(r['descripcion'] or '')[:70]} · " + (f"corte {c['corte']} · {c['filas']} filas" if c else 'sin cargar')))
    return '\n'.join(x for _, x in sorted(out)) or 'registro vacío'


def cargar_recompra(db, archivo, meta_p):
    texto = open(archivo, encoding='utf-8').read()
    lista = json.loads(texto)
    lista = lista if isinstance(lista, list) else next(v for v in lista.values() if isinstance(v, list))
    meta = leer_json(meta_p)
    st = [('DELETE FROM recompra', [])] + [(
        'INSERT INTO recompra VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
        [n, x.get('cliente'), x.get('sku'), x.get('ultimo_modelo'), x.get('linea'), x.get('compras'),
         str(x.get('primera') or '')[:10], str(x.get('ultima') or '')[:10], x.get('ciclo_dias'), str(x.get('proxima') or '')[:10] or None,
         x.get('estado'), jdump(x)]) for n, x in enumerate(lista, 1)]
    st.append(('INSERT OR REPLACE INTO archivos VALUES (?,?,?,?)', ['recompra.json', sha(texto), len(texto.encode()), texto]))
    st.append(carga_stmt('recompra', meta.get('corte') or meta.get('actualizado'), len(lista), sha(texto), 'recompra.py ' + str(meta.get('version')), meta))
    transaccion(db, st)
    return len(lista)


def campos_crm(col, d):
    emp = d.get('empresa') or d.get('cliente')
    est = d.get('etapa') if col == 'oportunidades' else d.get('estado')
    monto = d.get('monto') if col == 'oportunidades' else d.get('total')
    return [emp, d.get('cuit'), est, d.get('numero'), monto if isinstance(monto, (int, float)) else num(monto),
            d.get('fecha') or d.get('creado'), d.get('vence'), d.get('proximaFecha'), d.get('actualizado')]


def cargar_crm(db, crm_dir, fecha, incremental=False):
    """Completa: reemplaza cada colección presente. Incremental: solo agrega/actualiza los documentos bajados
    (los que cambiaron desde la última copia); las colecciones del arranque quedan con corte = fecha."""
    cols = sorted(c for c in os.listdir(crm_dir) if os.path.isdir(os.path.join(crm_dir, c))) if os.path.isdir(crm_dir) else []
    if not incremental and not {'oportunidades', 'cotizaciones'} <= set(cols):
        raise ValueError('cargar-crm: faltan oportunidades o cotizaciones en ' + crm_dir)
    cols = sorted(set(cols) | set(CRM_ARRANQUE))   # una colección vacía (ej. muestras) no deja carpeta
    prev = {c['fuente']: c for c in q(db, "SELECT fuente, meta FROM cargas WHERE fuente LIKE 'crm:%'")}
    st, conteo = [], {}
    for c in cols:
        if not incremental:
            st.append(('DELETE FROM crm WHERE coleccion=?', [c]))
        n = 0
        if not os.path.isdir(os.path.join(crm_dir, c)):
            os.makedirs(os.path.join(crm_dir, c), exist_ok=True)
        for f in sorted(os.listdir(os.path.join(crm_dir, c))):  # solo *.json (ArtifactData deja .x.json,by-others ocultos)
            if not f.endswith('.json') or (c, f[:-5]) in CRM_PRIVADO:
                continue
            d = leer_json(os.path.join(crm_dir, c, f))
            if not isinstance(d, dict):
                raise ValueError(f'{c}/{f}: no es objeto')
            st.append(('INSERT OR REPLACE INTO crm VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', [c, f[:-5]] + campos_crm(c, d) + [jdump(d)]))
            n += 1
        conteo[c] = n
        completa = fecha if not incremental else json.loads((prev.get('crm:' + c) or {}).get('meta') or '{}').get('completa')
        st.append(carga_stmt('crm:' + c, fecha, n, None, 'CRM FLgX ' + ('incremental' if incremental else 'completa'),
                             {'coleccion': c, 'completa': completa, 'bajados': n}))
        st.append(('UPDATE cargas SET filas=(SELECT COUNT(*) FROM crm WHERE coleccion=?) WHERE fuente=?', [c, 'crm:' + c]))
    transaccion(db, st)
    return conteo


def crm_desde(db, hoy):
    """Qué traer del CRM: 'COMPLETA' (sin copia o copia completa de más de 7 días) o 'DESDE AAAA-MM-DD'."""
    cg = {c['fuente']: c for c in q(db, "SELECT fuente, corte, meta FROM cargas WHERE fuente LIKE 'crm:%'")}
    fechas, completas = [], []
    for c in CRM_ARRANQUE:
        if 'crm:' + c not in cg:
            return 'COMPLETA'
        fechas.append(cg['crm:' + c]['corte'])
        completas.append(json.loads(cg['crm:' + c]['meta'] or '{}').get('completa'))
    if any(not x or (hoy - date.fromisoformat(x[:10])).days > 7 for x in completas):
        return 'COMPLETA'
    return 'DESDE ' + min(fechas)[:10]


def cargar_memoria(db, d):
    st, n = [], {}
    for col in ('cuentas', 'aprendizajes'):
        p = os.path.join(d, col)
        if not os.path.isdir(p):
            continue
        st.append((f'DELETE FROM {col}', []))
        docs = [(f[:-5], leer_json(os.path.join(p, f))) for f in sorted(os.listdir(p)) if f.endswith('.json')]
        for i, x in docs:
            if col == 'cuentas':
                st.append(('INSERT INTO cuentas VALUES (?,?,?,?,?,?)', [i, x.get('empresa'), x.get('cuit'), x.get('lleva'), x.get('actualizado'), jdump(x)]))
            else:
                st.append(('INSERT INTO aprendizajes VALUES (?,?,?,?,?,?)', [i, x.get('tipo'), x.get('estado'), x.get('regla'), x.get('fecha'), jdump(x)]))
        n[col] = len(docs)
        st.append(carga_stmt(col, max([str(x.get('actualizado') or x.get('fecha') or '') for _, x in docs] or ['']) or None,
                             len(docs), None, 'Data Center memoria', {}))
    transaccion(db, st)
    return n


def cargar_continuidad(db, p):
    d = leer_json(p)
    imp = (d.get('importante') or '').strip()
    if not imp or len(imp.encode()) >= 1000 or not re.match(r'^\d{4}-\d{2}-\d{2}$', str(d.get('actualizado'))):
        raise ValueError('continuidad: importante (no vacío, < 1000 bytes) y actualizado AAAA-MM-DD son obligatorios')
    transaccion(db, [('INSERT OR REPLACE INTO continuidad VALUES (?,?,?,?)', ['actual', d.get('actualizado'), d.get('importante'), jdump(d)]),
                     ('INSERT OR REPLACE INTO continuidad VALUES (?,?,?,?)', ['h:' + ahora(), d.get('actualizado'), d.get('importante'), jdump(d)]),
                     carga_stmt('continuidad', d.get('actualizado'), 1, sha(d.get('importante') or ''), 'cierre de chat', {})])


def cargar_cerebro(db, d):
    init(db)
    st, n = [], 0
    for r, _x, fs in os.walk(d):
        for f in sorted(fs):
            if not f.endswith('.json'):
                continue
            x = leer_json(os.path.join(r, f))
            if not isinstance(x, dict) or 'texto' not in x or 'id' not in x:
                continue
            if x.get('sha256') and x['sha256'] != sha(x['texto']):
                raise ValueError(f"cerebro {x['id']}: sha256 no coincide")
            st.append(('INSERT OR REPLACE INTO cerebro VALUES (?,?,?,?,?,?,?)',
                       [x['id'], x.get('titulo'), x.get('version'), x.get('fecha'), sha(x['texto']), x['texto'],
                        jdump({k: v for k, v in x.items() if k != 'texto'})]))
            n += 1
    st.append(carga_stmt('cerebro', max(r[1][3] or '' for r in st) if st else None, n, None, 'cerebro', {}))
    st.append(("UPDATE cargas SET filas=(SELECT COUNT(*) FROM cerebro), corte=(SELECT MAX(fecha) FROM cerebro) WHERE fuente='cerebro'", []))
    transaccion(db, st)
    try:
        c = indexar(db)
        for a_ in c.get('avisos', []):
            print('AVISO índice:', a_, file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f'AVISO cerebro cargado; falló el índice ({str(e)[:80]}): correr indexar-cerebro', file=sys.stderr)
    return n


def cargar_fichas(db, archivo, fecha):
    """JSON {fuentes: {F1: {pdf, sha256, pm_asset}}, fichas: [{modelo, familia, resumen, specs[[dato, valor]], venta, ojo, buscar, fuente}]}."""
    d = leer_json(archivo)
    fu, st = d.get('fuentes') or {}, []
    for f in d['fichas']:
        if not f.get('modelo') or not isinstance(f.get('specs'), list) or not f['specs']:
            raise ValueError(f"ficha sin modelo o sin specs: {f.get('modelo')}")
        src = fu.get(f.get('fuente')) or {}
        pdf = src.get('pdf', '') + (f" · PM /_blob/{src['pm_asset']}" if src.get('pm_asset') else '')
        st.append(('INSERT OR REPLACE INTO fichas VALUES (?,?,?,?,?,?,?,?,?,?)',
                   [f['modelo'], f.get('familia'), f.get('resumen'), jdump(f['specs']), f.get('venta'), f.get('ojo'), f.get('buscar'),
                    jdump(src), pdf, fecha]))
    st.append(carga_stmt('fichas', fecha, len(d['fichas']), sha(open(archivo, encoding='utf-8').read()), 'fichas técnicas', {}))
    st.append(("UPDATE cargas SET filas=(SELECT COUNT(*) FROM fichas) WHERE fuente='fichas'", []))
    transaccion(db, st)
    return len(d['fichas'])


def ficha(db, texto=None):
    """Tarjeta corta por modelo: datos de la ficha + lista, stock y ventas de Horizon (en vivo de la base)."""
    if not texto:
        rs = q(db, 'SELECT familia, GROUP_CONCAT(modelo, ' + "' · '" + ') m FROM fichas GROUP BY familia ORDER BY familia')
        return '\n'.join(f"{r['familia']}: {r['m']}" for r in rs) or 'sin fichas'
    t = '%' + texto.strip().replace(' ', '%') + '%'
    rs = q(db, 'SELECT * FROM fichas WHERE modelo LIKE ? OR familia LIKE ? ORDER BY modelo', t, t)
    if not rs:
        return f'no hay ficha para "{texto}". Modelos: ' + ' · '.join(r['modelo'] for r in q(db, 'SELECT modelo FROM fichas ORDER BY modelo'))
    out = []
    for r in rs[:6]:
        out.append(f"■ {r['modelo']} · {r['familia']}\n{r['resumen']}")
        out += [f'· {a}: {b}' for a, b in json.loads(r['specs'])]
        if r['venta']:
            out.append('Venta: ' + r['venta'])
        if r['ojo']:
            out.append('OJO: ' + r['ojo'])
        b = r['buscar']
        if b:
            li = q(db, "SELECT json_extract(data,'$.nombre') n FROM crm WHERE coleccion='lista' AND json_extract(data,'$.nombre') LIKE ?", b)
            sk = q(db, 'SELECT ROUND(SUM(stock)) s FROM stock WHERE producto LIKE ?', b)[0]['s']
            ve = q(db, "SELECT ROUND(SUM(cantidad)) c, COUNT(DISTINCT cuit) k, MAX(fecha) u FROM ventas WHERE producto LIKE ? AND empresa LIKE 'HORIZON%'", b)[0]
            cs = {c['fuente']: c['corte'] for c in q(db, "SELECT fuente, corte FROM cargas WHERE fuente IN ('R8','R10')")}
            out.append('Horizon: ' + ('en lista (' + ' / '.join(x['n'] for x in li[:3]) + ')' if li else 'NO está en la lista de precios (precio a confirmar)')
                       + f" · stock {int(sk) if sk else 0} (R8 {str(cs.get('R8'))[:10]}, a confirmar con JP)"
                       + (f" · vendidas {int(ve['c'])} a {ve['k']} cliente(s), última {ve['u']}" if ve['c'] else ' · sin ventas en R10'))
        out.append('Fuente: ' + (r['pdf'] or '-') + '\n')
    if len(rs) > 6:
        out.append(f'(+{len(rs) - 6} más: afinar la búsqueda)')
    return '\n'.join(out).rstrip()


def cargar_script(db, nombre, archivo, version):
    t = open(archivo, encoding='utf-8').read()
    transaccion(db, [('INSERT OR REPLACE INTO scripts VALUES (?,?,?,?)', [nombre, version, sha(t), t])])
    return sha(t)


# ------------------------------------------------------------------ bajar
def bajar(db, raiz):
    datos, scr = os.path.join(raiz, 'DATOS'), os.path.join(raiz, 'SCRIPTS')
    for p in (datos, scr):
        os.makedirs(p, exist_ok=True)
    fallas = []
    # 1.8.0: todo lo que baja sale en un solo viaje a Turso (antes 7)
    r_scr, r_arc, r_cg, r_crm, r_con, r_cue, r_apr = qs(db, [
        'SELECT nombre, sha256, texto FROM scripts WHERE nombre IN (%s)' % ','.join(f"'{x}'" for x in BAJAR_SCRIPTS),
        ('SELECT nombre, sha256, texto FROM archivos WHERE nombre IN (%s)' % ','.join('?' * len(BAJAR_ARCHIVOS)), BAJAR_ARCHIVOS),
        'SELECT * FROM cargas',
        'SELECT coleccion, id, data FROM crm ORDER BY coleccion, id',
        "SELECT data FROM continuidad WHERE id='actual'",
        'SELECT id, data FROM cuentas',
        'SELECT id, data FROM aprendizajes'])
    for s in r_scr:
        if sha(s['texto']) != s['sha256']:
            fallas.append(f"L2 script {s['nombre']}: sha256 no coincide")
        open(os.path.join(scr, s['nombre']), 'w', encoding='utf-8').write(s['texto'])
    if os.path.abspath(__file__) != os.path.abspath(os.path.join(scr, 'loki_sql.py')):
        shutil.copyfile(os.path.abspath(__file__), os.path.join(scr, 'loki_sql.py'))   # motor.py lo importa de su misma carpeta
    for a in r_arc:
        if sha(a['texto']) != a['sha256']:
            fallas.append(f"L2 archivo {a['nombre']}: sha256 no coincide")
        open(os.path.join(datos, a['nombre']), 'w', encoding='utf-8', newline='').write(a['texto'])
    cg = {c['fuente']: c for c in r_cg}
    for f, n in (('R10', 'R10_meta.json'), ('recompra', 'recompra_meta.json'), ('R8', 'R8_meta.json')):
        if f in cg:
            json.dump(json.loads(cg[f]['meta'] or '{}'), open(os.path.join(datos, n), 'w', encoding='utf-8'), ensure_ascii=False)
    colecciones, corte_crm = {}, None
    for r in r_crm:
        colecciones.setdefault(r['coleccion'], {})[r['id']] = json.loads(r['data'])
    cortes = [c['corte'] for k, c in cg.items() if k.startswith('crm:') and c['corte']]
    corte_crm = min(cortes) if cortes else None
    resp = dict(format='horizon-crm', version=3, exportedAt=f'{corte_crm}T00:00:00.000Z', origen='loki_sql', collections=colecciones)
    json.dump(resp, open(os.path.join(datos, 'respaldo.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(dict(exportadoEn=f'{corte_crm}T00:00:00.000Z', colecciones={k: len(v) for k, v in colecciones.items()}, origen='loki_sql'),
              open(os.path.join(datos, 'respaldo_meta.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    con = r_con
    json.dump(json.loads(con[0]['data']) if con else {}, open(os.path.join(datos, 'continuidad.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    for col, filas in (('cuentas', r_cue), ('aprendizajes', r_apr)):
        p = os.path.join(datos, col)
        os.makedirs(p, exist_ok=True)
        for r in filas:
            open(os.path.join(p, r['id'] + '.json'), 'w', encoding='utf-8').write(r['data'])
    return fallas, cg


# ------------------------------------------------------------------ controles y apertura
def controles(db, cg, hoy):
    falla, aviso = [], []
    tabla_conteo = {'R10': 'SELECT COUNT(*) n FROM ventas', 'R8': 'SELECT COUNT(*) n FROM stock', 'recompra': 'SELECT COUNT(*) n FROM recompra',
                    'cuentas': 'SELECT COUNT(*) n FROM cuentas', 'aprendizajes': 'SELECT COUNT(*) n FROM aprendizajes'}
    for f in ('R10', 'R8', 'recompra', 'crm:oportunidades', 'crm:cotizaciones', 'continuidad'):
        if f not in cg:
            falla.append(f'L1 falta la fuente {f}')
    stm = [(tabla_conteo[f], []) for f in tabla_conteo if f in cg]
    crm = [k for k in cg if k.startswith('crm:')]
    stm += [('SELECT COUNT(*) n FROM crm WHERE coleccion=?', [k[4:]]) for k in crm]
    # 1.8.0: continuidad e índice del cerebro van en el mismo viaje que los conteos
    stm += [("SELECT actualizado, importante FROM continuidad WHERE id='actual'", []), (SQL_INDICE, [])]
    try:
        res = db.run(stm)
        r_con, r_ind = res[-2], res[-1]
        res = res[:-2]
    except Exception:  # noqa: BLE001  base sin tablas del cerebro: conteos solos y el aviso L7 de siempre
        res = db.run(stm[:-1])
        r_con, r_ind = res[-1], None
        res = res[:-1]
    for (f, r) in zip([f for f in tabla_conteo if f in cg] + crm, res):
        if r[1][0][0] != cg[f]['filas']:
            falla.append(f"L3 {f}: {r[1][0][0]} filas en la base ≠ {cg[f]['filas']} registradas")
    edad = lambda c: (hoy - date.fromisoformat(str(c)[:10])).days if c else 999
    for f in ('R10', 'R8', 'recompra'):
        if f in cg:
            e = edad(cg[f]['corte'])
            (falla if e > 14 else aviso if e > 3 else []).append(f'L4 {f} corte {str(cg[f]["corte"])[:10]} ({e} días)')
    for f in crm:
        if f[4:] in CRM_ARRANQUE and edad(cg[f]['corte']) > 1:
            aviso.append(f'L4 {f} copiado el {cg[f]["corte"]}: copiar el CRM de nuevo')
        comp = json.loads(cg[f].get('meta') or '{}').get('completa') if f[4:] in CRM_ARRANQUE else 'x'
        if f[4:] in CRM_ARRANQUE and (not comp or edad(comp) > 7):
            aviso.append(f'L4 {f}: copia completa de más de 7 días (próximo arranque: COMPLETA)')
    if 'R10' in cg and 'recompra' in cg and str(cg['R10']['corte'])[:10] != str(cg['recompra']['corte'])[:10]:
        aviso.append('L6 recompra y R10 con cortes distintos')
    formato = []
    c = [dict(zip(r_con[0], f)) for f in r_con[1]]
    if c:
        if len((c[0]['importante'] or '').encode()) >= 1000:
            formato.append('L5 importante ≥ 1000 bytes')
        if edad(c[0]['actualizado']) > 14:
            formato.append(f"L5 continuidad actualizada hace {edad(c[0]['actualizado'])} días")
    if r_ind is None:
        aviso.append('L7 cerebro: sin tablas derivadas (correr indexar-cerebro)')
    else:
        des = [f[0] for f in r_ind[1]]
        if des:
            aviso.append('L7 cerebro: tablas derivadas desfasadas (' + ', '.join(des) + '): correr indexar-cerebro')
    clase = 'NO_LISTO_DATOS' if falla else 'AVISO_FORMATO' if formato else 'LISTO'
    return clase, falla, aviso + formato


def seccion(texto, buscar):
    lin = texto.split('\n')
    for i, l in enumerate(lin):
        m = re.match(r'^(#{2,3})\s', l)
        if m and buscar.lower() in l.lower():
            nivel, out = len(m.group(1)), [l]
            for l2 in lin[i + 1:]:
                m2 = re.match(r'^(#{1,3})\s', l2)
                if m2 and len(m2.group(1)) <= nivel:
                    break
                out.append(l2)
            return '\n'.join(out).strip()
    return None


def doc(db, i, sec=None):
    base = i.split('#', 1)[0]
    if base not in NO_INDEXAR:
        try:
            r = q(db, 'SELECT c.texto, c.sha256, EXISTS (SELECT 1 FROM cerebro_seccion s WHERE s.doc=c.id AND s.doc_sha256=c.sha256) ok '
                      'FROM cerebro c WHERE c.id=?', base)
        except Exception:  # noqa: BLE001  base sin tablas derivadas (falta init): se sigue con el texto
            r = None
        if r and sha(r[0]['texto']) != r[0]['sha256']:
            return f'(cerebro {base}: sha256 no coincide: no usar)'
        if r and r[0]['ok']:
            t = doc_sql(db, i, sec)
            if t is not None:
                return t
    if '#' in i and not sec:
        i, n = i.split('#', 1)
        sec = n + '.'
    r = q(db, 'SELECT texto, sha256 FROM cerebro WHERE id=?', i)
    if not r:
        return None
    if sha(r[0]['texto']) != r[0]['sha256']:
        return f'(cerebro {i}: sha256 no coincide: no usar)'
    return seccion(r[0]['texto'], sec) if sec else r[0]['texto']


def apertura(datos, clase, falla, aviso):
    j = lambda n: json.load(open(os.path.join(datos, n), encoding='utf-8')) if os.path.exists(os.path.join(datos, n)) else None
    a, u = j('abrir.json'), j('urgentes.json')
    out = [f"ARRANQUE {clase}" + (f" · avisos: {' | '.join(aviso)}" if aviso else '')]
    out += ['FALLA ' + x for x in falla]
    if a:
        fu, nu = a.get('fuentes') or {}, a.get('numeros') or {}
        out.append(f"FUENTES CRM {fu.get('respaldo')} · Finnegans {fu.get('finnegans')} · recompra {fu.get('recompra')}")
        out.append(f"NÚMEROS seguimientos {nu.get('seguimientos')} ({nu.get('cuentas')} cuentas) · posventa {nu.get('posventa')} · "
                   f"le toca {nu.get('le_toca')} · atrasadas {nu.get('atrasadas')}")
        al = (a.get('control') or {}).get('alertas') or []
        out.append('CONTROL OK' if not al else 'CONTROL alertas: ' + ' | '.join(str(x)[:120] for x in al[:4]))
        ven = [s for s in a.get('seguimientos') or [] if isinstance(s, dict) and s.get('est') in ('hoy', 'vencido')]
        out.append(f'VENCIDAS ({len(ven)}): ' + (' · '.join(f"{s.get('n')} {str(s.get('cliente'))[:24]} (vence {s.get('vence')})"
                                                          for s in ven[:10]) or 'ninguna'))
    if clase == 'NO_LISTO_DATOS':
        out.append('R-DETENER: sin ranking ni top 5; solo vencidas y qué falta.')
    elif u:
        out.append('TOP 5' + (' (arranque con aviso de formato)' if clase == 'AVISO_FORMATO' else '') + ':')
        for k, x in enumerate((u.get('top5') or [])[:5], 1):
            ojo = x.get('ojo')
            ojo = ' / '.join(map(str, ojo)) if isinstance(ojo, list) else (ojo or '')
            out.append(f"{k}. {str(x.get('cuenta'))[:30]} · USD {x.get('usd')} · {str(x.get('por_que'))[:80]} · hoy: {str(x.get('accion'))[:90]}"
                       + (f' · ojo: {ojo[:90]}' if ojo else ''))
        co, cf = u.get('cortas') or [], u.get('conflictos') or []
        out.append(f'CORTAS ({len(co)}): ' + (' · '.join(f"{str(x.get('cuenta'))[:22]} USD {x.get('usd')}" for x in co[:6]) or '-'))
        pv = u.get('posventa') or []
        out.append(f'POSVENTA · pestaña Posventa ({len(pv)}): ' + (' · '.join(f"{str(x.get('cuenta'))[:22]} {x.get('ref')}" for x in pv[:5]) or '-'))
        out.append(f'CONFLICTOS CRM ({len(cf)}): ' + (' · '.join(f"{str(x.get('cuenta'))[:22]}" for x in cf[:4]) or '-'))
    t = '\n'.join(out)
    return t if len(t) <= TOPE_APERTURA else t[:TOPE_APERTURA - 30].rsplit('\n', 1)[0] + '\n… (recortado)'


def abrir(db, raiz, hoy_s, crm_dir=None, reglas=False, incremental=False):
    hoy = date.fromisoformat(hoy_s)
    if crm_dir:
        n = cargar_crm(db, crm_dir, hoy_s, incremental)
        print(('CRM actualizado (cambios): ' if incremental else 'CRM copiado completo: ') + ' · '.join(f'{k} {v}' for k, v in n.items()))
    f_baj, cg = bajar(db, raiz)
    try:
        nc, na = armar_clientes(db)
        try:
            ncrm = armar_crm(db)
        except Exception as e:  # noqa: BLE001  la apertura no se cae por esto
            ncrm = f'no corrió ({str(e)[:80]})'
        cal = calidad(db)
        if cal['sin_cuit_con_dato'] or cal['cot_sin_revision'] or cal['cuit_duplicado']:
            extra_aviso = [f"L8 calidad: sin CUIT con venta/cotización {cal['sin_cuit_con_dato']} · cotización abierta sin fecha de revisión "
                           f"{cal['cot_sin_revision']} · CUIT duplicado {cal['cuit_duplicado']} (ver `calidad`)"]
        else:
            extra_aviso = []
    except Exception as e:  # noqa: BLE001  la apertura no se cae por esto
        nc, ncrm, extra_aviso = None, None, [f'L8 clientes/calidad no corrió ({str(e)[:80]})']
    clase, falla, aviso = controles(db, cg, hoy)
    aviso = aviso + extra_aviso
    falla = f_baj + falla
    clase = 'NO_LISTO_DATOS' if falla else clase
    datos, scr = os.path.join(raiz, 'DATOS'), os.path.join(raiz, 'SCRIPTS')
    py = [sys.executable, '-I']
    for cmd, salida in (('abrir', 'abrir.json'), ('urgentes', 'urgentes.json')):
        p = subprocess.run(py + [os.path.join(scr, 'loki.py'), cmd, datos, hoy_s], capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            falla.append(f'loki.py {cmd}: exit {p.returncode} {p.stderr.strip()[-160:]}')
            clase = 'NO_LISTO_DATOS'
        open(os.path.join(datos, salida), 'w', encoding='utf-8').write(p.stdout)
    try:   # 1.8.0: continuidad, bitácora y despacho en un viaje (antes 4)
        con, b, ult, gsd = qs(db, ["SELECT importante FROM continuidad WHERE id='actual'",
                                   "SELECT COUNT(*) n, SUM(estado='abierto') a FROM bitacora",
                                   "SELECT id, fecha, tema FROM bitacora WHERE origen NOT LIKE 'continuidad:%' ORDER BY id DESC LIMIT 3",
                                   'SELECT COUNT(*) n FROM v_ganadas_sin_despacho'])
        b, gsd = b[0], gsd[0]['n']
    except Exception:  # noqa: BLE001  se cae a las consultas sueltas de siempre
        con, b, ult, gsd = q(db, "SELECT importante FROM continuidad WHERE id='actual'"), None, None, None
    print('IMPORTANTE: ' + ((con[0]['importante'] or '(continuidad sin importante: avisar y rehacerla al cerrar)') if con else '(sin continuidad)'))
    print(apertura(datos, clase, falla, aviso))
    try:
        b = b or q(db, "SELECT COUNT(*) n, SUM(estado='abierto') a FROM bitacora")[0]
        ult = ult if ult is not None else q(db, "SELECT id, fecha, tema FROM bitacora WHERE origen NOT LIKE 'continuidad:%' ORDER BY id DESC LIMIT 3")
        print(f"BITÁCORA {b['n']} filas · {b['a'] or 0} abiertas · clientes {nc}" + (' · últimas: ' + ' · '.join(
            f"#{r['id']} {r['fecha'][5:]} {r['tema'][:50]}" for r in ult) if ult else ''))
    except Exception as e:  # noqa: BLE001
        print(f'BITÁCORA no disponible ({str(e)[:80]})')
    try:
        if isinstance(ncrm, dict):
            g = gsd if gsd is not None else q(db, 'SELECT COUNT(*) n FROM v_ganadas_sin_despacho')[0]['n']
            print('CRM EN TABLAS ' + ' · '.join(f'{k} {v}' for k, v in ncrm.items()) + f' · ganadas sin dato de despacho {g}')
        else:
            print(f'CRM EN TABLAS {ncrm}')
    except Exception as e:  # noqa: BLE001
        print(f'CRM EN TABLAS no disponible ({str(e)[:80]})')
    try:   # status de clientes: se recalcula solo si llegó CRM o reporte nuevo después del último cálculo (Nicolás 18/11)
        viejo = status_viejo(db)
        if viejo:
            r = status_calcular(db, hoy_s)
            print(f"STATUS recalculado ({', '.join(viejo)} nuevo): {r['fichas']} fichas en {r['total_s']} s · CONTROL: "
                  + ('PASA' if not r['fallan'] else f"FALLA en {len(r['fallan'])} fichas (ver status-calcular)"))
        else:
            u = q(db, 'SELECT MAX(calculado) c, COUNT(*) n FROM status_cliente')[0]
            print(f"STATUS al día: {u['n']} fichas calculadas {u['c']}")
    except Exception as e:  # noqa: BLE001  la apertura no se cae por esto
        print(f'STATUS no se recalculó ({str(e)[:80]}): correr status-calcular')
    p = subprocess.run(py + [os.path.join(scr, 'memoria_check.py'), datos, hoy_s], capture_output=True, text=True, timeout=300)
    lineas = [l for l in p.stdout.splitlines() if l.strip()]
    print('MEMORIA ' + (' '.join(lineas[:1]) if lineas else f'sin salida (exit {p.returncode})'))
    for l in lineas[1:]:
        if not l.startswith(('BOX ', 'FACTURA_SIN_CARGAR')):
            print('  ' + l.strip()[:200])
    fac = [l.split(None, 1)[1][:70] for l in lineas if l.startswith('FACTURA_SIN_CARGAR')]
    if fac:
        print(f'  FACTURAS SIN CARGAR ({len(fac)}): ' + ' · '.join(fac))
    if reglas:
        k = conocimiento(db)
        ped = (('respuestas', '1.'),) if k else (('reglas', 'Parte 0'), ('preferencias', None), ('respuestas', '1.'))
        if k:
            print('\n' + k)
        for (i, _), t in zip(ped, docs_lote(db, ped)):
            print('\n' + (t or f'({i} no está en la base)'))
    return {'LISTO': 0, 'AVISO_FORMATO': 2, 'NO_LISTO_DATOS': 1}[clase]


def estado(db, hoy):
    cg = {c['fuente']: c for c in q(db, 'SELECT * FROM cargas ORDER BY fuente')}
    for f, c in cg.items():
        print(f"{f:<22} corte {str(c['corte'])[:10]:<10} filas {c['filas']:>5}  cargado {c['cargado']}")
    clase, falla, aviso = controles(db, cg, hoy)
    print('CONTROLES', clase, *(['FALLA ' + x for x in falla] + ['AVISO ' + x for x in aviso]), sep='\n  ')
    return 1 if falla else 0


# ------------------------------------------------------------------ cerebro estructurado (1.3.0)
# Los documentos de la tabla `cerebro` siguen siendo la fuente; estas tablas se DERIVAN de ellos en la misma
# transacción de cargar-cerebro (o con indexar-cerebro). Nunca se editan a mano: se edita el documento.
NO_INDEXAR = {'cargador'}                       # código, no texto


def partir(texto):
    """[(orden, nivel, titulo, cuerpo)] cortando en títulos #, ## y ###, fuera de bloques ```.
    '\\n'.join(cuerpo de cada una) reproduce el texto EXACTO (lo controla indexar)."""
    out, cur, nivel, tit, fence = [], [], 0, '', False
    for l in texto.split('\n'):
        if l.lstrip().startswith('```'):
            fence = not fence
        m = None if fence else re.match(r'^(#{1,3})\s+(.*)$', l)
        if m and (cur or out):
            out.append((nivel, tit, '\n'.join(cur)))
            cur = []
        if m:
            nivel, tit = len(m.group(1)), m.group(2).strip()
        cur.append(l)
    out.append((nivel, tit, '\n'.join(cur)))
    return [(i, n, t, c) for i, (n, t, c) in enumerate(out)]


def clave_de(titulo):
    t = titulo.strip()
    m = re.match(r'^(D\d{2}|P\d{2}|R-[A-Z0-9-]+)\b', t)
    if m:
        return m.group(1)
    m = re.match(r'^(\d{1,2})\.\s', t)
    if m:
        return '§' + m.group(1)
    m = re.match(r'^(Parte \d)\b', t)
    return m.group(1) if m else None


def _reglas(texto):
    """reglas → filas (id, tipo, titulo, resumen, texto, estado, destino, etiqueta, origen, bloqueante, orden)."""
    filas, res, orden = {}, {}, 0
    lin = texto.split('\n')
    parte = None
    i = 0
    while i < len(lin):
        l = lin[i]
        h = re.match(r'^(#{2,3})\s+(.*)$', l)
        if h:
            t = h.group(2)
            if h.group(1) == '##':
                parte = 'p0' if t.startswith('Parte 0') else 'p1' if t.startswith('Parte 1') else \
                        'pend' if t.lower().startswith('pendientes') else 'p2' if t.startswith('Parte 2') else None
            elif parte == 'p1':
                m = re.match(r'^(D\d{2})\s*·\s*(.*)$', t)
                if m:
                    cuerpo = []
                    j = i + 1
                    while j < len(lin) and not re.match(r'^#{1,3}\s', lin[j]):
                        cuerpo.append(lin[j]); j += 1
                    c = '\n'.join(cuerpo).strip()
                    o = re.search(r'^Origen:\s*(.*)$', c, re.M)
                    orden += 1
                    filas[m.group(1)] = dict(id=m.group(1), tipo='dura', titulo=m.group(2).strip(), texto=c, estado='VIGENTE',
                                             destino=None, etiqueta='DECISION', origen=o.group(1).strip() if o else None,
                                             bloqueante=1, orden=orden)
                    i = j; continue
            i += 1; continue
        if parte == 'p0':
            m = re.match(r'^- \*\*(D\d{2})\s+([^*]+)\*\*:\s*(.*)$', l)
            if m:
                res[m.group(1)] = m.group(3).strip()
        elif parte == 'pend':
            m = re.match(r'^- (P\d{2})\s+(.*)$', l)
            if m:
                cuerpo = m.group(2).strip()
                tit = re.split(r': | \(', cuerpo, maxsplit=1)[0].strip()
                orden += 1
                filas[m.group(1)] = dict(id=m.group(1), tipo='pendiente', titulo=tit, texto=cuerpo, estado='PENDIENTE DE NICOLÁS',
                                         destino=','.join(sorted(set(re.findall(r'R-H\d+|D\d{2}', cuerpo)))) or None,
                                         etiqueta=None, origen=None, bloqueante=0, orden=orden)
        elif parte == 'p2':
            m = re.match(r'^- \*\*(R-[A-Z0-9-]+)\*\*\s*·\s*([^·]+)·\s*([^·]+)·\s*(no bloqueante|bloqueante)\s*→\s*(.*)$', l)
            if m:
                cuerpo = []
                j = i + 1
                while j < len(lin) and lin[j].startswith('  '):
                    cuerpo.append(lin[j].strip()); j += 1
                est = m.group(5).strip()
                e = re.match(r'^(VIGENTE|FUSIONADA|PENDIENTE DE NICOLÁS|DESACTUALIZADA|DESCARTADA|REEMPLAZADA)', est)
                orden += 1
                filas[m.group(1)] = dict(id=m.group(1), tipo='json', titulo=None, texto=' '.join(cuerpo),
                                         estado=e.group(1) if e else est.split()[0], destino=est,
                                         etiqueta=m.group(2).strip(), origen=m.group(3).strip(),
                                         bloqueante=1 if m.group(4) == 'bloqueante' else 0, orden=orden)
                i = j; continue
        i += 1
    for k, v in res.items():
        if k in filas:
            filas[k]['resumen'] = v
    return list(filas.values())


def _router(texto):
    sec = seccion(texto, 'Router') or ''
    filas = []
    for l in sec.split('\n'):
        c = [x.strip() for x in l.strip().strip('|').split('|')]
        if len(c) < 4 or not re.match(r'^[a-z0-9_]+$', c[0]) or c[0] == 'intencion':
            continue
        docs = []
        for d in (x.strip() for x in c[2].split(',') if x.strip()):
            m = re.match(r'^([a-z0-9_]+)(.*)$', d)
            if m:
                secs = re.findall(r'§\s*(\d+)', m.group(2))
                for s_ in secs or [None]:
                    docs.append((len(docs), m.group(1), '§' + s_ if s_ else None))
        filas.append((c[0], c[1], c[2], c[3], docs))
    return filas


def indexar_stmts(db):
    """Sentencias que rearman las tablas derivadas desde `cerebro` (sin transacción propia)."""
    st = [('DELETE FROM cerebro_seccion', []), ('DELETE FROM cerebro_regla', []),
          ('DELETE FROM cerebro_router', []), ('DELETE FROM cerebro_router_doc', [])]
    docs = q(db, 'SELECT id, version, sha256, texto FROM cerebro ORDER BY id')
    cuenta = {'docs': 0, 'secciones': 0, 'reglas': 0, 'router': 0}
    for d in docs:
        if sha(d['texto']) != d['sha256']:
            raise ValueError(f"cerebro {d['id']}: sha256 no coincide: no se indexa")
        if d['id'] in NO_INDEXAR:
            continue
        partes = partir(d['texto'])
        if '\n'.join(p[3] for p in partes) != d['texto']:
            raise ValueError(f"cerebro {d['id']}: las secciones no reproducen el documento")
        cuenta['docs'] += 1
        for orden, nivel, tit, cuerpo in partes:
            st.append(('INSERT INTO cerebro_seccion VALUES (?,?,?,?,?,?,?,?)',
                       [d['id'], orden, nivel, tit, clave_de(tit) if nivel >= 2 else None, cuerpo, sha(cuerpo), d['sha256']]))
            cuenta['secciones'] += 1
        if d['id'] == 'reglas':
            for r in _reglas(d['texto']):
                st.append(('INSERT INTO cerebro_regla VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                           [r['id'], r['tipo'], r.get('titulo'), r.get('resumen'), r['texto'], r['estado'], r.get('destino'),
                            r.get('etiqueta'), r.get('origen'), r['bloqueante'], r['orden'], d['sha256']]))
                cuenta['reglas'] += 1
        if d['id'] == 'indice':
            for n, (it, ej, dt, fu, ds) in enumerate(_router(d['texto'])):
                st.append(('INSERT INTO cerebro_router VALUES (?,?,?,?,?,?)', [it, n, ej, dt, fu, d['sha256']]))
                for k, doc_id, sec in ds:
                    st.append(('INSERT INTO cerebro_router_doc VALUES (?,?,?,?)', [it, k, doc_id, sec]))
                cuenta['router'] += 1
    av = []
    ids = {x['id'] for x in docs}
    if 'reglas' in ids:
        tipos = {}
        for s_, a_ in st:
            if s_.startswith('INSERT INTO cerebro_regla'):
                tipos[a_[1]] = tipos.get(a_[1], 0) + 1
        if tipos.get('dura', 0) < 17 or tipos.get('pendiente', 0) < 1:
            av.append(f"reglas: el parser leyó {tipos} (¿cambió el formato?)")
    if 'indice' in ids and not cuenta['router']:
        av.append('indice: 0 filas de router (¿cambió el título o la tabla?)')
    if av:
        cuenta['avisos'] = av
    return st, cuenta


def indexar(db):
    init(db)
    st, cuenta = indexar_stmts(db)
    transaccion(db, st)
    return cuenta


def indice_al_dia(db):
    """[] si las tablas derivadas corresponden a los documentos actuales; si no, la lista de documentos desfasados."""
    return [r['id'] for r in q(db, SQL_INDICE)]


SQL_INDICE = ("SELECT c.id FROM cerebro c WHERE c.id NOT IN ('" + "','".join(NO_INDEXAR) + "') AND NOT EXISTS "
              "(SELECT 1 FROM cerebro_seccion s WHERE s.doc=c.id AND s.doc_sha256=c.sha256) ORDER BY c.id")


def doc_sql(db, i, sec=None):
    """Documento o sección desde cerebro_seccion (clave exacta: D06, §2, P01, Parte 0; si no, título que contiene)."""
    if '#' in i and not sec:
        i, sec = i.split('#', 1)
        sec = sec if sec.startswith('§') or not sec.isdigit() else '§' + sec
    filas = q(db, 'SELECT orden, nivel, titulo, clave, texto FROM cerebro_seccion WHERE doc=? ORDER BY orden', i)
    return _doc_de_filas(filas, sec)


def _doc_de_filas(filas, sec):
    if not filas:
        return None
    if not sec:
        return '\n'.join(f['texto'] for f in filas)
    s = sec.strip()
    s2 = '§' + s.rstrip('.') if re.match(r'^\d{1,2}\.?$', s) else s
    ini = next((k for k, f in enumerate(filas) if f['clave'] and f['clave'].lower() == s2.lower()), None)
    if ini is None and not s2.startswith('§'):
        ini = next((k for k, f in enumerate(filas) if f['nivel'] >= 2 and s.lower() in f['titulo'].lower()), None)
    if ini is None:
        return None
    out = [filas[ini]['texto']]
    for f in filas[ini + 1:]:
        if f['nivel'] <= filas[ini]['nivel']:
            break
        out.append(f['texto'])
    return '\n'.join(out).strip()


def docs_lote(db, pedidos):
    """1.8.0: varios documentos/secciones en un solo viaje. pedidos = [(id, seccion|None)]; mismo resultado que doc()."""
    ids = list(dict.fromkeys(i for i, _ in pedidos))
    try:
        res = qs(db, [x for i in ids for x in (
            ('SELECT c.texto, c.sha256, EXISTS (SELECT 1 FROM cerebro_seccion s WHERE s.doc=c.id AND s.doc_sha256=c.sha256) ok '
             'FROM cerebro c WHERE c.id=?', [i]),
            ('SELECT orden, nivel, titulo, clave, texto FROM cerebro_seccion WHERE doc=? ORDER BY orden', [i]))])
    except Exception:  # noqa: BLE001
        return [doc(db, i, s_) for i, s_ in pedidos]
    por = {i: (res[2 * k], res[2 * k + 1]) for k, i in enumerate(ids)}
    out = []
    for i, s_ in pedidos:
        chk, filas = por[i]
        t = None
        if i not in NO_INDEXAR and chk and sha(chk[0]['texto']) == chk[0]['sha256'] and chk[0]['ok']:
            t = _doc_de_filas(filas, s_)
        out.append(t if t is not None else doc(db, i, s_))
    return out


def frescura(db, doc_id, tabla):
    try:
        r = q(db, f'SELECT (SELECT sha256 FROM cerebro WHERE id=?) = (SELECT MAX(doc_sha256) FROM {tabla}) ok', doc_id)
        return '' if r and r[0]['ok'] else f'AVISO {tabla} no corresponde al {doc_id} actual: correr indexar-cerebro\n'
    except Exception:  # noqa: BLE001
        return f'AVISO sin {tabla}: correr init e indexar-cerebro\n'


def _hay_k(db):
    return bool(q(db, "SELECT 1 FROM sqlite_master WHERE type='table' AND name='k_regla'"))


def conocimiento(db):
    """Capa 1 (1.9.0): lo que Loki tiene que saber al abrir, desde las tablas k_*. None si la base no las tiene."""
    if not _hay_k(db):
        return None
    du, ot, pr, de, mo = qs(db, [
        "SELECT id, titulo, texto FROM k_regla WHERE estado='vigente' AND dura=1 ORDER BY id",
        "SELECT id, titulo, aplica FROM k_regla WHERE estado='vigente' AND dura=0 ORDER BY id",
        "SELECT id, tema, texto FROM k_preferencia ORDER BY tema, id",
        "SELECT id, fecha, que FROM k_decision WHERE estado='vigente' ORDER BY fecha DESC, id",
        "SELECT nombre, pestana, que_hace, estado FROM k_motor ORDER BY id"])
    out = [f'CONOCIMIENTO (tablas k_*) · reglas duras {len(du)} · otras vigentes {len(ot)} · preferencias {len(pr)} · decisiones {len(de)}',
           '## Reglas duras (no se negocian)']
    out += [f"- {r['id']} · {r['titulo']}: {r['texto']}" for r in du]
    out.append('## Otras reglas vigentes (detalle: `regla ID`)')
    out.append(' · '.join(f"{r['id']} {r['titulo']}" + (f" [{r['aplica']}]" if r['aplica'] and r['aplica'] != 'todo' else '') for r in ot))
    out.append('## Preferencias de Nicolás')
    tema = None
    for r in pr:
        if r['tema'] != tema:
            tema = r['tema']; out.append(f'{tema}:')
        out.append(f"- {r['texto']}")
    out.append(f'## Últimas decisiones (6 de {len(de)}; todas: sql k_decision)')
    out += [f"- {r['id']} {str(r['fecha'])[8:10]}/{str(r['fecha'])[5:7]}: {r['que'][:120]}" for r in de[:6]]
    out.append('## Motores → pestaña: ' + ' · '.join(f"{r['nombre']} → {r['pestana']} ({r['estado']})" for r in mo))
    return '\n'.join(out)


def regla(db, i):
    if _hay_k(db):
        r = q(db, 'SELECT * FROM k_regla WHERE upper(id)=upper(?)', i)
        if r:
            r = r[0]
            cab = f"{r['id']} · {'dura' if r['dura'] else 'regla'} · {r['estado']}" + (f" → reemplazada por {r['reemplazada_por']}" if r['reemplazada_por'] else '')
            return '\n'.join(x for x in [cab, r['titulo'], r['texto'], r['aplica'] and f"Aplica: {r['aplica']}", r['origen'] and f"Origen: {r['origen']}"] if x)
    av = frescura(db, 'reglas', 'cerebro_regla')
    r = q(db, 'SELECT * FROM cerebro_regla WHERE upper(id)=upper(?)', i) if not av.startswith('AVISO sin') else []
    if not r:
        return (av + f'no está: {i}') if av else None
    r = r[0]
    cab = f"{r['id']} · {r['tipo']} · {r['estado']}" + (f" → {r['destino']}" if r['destino'] and r['tipo'] != 'json' else '')
    if r['tipo'] == 'json':
        cab = f"{r['id']} · {r['etiqueta']} · {r['origen']} · {'bloqueante' if r['bloqueante'] else 'no bloqueante'} → {r['destino']}"
    return av + '\n'.join(x for x in [cab, (r['titulo'] or '') and f"{r['titulo']}", r['resumen'] and f"Resumen: {r['resumen']}", r['texto']] if x)


def reglas_lista(db, tipo=None, estado=None):
    if _hay_k(db):
        w, a = [], []
        if tipo == 'dura':
            w.append('dura=1')
        elif tipo == 'pendiente':
            w.append("estado='pendiente'")
        if estado:
            w.append('lower(estado) LIKE lower(?)'); a.append(estado + '%')
        filas = q(db, 'SELECT id, dura, estado, titulo, texto FROM k_regla' + (' WHERE ' + ' AND '.join(w) if w else '') + ' ORDER BY estado DESC, id', *a)
        return '\n'.join(f"{f['id']:<12} {'dura' if f['dura'] else 'regla':<6} {f['estado']:<10} {(f['titulo'] + ': ' + f['texto'])[:110]}"
                         for f in filas) + f"\n({len(filas)} reglas · tablas k_*)"
    w, a = [], []
    if tipo:
        w.append('tipo=?'); a.append(tipo)
    if estado:
        w.append('upper(estado) LIKE upper(?)'); a.append(estado + '%')
    av = frescura(db, 'reglas', 'cerebro_regla')
    filas = q(db, 'SELECT id, tipo, estado, titulo, resumen, texto FROM cerebro_regla' + (' WHERE ' + ' AND '.join(w) if w else '') +
              ' ORDER BY orden', *a)
    return av + '\n'.join(f"{f['id']:<12} {f['tipo']:<9} {f['estado']:<22} {(f['titulo'] or f['resumen'] or f['texto'] or '')[:110]}"
                     for f in filas) + f"\n({len(filas)} reglas)"


def intencion(db, nombre, texto=False):
    av = frescura(db, 'indice', 'cerebro_router')
    r = q(db, 'SELECT * FROM cerebro_router WHERE intencion=?', nombre)
    if not r:
        todas = [x['intencion'] for x in q(db, 'SELECT intencion FROM cerebro_router ORDER BY orden')]
        return f"no está: {nombre}. Intenciones: {', '.join(todas)}"
    r = r[0]
    ds = q(db, 'SELECT doc, seccion FROM cerebro_router_doc WHERE intencion=? ORDER BY n', nombre)
    out = ([av.strip()] if av else []) + [f"INTENCIÓN {nombre} · ejemplos: {r['ejemplos']}", 'DOCS ' + ' · '.join(d['doc'] + (' ' + d['seccion'] if d['seccion'] else '') for d in ds),
           f"FUENTES {r['fuentes']}"]
    if texto:
        for d in ds:
            if d['seccion']:          # solo las secciones puntuales; los documentos enteros se piden con doc
                out.append('\n' + (doc_sql(db, d['doc'], d['seccion']) or f"({d['doc']} {d['seccion']} no está)"))
    return '\n'.join(out)


# ------------------------------------------------------------------ autotest
def autotest():
    base = tempfile.mkdtemp(prefix='lokisql_')
    os.environ['LOKI_SQL_LOCAL'] = os.path.join(base, 't.db')
    mal, n = 0, 0
    def chk(nombre, ok):
        nonlocal mal, n
        n += 1
        mal += 0 if ok else 1
        print(f"{'BIEN' if ok else 'MAL':<5} {nombre}")
    try:
        db = conectar()
        init(db); init(db)
        chk('init idempotente', q(db, 'SELECT COUNT(*) n FROM esquema')[0]['n'] == 1)
        w = lambda p, t: (os.makedirs(os.path.dirname(p), exist_ok=True), open(p, 'w', encoding='utf-8').write(t))
        csv10 = 'Fecha;Comprobante;Cliente;Nro de identificación;Importe;Unidad;Unidad;Empresa\n2026-11-01;A-1;Cli;30-1-2;10.5;u;u;HORIZON TRADING S.A.\n2026-11-02;A-2;Cli;30-1-2;4.5;u;u;HORIZON TRADING S.A.\n'
        w(f'{base}/R10.csv', csv10)
        w(f'{base}/R10m.json', json.dumps({'corte': '2026-11-13', 'sha256': sha(csv10)}))
        chk('R10 carga 2 filas', cargar_reporte(db, 'R10', f'{base}/R10.csv', f'{base}/R10m.json') == 2)
        chk('vista ventas por cliente suma', q(db, 'SELECT importe FROM v_ventas_cliente')[0]['importe'] == 15.0)
        w(f'{base}/R10m2.json', json.dumps({'corte': '2026-11-13', 'sha256': '0' * 64}))
        try:
            cargar_reporte(db, 'R10', f'{base}/R10.csv', f'{base}/R10m2.json'); chk('sha distinto se rechaza', False)
        except ValueError:
            chk('sha distinto se rechaza', q(db, 'SELECT COUNT(*) n FROM ventas')[0]['n'] == 2)
        w(f'{base}/R8.csv', 'Productoid;Producto;Stock\n1;ONT;5\n'); w(f'{base}/R8m.json', '{"corte":"2026-11-13"}')
        cargar_reporte(db, 'R8', f'{base}/R8.csv', f'{base}/R8m.json')
        w(f'{base}/rc.json', json.dumps([{'cliente': 'Cli', 'sku': 'ONT', 'estado': 'Le toca', 'proxima': '2026-11-20T00:00:00.000'}]))
        w(f'{base}/rcm.json', '{"corte":"2026-11-13","version":"v3"}')
        cargar_recompra(db, f'{base}/rc.json', f'{base}/rcm.json')
        w(f'{base}/CRM/oportunidades/o1.json', json.dumps({'empresa': 'Cli', 'cuit': '30-1-2', 'etapa': 'cotizado', 'monto': 100}))
        w(f'{base}/CRM/cotizaciones/c1.json', json.dumps({'id': 'c1', 'data': {'cliente': 'Cli', 'numero': 'NM1', 'estado': 'enviada', 'total': 121}, 'version': 2}))
        w(f'{base}/CRM/config/datosBancarios.json', '{"cbu":"123"}'); w(f'{base}/CRM/config/tc.json', '{"valor":1}')
        n2 = cargar_crm(db, f'{base}/CRM', '2026-11-17')
        chk('CRM sin datos bancarios (D10)', n2.get('config') == 1 and not q(db, "SELECT 1 FROM crm WHERE id='datosBancarios'"))
        chk('envoltorio del Data Center se saca', q(db, 'SELECT numero FROM v_cotizaciones_abiertas')[0]['numero'] == 'NM1')
        w(f'{base}/CRM2/oportunidades/o1.json', '{"empresa":"X"}')
        try:
            cargar_crm(db, f'{base}/CRM2', '2026-11-17'); chk('CRM sin cotizaciones se rechaza', False)
        except ValueError:
            chk('CRM sin cotizaciones se rechaza', q(db, "SELECT COUNT(*) n FROM crm WHERE coleccion='cotizaciones'")[0]['n'] == 1)
        chk('crm-desde tras copia completa', crm_desde(db, date(2026, 11, 18)) == 'DESDE 2026-11-17')
        w(f'{base}/INC/oportunidades/o2.json', '{"empresa":"Nueva","actualizado":"2026-11-18"}')
        cargar_crm(db, f'{base}/INC', '2026-11-18', incremental=True)
        chk('incremental agrega sin borrar', q(db, "SELECT COUNT(*) n FROM crm WHERE coleccion='oportunidades'")[0]['n'] == 2
            and q(db, "SELECT filas FROM cargas WHERE fuente='crm:oportunidades'")[0]['filas'] == 2
            and q(db, "SELECT corte FROM cargas WHERE fuente='crm:cotizaciones'")[0]['corte'] == '2026-11-18')
        chk('a los 8 días pide COMPLETA', crm_desde(db, date(2026, 11, 25)) == 'COMPLETA')
        w(f'{base}/INC2/oportunidades/o1.json', '{"empresa":"Cli editada","actualizado":"2026-11-18"}')
        cargar_crm(db, f'{base}/INC2', '2026-11-18', incremental=True)
        chk('incremental actualiza un documento existente', q(db, "SELECT empresa FROM crm WHERE id='o1'")[0]['empresa'] == 'Cli editada')
        try:
            transaccion(db, [("UPDATE crm SET empresa='ROTO' WHERE id='o1'", []), ('INSERT INTO tabla_que_no_existe VALUES (1)', [])])
        except Exception:
            pass
        chk('error a mitad: ROLLBACK (todo o nada)', q(db, "SELECT empresa FROM crm WHERE id='o1'")[0]['empresa'] == 'Cli editada')
        w(f'{base}/MEM/cuentas/h-x.json', '{"empresa":"Cli","cuit":"30-1-2"}'); w(f'{base}/MEM/aprendizajes/P-a.json', '{"tipo":"patrón","fecha":"2026-11-15"}')
        chk('memoria', cargar_memoria(db, f'{base}/MEM') == {'cuentas': 1, 'aprendizajes': 1})
        w(f'{base}/contmal.json', json.dumps({'importante': 'x', 'actualizado': '16/11'}))
        try:
            cargar_continuidad(db, f'{base}/contmal.json'); chk('continuidad mal formada se rechaza', False)
        except ValueError:
            chk('continuidad mal formada se rechaza', True)
        w(f'{base}/contvacia.json', json.dumps({'actualizado': '2026-11-16', 'abiertos': []}))
        try:
            cargar_continuidad(db, f'{base}/contvacia.json'); chk('continuidad sin importante se rechaza', False)
        except ValueError:
            chk('continuidad sin importante se rechaza', True)
        w(f'{base}/cont.json', json.dumps({'importante': 'x' * 50, 'actualizado': '2026-11-16'}))
        cargar_continuidad(db, f'{base}/cont.json')
        t = '# Reglas\n## Parte 0 · Duras\n- D01\n## Parte 1\n- otra\n'
        w(f'{base}/CER/cerebro/reglas.json', json.dumps({'id': 'reglas', 'texto': t, 'sha256': sha(t), 'version': '1.0.0'}))
        cargar_cerebro(db, f'{base}/CER')
        chk('doc por sección', doc(db, 'reglas', 'Parte 0') == '## Parte 0 · Duras\n- D01')
        tr = ('# Reglas\nintro\n## Parte 0 · Resumen\n- **D01 Hacelo**: nada sin hacelo.\n- **D02 Viva**: sigue viva.\n'
              '## Parte 1 · Vigentes\n### D01 · Hacelo\nNada se suma.\nOrigen: R-HACELO.\n### D02 · Cotización viva\nViva.\n'
              '## Pendientes de Nicolás\n- P01 Apertura: fichas o texto (R-H49).\n- P02 Atajo: horizon (D01).\n'
              '## Parte 2 · json\n- **R-VIVA** · DECISION · Nicolás 10/11 · bloqueante → VIGENTE → D02\n  Toda cotización sigue viva.\n\n'
              '- **R-H01** · DECISION · Nicolás s/f · no bloqueante → PENDIENTE DE NICOLÁS (P04)\n  Roles.\n'
              '```\n# esto no es título\n```\n')
        ti = ('# Índice\n## Router (intención → documentos)\n| Intención | Ejemplos | Documentos | Fuentes |\n|---|---|---|---|\n'
              '| apertura | Loki | loki_arranque, respuestas §1 | continuidad |\n| cambio | hacelo | respuestas §10, reglas | doc |\n## Otra\nx\n')
        tres = '# Respuestas\n## 1. Apertura\nTexto corto.\n## 10. Cambio\nPropuesta.\n'
        for i_, t_ in (('reglas', tr), ('indice', ti), ('respuestas', tres), ('cargador', '# código\nprint(1)\n')):
            w(f'{base}/CER2/cerebro/{i_}.json', json.dumps({'id': i_, 'texto': t_, 'sha256': sha(t_), 'version': '2.0.0'}))
        cargar_cerebro(db, f'{base}/CER2')
        chk('secciones reproducen cada documento', all('\n'.join(r['texto'] for r in q(db, 'SELECT texto FROM cerebro_seccion WHERE doc=? ORDER BY orden', i_)) == t_
                                                      for i_, t_ in (('reglas', tr), ('indice', ti), ('respuestas', tres))))
        chk('cargador no se indexa', not q(db, "SELECT 1 FROM cerebro_seccion WHERE doc='cargador'"))
        chk('``` no corta sección', not q(db, "SELECT 1 FROM cerebro_seccion WHERE titulo='esto no es título'"))
        cnt = {r['tipo']: r['n'] for r in q(db, 'SELECT tipo, COUNT(*) n FROM cerebro_regla GROUP BY tipo')}
        chk('reglas: 2 duras, 2 pendientes, 2 json', cnt == {'dura': 2, 'pendiente': 2, 'json': 2})
        chk('regla dura con resumen y origen', q(db, "SELECT resumen, origen FROM cerebro_regla WHERE id='D01'")[0] == {'resumen': 'nada sin hacelo.', 'origen': 'R-HACELO.'})
        chk('regla json con estado y bloqueante', q(db, "SELECT estado, bloqueante FROM cerebro_regla WHERE id='R-H01'")[0] == {'estado': 'PENDIENTE DE NICOLÁS', 'bloqueante': 0})
        chk('doc por clave D02 y §10', doc(db, 'reglas', 'D02') == '### D02 · Cotización viva\nViva.' and doc(db, 'respuestas#10') == '## 10. Cambio\nPropuesta.')
        chk('§1 no confunde con §10', doc(db, 'respuestas#1') == '## 1. Apertura\nTexto corto.')
        chk('router: docs y secciones', [(r['doc'], r['seccion']) for r in q(db, "SELECT doc, seccion FROM cerebro_router_doc WHERE intencion='apertura' ORDER BY n")]
            == [('loki_arranque', None), ('respuestas', '§1')] and 'Texto corto.' in intencion(db, 'apertura', True))
        # 1.9.0: conocimiento desde las tablas k_* (sin ellas, el arranque vuelve a la prosa)
        chk('sin k_regla: conocimiento None y regla desde el cerebro', conocimiento(db) is None and 'Viva.' in (regla(db, 'D02') or ''))
        db.run([(x, []) for x in (
            "CREATE TABLE k_regla (id TEXT PRIMARY KEY, titulo TEXT NOT NULL, texto TEXT NOT NULL, dura INTEGER NOT NULL DEFAULT 0, aplica TEXT, estado TEXT NOT NULL, reemplazada_por TEXT, desde TEXT, origen TEXT)",
            "CREATE TABLE k_preferencia (id TEXT PRIMARY KEY, tema TEXT NOT NULL, texto TEXT NOT NULL, desde TEXT, origen TEXT)",
            "CREATE TABLE k_decision (id TEXT PRIMARY KEY, fecha TEXT NOT NULL, que TEXT NOT NULL, efecto TEXT, estado TEXT NOT NULL DEFAULT 'vigente', origen TEXT)",
            "CREATE TABLE k_motor (id TEXT PRIMARY KEY, nombre TEXT NOT NULL, pestana TEXT, que_hace TEXT NOT NULL, lee TEXT, entrega TEXT, version TEXT, donde TEXT, estado TEXT)",
            "INSERT INTO k_regla VALUES ('D01','Hacelo','nada sin hacelo.',1,'todo','vigente',NULL,NULL,'reglas §D01')",
            "INSERT INTO k_regla VALUES ('N01','Cada motor en su pestaña','Sales solo venta.',0,'sales,posventa','vigente',NULL,NULL,NULL)",
            "INSERT INTO k_regla VALUES ('P99','Vieja','ya no va.',1,'todo','historica','N01',NULL,NULL)",
            "INSERT INTO k_preferencia VALUES ('PR01','Cómo hablarle','Rioplatense.',NULL,NULL)",
            "INSERT INTO k_decision VALUES ('DEC-1','2026-11-21','Finnegans manual.',NULL,'vigente',NULL)",
            "INSERT INTO k_decision VALUES ('DEC-0','2026-11-20','Finnegans automático.',NULL,'historica',NULL)",
            "INSERT INTO k_motor VALUES ('sales','Sales Engine','Sales','Empuja la venta.',NULL,NULL,NULL,NULL,'sellado')")])
        k = conocimiento(db) or ''
        chk('conocimiento: dura entera, otra en una línea, sin históricas', '- D01 · Hacelo: nada sin hacelo.' in k and 'N01 Cada motor en su pestaña [sales,posventa]' in k and 'P99' not in k)
        chk('conocimiento: preferencias, solo decisiones vigentes y motores', 'Rioplatense.' in k and 'DEC-1 21/11' in k and 'DEC-0' not in k and 'Sales Engine → Sales (sellado)' in k)
        chk('regla desde k_regla con reemplazo', regla(db, 'p99').startswith('P99 · dura · historica → reemplazada por N01'))
        chk('reglas --tipo dura desde k_regla', reglas_lista(db, 'dura').count(chr(10)) == 2 and '(2 reglas · tablas k_*)' in reglas_lista(db, 'dura'))
        # 1.10.0: conocimiento-cargar
        nk = conocimiento_cargar(db, {'k_decision': [{'id': 'DEC-1', 'estado': 'historica'}, {'id': 'DEC-2', 'fecha': '2026-11-22', 'que': 'Solo nube.'}]})
        k = conocimiento(db) or ''
        chk('conocimiento-cargar: cambia y agrega por id', nk == {'k_decision': 2} and 'DEC-2 22/11' in k and 'DEC-1 21/11' not in k)
        try:
            conocimiento_cargar(db, {'k_decision': [{'id': 'DEC-3', 'fecha': 'x', 'que': 'y'}, {'id': 'DEC-2', 'inventada': 1}]})
            rechaza = False
        except ValueError:
            rechaza = True
        chk('conocimiento-cargar: columna inexistente = nada escrito', rechaza and not q(db, "SELECT 1 FROM k_decision WHERE id='DEC-3'"))
        try:
            conocimiento_cargar(db, {'cerebro': [{'id': 'x'}]}); rechaza = False
        except ValueError:
            rechaza = True
        chk('conocimiento-cargar: solo tablas k_*', rechaza)
        conocimiento_cargar(db, {'k_decision': [{'id': 'DEC-1', 'estado': 'vigente'}]})
        db.run([("DELETE FROM k_decision WHERE id='DEC-2'", [])])
        chk('índice al día', indice_al_dia(db) == [])
        db.run([("UPDATE cerebro SET texto=texto||'x', sha256=? WHERE id='respuestas'", [sha(tres + 'x')])])
        chk('doc cambiado sin indexar: L7 y doc lee el texto nuevo', indice_al_dia(db) == ['respuestas'] and doc(db, 'respuestas').endswith('x'))
        indexar(db)
        chk('indexar lo pone al día', indice_al_dia(db) == [])
        hoy = date(2026, 11, 17)
        cg = {c['fuente']: c for c in q(db, 'SELECT * FROM cargas')}
        clase, fa, av = controles(db, cg, hoy)
        chk('sano: LISTO con aviso de frescura', clase == 'LISTO' and any(x.startswith('L4 R10') for x in av))
        db.run([("DELETE FROM ventas WHERE n=2", [])])
        clase, fa, av = controles(db, cg, hoy)
        chk('fila borrada: NO_LISTO (L3)', clase == 'NO_LISTO_DATOS' and any(x.startswith('L3 R10') for x in fa))
        cargar_reporte(db, 'R10', f'{base}/R10.csv', f'{base}/R10m.json')
        clase, fa, av = controles(db, cg, date(2026, 12, 15))
        chk('Finnegans de 32 días: NO_LISTO (L4)', clase == 'NO_LISTO_DATOS')
        w(f'{base}/cont2.json', json.dumps({'importante': 'x' * 1200, 'actualizado': '2026-11-16'}))
        db.run([("UPDATE continuidad SET importante=? WHERE id='actual'", ['x' * 1200])])
        cg = {c['fuente']: c for c in q(db, 'SELECT * FROM cargas')}
        chk('importante largo: AVISO_FORMATO (L5)', controles(db, cg, hoy)[0] == 'AVISO_FORMATO')
        cargar_continuidad(db, f'{base}/cont.json')
        w(f'{base}/s.py', 'print(1)\n')
        cargar_script(db, 'loki.py', f'{base}/s.py', 't')
        db.run([("UPDATE scripts SET texto='print(2)' WHERE nombre='loki.py'", [])])
        fb, _ = bajar(db, f'{base}/RAIZ')
        chk('script alterado: L2', any('L2 script loki.py' in x for x in fb))
        chk('bajar reproduce R10.csv exacto', sha(open(f'{base}/RAIZ/DATOS/R10.csv', encoding='utf-8').read()) == sha(csv10))
        r = json.load(open(f'{base}/RAIZ/DATOS/respaldo.json', encoding='utf-8'))
        chk('respaldo.json formato v3', r['collections']['cotizaciones']['c1']['numero'] == 'NM1' and r['exportedAt'].startswith('2026-11-17'))
        try:
            main(['sql', 'DELETE FROM ventas']); chk('sql solo lectura', False)
        except SystemExit as e:
            chk('sql solo lectura', e.code == 1 and q(db, 'SELECT COUNT(*) n FROM ventas')[0]['n'] == 2)
        w(f'{base}/fichas.json', json.dumps({'fuentes': {'F1': {'pdf': 'X.pdf', 'pm_asset': 'abc'}}, 'fichas': [
            {'modelo': 'FitDP-1', 'familia': 'Caja', 'resumen': 'r', 'specs': [['IP', 'IP68']], 'buscar': '%Cli%', 'fuente': 'F1'}]}))
        cargar_fichas(db, f'{base}/fichas.json', '2026-11-17')
        f1 = ficha(db, 'fitdp 1')
        chk('ficha: datos + PDF + cruce', '· IP: IP68' in f1 and 'PM /_blob/abc' in f1 and 'NO está en la lista' in f1)
        chk('ficha inexistente lista modelos', 'FitDP-1' in ficha(db, 'zzz'))
        w(f'{base}/fichas_mal.json', json.dumps({'fichas': [{'modelo': 'X', 'specs': []}]}))
        try:
            cargar_fichas(db, f'{base}/fichas_mal.json', '2026-11-17'); chk('ficha sin specs se rechaza', False)
        except ValueError:
            chk('ficha sin specs se rechaza', True)
        # ---- 1.4.0 bitácora / clientes / calidad
        chk('norm saca S.R.L. y acentos', norm('Pampacóm S.R.L.') == 'pampacom' and norm('NODO NET S.A.') == norm('Nodo Net'))
        chk('cuit_ok normaliza y rechaza DNI', cuit_ok('30714498173') == '30-71449817-3' and cuit_ok('16.497.924') is None)
        db.run([("INSERT OR REPLACE INTO crm (coleccion,id,empresa,cuit,estado,data) VALUES ('oportunidades','o3','Cli S.A.','',"
                 "'cotizado','{}')", []),
                ("INSERT OR REPLACE INTO crm (coleccion,id,empresa,cuit,estado,data) VALUES ('oportunidades','o4','Otra','30-9-9','prospecto','{}')", []),
                ("INSERT OR REPLACE INTO crm (coleccion,id,empresa,cuit,estado,data) VALUES ('oportunidades','o5','Otra bis','30-9-9','prospecto','{}')", []),
                ("UPDATE crm SET cuit='30-12345678-9' WHERE id='o1'", []), ("UPDATE ventas SET cuit='30-12345678-9'", []),
                ("UPDATE cuentas SET cuit='30-12345678-9'", [])])
        nc, na = armar_clientes(db)
        chk('clientes por CUIT (DNI/CUIT mal formado fuera)', nc == 1 and q(db, 'SELECT crm_id FROM clientes')[0]['crm_id'] == 'o1')
        chk('alias: nombre de factura y de ficha → mismo CUIT', buscar_cuit(db, 'CLI') == [('30-12345678-9', 'Cli editada')])
        armar_clientes(db)
        chk('armar-clientes idempotente', q(db, 'SELECT COUNT(*) n FROM clientes')[0]['n'] == 1)
        cal = calidad(db)
        chk('L8: sin CUIT con dato y cotización sin vence', cal['sin_cuit_con_dato'] == 1 and cal['cot_sin_revision'] == 1)
        chk('L8 detalle sugiere CUIT', '30-12345678-9' in calidad(db, True))
        db.run([("UPDATE crm SET cuit='30-99999999-9' WHERE id IN ('o4','o5')", [])])
        chk('L8: CUIT duplicado', calidad(db)['cuit_duplicado'] == 1)
        i1 = anotar(db, 'pendiente', 'Nodo Net NM51', 'renovar', cuit='30714498173', fecha='2026-11-17')
        chk('anotar pendiente queda abierto con CUIT normalizado',
            q(db, 'SELECT estado, cuit FROM bitacora WHERE id=?', i1)[0] == {'estado': 'abierto', 'cuit': '30-71449817-3'})
        for mal_, args in (('tipo inválido', ('chisme', 't', 'x')), ('texto vacío', ('hecho', 't', ' ')),):
            try:
                anotar(db, *args); chk(mal_ + ' se rechaza', False)
            except ValueError:
                chk(mal_ + ' se rechaza', True)
        try:
            anotar(db, 'hecho', 't', 'x', cuit='123'); chk('CUIT mal formado se rechaza', False)
        except ValueError:
            chk('CUIT mal formado se rechaza', True)
        i2 = anotar(db, 'hecho', 'cierra', 'renovada NM51', cierra=i1)
        chk('cerrar: el pendiente pasa a cerrado y queda el vínculo',
            q(db, 'SELECT estado FROM bitacora WHERE id=?', i1)[0]['estado'] == 'cerrado' and q(db, 'SELECT cierra FROM bitacora WHERE id=?', i2)[0]['cierra'] == i1)
        try:
            anotar(db, 'hecho', 'x', 'y', cierra=i1); chk('no se cierra dos veces', False)
        except ValueError:
            chk('no se cierra dos veces', True)
        try:
            db.run([("INSERT INTO bitacora (fecha,tipo,tema,texto,estado,creado) VALUES ('2026-11-17','hecho','t','x','raro','x')", [])])
            chk('CHECK de estado en la tabla', False)
        except Exception:
            chk('CHECK de estado en la tabla', True)
        b = bitacora(db, abiertos=True)
        chk('bitacora --abiertos', b.startswith('BITÁCORA 2 filas · 0 abiertas'))
        db.run([("UPDATE continuidad SET data=? WHERE id='actual'", [json.dumps({'abiertos': [{'tema': 'Cli · algo (05/11)', 'estado': 'e1'},
                                                                                              {'tema': 'Sin cuenta', 'estado': 'e2'}]})])])
        chk('migrar-continuidad: 2 filas con fecha y CUIT', migrar_continuidad(db) == 2 and q(db,
            "SELECT fecha, cuit FROM bitacora WHERE origen='continuidad:abiertos:0'")[0] == {'fecha': '2026-11-05', 'cuit': '30-12345678-9'})
        chk('migrar-continuidad idempotente', migrar_continuidad(db) == 0)
        c360 = cliente(db, 'cli')
        chk('cliente 360: ficha + ventas + bitácora', 'CUIT 30-12345678-9' in c360 and 'Ventas (R10) 2 comprobantes' in c360 and 'Cli · algo' in c360)
        chk('vistas nuevas responden', all(q(db, f'SELECT COUNT(*) n FROM {v}') for v in ('v_seguimientos_hoy', 'v_revisar_hoy', 'v_bitacora_abierta')))
        # ---- 1.6.0 CRM en tablas ordenadas
        op6 = {'empresa': 'Howard', 'cuit': '20-11111111-2', 'etapa': 'ganado', 'monto': '1234,5', 'contacto': 'Pablo', 'telefono': '11',
               'transporte': ' ', 'domicilio': 'Calle 1', 'archivada': False, 'noProspectar': 'si', 'zzNuevo': 'x',
               'historial': [{'t': '2026-11-17', 'txt': 'nota'}, 'basura'],
               'contactosAdicionales': [{'nombre': 'Ana', 'cargo': 'Compras', 'mail': 'a@b'}, {'nombre': ''}]}
        op7 = {'empresa': 'Sin CUIT en ficha', 'etapa': 'cotizado', 'transporte': 'Expreso X', 'domicilio': 'Calle 2'}
        cot6 = {'numero': 'NM99', 'cliente': 'Howard', 'cuit': '', 'oportunidadId': 'o6', 'estado': 'aceptada', 'fecha': '2026-11-17',
                'total': 100, 'neto': 82.6, 'ivaTotal': 17.4, 'hz_operacion': {'despacho': 'pendiente'},
                'items': [{'codigo': 'A', 'cantidad': 20, 'precio': 4.13, 'neto': 82.6}]}
        cot7 = {'numero': 'NM98', 'cliente': 'Sin CUIT', 'oportunidadId': 'o7', 'estado': 'aceptada', 'fecha': '2026-11-16', 'total': 5}
        mu6 = {'oportunidadId': 'o6', 'productos': 'ONT', 'estado': 'enviada', 'devolver': True}
        db.run([("INSERT OR REPLACE INTO crm (coleccion,id,empresa,cuit,estado,data) VALUES ('oportunidades','o6','Howard','20-11111111-2','ganado',?)", [json.dumps(op6)]),
                ("INSERT OR REPLACE INTO crm (coleccion,id,empresa,cuit,estado,data) VALUES ('oportunidades','o7','Sin CUIT en ficha','','cotizado',?)", [json.dumps(op7)]),
                ("INSERT OR REPLACE INTO crm (coleccion,id,estado,data) VALUES ('cotizaciones','k6','aceptada',?)", [json.dumps(cot6)]),
                ("INSERT OR REPLACE INTO crm (coleccion,id,estado,data) VALUES ('cotizaciones','k7','aceptada',?)", [json.dumps(cot7)]),
                ("INSERT OR REPLACE INTO crm (coleccion,id,estado,data) VALUES ('muestras','m6','enviada',?)", [json.dumps(mu6)])])
        armar_clientes(db)
        n6 = armar_crm(db)
        tot = {x: q(db, f"SELECT COUNT(*) n FROM crm WHERE coleccion='{x}'")[0]['n'] for x in ('oportunidades', 'cotizaciones', 'muestras')}
        chk('armar-crm: una fila por documento', n6['oportunidades'] == tot['oportunidades'] and n6['cotizaciones'] == tot['cotizaciones']
            and n6['muestras'] == tot['muestras'] and q(db, 'SELECT COUNT(*) n FROM crm_oportunidad')[0]['n'] == tot['oportunidades'])
        o6 = q(db, "SELECT * FROM crm_oportunidad WHERE id='o6'")[0]
        chk('oportunidad: monto texto → número, vacío → NULL, si → 1, extra guarda lo no mapeado',
            o6['monto'] == 1234.5 and o6['transporte'] is None and o6['no_prospectar'] == 1 and json.loads(o6['extra']) == {'zzNuevo': 'x'})
        chk('contactos: principal + adicional (vacío fuera)', [(r['principal'], r['nombre']) for r in
            q(db, "SELECT principal, nombre FROM crm_contacto WHERE oportunidad_id='o6' ORDER BY n")] == [(1, 'Pablo'), (0, 'Ana')])
        chk('historial: solo entradas válidas', q(db, "SELECT COUNT(*) n FROM crm_historial WHERE oportunidad_id='o6'")[0]['n'] == 1)
        k6 = q(db, "SELECT cuit, despacho, total FROM crm_cotizacion WHERE id='k6'")[0]
        chk('cotización sin CUIT hereda el de su oportunidad', k6 == {'cuit': '20-11111111-2', 'despacho': 'pendiente', 'total': 100.0})
        chk('ítems con CUIT y cantidad', q(db, "SELECT cuit, cantidad FROM crm_cotizacion_item WHERE cotizacion_id='k6'")[0]
            == {'cuit': '20-11111111-2', 'cantidad': 20.0})
        chk('muestra hereda CUIT', q(db, "SELECT cuit, devolver FROM crm_muestra WHERE id='m6'")[0] == {'cuit': '20-11111111-2', 'devolver': 1})
        g6 = {r['numero']: r['falta'] for r in q(db, 'SELECT numero, falta FROM v_ganadas_sin_despacho')}
        chk('ganadas sin despacho: falta transporte (Howard), completa fuera', g6.get('NM99') == 'falta transporte' and 'NM98' not in g6)
        chk('v_despacho: última aceptada', q(db, "SELECT ultima_aceptada FROM v_despacho WHERE id='o6'")[0]['ultima_aceptada'] == 'NM99')
        # ---- 1.7.0 status
        sd = os.path.join(base, 'st')
        ex7, l7 = status_vivo(db, '20-11111111-2', sd, '2026-11-18', png=False)
        h7 = open(os.path.join(sd, 'howard.html'), encoding='utf-8').read()
        chk('status: arma tarjeta y control PASA', ex7 == 0 and l7[-1] == 'CONTROL: PASA' and all(f'id="p{k}"' in h7 for k in (1, 2, 3, 4)))
        chk('status: sin botones y con CUIT', '↗' not in h7 and '20-11111111-2' in h7 and 'Posventa' in h7)
        chk('status: control detecta un total que falta', any('ventas' in x for x in status_control(db, status_datos(db, '20-11111111-2', '2026-11-18'),
            h7.replace('USD 0,00', 'USD 9,99'))))
        chk('status: inexistente no arma', status_vivo(db, 'zzzz inexistente', sd, png=False)[0] == 1)
        r7 = status_calcular(db, '2026-11-18')
        f7 = q(db, "SELECT * FROM status_cliente WHERE cuit='20-11111111-2'")
        chk('status-calcular: una fila por ficha viva con CUIT, con motor y fecha', r7['fichas'] == q(db,
            "SELECT COUNT(DISTINCT cuit) n FROM crm_oportunidad WHERE cuit IS NOT NULL AND archivada=0")[0]['n'] and f7 and f7[0]['motor'] == ST_MOTOR)
        chk('status-calcular idempotente', status_calcular(db, '2026-11-18')['fichas'] == r7['fichas'] and q(db, 'SELECT COUNT(*) n FROM status_cliente')[0]['n'] == r7['fichas'])
        chk('status al día tras calcular', status_viejo(db) == [])
        db.run([("UPDATE cargas SET cargado='2999-01-01T00:00:00Z' WHERE fuente='R10'", [])])
        chk('R10 nuevo → status viejo', status_viejo(db) == ['R10'])
        pg = status_pagina(f7[0], [os.path.join(sd, 'x.png')] * 4) if (open(os.path.join(sd, 'x.png'), 'wb').write(b'png') or True) else ''
        chk('página: 2 columnas, botones reales, historial y pie', 'id="verHist"' in pg and 'id="evalBtn"' in pg and "use('sample')" in pg
            and 'motor ' + ST_MOTOR in pg and pg.count('<img') == 4)
        armar_crm(db)
        chk('armar-crm idempotente', q(db, 'SELECT COUNT(*) n FROM crm_contacto')[0]['n'] == n6['contactos'])
        # 1.8.0: lotes y esquema 6
        a1, a2 = qs(db, ['SELECT COUNT(*) n FROM crm', ("SELECT COUNT(*) n FROM crm WHERE coleccion=?", ['cotizaciones'])])
        chk('qs: varias lecturas en un viaje, en orden', a1[0]['n'] == q(db, 'SELECT COUNT(*) n FROM crm')[0]['n']
            and a2[0]['n'] == q(db, "SELECT COUNT(*) n FROM crm WHERE coleccion='cotizaciones'")[0]['n'])
        r8 = ('Orden;Productoid;Empresaid;Producto;Familia;Subfamilia;Stock;Stock partida;Pedidos de venta s/f;Fecha pedidos de venta s/f;'
              'Facturas de venta s/r;Fecha facturas de venta s/r;En producción;Fecha en producción;En tránsito;Fecha en tránsito;Total\n'
              '1;1179;16;Drop;FO;DROP;3750.000000;H2025-013;;;;;;;;;\n2;1179;16;Drop;FO;DROP;;;250.000000;;;;;;;;\n'
              '4;1179;16;Drop;FO;DROP;;;;;;;1080000.000000;2026-11-17;;;\n6;1179;16;Drop;FO;DROP;;;;;;;;;;;1083750.0000\n')
        w(f'{base}/R8b.csv', r8); w(f'{base}/R8bm.json', '{"corte":"2026-11-17"}')
        cargar_reporte(db, 'R8', f'{base}/R8b.csv', f'{base}/R8bm.json')
        s8 = q(db, "SELECT SUM(stock) s, SUM(en_produccion) p, MAX(fecha_produccion) f, MAX(partida) pa, SUM(pedidos_sf) pe,"
                   " MAX(total) t, COUNT(*) n, MIN(orden) o FROM stock")[0]
        chk('R8 guarda En producción, fecha, partida y orden (esquema 6)', s8['p'] == 1080000 and s8['f'] == '2026-11-17'
            and s8['pa'] == 'H2025-013' and s8['s'] == 3750 and s8['pe'] == 250 and s8['t'] == 1083750 and s8['n'] == 4 and s8['o'] == 1)
        chk('R8 nuevo: filas = registradas (L3)', q(db, "SELECT filas FROM cargas WHERE fuente='R8'")[0]['filas'] == 4)
        viejo = Local(':memory:')
        viejo.run([('CREATE TABLE stock (n INTEGER PRIMARY KEY, productoid TEXT, producto TEXT, familia TEXT, subfamilia TEXT,'
                    ' stock REAL, pedidos_sf REAL, facturas_sr REAL, en_transito REAL, total REAL)', []),
                   ("INSERT INTO stock VALUES (1,'1','ONT','F','S',5,NULL,NULL,NULL,5)", [])])
        init(viejo); init(viejo)
        cols8 = {r['name'] for r in q(viejo, 'PRAGMA table_info(stock)')}
        chk('init migra stock viejo sin perder filas (idempotente)', {c for c, _ in STOCK_NUEVAS} <= cols8
            and q(viejo, 'SELECT stock FROM stock')[0]['stock'] == 5)
        viejo.close()
        os.makedirs(f'{base}/B', exist_ok=True)
        cargar_script(db, 'motor.py', f'{base}/R8b.csv', 'x')
        fb, _cg = bajar(db, f'{base}/B')
        chk('bajar trae motor.py con sha256 verificado', not [x for x in fb if 'motor' in x] and os.path.exists(f'{base}/B/SCRIPTS/motor.py'))
        chk('bajar deja loki_sql.py al lado de motor.py', os.path.exists(f'{base}/B/SCRIPTS/loki_sql.py'))
        db.close()
    finally:
        os.environ.pop('LOKI_SQL_LOCAL', None)
        shutil.rmtree(base, ignore_errors=True)
    print(f'AUTOTEST {"OK" if not mal else "FALLÓ"}: {n - mal}/{n}')
    return 1 if mal else 0


# ------------------------------------------------------------------ bitácora, clientes y calidad (1.4.0)
# bitacora = el hilo, una fila por hecho (se escribe con `anotar`, sin hacelo: aprobado por Nicolás 17/11).
# clientes / cliente_alias = DERIVADAS (crm + ventas + cuentas); se rearman al abrir; nunca se editan a mano.
TIPOS_BIT = ('decision', 'hecho', 'pendiente', 'error', 'aprendizaje', 'carga', 'cierre')
LEGALES = {'sa', 'srl', 'sas', 'sapem', 'saci', 'sacif', 'sh', 'ltda', 'limitada', 'sociedad', 'anonima', 'responsabilidad'}
HOY_AR = "date('now','-3 hours')"


def norm(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower().replace('.', '')
    return ' '.join(t for t in re.sub(r'[^a-z0-9]+', ' ', s).split() if t not in LEGALES)


def cuit_ok(c):
    d = re.sub(r'\D', '', str(c or ''))
    return f'{d[:2]}-{d[2:10]}-{d[10]}' if len(d) == 11 else None


def armar_clientes(db):
    """Rearma clientes y cliente_alias desde crm (oportunidades), ventas (solo HORIZON) y cuentas. Todo o nada."""
    cli, alias = {}, set()
    def base(c):
        return cli.setdefault(c, dict(razon=None, crm_id=None, fichas=0, lleva=None, otro=None, nop=0, arch=1, unif=None, fuentes=set()))
    r_opo, r_ven, r_cue = qs(db, [   # 1.8.0: un viaje (antes 3)
        "SELECT id, empresa, cuit, data FROM crm WHERE coleccion='oportunidades'",
        "SELECT cuit, MAX(cliente) cliente FROM ventas WHERE empresa LIKE 'HORIZON TRADING%' GROUP BY cuit, cliente",
        'SELECT empresa, cuit, lleva FROM cuentas'])
    for r in r_opo:
        d = json.loads(r['data'])
        cs = [cuit_ok(r['cuit'])] + [cuit_ok(x) for x in (d.get('cuitsAdicionales') or []) if isinstance(d.get('cuitsAdicionales'), list)]
        for k, c in enumerate(x for x in cs if x):
            b = base(c); b['fuentes'].add('crm'); b['fichas'] += 1
            activa = not d.get('archivada') and not d.get('unificadaEn')
            if k == 0 and (b['crm_id'] is None or (activa and b['arch'])):
                b.update(razon=r['empresa'], crm_id=r['id'], arch=0 if activa else 1, unif=d.get('unificadaEn'),
                         nop=1 if d.get('noProspectar') == 'si' else 0, otro=d.get('otroVendedor') or None)
            if r['empresa']:
                alias.add((norm(r['empresa']), r['empresa'], c, 'crm'))
    for r in r_ven:
        c = cuit_ok(r['cuit'])
        if not c:
            continue
        b = base(c); b['fuentes'].add('ventas'); b['razon'] = b['razon'] or r['cliente']
        alias.add((norm(r['cliente']), r['cliente'], c, 'ventas'))
    for r in r_cue:
        c = cuit_ok(r['cuit'])
        if not c:
            continue
        b = base(c); b['fuentes'].add('cuentas'); b['lleva'] = r['lleva']; b['razon'] = b['razon'] or r['empresa']
        alias.add((norm(r['empresa']), r['empresa'], c, 'cuentas'))
    st = [('DELETE FROM clientes', []), ('DELETE FROM cliente_alias', [])]
    st += [('INSERT INTO clientes VALUES (?,?,?,?,?,?,?,?,?,?,?)', [c, b['razon'], b['crm_id'], b['fichas'], b['lleva'], b['otro'], b['nop'],
            b['arch'] if b['crm_id'] else None, b['unif'], ','.join(sorted(b['fuentes'])), ahora()]) for c, b in sorted(cli.items())]
    st += [('INSERT OR IGNORE INTO cliente_alias VALUES (?,?,?,?)', list(a)) for a in sorted(alias) if a[0]]
    transaccion(db, st)
    return len(cli), len({a[0] for a in alias if a[0]})


def buscar_cuit(db, texto, exacto=False):
    """CUIT exacto o nombre → [(cuit, razon)]. Varios = ambiguo (D03: preguntar, no elegir)."""
    c = cuit_ok(texto)
    if c:
        return [(r['cuit'], r['razon_social']) for r in q(db, 'SELECT cuit, razon_social FROM clientes WHERE cuit=?', c)] or [(c, None)]
    n = norm(texto)
    r = q(db, 'SELECT DISTINCT a.cuit, c.razon_social FROM cliente_alias a JOIN clientes c USING (cuit) WHERE a.alias_norm=?', n)
    if not r and not exacto and len(n) >= 4:
        r = q(db, "SELECT DISTINCT a.cuit, c.razon_social FROM cliente_alias a JOIN clientes c USING (cuit) WHERE a.alias_norm LIKE ?", f'%{n}%')
    return [(x['cuit'], x['razon_social']) for x in r]


def anotar(db, tipo, tema, texto, cuit=None, cuenta=None, fuente=None, chat=None, cierra=None, fecha=None, origen='chat'):
    if tipo not in TIPOS_BIT:
        raise ValueError('tipo: ' + ' | '.join(TIPOS_BIT))
    if not str(tema or '').strip() or not str(texto or '').strip():
        raise ValueError('tema y texto son obligatorios')
    if cuit and not cuit_ok(cuit):
        raise ValueError(f'CUIT mal formado: {cuit} (D03)')
    fecha = fecha or q(db, f'SELECT {HOY_AR} d')[0]['d']
    st = []
    if cierra:
        x = q(db, 'SELECT estado FROM bitacora WHERE id=?', int(cierra))
        if not x or x[0]['estado'] != 'abierto':
            raise ValueError(f'#{cierra} no existe o no está abierto')
        st.append(("UPDATE bitacora SET estado='cerrado' WHERE id=?", [int(cierra)]))
    estado = 'abierto' if tipo == 'pendiente' else 'info'
    st.append(('INSERT INTO bitacora (fecha, chat, tipo, cuit, cuenta, tema, texto, fuente, estado, cierra, creado, origen)'
               ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', [fecha, int(chat) if chat else None, tipo, cuit_ok(cuit), cuenta, tema.strip(),
                                                    texto.strip(), fuente, estado, int(cierra) if cierra else None, ahora(), origen]))
    transaccion(db, st)
    return q(db, 'SELECT MAX(id) i FROM bitacora')[0]['i']


def bitacora(db, cuit=None, abiertos=False, tipo=None, buscar=None, n=15):
    w, args = [], []
    if cuit:
        w.append('cuit=?'); args.append(cuit)
    if abiertos:
        w.append("estado='abierto'")
    if tipo:
        w.append('tipo=?'); args.append(tipo)
    if buscar:
        w.append('(tema LIKE ? OR texto LIKE ? OR cuenta LIKE ?)'); args += [f'%{buscar}%'] * 3
    rs = q(db, 'SELECT * FROM bitacora' + (' WHERE ' + ' AND '.join(w) if w else '') + ' ORDER BY fecha DESC, id DESC LIMIT ?', *args, int(n))
    tot = q(db, "SELECT COUNT(*) n, SUM(estado='abierto') a FROM bitacora")[0]
    out = [f"BITÁCORA {tot['n']} filas · {tot['a'] or 0} abiertas · mostrando {len(rs)}"]
    for r in rs:
        out.append(f"#{r['id']} {r['fecha']} {r['tipo']}/{r['estado']}" + (f" · {r['cuenta'] or ''} {r['cuit'] or ''}".rstrip() if r['cuit'] or r['cuenta'] else '')
                   + f" · {r['tema']}\n    {r['texto'][:400]}" + (f" (cierra #{r['cierra']})" if r['cierra'] else '') + (f" [{r['fuente']}]" if r['fuente'] else ''))
    return '\n'.join(out)


def migrar_continuidad(db):
    """Una vez: cada `abiertos` de la continuidad → fila pendiente/abierto. Idempotente (origen continuidad:abiertos:N)."""
    c = q(db, "SELECT actualizado, data FROM continuidad WHERE id='actual'")
    if not c:
        return 0
    hechos = {r['origen'] for r in q(db, "SELECT origen FROM bitacora WHERE origen LIKE 'continuidad:%'")}
    n = 0
    for i, a in enumerate(json.loads(c[0]['data']).get('abiertos') or []):
        org = f'continuidad:abiertos:{i}'
        if org in hechos or not isinstance(a, dict):
            continue
        tema = str(a.get('tema') or '(sin tema)')
        m = re.search(r'\b(\d{1,2})/(\d{1,2})\b', tema)
        fecha = f'2026-{int(m.group(2)):02d}-{int(m.group(1)):02d}' if m and 1 <= int(m.group(2)) <= 12 else c[0]['actualizado']
        cands = buscar_cuit(db, re.split(r'\s[·(]', tema)[0], exacto=True)
        cuit, cuenta = (cands[0][0], cands[0][1]) if len(cands) == 1 and cands[0][1] else (None, None)
        anotar(db, 'pendiente', tema, str(a.get('estado') or tema), cuit=cuit, cuenta=cuenta, fuente='continuidad 17/11',
               fecha=fecha, origen=org)
        n += 1
    return n


def calidad(db, detalle=False):
    """L8 (aviso, no corta): CUIT faltantes con candidato, cotizaciones abiertas sin vencimiento, CUIT duplicados."""
    act = ("coleccion='oportunidades' AND COALESCE(json_extract(data,'$.archivada'),0)=0 AND json_extract(data,'$.unificadaEn') IS NULL")
    # 1.8.0: las 5 consultas en un solo viaje (no una por ficha: Turso va por red)
    sin, r_al, r_cot, sv, dup = qs(db, [
        f"SELECT id, empresa FROM crm WHERE {act} AND (cuit IS NULL OR cuit='')",
        "SELECT alias_norm, cuit FROM cliente_alias WHERE fuente IN ('ventas','cuentas')",
        "SELECT empresa, COUNT(*) k FROM crm WHERE coleccion='cotizaciones' GROUP BY empresa",
        "SELECT numero, empresa FROM v_para_revisar WHERE revision IS NULL",
        f"SELECT cuit, GROUP_CONCAT(id, ' | ') ids, GROUP_CONCAT(empresa, ' | ') emp FROM crm WHERE {act} AND cuit<>'' GROUP BY cuit HAVING COUNT(*)>1"])
    al = {}
    for y in r_al:
        al.setdefault(y['alias_norm'], set()).add(y['cuit'])
    cots = {}
    for y in r_cot:
        cots[norm(y['empresa'])] = cots.get(norm(y['empresa']), 0) + y['k']
    cand = []
    for r in sin:
        n = norm(r['empresa'])
        if n and (n in al or cots.get(n)):
            cand.append((r['id'], r['empresa'], sorted(al.get(n, ())), cots.get(n, 0)))
    res = dict(sin_cuit=len(sin), sin_cuit_con_dato=len(cand), cot_sin_revision=len(sv), cuit_duplicado=len(dup))
    if not detalle:
        return res
    out = [f"L8 CALIDAD · oportunidades activas sin CUIT {len(sin)} · con venta o cotización (prioridad) {len(cand)} · "
           f"cotizaciones abiertas sin fecha de revisión {len(sv)} · CUIT duplicados {len(dup)}"]
    out.append('-- SIN CUIT con dato (ficha · empresa · CUIT candidato por nombre exacto en R10/cuentas · cotizaciones):')
    out += [f"  {i} · {e} · {', '.join(c) if c else 'sin candidato: pedir CUIT'}" + (' · AMBIGUO' if len(c) > 1 else '') + f' · cot {k}'
            for i, e, c, k in cand]
    out.append('-- COTIZACIONES ABIERTAS SIN FECHA DE REVISIÓN (revisionFecha / seguimiento / vence):')
    out += [f"  {r['numero']} · {r['empresa']}" for r in sv]
    out.append('-- CUIT DUPLICADO (fichas activas):')
    out += [f"  {r['cuit']} · {r['emp']} · {r['ids']}" for r in dup]
    return '\n'.join(out)


def cliente(db, texto):
    c = buscar_cuit(db, texto)
    if not c:
        return f'no está: {texto} (sin CUIT en clientes; buscar en el CRM)'
    if len(c) > 1:
        return 'AMBIGUO (D03, elegí por CUIT): ' + ' · '.join(f'{a} {b}' for a, b in c[:12])
    r = q(db, 'SELECT * FROM v_cliente_360 WHERE cuit=?', c[0][0])
    if not r:
        return f'{c[0][0]}: no está en clientes'
    x = r[0]
    out = [f"{x['razon_social']} · CUIT {x['cuit']} · ficha {x['crm_id'] or '-'} ({x['fichas']} fichas) · lleva: {x['lleva'] or '-'}"
           + (' · OTRO VENDEDOR' if x['otro_vendedor'] else '') + (' · NO PROSPECTAR' if x['no_prospectar'] else ''),
           f"CRM etapa {x['etapa'] or '-'} · próxima {x['proxima'] or '-'} · cotizaciones abiertas {x['cot_abiertas']} (USD {x['cot_monto'] or 0})",
           f"Ventas (R10) {x['comprobantes'] or 0} comprobantes · USD {x['ventas_importe'] or 0} · última {x['ultima_compra'] or '-'}"]
    out.append(bitacora(db, cuit=x['cuit'], n=8))
    return '\n'.join(out)


# ------------------------------------------------------------------ main

# ------------------------------------------------------------------ CRM en tablas ordenadas (1.6.0)
OPO_COLS = (('cuit', None), ('empresa', 'empresa'), ('etapa', 'etapa'), ('tipo', 'tipo'), ('zona', 'zona'), ('prioridad', 'prioridad'),
            ('monto', 'monto'), ('contacto', 'contacto'), ('telefono', 'telefono'), ('email', 'email'), ('domicilio', 'domicilio'),
            ('transporte', 'transporte'), ('cond_iva', 'condIva'), ('pago', 'pago'), ('tecnologia', 'tecnologia'), ('abonados', 'abonados'),
            ('marca_olt', 'marcaOlt'), ('modelo_olt', 'modeloOlt'), ('olt_fh', 'oltFH'), ('usa_fh', 'usaFH'),
            ('cliente_horizon', 'clienteHorizon'), ('productos', 'productos'), ('competidor', 'competidor'),
            ('proxima_accion', 'proximaAccion'), ('proxima_fecha', 'proximaFecha'), ('ultimo_contacto', 'ultimoContacto'),
            ('fecha_ganado', 'fechaGanado'), ('motivo_perdida', 'motivoPerdida'), ('archivada', 'archivada'), ('unificada_en', 'unificadaEn'),
            ('no_prospectar', 'noProspectar'), ('otro_vendedor', 'otroVendedor'), ('cuenta_compartida', 'cuentaCompartida'),
            ('notas', 'notas'), ('creado', 'creado'), ('actualizado', 'actualizado'))
OPO_USADAS = {k for _, k in OPO_COLS if k} | {'cuit', 'historial', 'contactosAdicionales'}


def _txt(v):
    """Texto limpio o None (vacío → None; listas/objetos → JSON)."""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return jdump(v) if v else None
    s = str(v).strip()
    return s or None


def _si(v):
    if v in (None, '', False):
        return 0
    return 1 if v is True or str(v).strip().lower() in ('si', 'sí', 'true', '1') else 0


def armar_crm(db):
    """Rearma las tablas crm_* desde la copia `crm` (todo o nada). CUIT: el del documento; si no, el de `clientes`
    (por crm_id o cuitsAdicionales); cotizaciones y muestras heredan el de su oportunidad. Devuelve conteos."""
    r_cli, r_opo, r_cot, r_mue = qs(db, [   # 1.8.0: un viaje (antes 4)
        'SELECT crm_id, cuit FROM clientes WHERE crm_id IS NOT NULL',
        "SELECT id, data FROM crm WHERE coleccion='oportunidades' ORDER BY id",
        "SELECT id, data FROM crm WHERE coleccion='cotizaciones' ORDER BY id",
        "SELECT id, data FROM crm WHERE coleccion='muestras' ORDER BY id"])
    cuit_por_opo = {r['crm_id']: r['cuit'] for r in r_cli}
    st = [('DELETE FROM ' + x, []) for x in ('crm_oportunidad', 'crm_contacto', 'crm_historial', 'crm_cotizacion',
                                             'crm_cotizacion_item', 'crm_muestra')]
    n = dict(oportunidades=0, contactos=0, historial=0, cotizaciones=0, items=0, muestras=0)
    opo_cuit = {}
    for r in r_opo:
        d = json.loads(r['data'])
        c = cuit_ok(d.get('cuit')) or cuit_por_opo.get(r['id'])
        opo_cuit[r['id']] = c
        fila = []
        for col, k in OPO_COLS:
            v = c if col == 'cuit' else d.get(k)
            if col == 'monto':
                v = v if isinstance(v, (int, float)) and not isinstance(v, bool) else num(v)
            elif col in ('archivada', 'no_prospectar', 'otro_vendedor'):
                v = _si(v)
            else:
                v = _txt(v)
            fila.append(v)
        extra = {k: v for k, v in d.items() if k not in OPO_USADAS and v not in (None, '', [], {})}
        st.append(('INSERT INTO crm_oportunidad VALUES (%s)' % ','.join('?' * (len(OPO_COLS) + 2)), [r['id']] + fila + [jdump(extra) if extra else None]))
        n['oportunidades'] += 1
        cont = []
        if _txt(d.get('contacto')) or _txt(d.get('telefono')) or _txt(d.get('email')):
            cont.append((1, _txt(d.get('contacto')), None, _txt(d.get('telefono')), _txt(d.get('email')), 'ficha'))
        for e in d.get('contactosAdicionales') or []:
            if isinstance(e, dict) and any(_txt(e.get(x)) for x in ('nombre', 'celular', 'mail')):
                cont.append((0, _txt(e.get('nombre')), _txt(e.get('cargo')), _txt(e.get('celular')), _txt(e.get('mail')), _txt(e.get('fuente'))))
        for i, ct in enumerate(cont):
            st.append(('INSERT INTO crm_contacto VALUES (?,?,?,?,?,?,?,?,?)', [r['id'], i, c] + list(ct)))
        n['contactos'] += len(cont)
        for i, h in enumerate(e for e in (d.get('historial') or []) if isinstance(e, dict)):
            st.append(('INSERT INTO crm_historial VALUES (?,?,?,?,?)', [r['id'], i, c, _txt(h.get('t')), _txt(h.get('txt'))]))
            n['historial'] += 1
    for r in r_cot:
        d = json.loads(r['data'])
        op_id = _txt(d.get('oportunidadId'))
        c = cuit_ok(d.get('cuit')) or opo_cuit.get(op_id)
        o = d.get('hz_operacion') if isinstance(d.get('hz_operacion'), dict) else {}
        res = d.get('hz_resultado') if isinstance(d.get('hz_resultado'), dict) else {}
        rev = _txt(d.get('revisionFecha')) or _txt(res.get('fechaSeguimiento')) or _txt(d.get('vence'))
        st.append(('INSERT INTO crm_cotizacion VALUES (%s)' % ','.join('?' * 32), [
            r['id'], _txt(d.get('numero')), op_id, c, _txt(d.get('cliente')), _txt(d.get('estado')), _txt(d.get('fecha')),
            _txt(d.get('vence')), rev, _txt(d.get('fechaGanada')), _txt(d.get('marca')), _txt(d.get('familia')),
            _txt(d.get('condPago')), _txt(d.get('condIva')), num(d.get('tc')), num(d.get('neto')), num(d.get('ivaTotal')), num(d.get('total')),
            _si(d.get('archivada')), _txt(d.get('motivoPerdida')), _txt(d.get('domicilio')), _txt(o.get('pedidoConfirmado')),
            _txt(o.get('despacho')), _txt(o.get('despachoAt')), _txt(o.get('entrega')), _txt(o.get('entregaAt')), _txt(o.get('pago')),
            _txt(o.get('pagoAt')), _txt(o.get('factura')), _txt(res.get('estado')), _txt(d.get('notas')), _txt(d.get('actualizado'))]))
        n['cotizaciones'] += 1
        for i, it in enumerate(e for e in (d.get('items') or []) if isinstance(e, dict)):
            st.append(('INSERT INTO crm_cotizacion_item VALUES (?,?,?,?,?,?,?,?,?,?,?)', [
                r['id'], i, c, _txt(it.get('codigo')), _txt(it.get('articulo')), _txt(it.get('descripcion')), _txt(it.get('marca')),
                num(it.get('cantidad')), num(it.get('precio')), num(it.get('iva')), num(it.get('neto'))]))
            n['items'] += 1
    for r in r_mue:
        d = json.loads(r['data'])
        op_id = _txt(d.get('oportunidadId'))
        st.append(('INSERT INTO crm_muestra VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', [
            r['id'], op_id, opo_cuit.get(op_id), _txt(d.get('productos')), _txt(d.get('estado')), _txt(d.get('envio')),
            _txt(d.get('fechaPedido')), _txt(d.get('fechaEnvio')), _si(d.get('devolver')), _txt(d.get('seguimiento')),
            _txt(d.get('notas')), _txt(d.get('actualizado'))]))
        n['muestras'] += 1
    transaccion(db, st)
    return n


# ------------------------------------------------------------------ status de un cliente (1.7.0)
# `status X`: tarjeta "LOKI · INTELIGENCIA COMERCIAL" (diseño A, respuestas §4) armada SOLO desde la base, sin botones,
# con control independiente (recalcula desde la base y compara con lo publicado) y entrega en 4 imágenes (L-158):
# cabecera · Prioridad comercial · Facturación confirmada · Antes de avanzar + Próxima acción, todas del mismo tamaño.
ST_CERRADAS = ('aceptada', 'perdida', 'rechazada', 'ganada', 'anulada')
ST_FONDO = '#12151C'
ST_CSS = """:root{--bg:#12151C;--card:#12151C;--tx:#eef0f3;--mut:#9aa3ae;--bd:#2d323a;--ac:#5b8cff;--am:#f0b54a;--amb:#2e2412;
--amd:#6b5220;--gr:#5fd39a;--grb:#15301f;--rd:#ff6b61;--blb:#1c2a4a}
*{box-sizing:border-box}html,body{background:var(--bg)}body{margin:0;color:var(--tx);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;padding:10px;zoom:1.4}
.pz{padding:10px;background:var(--bg)}.lbl{font-size:11px;letter-spacing:.08em;color:var(--mut);text-transform:uppercase}
h1{font-size:24px;margin:6px 0 2px}.sub{color:var(--mut)}
.alert{margin:12px 0 0;background:var(--amb);border:1px solid var(--amd);color:var(--am);border-radius:10px;padding:10px 12px}
.card{border:1px solid var(--bd);border-radius:12px;padding:14px}.main{border:2px solid var(--ac)}
.pill{display:inline-block;font-size:11px;padding:2px 9px;border-radius:99px;font-weight:600}
.pb{background:var(--blb);color:var(--ac)}.pg{background:var(--grb);color:var(--gr)}.pa{background:var(--amb);color:var(--am)}
h2{font-size:17px;margin:8px 0 0}.big{font-size:30px;font-weight:700;margin:10px 0 6px}.big small{font-size:13px;font-weight:400;color:var(--mut)}
.row{display:flex;justify-content:space-between;gap:12px;border-top:1px solid var(--bd);padding:6px 0}
.row span:first-child{color:var(--mut);flex:0 0 auto}.row span:last-child{text-align:right;font-weight:500}
.am{color:var(--am)}.rd{color:var(--rd)}.gr{color:var(--gr)}
.box{border:1px solid var(--bd);border-radius:12px;padding:12px 14px}.box+.box{margin-top:12px}.box h3{margin:0 0 6px;font-size:13px;color:var(--mut);font-weight:500}
ul{margin:0;padding-left:0;list-style:none}li{padding:3px 0}li.ck::before{content:"○ ";color:var(--mut)}li.ok::before{content:"✓ ";color:var(--gr)}"""

ST_JS = r"""const {chromium}=require('playwright');
(async()=>{const [html,pref]=process.argv.slice(2);const b=await chromium.launch();
const p=await b.newPage({viewport:{width:600,height:900},deviceScaleFactor:2.5});
await p.goto('file://'+html);await p.addStyleTag({content:'.btn,button{display:none!important}'});
const out=[];for(const i of [1,2,3,4]){const f=pref+'_'+i+'.png';await p.locator('#p'+i).screenshot({path:f});out.push(f);}
await b.close();console.log(out.join('\n'));})().catch(e=>{console.error(e);process.exit(1)});"""


def _usd(x):
    s = f'{abs(x or 0):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('−' if (x or 0) < 0 else '') + 'USD ' + s


def _dm(f):
    f = str(f or '')[:10]
    return f'{f[8:10]}/{f[5:7]}' if re.match(r'\d{4}-\d{2}-\d{2}', f) else '-'


def _h(s):
    import html
    return html.escape(str(s if s is not None else ''), quote=True)


def _cant(x):
    return f'{x:,.0f}'.replace(',', '.') if x is not None and float(x).is_integer() else str(x).replace('.', ',')


def _corto(s, n):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    s = re.sub(r'^Cable Óptico ', '', re.sub(r'\s*\((bobina|unidad)\)', '', s, flags=re.I))
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def status_datos(db, cuit, hoy):
    """Todo lo que muestra la tarjeta, leído de la base (crm_*, ventas R10, stock R8, cargas). Sin cálculos de memoria."""
    ops = q(db, 'SELECT * FROM crm_oportunidad WHERE cuit=? ORDER BY archivada, actualizado DESC', cuit)
    op = ops[0] if ops else {}
    extra = json.loads(op['extra']) if op.get('extra') else {}
    grupo = [g for g in (extra.get('cuitsAdicionales') or []) if isinstance(g, dict) and cuit_ok(g.get('cuit'))]
    cots = q(db, 'SELECT * FROM crm_cotizacion WHERE cuit=? AND archivada=0 ORDER BY fecha DESC', cuit)
    abiertas = [c for c in cots if (c['estado'] or '').lower() not in ST_CERRADAS and not c['motivo_perdida']]
    for c in cots:
        c['items'] = q(db, 'SELECT * FROM crm_cotizacion_item WHERE cotizacion_id=? ORDER BY n', c['id'])
        c['vencida'] = bool(c['vence'] and c['vence'][:10] < hoy and c in abiertas)
    anio = hoy[:4]
    ven = q(db, "SELECT * FROM ventas WHERE cuit=? AND empresa LIKE 'HORIZON TRADING%' ORDER BY fecha, comprobante, n", cuit)
    periodo = anio if any((v['fecha'] or '')[:4] == anio for v in ven) else 'completo'
    ven_p = [v for v in ven if periodo == 'completo' or (v['fecha'] or '')[:4] == anio]
    comp = {}
    for v in ven_p:
        k = v['comprobante']
        c = comp.setdefault(k, dict(fecha=v['fecha'], comprobante=k, nc='Crédito' in (v['documento'] or ''), importe=0.0, lineas=[]))
        c['importe'] += v['importe'] or 0
        c['lineas'].append(f"{_cant(abs(v['cantidad'] or 0))} {_corto(v['producto'], 34)}")
    hist_c = {}
    for v in ven:
        k = v['comprobante']
        c = hist_c.setdefault(k, dict(fecha=v['fecha'], comprobante=k, documento=v['documento'], productos=[], neto=0.0, total=0.0))
        c['neto'] += v['importe'] or 0
        c['total'] += (v['importe'] or 0) * (1 + (v['tasa_iva'] or 0) / 100)
        c['productos'].append(f"{_cant(v['cantidad'] or 0)} {re.sub(chr(32)+'+', ' ', (v['producto'] or '').strip())}")
    pagos = {}
    for v in ven_p:
        if v['condicion_pago'] and 'Crédito' not in (v['documento'] or ''):
            pagos[v['condicion_pago']] = pagos.get(v['condicion_pago'], 0) + 1
    grupo_ventas = []
    for g in grupo:
        r = q(db, "SELECT COALESCE(SUM(importe),0) s FROM ventas WHERE cuit=? AND empresa LIKE 'HORIZON TRADING%' AND substr(fecha,1,4)=?",
              cuit_ok(g['cuit']), anio)[0]['s']
        grupo_ventas.append((g.get('nombre') or g['cuit'], cuit_ok(g['cuit']), r))
    corte = {r['fuente']: r['corte'] for r in q(db, "SELECT fuente, MAX(corte) corte FROM cargas WHERE fuente IN ('R10','R8','crm:oportunidades') GROUP BY fuente")}
    hist = q(db, 'SELECT t, txt FROM crm_historial WHERE oportunidad_id=? ORDER BY t DESC LIMIT 1', op.get('id')) if op else []
    cont = q(db, 'SELECT * FROM crm_contacto WHERE oportunidad_id=? ORDER BY principal DESC, n', op.get('id')) if op else []
    mues = [m for m in q(db, 'SELECT * FROM crm_muestra WHERE cuit=?', cuit) if (m['estado'] or '').lower() not in ('devuelta', 'cerrada', 'aprobada', 'rechazada')]
    gsd = q(db, 'SELECT numero, falta FROM v_ganadas_sin_despacho WHERE cuit=?', cuit)
    return dict(cuit=cuit, hoy=hoy, op=op, grupo=grupo, cots=cots, abiertas=abiertas, periodo=periodo, comp=list(comp.values()),
                ventas_total=sum(v['importe'] or 0 for v in ven_p), pago=max(pagos, key=pagos.get) if pagos else None,
                grupo_ventas=grupo_ventas, corte=corte, hist=hist[0] if hist else None, contactos=cont, muestras=mues, gsd=gsd,
                historial=[dict(x, neto=round(x['neto'], 2), total=round(x['total'], 2)) for x in hist_c.values()])


def _stock(db, it):
    """Stock R8 del artículo: por código (productoid) o por nombre. None = no está en R8."""
    filas = q(db, 'SELECT productoid, producto, stock, total FROM stock WHERE productoid=?', it['codigo']) if it.get('codigo') else []
    if not filas and it.get('articulo'):
        n = norm(re.sub(r'\(.*?\)', '', it['articulo']))
        filas = [r for r in q(db, 'SELECT productoid, producto, stock, total FROM stock') if n and norm(r['producto']) == n]
    if not filas:
        return None
    tot = [r['total'] for r in filas if r['total'] is not None]
    return dict(productoid=filas[0]['productoid'], cant=max(tot) if tot else sum(r['stock'] or 0 for r in filas))


def _unidad(it):
    t = f"{it.get('articulo') or ''} {it.get('descripcion') or ''}".lower()
    return 'bobinas' if 'bobina' in t else 'm' if re.search(r'cable|fibra|drop', t) and (it.get('cantidad') or 0) >= 500 else 'unidades'


def status_html(db, d):
    op, hoy, corte = d['op'], d['hoy'], d['corte']
    razon = op.get('empresa') or q(db, 'SELECT razon_social FROM clientes WHERE cuit=?', d['cuit'])[0]['razon_social']
    olt = (f"OLT: {op['marca_olt']}" + (f" {op['modelo_olt']}" if op.get('modelo_olt') else ' (modelo sin cargar)')) if op.get('marca_olt') \
        else 'OLT: sin cargar' + (' (usa FH)' if op.get('usa_fh') == 'si' else '')
    sub = [f"CUIT {d['cuit']}", f"Cliente Horizon: {op.get('cliente_horizon') or '-'}", olt]
    if op.get('tipo'):
        sub.append(op['tipo'])
    if d['grupo']:
        sub.append('grupo con ' + ', '.join(_corto(g.get('nombre') or g['cuit'], 28) for g in d['grupo']))
    sub += [f"prioridad {op.get('prioridad') or '-'}", f"etapa {op.get('etapa') or '-'}"]
    ab = sorted(d['abiertas'], key=lambda c: -(c['total'] or 0))
    main = ab[0] if ab else next((c for c in d['cots'] if (c['estado'] or '') == 'aceptada'), None)
    p = [f'<div class="pz" id="p1"><div class="lbl">Loki · Inteligencia comercial</div><h1>{_h(razon)}</h1><div class="sub">{_h(" · ".join(sub))}</div>']
    if main:
        it = main['items'][0] if main['items'] else {}
        estado_txt = (f"venció el {_dm(main['vence'])}" if main.get('vencida') else f"vence {_dm(main['vence'])}") if main in ab else f"{main['estado']} el {_dm(main['fecha_ganada'] or main['fecha'])}"
        alerta = f"{main['numero']} · {_cant(it.get('cantidad')) + ' ' if it.get('cantidad') else ''}{_corto(it.get('articulo') or main['familia'], 48)}"
        alerta += f" · {_usd(main['total'])} c/IVA · {estado_txt}"
        if op.get('proxima_fecha'):
            alerta += f" · próxima acción {_dm(op['proxima_fecha'])}" + (' (vencida)' if op['proxima_fecha'][:10] < hoy else '')
        p.append(f'<div class="alert">{_h(alerta)}</div>')
    else:
        p.append('<div class="alert">Sin cotización abierta en el CRM.</div>')
    p.append('</div>')
    # ---- tarjeta 2
    if main:
        it = main['items'][0] if main['items'] else {}
        posventa = main not in ab
        ivap = round(100 * (main['iva'] or 0) / main['neto'], 1) if main['neto'] else None
        filas = [('Modelo / SKU', _h(_corto(it.get('articulo') or '-', 46) + (f" · {it['codigo']}" if it.get('codigo') else '')), ''),
                 ('Cotización', _h(f"{(main['resultado'] or main['estado'] or '').replace('_', ' ').capitalize()} · " +
                                   (f"venció {_dm(main['vence'])}" if main.get('vencida') else f"vence {_dm(main['vence'])}" if not posventa else f"ganada {_dm(main['fecha_ganada'])}")),
                  'rd' if main.get('vencida') else ''),
                 ('Precio', _h((f"{_usd(it['precio'])} c/u" if it.get('precio') else 'a confirmar') + (f" + IVA {str(ivap).replace('.', ',').replace(',0', '')} %" if ivap else '')), ''),
                 ('Total con IVA', f"<b>{_h(_usd(main['total']))}</b>", '')]
        if len(main['items']) > 1:
            filas.insert(1, ('Ítems', _h(f"{len(main['items'])} renglones"), ''))
        for x in main['items'][:3]:
            s = _stock(db, x)
            nom = _corto(x.get('articulo'), 24) if len(main['items']) > 1 else ''
            if s is None or not s['cant']:
                filas.append(('Stock', _h(f"{nom + ': ' if nom else ''}sin stock en R8 al {_dm(corte.get('R8'))} · confirmar con JP"), 'am'))
            else:
                filas.append(('Stock', _h(f"{nom + ': ' if nom else ''}{_cant(s['cant'])} en R8 al {_dm(corte.get('R8'))} · confirmar con JP"), 'am'))
        if posventa:
            filas += [('Despacho', _h(main['despacho'] or 'sin dato'), '' if main['despacho'] == 'confirmado' else 'am'),
                      ('Pago', _h(main['pago'] or 'sin dato'), '')]
        otras = [c for c in ab if c is not main]
        if otras:
            filas.append(('También abiertas', _h(' · '.join(f"{c['numero']} {_usd(c['total'])}" for c in otras)), ''))
        unidad = _unidad(it)
        p.append(f'<div class="pz" id="p2"><div class="card main"><span class="pill {"pg" if posventa else "pb"}">{"Posventa" if posventa else "Prioridad comercial"}</span>'
                 f'<h2>{_h(main["numero"])} · {_h(_corto(it.get("articulo") or main["familia"], 40))}</h2>'
                 f'<div class="sub">Cotizada el {_dm(main["fecha"])}' + (f' a {_h(main["cliente"])}' if norm(main['cliente']) != norm(razon) else '')
                 + (f' · revisión {_dm(main["revision"])}' if main.get('revision') else '') + '</div>'
                 f'<div class="big">{_h(_cant(it.get("cantidad")) if it.get("cantidad") else "-")} <small>{unidad}</small></div>'
                 + ''.join(f'<div class="row"><span>{a}</span><span class="{c}">{b}</span></div>' for a, b, c in filas) + '</div></div>')
    else:
        p.append('<div class="pz" id="p2"><div class="card main"><span class="pill pa">Sin operación</span><h2>No hay cotización abierta</h2>'
                 '<div class="sub">El CRM no tiene cotizaciones vivas para este CUIT.</div></div></div>')
    # ---- tarjeta 3
    per = f"Historial {d['periodo']}" if d['periodo'] != 'completo' else 'Historial completo'
    rows = ''.join(f'<div class="row"><span>{_dm(c["fecha"])}</span><span class="{"rd" if c["nc"] else ""}">'
                   f'{_h(("NC " if c["nc"] else "") + _corto(" + ".join(c["lineas"]), 60))} · {_h(_usd(c["importe"]))}</span></div>' for c in d['comp'][-8:])
    if len(d['comp']) > 8:
        rows = f'<div class="row"><span>…</span><span>{len(d["comp"]) - 8} comprobantes anteriores</span></div>' + rows
    if d['pago']:
        rows += f'<div class="row"><span>Pago habitual</span><span>{_h(d["pago"])}</span></div>'
    p.append(f'<div class="pz" id="p3"><div class="card"><span class="pill pg">Facturación confirmada</span><h2>{per}</h2>'
             f'<div class="sub">R10 al {_dm(corte.get("R10"))} · sin IVA · NC restadas · solo este CUIT</div>'
             f'<div class="big">{_h(_usd(d["ventas_total"]))} <small>{len(d["comp"])} comprobantes</small></div>{rows or "<div class=row><span>Sin compras</span><span>-</span></div>"}</div></div>')
    # ---- tarjeta 4
    av = []
    venc = [c for c in d['abiertas'] if c['vencida']]
    if venc:
        av.append(f"<b class=rd>Vencidas:</b> {_h(' · '.join(c['numero'] + ' (' + _dm(c['vence']) + ')' for c in venc))}: elegí nuevo estado o perdida.")
    if op.get('proxima_fecha') and op['proxima_fecha'][:10] < hoy:
        av.append(f"El <b>seguimiento del {_dm(op['proxima_fecha'])}</b> está vencido.")
    if not op.get('marca_olt'):
        av.append('La ficha no tiene <b>OLT cargada</b>' + (' (usa FiberHome).' if op.get('usa_fh') == 'si' else '.'))
    elif not op.get('modelo_olt'):
        av.append(f"OLT {_h(op['marca_olt'])} sin modelo cargado.")
    ont = any(re.search(r'\b(ont|onu)\b', (x.get('articulo') or '').lower()) for c in d['abiertas'] for x in c['items'])
    if ont and op.get('olt_fh') != 'si':
        av.append('<span class=am>Se ofrece ONT FH: confirmar compatibilidad con la OLT.</span>')
    if main and norm(main['cliente']) != norm(razon):
        av.append(f"{_h(main['numero'])} está a nombre de <b>{_h(main['cliente'])}</b>: definir qué razón social factura.")
    for m in d['muestras']:
        av.append(f"<span class=am>Muestra {_h(_corto(m['productos'], 60))}: {_h(m['estado'] or 'sin estado')}.</span>")
    for g in d['gsd']:
        av.append(f"{_h(g['numero'])} ganada: {_h(g['falta'])} (cargar en el CRM).")
    for nom, c, s in d['grupo_ventas']:
        av.append(f"{_h(nom)} (mismo grupo) compró {_h(_usd(s))} en {d['hoy'][:4]}: no está sumado acá.")
    acc = []
    if d['hist']:
        acc.append(('ok', f"{_dm(d['hist']['t'])} · {_corto(d['hist']['txt'], 150)}"))
    if op.get('proxima_accion'):
        for k, x in enumerate(op['proxima_accion'].split(' · ')):
            acc.append(('ck', (f"{_dm(op['proxima_fecha'])} · " if k == 0 and op.get('proxima_fecha') else '') + _corto(x, 140)))
    for c in venc:
        if c['numero'] not in (op.get('proxima_accion') or ''):
            acc.append(('ck', f"Renovar {c['numero']} o marcarla perdida"))
    if op.get('proxima_fecha') and op['proxima_fecha'][:10] < hoy:
        acc.append(('ck', 'Poner fecha nueva al seguimiento en el CRM'))
    if d['contactos']:
        c0 = d['contactos'][0]
        acc.append(('ck', f"Contacto: {c0['nombre'] or '-'}" + (f" ({c0['celular']})" if c0.get('celular') else '')))
    p.append('<div class="pz" id="p4"><div class="box"><h3>Antes de avanzar</h3>' + ('<br>'.join(av) or 'Nada pendiente de confirmar.') + '</div>'
             '<div class="box"><h3>Próxima acción sugerida</h3><ul>' + ''.join(f'<li class="{a}">{_h(b)}</li>' for a, b in acc) + '</ul></div></div>')
    return (f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Status {_h(razon)}</title><style>{ST_CSS}</style></head><body>' + re.sub(r'Finnegans', 'facturación', ''.join(p), flags=re.I) + '</body></html>')


def status_control(db, d, html):
    """Auditor: recalcula desde la base, sin usar lo que armó status_datos, y lo busca en la tarjeta publicada."""
    import html as H
    t = H.unescape(re.sub(r'<[^>]+>', ' ', html))
    t = re.sub(r'\s+', ' ', t)
    f = []
    if d['cuit'] not in t:
        f.append('falta el CUIT')
    for i in (1, 2, 3, 4):
        if f'id="p{i}"' not in html:
            f.append(f'falta la parte {i}')
    if re.search(r'<button|class="btn"|↗', html):
        f.append('la tarjeta tiene botones')
    anio = d['hoy'][:4]
    s = q(db, "SELECT COALESCE(SUM(importe),0) s, COUNT(DISTINCT comprobante) n FROM ventas WHERE cuit=? AND empresa LIKE 'HORIZON TRADING%'"
          + (" AND substr(fecha,1,4)=?" if d['periodo'] != 'completo' else ''), *([d['cuit'], anio] if d['periodo'] != 'completo' else [d['cuit']]))[0]
    if _usd(s['s']) not in t:
        f.append(f"ventas: la base da {_usd(s['s'])} y no está en la tarjeta")
    if f"{s['n']} comprobantes" not in t:
        f.append(f"ventas: la base da {s['n']} comprobantes")
    ab = q(db, "SELECT numero, total, vence FROM crm_cotizacion WHERE cuit=? AND archivada=0 AND motivo_perdida IS NULL AND lower(COALESCE(estado,'')) NOT IN (%s)"
           % ','.join('?' * len(ST_CERRADAS)), d['cuit'], *ST_CERRADAS)
    for c in ab:
        if c['numero'] not in t or _usd(c['total']) not in t:
            f.append(f"cotización abierta {c['numero']} {_usd(c['total'])} no está en la tarjeta")
        if c['vence'] and c['vence'][:10] < d['hoy'] and not re.search(re.escape(c['numero']) + r' \(' + _dm(c['vence']), t):
            f.append(f"{c['numero']} vencida el {_dm(c['vence'])} sin aviso")
    if 'Finnegans' in t:
        f.append('dice Finnegans en pantalla (D10)')
    return f


ST_MOTOR = '1.7.1'
ST_TABLAS = ('crm_oportunidad', 'crm_cotizacion', 'crm_cotizacion_item', 'crm_historial', 'crm_contacto', 'crm_muestra',
             'ventas', 'stock', 'cargas', 'clientes', 'cliente_alias')
ST_DDL = ['CREATE TABLE IF NOT EXISTS status_cliente (cuit TEXT PRIMARY KEY, razon TEXT, crm_id TEXT, html TEXT NOT NULL, '
          'historial TEXT, control TEXT, resumen TEXT, crm_corte TEXT, r10_corte TEXT, motor TEXT, calculado TEXT)',
          'CREATE TABLE IF NOT EXISTS status_pagina (cuit TEXT PRIMARY KEY, url TEXT NOT NULL, actualizado TEXT)']


def _copia_local(db):
    """Copia en memoria de las tablas que usa la tarjeta: el cálculo de todas las fichas no va y viene a Turso."""
    loc = Local(':memory:')
    # 1.8.0: definiciones + datos de las 11 tablas + vista en 1 viaje (antes 23)
    res = db.run([("SELECT name, sql FROM sqlite_master WHERE name IN (%s)" % ','.join('?' * len(ST_TABLAS)), list(ST_TABLAS))]
                 + [(f'SELECT * FROM {t}', []) for t in ST_TABLAS]
                 + [('SELECT numero, cuit, falta FROM v_ganadas_sin_despacho', [])])
    ddl = {n: s_ for n, s_ in res[0][1]}
    for t, (cols, filas) in zip(ST_TABLAS, res[1:-1]):
        loc.run([(ddl[t], [])])
        if filas:
            loc.run([(f'INSERT INTO {t} VALUES ({",".join("?" * len(cols))})', f) for f in filas])
    loc.run([('CREATE TABLE v_ganadas_sin_despacho (numero TEXT, cuit TEXT, falta TEXT)', [])]
            + [('INSERT INTO v_ganadas_sin_despacho VALUES (?,?,?)', f) for f in res[-1][1]])
    return loc


def _resumen(d):
    venc = [x['numero'] for x in d['abiertas'] if x['vencida']]
    return (f"{_usd(sum(x['total'] or 0 for x in d['abiertas']))} cotizados en {len(d['abiertas'])} abiertas"
            + (f" · vencidas {', '.join(venc)}" if venc else '') + f" · ventas {d['periodo']} {_usd(d['ventas_total'])}")


def status_calcular(db, hoy=None, solo=None):
    """Cálculo previo: todas las fichas vivas del CRM (con CUIT) de una vez → status_cliente. Se corre al llegar CRM o R10."""
    import time
    t0 = time.time()
    loc = _copia_local(db)
    hoy = hoy or q(loc, f'SELECT {HOY_AR} d')[0]['d']
    corte = {r['fuente']: r['corte'] for r in q(loc, "SELECT fuente, MAX(corte) corte FROM cargas GROUP BY fuente")}
    cuits = solo or [r['cuit'] for r in q(loc, "SELECT DISTINCT cuit FROM crm_oportunidad WHERE cuit IS NOT NULL AND archivada=0")]
    st, fallan, cuando = [(x, []) for x in ST_DDL], [], ahora()
    for c in cuits:
        d = status_datos(loc, c, hoy)
        html = status_html(loc, d)
        f = status_control(loc, d, html)
        if f:
            fallan.append((c, f))
        st.append(('INSERT OR REPLACE INTO status_cliente VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   [c, d['op'].get('empresa'), d['op'].get('id'), html, jdump(d['historial']), jdump(f), _resumen(d),
                    corte.get('crm:oportunidades'), corte.get('R10'), ST_MOTOR, cuando]))
    t1 = time.time()
    transaccion(db, st)
    return dict(fichas=len(cuits), fallan=fallan, calculo_s=round(t1 - t0, 1), total_s=round(time.time() - t0, 1),
                crm=corte.get('crm:oportunidades'), r10=corte.get('R10'))


def status_pagina(fila, pngs, url_fondo=''):
    """Página del panel lateral: 2 columnas sin huecos (1+3 | 2+4), una sola en el celular (1-2-3-4), botones de verdad."""
    import html as H
    img = lambda k: 'data:image/png;base64,' + base64.b64encode(open(pngs[k], 'rb').read()).decode()
    texto = H.unescape(re.sub(r'<[^>]+>', ' ', re.sub(r'</(div|li|h1|h2|h3)>', '\n', fila['html'])))
    texto = '\n'.join(' '.join(x.split()) for x in texto.splitlines() if x.strip())
    hist = json.loads(fila['historial'] or '[]')
    filas = ''.join(f'<tr class="{"nc" if "Crédito" in (h.get("documento") or "") else ""}"><td>{_dm(h["fecha"])}/{str(h["fecha"])[2:4]}</td>'
                    f'<td>{_h(h["comprobante"])}</td><td>{_h(" + ".join(h["productos"]))}</td><td class="n">{_h(_usd(h["neto"]))}</td>'
                    f'<td class="n">{_h(_usd(h["total"]))}</td></tr>' for h in reversed(hist))
    hist_txt = '\n'.join(f"{h['fecha']} {h['comprobante']} {h.get('documento') or ''}: {' + '.join(h['productos'])} · neto {_usd(h['neto'])} · total {_usd(h['total'])}" for h in hist)
    pie = (f"{fila['razon'] or '-'} · CUIT {fila['cuit']} · motor {fila['motor']} · CRM {_dm(fila['crm_corte'])} · R10 {_dm(fila['r10_corte'])}"
           f" · calculado {_dm(fila['calculado'])} {str(fila['calculado'])[11:16]} UTC · control {'PASA' if fila['control'] in ('[]', None) else 'FALLA'}")
    return f"""<title>Status {_h(fila['razon'] or fila['cuit'])}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
/* Panel lateral: dos columnas de imágenes sin huecos (1+3 | 2+4); una sola columna en el celular (1-2-3-4) */
:root{{--bg:#12151C;--line:#2d323a;--tx:#eef0f3;--mut:#9aa3ae;--ac:#5b8cff;--rd:#ff6b61;color-scheme:dark}}
body{{background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
padding-block:16px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}}
.wrap{{display:flex;gap:12px;align-items:flex-start;max-width:1100px;margin:0 auto}}
.col{{flex:1 1 0;min-width:0;display:flex;flex-direction:column;gap:12px}}
.col img{{width:100%;display:block}}
.grp{{display:flex;flex-direction:column;gap:10px;min-width:0}}
.btn{{align-self:flex-start;background:transparent;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:7px 14px;font:inherit;cursor:pointer}}
.btn:hover{{border-color:var(--ac)}}.btn:focus-visible{{outline:2px solid var(--ac);outline-offset:2px}}
.panel{{border:1px solid var(--line);border-radius:12px;padding:12px 14px;min-width:0}}
.tabla{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;min-width:560px;font-size:12.5px;font-variant-numeric:tabular-nums}}
td,th{{text-align:left;padding:6px 8px;border-top:1px solid var(--line);vertical-align:top}}th{{color:var(--mut);font-weight:500;border-top:0}}
td.n,th.n{{text-align:right;white-space:nowrap}}td:nth-child(-n+2){{white-space:nowrap}}tr.nc td{{color:var(--rd)}}
#eval{{white-space:pre-wrap}}.mut{{color:var(--mut);font-size:12px}}
.pie{{max-width:1100px;margin:14px auto 0;color:var(--mut);font-size:12px}}
@media (max-width:720px){{.wrap{{flex-direction:column}}.col{{display:contents}}
#b1{{order:1}}#b2{{order:2}}#b3{{order:3}}#b4{{order:4}}.wrap>.col>*{{width:100%}}.wrap{{gap:12px}}}}
</style>
<div class="wrap">
 <div class="col">
  <div id="b1"><img src="{img(0)}" alt="Cabecera y alerta"></div>
  <div id="b3" class="grp"><img src="{img(2)}" alt="Facturación confirmada">
   <button class="btn" id="verHist" type="button" aria-expanded="false">Ver historial ↗</button>
   <div class="panel" id="hist" hidden><div class="tabla"><table><thead><tr><th>Fecha</th><th>Comprobante</th><th>Productos</th><th class="n">Neto</th><th class="n">Total c/IVA</th></tr></thead>
   <tbody>{filas or '<tr><td colspan="5">Sin comprobantes en R10.</td></tr>'}</tbody></table></div><div class="mut">R10 al {_dm(fila['r10_corte'])} · todos los comprobantes de este CUIT · NC en rojo</div></div>
  </div>
 </div>
 <div class="col">
  <div id="b2" class="grp"><img src="{img(1)}" alt="Prioridad comercial">
   <button class="btn" id="evalBtn" type="button" hidden>Evaluar cotización ↗</button>
   <div class="panel" id="evalBox" hidden><div id="eval"></div><div class="mut" id="evalNota">Claude con el texto de la tarjeta y el historial, nada más.</div></div>
  </div>
  <div id="b4"><img src="{img(3)}" alt="Antes de avanzar y próxima acción"></div>
 </div>
</div>
<div class="pie">{_h(pie)}</div>
<script>
const TARJETA = {json.dumps(texto, ensure_ascii=False)};
const HISTORIAL = {json.dumps(hist_txt, ensure_ascii=False)};
const vh = document.getElementById('verHist'), hb = document.getElementById('hist');
vh.addEventListener('click', () => {{ hb.hidden = !hb.hidden; vh.setAttribute('aria-expanded', String(!hb.hidden)); vh.textContent = hb.hidden ? 'Ver historial ↗' : 'Ocultar historial'; }});
(async () => {{
  const sample = window.claude ? await window.claude.use('sample') : null;
  if (!sample) return;
  const b = document.getElementById('evalBtn'), box = document.getElementById('evalBox'), out = document.getElementById('eval');
  b.hidden = false;
  let busy = false;
  b.addEventListener('click', async () => {{
    if (busy) return; busy = true; box.hidden = false; out.textContent = 'Pensando…'; b.disabled = true;
    const pedido = 'Sos Loki, asistente comercial de Nicolás (ventas, Horizon Trading, distribuidor FTTH). Evaluá la cotización principal de esta tarjeta en EXACTAMENTE 5 líneas cortas, en castellano rioplatense: 1) qué tan viva está y por qué, 2) riesgo principal, 3) qué dice el historial de compras, 4) qué confirmar antes de avanzar, 5) la próxima acción concreta con quién. Usá SOLO el texto de abajo; si algo no está, decí que no está. No inventes precios, stock ni fechas.\\n\\nTARJETA:\\n' + TARJETA + '\\n\\nHISTORIAL DE COMPROBANTES:\\n' + (HISTORIAL || 'sin comprobantes');
    try {{
      const r = await sample(pedido, {{ onText: ({{text}}) => {{ out.textContent = text; }}, modelTier: 'default' }});
      out.textContent = r.text;
    }} catch (e) {{
      if (e && e.code === 'not_granted') {{ box.hidden = true; b.hidden = true; }}
      else out.textContent = (e && e.code === 'rate_limited') ? 'Claude está ocupado: probá de nuevo en un rato.' : 'No se pudo evaluar: ' + ((e && e.message) || 'error');
    }} finally {{ busy = false; b.disabled = false; }}
  }});
}})();
</script>"""


def status_viejo(db):
    """Qué fuentes llegaron después del último status-calcular (vacío = al día). Sin tabla = nunca se calculó."""
    try:   # 1.8.0: un viaje (antes 3)
        u, fu = qs(db, ['SELECT MAX(calculado) c FROM status_cliente',
                        "SELECT fuente, MAX(cargado) c FROM cargas WHERE fuente IN ('crm:oportunidades','crm:cotizaciones',"
                        "'crm:muestras','R10','R8') GROUP BY fuente"])
    except Exception:  # noqa: BLE001  no existe la tabla
        return ['nunca se calculó']
    ult = u[0]['c']
    if not ult:
        return ['status_cliente vacía']
    return [r['fuente'] for r in fu if r['c'] > ult]


def status_pedir(db, texto, salida, hoy=None):
    """Pedir un status = leer la fila precalculada (CUIT o comienzo de palabra de la razón social), sacar 4 PNG y armar la página."""
    c = cuit_ok(texto)
    if c:
        filas = q(db, 'SELECT * FROM status_cliente WHERE cuit=?', c)
    else:
        n = norm(texto)
        filas = [r for r in q(db, 'SELECT * FROM status_cliente') if n and (' ' + n) in (' ' + norm(r['razon'] or ''))]
        if not filas:
            filas = [r for r in q(db, 'SELECT s.* FROM status_cliente s JOIN cliente_alias a USING (cuit) WHERE a.alias_norm LIKE ?', f'{n}%')]
        filas = list({r['cuit']: r for r in filas}.values())
    if not filas:
        return 1, [f'no está en status_cliente: {texto} (correr status-calcular o buscar por CUIT)'], None
    if len(filas) > 1:
        return 2, ['AMBIGUO (elegí por CUIT): ' + ' · '.join(f"{r['cuit']} {r['razon']}" for r in filas[:12])], None
    f = filas[0]
    os.makedirs(salida, exist_ok=True)
    base = re.sub(r'[^a-z0-9]+', '_', norm(f['razon'] or f['cuit'])).strip('_') or 'cliente'
    hp = os.path.join(salida, f'{base}_tarjeta.html')
    open(hp, 'w', encoding='utf-8').write(f['html'])
    jp = os.path.join(salida, 'tarjeta_png.js')
    open(jp, 'w', encoding='utf-8').write(ST_JS)
    r = subprocess.run(['node', jp, os.path.abspath(hp), os.path.abspath(os.path.join(salida, base))], capture_output=True, text=True, timeout=180)
    if r.returncode:
        return 1, ['imágenes: ' + (r.stderr.strip().splitlines() or ['node falló'])[-1]], None
    pngs = r.stdout.split()
    pp = os.path.join(salida, f'{base}.html')
    open(pp, 'w', encoding='utf-8').write(status_pagina(f, pngs))
    url = q(db, 'SELECT url FROM status_pagina WHERE cuit=?', f['cuit']) if q(db, "SELECT name FROM sqlite_master WHERE name='status_pagina'") else []
    ctrl = json.loads(f['control'] or '[]')
    out = [f'PAGINA {pp}', 'URL ' + (url[0]['url'] if url else 'nueva (publicar y guardar con status-url)'), f"CUIT {f['cuit']}",
           f"RESUMEN {f['resumen']}", f"DATOS CRM {_dm(f['crm_corte'])} · R10 {_dm(f['r10_corte'])} · calculado {f['calculado']} · motor {f['motor']}",
           'CONTROL: PASA' if not ctrl else 'CONTROL: FALLA · ' + ' · '.join(ctrl)]
    return (0 if not ctrl else 1), out, pp


def status_vivo(db, texto, salida, hoy=None, png=True):
    """Arma la tarjeta, la controla y la corta en 4 PNG. Devuelve (exit, líneas)."""
    c = buscar_cuit(db, texto)
    if not c:
        return 1, [f'no está: {texto} (sin CUIT en clientes; buscar en el CRM)']
    if len(c) > 1:
        return 2, ['AMBIGUO (D03, elegí por CUIT): ' + ' · '.join(f'{a} {b}' for a, b in c[:12])]
    hoy = hoy or q(db, f'SELECT {HOY_AR} d')[0]['d']
    d = status_datos(db, c[0][0], hoy)
    html = status_html(db, d)
    os.makedirs(salida, exist_ok=True)
    base = re.sub(r'[^a-z0-9]+', '_', norm(d['op'].get('empresa') or c[0][1] or c[0][0])).strip('_') or 'cliente'
    hp = os.path.join(salida, f'{base}.html')
    with open(hp, 'w', encoding='utf-8') as fh:
        fh.write(html)
    fallas = status_control(db, d, html)
    out = [f'FICHA {hp}']
    if png:
        jp = os.path.join(salida, 'tarjeta_png.js')
        with open(jp, 'w', encoding='utf-8') as fh:
            fh.write(ST_JS)
        r = subprocess.run(['node', jp, os.path.abspath(hp), os.path.abspath(os.path.join(salida, base))], capture_output=True, text=True, timeout=180)
        if r.returncode:
            fallas.append('imágenes: ' + (r.stderr.strip().splitlines() or ['node falló'])[-1])
        else:
            out += ['PNG ' + x for x in r.stdout.split()]
    venc = [x['numero'] for x in d['abiertas'] if x['vencida']]
    out.append(f"RESUMEN {_usd(sum(x['total'] or 0 for x in d['abiertas']))} cotizados en {len(d['abiertas'])} abiertas"
               + (f" · vencidas {', '.join(venc)}" if venc else '') + f" · ventas {d['periodo']} {_usd(d['ventas_total'])}")
    out.append('CONTROL: PASA' if not fallas else 'CONTROL: FALLA · ' + ' · '.join(fallas))
    return (0 if not fallas else 1), out


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__); return 0
    if argv[0] == '--autotest':
        return autotest()
    op, a = argv[0], argv[1:]
    db = conectar()
    try:
        if op == 'init':
            init(db); print('OK esquema', ESQUEMA)
        elif op == 'abrir':
            hoy = a[1]
            return abrir(db, a[0], hoy, a[a.index('--crm') + 1] if '--crm' in a else None, '--reglas' in a, '--incremental' in a)
        elif op == 'crm-desde':
            print(crm_desde(db, date.fromisoformat(a[0]) if a else date.today()))
        elif op == 'estado':
            return estado(db, date.today())
        elif op == 'sql':
            if not re.match(r'^\s*(select|with|pragma)\b', a[0], re.I) or ';' in a[0].strip().rstrip(';'):
                print('solo lectura: SELECT / WITH / PRAGMA (una sentencia)'); sys.exit(1)
            for r in q(db, a[0]):
                print(json.dumps(r, ensure_ascii=False))
        elif op == 'doc':
            t = doc(db, a[0], a[a.index('--seccion') + 1] if '--seccion' in a else None)
            print(t if t is not None else f'no está: {a[0]}'); return 0 if t else 1
        elif op == 'bajar':
            f, _ = bajar(db, a[0]); print(*(f or ['OK bajado']), sep='\n'); return 1 if f else 0
        elif op == 'cargar-reporte':
            print('OK', a[0], cargar_reporte(db, a[0], a[1], a[2]), 'filas')
        elif op == 'registrar-reporte':
            print('OK registrado', registrar_reporte(db, a[0]))
        elif op == 'bajar-reportes':
            n, f = bajar_reportes(db, a[0]); print(*(f or [f'OK {n} definiciones + CSV cargados + auditar.py → {a[0]}']), sep='\n'); return 1 if f else 0
        elif op == 'reportes':
            print(reportes_lista(db))
        elif op == 'cargar-recompra':
            print('OK recompra', cargar_recompra(db, a[0], a[1]), 'filas')
        elif op == 'cargar-crm':
            f = a[a.index('--fecha') + 1] if '--fecha' in a else date.today().isoformat()
            print('OK crm', cargar_crm(db, a[0], f, '--incremental' in a))
        elif op == 'cargar-memoria':
            print('OK memoria', cargar_memoria(db, a[0]))
        elif op == 'cargar-continuidad':
            cargar_continuidad(db, a[0]); print('OK continuidad')
        elif op == 'regla':
            t = regla(db, a[0]); print(t or f'no está: {a[0]}'); return 0 if t else 1
        elif op == 'reglas':
            print(reglas_lista(db, a[a.index('--tipo') + 1] if '--tipo' in a else None, a[a.index('--estado') + 1] if '--estado' in a else None))
        elif op == 'pendientes':
            print(reglas_lista(db, 'pendiente'))
        elif op == 'intencion':
            print(intencion(db, a[0], '--texto' in a))
        elif op == 'indexar-cerebro':
            print('OK indexado', indexar(db))
        elif op == 'cargar-cerebro':
            print('OK cerebro', cargar_cerebro(db, a[0]), 'documentos')
        elif op == 'ficha':
            print(ficha(db, ' '.join(a) if a else None))
        elif op == 'cargar-fichas':
            print('OK fichas', cargar_fichas(db, a[0], a[1] if len(a) > 1 else date.today().isoformat()))
        elif op == 'bitacora':
            g = lambda k: a[a.index(k) + 1] if k in a else None
            cu = g('--cuit')
            if cu and not cuit_ok(cu):
                c = buscar_cuit(db, cu)
                if len(c) != 1:
                    print('AMBIGUO o no está: ' + ' · '.join(f'{x} {y}' for x, y in c[:10])); return 1
                cu = c[0][0]
            print(bitacora(db, cuit_ok(cu) if cu else None, '--abiertos' in a, g('--tipo'), g('--buscar'), g('-n') or 15))
        elif op == 'anotar':
            g = lambda k: a[a.index(k) + 1] if k in a else None
            i = anotar(db, a[0], a[1], a[2], cuit=g('--cuit'), cuenta=g('--cuenta'), fuente=g('--fuente'), chat=g('--chat'), cierra=g('--cierra'))
            print(f'OK bitácora #{i}')
        elif op == 'cerrar':
            i = anotar(db, 'hecho', 'cierra #' + a[0], a[1], cierra=a[0], chat=a[a.index('--chat') + 1] if '--chat' in a else None)
            print(f'OK #{a[0]} cerrado por #{i}')
        elif op == 'migrar-continuidad':
            armar_clientes(db); print('OK migradas', migrar_continuidad(db), 'filas')
        elif op == 'armar-crm':
            print('OK crm en tablas', armar_crm(db))
        elif op == 'armar-clientes':
            print('OK clientes %s · alias %s' % armar_clientes(db))
        elif op == 'calidad':
            print(calidad(db, True))
        elif op == 'cliente':
            print(cliente(db, ' '.join(a)))
        elif op in ('status', 'status-vivo'):
            g = lambda k: a[a.index(k) + 1] if k in a else None
            nombre = ' '.join(x for i, x in enumerate(a) if not x.startswith('--') and (i == 0 or a[i - 1] not in ('--salida', '--hoy')))
            sal = g('--salida') or os.path.join(tempfile.gettempdir(), 'loki_status')
            if op == 'status':
                ex, lineas, _ = status_pedir(db, nombre, sal)
            else:
                ex, lineas = status_vivo(db, nombre, sal, g('--hoy'), '--sin-png' not in a)
            print(*lineas, sep='\n'); return ex
        elif op == 'status-calcular':
            r = status_calcular(db, a[a.index('--hoy') + 1] if '--hoy' in a else None)
            print(f"OK status {r['fichas']} fichas · cálculo {r['calculo_s']} s · total {r['total_s']} s · CRM {r['crm']} · R10 {r['r10']} · motor {ST_MOTOR}")
            print(f"CONTROL: {'PASA' if not r['fallan'] else 'FALLA en ' + str(len(r['fallan'])) + ' fichas'}")
            for c, f in r['fallan'][:20]:
                print(' ', c, '·', ' · '.join(f))
            return 0 if not r['fallan'] else 1
        elif op == 'status-url':
            c = cuit_ok(a[0])
            if not c or not re.match(r'^https://claude\.ai/(code/)?artifact/[A-Za-z0-9-]+$', a[1]):
                print('uso: status-url CUIT https://claude.ai/artifact/ID'); return 1
            transaccion(db, [(x, []) for x in ST_DDL] + [('INSERT OR REPLACE INTO status_pagina VALUES (?,?,?)', [c, a[1], ahora()])])
            print('OK', c, a[1])
        elif op == 'conocimiento-cargar':
            print('OK conocimiento', conocimiento_cargar(db, leer_json(a[0])))
        elif op == 'cargar-script':
            print('OK script', a[0], cargar_script(db, a[0], a[1], a[2])[:12])
        else:
            print(__doc__); return 1
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
