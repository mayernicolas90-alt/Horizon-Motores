"""Panal V8 (versión Claude): plantilla intacta + panal + acento exacto en tercio/φ + informe de 5 pruebas."""
import sys,math,json,numpy as np,cv2
from PIL import Image,ImageDraw
src,dst,fam=sys.argv[1],sys.argv[2],(sys.argv[3] if len(sys.argv)>3 else 'olt')
im=Image.open(src).convert('RGB');W,H=im.size
g=cv2.cvtColor(np.array(im),cv2.COLOR_RGB2GRAY)
e=cv2.magnitude(cv2.Sobel(g,cv2.CV_32F,1,0),cv2.Sobel(g,cv2.CV_32F,0,1))
m=cv2.morphologyEx(cv2.dilate((e>40).astype('uint8'),np.ones((9,9),np.uint8)),cv2.MORPH_CLOSE,np.ones((31,31),np.uint8))
ff=m.copy();cv2.floodFill(ff,np.zeros((H+2,W+2),np.uint8),(W-2,2),2)
occ0=(ff!=2).astype('uint8');foot=H-(230 if H>1500 else 164);occ0[foot:]=1
occ=cv2.dilate(occ0,np.ones((25,25),np.uint8))                      # margen 12 px
n,l,st,cen=cv2.connectedComponentsWithStats(occ0[:foot]);k=1+np.argmax(st[1:,cv2.CC_STAT_AREA]);fx,fy=cen[k];PB=(st[k,0],st[k,1],st[k,0]+st[k,2],st[k,1]+st[k,3])   # foco = bloque de foto
r=round(0.035*min(W,H*0.8));dx,dy=math.sqrt(3)*r,1.5*r;maxH=H/3 if H>1500 else H
ANC={'olt':(W+r*.4,-r*.2),'ont':(-r*.4,-r*.2),'pasivo':(W+r*.4,H*.45)};anc0=ANC.get(fam,ANC['olt'])
def pts(cx,cy,rr):return [(cx+rr*math.cos(math.radians(t)),cy+rr*math.sin(math.radians(t))) for t in(-90,-30,30,90,150,210)]
def free(cx,cy):
  p=pts(cx,cy,r*.92);xs=[q[0] for q in p];ys=[q[1] for q in p]
  x0,x1,y0,y1=int(max(0,min(xs))),int(min(W-1,max(xs))),int(max(0,min(ys))),int(min(H-1,max(ys)))
  if x1<=x0 or y1<=y0:return None
  if (x1-x0)*(y1-y0)/((max(xs)-min(xs))*(max(ys)-min(ys)))<.4 or occ[y0:y1,x0:x1].any():return None
  return p
def grid(anc):
  ex=min(max(anc[0],PB[0]),PB[2]);ey=min(max(anc[1],PB[1]),PB[3]);D=max(1,math.hypot(ex-anc[0],ey-anc[1]));DC=math.hypot(fx-anc[0],fy-anc[1]);out=[]   # se apaga al llegar al borde de la foto
  for j in range(-2,int(H/dy)+3):
    for i in range(-int(W/dx)-3,int(W/dx)+3):
      cx=anc[0]+i*dx+(dx/2 if j%2 else 0);cy=anc[1]+j*dy
      if cy>maxH+r:continue
      p=free(cx,cy)
      if not p:continue
      dd=math.hypot(cx-anc[0],cy-anc[1])
      if dd/DC>.92:continue                      # extensión del panal (igual que antes)
      kk=min(1,dd/DC)
      a=.48*(1-kk)**1.6+.04
      gx=max(PB[0]-cx,0,cx-PB[2]);gy=max(PB[1]-cy,0,cy-PB[3])
      if math.hypot(gx,gy)<1.2*r*3:a=min(a,.06)      # pegadas a la foto: casi apagadas (regla 1.2)
      a=min(a,.04+.44*min(1,math.hypot(gx,gy)/(6*r)))   # rampa suave hacia la foto
      out.append(dict(cx=cx,cy=cy,a=a,w=2.8-1.2*kk,p=p))
  return out
