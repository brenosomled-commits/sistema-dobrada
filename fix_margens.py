import pathlib
for path in [r"C:\SistemaOS\templates\nota_dobrada.html", r"C:\SistemaOS\templates\editar_venda.html", r"C:\SistemaOS\templates\acompanhamento_notas.html"]:
    p=pathlib.Path(path)
    t=p.read_text(encoding='utf-8')
    t=t.replace('@page{ size:A4 portrait; margin:0; }','@page{ size:A4 portrait; margin:5mm; }')
    t=t.replace('@page{size:A4 portrait;margin:0}','@page{ size:A4 portrait; margin:5mm; }')
    t=t.replace('width:198mm;min-height:139mm;padding:9mm 10mm 8mm;','width:190mm;min-height:132mm;padding:6mm 8mm;')
    t=t.replace('width:198mm; min-height:139mm; padding:9mm 10mm 8mm;','width:190mm; min-height:132mm; padding:6mm 8mm;')
    t=t.replace('width:210mm;min-height:297mm;','width:200mm;min-height:287mm;')
    t=t.replace('width:210mm; min-height:297mm;','width:200mm; min-height:287mm;')
    t=t.replace('margin:4.5mm auto 0;','margin:3mm auto 0;')
    t=t.replace('margin:4.5mm auto 0','margin:3mm auto 0')
    # inline JS via strings also have width 198mm
    t=t.replace('width:198mm;min-height:139mm;padding:9mm 10mm 8mm;','width:190mm;min-height:132mm;padding:6mm 8mm;')
    t=t.replace('width:198mm; min-height:139mm; padding:9mm 10mm 8mm;','width:190mm; min-height:132mm; padding:6mm 8mm;')
    p.write_text(t, encoding='utf-8')
    print(f"fixed {path}")
print("done")
