"""Recompra por cliente + SKU desde el Data Center (R10 facturación por renglón, 2024→).
Reglas: Empresa HORIZON; NC electrónicas neteadas por cantidad; notas por diferencia de cambio afuera;
v3 09/11: cada NC anula lo ultimo facturado antes que ella por TransaccionID; líneas vigentes FH/Ousent/Huawei/ZTT (+HW no Cisco);
discontinuados se marcan para reemplazo. Pte Dest > 0 = facturado sin entregar. IVA Huawei debe ser 10,5 %.
"""
import pandas as pd, numpy as np, json, sys

HOY = pd.Timestamp(sys.argv[1] if len(sys.argv) > 1 else pd.Timestamp.today().date())
NOPROS = ['pogliotti','itsa','amma','mutual mercantil','obercom','wiltel','gigared','astesano','generaci','itc comunic',
          'ax internet','fibrazo','tv music','support internet','itelsa','comworks',
          'fesacom','sur technology','presupuesto horizon','horizon trading']
VIG = {'FiberHome','Ousent','Huawei','ZTT'}
CISCO_PAT = r'UBR|ESR|C7200|CMTS|ERB'

r = pd.read_csv('R10.csv', sep=';', dtype=str)
r = r[r['Empresa'].str.strip() == 'HORIZON TRADING S.A.']
doc = r['Documento'].str.lower()
r = r[~doc.str.contains('dif. cambio') & ~doc.str.contains('débito')]
es_nc = r['Documento'].str.lower().str.contains('crédito')
r['cant'] = pd.to_numeric(r['Cantidad'], errors='coerce').fillna(0).where(~es_nc, -pd.to_numeric(r['Cantidad'], errors='coerce').fillna(0).abs())  # v2 07/11: la NC ya viene negativa en R10; se fuerza negativa sin invertir
r['fecha'] = pd.to_datetime(r['Fecha'])
r['pte'] = pd.to_numeric(r['Pte Dest.'], errors='coerce').fillna(0)
r['iva'] = pd.to_numeric(r['Tasa impositiva'], errors='coerce')
r['imp'] = pd.to_numeric(r['Importe'], errors='coerce').fillna(0).where(~es_nc, -pd.to_numeric(r['Importe'], errors='coerce').fillna(0).abs())
r['marca'] = r['Marca'].fillna('').str.strip()
r['prod'] = r['Producto'].fillna('').str.strip()
r['cli'] = r['Cliente'].fillna('').str.strip()

def linea(row):
    m = row['marca']
    if m in VIG: return m
    if m == 'HW':
        return 'HFC disc' if pd.Series([row['prod']]).str.contains(CISCO_PAT, case=False).iloc[0] else 'Huawei'
    return 'otra'
r['linea'] = r.apply(linea, axis=1)
EXACTOS = {'itel s.a.','sion s.a.'}
r['nopros'] = r['cli'].str.lower().apply(lambda c: c in EXACTOS or any(k in c for k in NOPROS))

# --- no son productos (servicios, licencias, intereses, anticipos) ---
NOPROD = r'Hi-Care|Series Basic SW|upgrade RTU|Intereses|Servicios Admin|Gastos de Admin|Anticipo|Flete|Licencia|Descuento'
r = r[~r['prod'].str.contains(NOPROD, case=False, regex=True)]

# --- familia comercial: las ONT FH se miden juntas (el cliente cambia de modelo, no deja de comprar) ---
es_ont = r['prod'].str.contains(r'^(Ont|Onu)\b', case=False, regex=True)
r['fam'] = np.where(es_ont & (r['linea'] == 'FiberHome'), 'ONT FiberHome (cualquier modelo)',
           np.where(es_ont & (r['linea'] == 'Huawei'), 'ONU Huawei → reemplazo FH', r['prod']))
es_switch = r['prod'].str.contains(r'^Switch S5735|^Switch S6730', case=False, regex=True)

# --- chequeos ---
iva_mal = r[(r['linea'] == 'Huawei') & (~es_nc) & (r['iva'] != 10.5)][['Fecha','cli','prod','Tasa impositiva','Comprobante']]
pte = r[(r['pte'] > 0) & (~es_nc) & (~r['nopros'])][['Fecha','cli','prod','cant','pte','Comprobante','Vendedor']]

