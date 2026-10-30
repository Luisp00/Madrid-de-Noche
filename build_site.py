#!/usr/bin/env python3
"""Genera la versión web estática (GitHub Pages) en un directorio: index.html completo + data/events.json + data/status.json.
Uso: python3 -I build_site.py out/ site/      (out/ = salida de merge.py con events.json y status.json)
"""
import sys, os, shutil
src=os.path.dirname(os.path.abspath(__file__))
out_dir=sys.argv[1] if len(sys.argv)>1 else "out"; site=sys.argv[2] if len(sys.argv)>2 else "site"
frag=open(os.path.join(src,"index.html"),encoding="utf-8").read()
html=('<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
      '<meta name="theme-color" content="#0a0a0f"><meta name="description" content="Todos los eventos nocturnos de Madrid con precio, música, dress code y entradas, actualizados cada día.">'
      '<link rel="manifest" href=\'data:application/manifest+json,{"name":"Madrid de Noche","short_name":"MdN","start_url":".","display":"standalone","background_color":"%230a0a0f","theme_color":"%230a0a0f"}\'>'
      '<style>:root{padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style></head><body>'
      + frag + '</body></html>')
os.makedirs(os.path.join(site,"data"),exist_ok=True)
open(os.path.join(site,"index.html"),"w",encoding="utf-8").write(html)
for f in ("events.json","status.json"):
    p=os.path.join(out_dir,f)
    if os.path.exists(p): shutil.copy(p,os.path.join(site,"data",f))
open(os.path.join(site,".nojekyll"),"w").close()
print("sitio generado en",site, os.listdir(os.path.join(site,"data")))
