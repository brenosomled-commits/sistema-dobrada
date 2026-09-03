import pathlib
p=pathlib.Path(r'C:\SistemaOS\templates\editar_venda.html')
t=p.read_text(encoding='utf-8')
if 'id="areaImpressao"' not in t:
    t=t.replace('</body>', '<div id="areaImpressao" style="display:none"></div><style>@media print{ body > .layout{display:none!important} #areaImpressao{display:block!important} @page{size:A4 portrait;margin:0} }</style></body>')
    p.write_text(t, encoding='utf-8')
    print('added div')
else:
    print('already has')