# --- ciclos: compras a menos de 15 días = una sola compra (entregas partidas) ---
v = r[~r['nopros']].copy()
v['switch'] = es_switch
v['tid'] = pd.to_numeric(v['TransaccionID'], errors='coerce').fillna(0)  # v3: orden real de carga dentro del dia
DISC = {'I-con','Zte','ZTE','Netconn','Intelbras','Cisco','Compal','Arris','Wolk','China Mobile'}
marca_de = v.groupby(['cli','fam'])['marca'].last().to_dict()
filas = []
for (cli, fam, lin), d in v.groupby(['cli','fam','linea']):
    d = d.sort_values(['fecha','tid'])
    # v3 09/11: cada NC anula, en orden de TransaccionID, lo ultimo facturado antes que ella. Asi FA 15/10 + NC 20/10 + FA 20/10 = compra del 20/10.
    vivas = []
    for _, x in d.iterrows():
        if x['cant'] < 0:
            resto = -x['cant']
            while resto > 1e-9 and vivas:
                t = min(vivas[-1]['cant'], resto); vivas[-1]['cant'] -= t; resto -= t
                if vivas[-1]['cant'] <= 1e-9: vivas.pop()
        elif x['cant'] > 0:
            vivas.append({'fecha': x['fecha'], 'cant': x['cant'], 'modelo': x['prod'], 'switch': x['switch']})
    ev = []  # eventos de compra
    for x in vivas:
        if ev and (x['fecha'] - ev[-1]['f0']).days < 15:
            ev[-1]['cant'] += x['cant']; ev[-1]['f'] = x['fecha']; ev[-1]['modelo'] = x['modelo']
        else:
            ev.append({'f0': x['fecha'], 'f': x['fecha'], 'cant': x['cant'], 'modelo': x['modelo']})
    if not ev: continue
    fechas = [e['f0'] for e in ev]; n = len(ev)
    ult = ev[-1]['f']; dias_ult = (HOY - ult).days
    ciclo = int(np.median(np.diff(fechas).astype('timedelta64[D]').astype(int))) if n >= 2 else None
    sw = any(x['switch'] for x in vivas)
    d = pd.DataFrame({'cant': [e['cant'] for e in ev]})
    prod = ev[-1]['modelo']
    if sw:
        estado = 'Switch (campaña, fuera del motor)'
    elif fam.startswith('ONU Huawei'):
        estado = 'Reemplazo (ONU Huawei → FH)'
    elif lin not in VIG and lin != 'Huawei':
        mc = marca_de.get((cli, fam), '')
        estado = 'Reemplazo (discontinuado)' if (lin == 'HFC disc' or mc in DISC) else ('Sin marca (revisar)' if mc == '' else 'Otra marca')
    elif ciclo is None:
        estado = 'Sin ciclo (1 compra)' if dias_ult <= 540 else 'Dormido'
    else:
        prox = ult + pd.Timedelta(days=ciclo)
        atraso = (HOY - prox).days
        if atraso < -15: estado = 'En ciclo'
        elif atraso <= 30: estado = 'Le toca'
        elif dias_ult <= max(2*ciclo, 180): estado = 'Atrasado'
        else: estado = 'Se fue'
    filas.append(dict(cliente=cli, sku=fam, ultimo_modelo=prod, linea=lin, compras=n, primera=fechas[0].date(), ultima=ult.date(),
                      dias_desde_ultima=dias_ult, ciclo_dias=ciclo,
                      proxima=(ult + pd.Timedelta(days=ciclo)).date() if ciclo else None,
                      cant_prom=round(d['cant'].mean()), cant_ult=round(d['cant'].iloc[-1]), cant_total=round(d['cant'].sum()),
                      estado=estado))
out = pd.DataFrame(filas)
orden = {'Le toca':0,'Atrasado':1,'Se fue':2,'Reemplazo (ONU Huawei → FH)':3,'Sin ciclo (1 compra)':4,'En ciclo':5,
         'Reemplazo (discontinuado)':6,'Sin marca (revisar)':6,'Otra marca':6,'Switch (campaña, fuera del motor)':7,'Dormido':8}
out['o'] = out['estado'].map(orden)
out = out.sort_values(['o','dias_desde_ultima']).drop(columns='o')

with pd.ExcelWriter(f'LOKI_Recompra_SKU_{HOY.date()}.xlsx') as w:
    out.to_excel(w, sheet_name='Recompra por SKU', index=False)
    pte.to_excel(w, sheet_name='Facturado sin entregar', index=False)
    iva_mal.to_excel(w, sheet_name='IVA Huawei a revisar', index=False)
out.to_json('recompra_sku.json', orient='records', date_format='iso', force_ascii=False)
print(out['estado'].value_counts().to_string())
print('pte', len(pte), 'iva_mal', len(iva_mal), 'nopros excl lines', int(r['nopros'].sum()))

# --- post: ONU Huawei ya migradas a ONT FH no son reemplazo ---
fh = out[out['sku'].str.startswith('ONT FiberHome')].set_index('cliente')['ultima']
m = out['estado'].eq('Reemplazo (ONU Huawei → FH)') & out['cliente'].map(fh).notna()
m &= pd.to_datetime(out['cliente'].map(fh)) > pd.to_datetime(out['ultima'])
out.loc[m, 'estado'] = 'Ya migró a FH'
with pd.ExcelWriter(f'LOKI_Recompra_SKU_{HOY.date()}.xlsx') as w:
    out.to_excel(w, sheet_name='Recompra por SKU', index=False)
    pte.to_excel(w, sheet_name='Facturado sin entregar', index=False)
    iva_mal.to_excel(w, sheet_name='IVA Huawei a revisar', index=False)
out.to_json('recompra_sku.json', orient='records', date_format='iso', force_ascii=False)
print('migradas', int(m.sum()))
