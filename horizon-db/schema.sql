-- Horizon DB · esquema base
-- Llave de todo: el CUIT del cliente. Montos en USD sin IVA.

CREATE TABLE IF NOT EXISTS clientes (
  cuit        TEXT PRIMARY KEY,
  nombre      TEXT NOT NULL,
  segmento    TEXT,              -- ISP, integrador, gobierno, etc.
  puntaje     INTEGER,           -- del motor 1.0 (0-100)
  marca_olt   TEXT,              -- marca de OLT que usa
  usa_fh      INTEGER DEFAULT 0, -- 1 si usa FiberHome
  ciudad      TEXT,
  notas       TEXT,
  actualizado TEXT               -- AAAA-MM-DD
);

CREATE TABLE IF NOT EXISTS contactos (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  cuit      TEXT NOT NULL REFERENCES clientes(cuit),
  nombre    TEXT NOT NULL,
  cargo     TEXT,
  telefono  TEXT,
  email     TEXT
);

CREATE TABLE IF NOT EXISTS oportunidades (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  cuit        TEXT NOT NULL REFERENCES clientes(cuit),
  titulo      TEXT,
  etapa       TEXT,              -- prospecto, cotizada, negociacion, ganada, perdida
  monto_usd   REAL,
  probabilidad INTEGER,          -- %
  fecha       TEXT,
  actualizado TEXT
);

CREATE TABLE IF NOT EXISTS cotizaciones (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  cuit      TEXT NOT NULL REFERENCES clientes(cuit),
  numero    TEXT,
  fecha     TEXT,
  total_usd REAL,
  estado    TEXT                 -- enviada, aceptada, vencida
);

CREATE TABLE IF NOT EXISTS ventas (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  cuit      TEXT NOT NULL REFERENCES clientes(cuit),
  fecha     TEXT,
  factura   TEXT,
  total_usd REAL,
  detalle   TEXT
);

CREATE TABLE IF NOT EXISTS productos (
  codigo      TEXT PRIMARY KEY,
  descripcion TEXT NOT NULL,
  categoria   TEXT,              -- OLT, ONT, placa, SFP, cable, pasivo, energia
  precio_usd  REAL,
  stock       INTEGER
);

CREATE TABLE IF NOT EXISTS seguimientos (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  cuit        TEXT NOT NULL REFERENCES clientes(cuit),
  fecha_prox  TEXT,              -- AAAA-MM-DD cuando toca
  prioridad   INTEGER DEFAULT 3, -- 1 alta, 2 media, 3 baja
  motivo      TEXT,
  estado      TEXT DEFAULT 'pendiente', -- pendiente, hecho
  actualizado TEXT
);

CREATE TABLE IF NOT EXISTS minutas (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  cuit      TEXT NOT NULL REFERENCES clientes(cuit),
  fecha     TEXT,
  canal     TEXT,                -- whatsapp, llamada, mail, visita
  texto     TEXT,                -- qué pasó
  pendiente TEXT,                -- qué quedó sin resolver
  accion    TEXT                 -- qué toca hacer
);

CREATE INDEX IF NOT EXISTS idx_seg_fecha ON seguimientos(fecha_prox, estado);
CREATE INDEX IF NOT EXISTS idx_cli_nombre ON clientes(nombre);
CREATE INDEX IF NOT EXISTS idx_prod_desc ON productos(descripcion);