PHI=(1+5**.5)/2
VL=[W/3,2*W/3,W/PHI,W*(1-1/PHI)];HL=[H/3,2*H/3,H/PHI,H*(1-1/PHI)];PP=[(x,y) for x in VL for y in HL]
def lined(c):return min(min(abs(c['cx']-x) for x in VL),min(abs(c['cy']-y) for y in HL))
base=grid(anc0);cells,anc,acc,tgt=base,anc0,None,None
# los puntos de tercio caen sobre foto/título: el acento va sobre una LÍNEA de tercio o φ, en la celda visible más cerca de un punto fuerte
cand=sorted([c for c in base if c['a']>.15],key=lambda c:min(math.hypot(c['cx']-p[0],c['cy']-p[1]) for p in PP))
for c in cand:
  dv=min(VL,key=lambda x:abs(c['cx']-x))-c['cx'];dh=min(HL,key=lambda y:abs(c['cy']-y))-c['cy']
  d=(dv,0) if abs(dv)<=abs(dh) else (0,dh)
  if math.hypot(*d)>r*1.8:continue
  a2=(anc0[0]+d[0],anc0[1]+d[1]);g2=grid(a2);t=(c['cx']+d[0],c['cy']+d[1])
  hit=[q for q in g2 if math.hypot(q['cx']-t[0],q['cy']-t[1])<=r*.5 and sum(1 for z in g2 if z is not q and z['a']>.12 and math.hypot(z['cx']-q['cx'],z['cy']-q['cy'])<dx*1.1)>=2]   # el acento queda dentro del panal
  if hit:cells,anc,acc,tgt=g2,a2,hit[0],t;break
if acc:acc.update(acc=True,a=.85,w=3)
S=2;lay=Image.new('RGBA',(W*S,H*S),(0,0,0,0));dr=ImageDraw.Draw(lay)
for c in sorted(cells,key=lambda c:c['a']):
  col=(47,224,138) if c.get('acc') else (92,118,186);p=[(x*S,y*S) for x,y in c['p']]
  dr.line(p+[p[0],p[1]],fill=col+(int(255*c['a']),),width=int(c['w']*S),joint='curve')
HD=sys.argv[4] if len(sys.argv)>4 else None
if HD:                                   # mismo panal, dibujado nativo en la pieza HD (sin reescalar el raster)
  hi=Image.open(HD).convert('RGBA');K=2*hi.size[0]/W;l2=Image.new('RGBA',(hi.size[0]*2,hi.size[1]*2),(0,0,0,0));d2=ImageDraw.Draw(l2)
  for c in sorted(cells,key=lambda c:c['a']):
    col=(47,224,138) if c.get('acc') else (92,118,186);p=[(x*K,y*K) for x,y in c['p']]
    d2.line(p+[p[0],p[1]],fill=col+(int(255*c['a']),),width=max(1,round(c['w']*K)),joint='curve')
  l2=l2.resize(hi.size,Image.LANCZOS);hi.alpha_composite(l2);hi.convert('RGB').save(HD.replace('_hd.png','_hd_final.png'),optimize=True)
lay=lay.resize((W,H),Image.LANCZOS);A=np.array(lay)[...,3]
out=im.convert('RGBA');out.alpha_composite(lay);out.convert('RGB').save(dst)
ink=float((A>20).mean());neg=float(1-((occ0>0)|(A>20)).mean())
ordi=[c for c in cells if not c.get('acc')];avg=lambda L:sum(c['a'] for c in L)/max(1,len(L))
nf=sorted(ordi,key=lambda c:math.hypot(max(PB[0]-c['cx'],0,c['cx']-PB[2]),max(PB[1]-c['cy'],0,c['cy']-PB[3])))[:5];na=sorted(ordi,key=lambda c:math.hypot(c['cx']-anc[0],c['cy']-anc[1]))[:5]
fade=avg(nf)/max(avg(na),1e-4);touch=int(((A>20)&(occ0[:,:]>0)).sum())
T={'acento':bool(acc) and lined(acc)<=r*.5,'tinta_y_negativo':ink<=.08 and neg>=.35,'zonas_libres':touch==0,'disolucion':fade<.25,'anclaje':fam in ANC}
rep=dict(pieza=dst,familia=fam,celdas=len(cells),radio=r,tinta_pct=round(ink*100,2),negativo_pct=round(neg*100,1),acento_px=round(lined(acc),1) if acc else None,disolucion=round(fade,3),pixeles_sobre_contenido=touch,pruebas=T,aprobado=all(T.values()))
json.dump(rep,open(dst.rsplit('.',1)[0]+'.json','w'),ensure_ascii=False,indent=1);print(json.dumps({k:rep[k] for k in('pieza','celdas','tinta_pct','negativo_pct','acento_px','disolucion','pixeles_sobre_contenido','aprobado')}))
