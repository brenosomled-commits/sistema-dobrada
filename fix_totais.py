import pathlib, re
for path in [r"C:\SistemaOS\templates\editar_venda.html", r"C:\SistemaOS\templates\acompanhamento_notas.html", r"C:\SistemaOS\templates\nota_dobrada.html"]:
    p=pathlib.Path(path)
    t=p.read_text(encoding='utf-8')
    # replace centered totals with bottom-right
    # pattern for 104mm centered
    t=t.replace('width:104mm;margin:14px auto 0','width:68mm;margin-left:auto;margin-top:auto;padding-top:10px;text-align:right')
    t=t.replace('width:104mm;margin:14px auto 0','width:68mm;margin-left:auto;margin-top:auto;padding-top:10px;text-align:right')
    # also ensure via has flex
    # add flex to via-impressao inline if not present
    t=t.replace('width:198mm;min-height:139mm;padding:9mm 10mm 8mm;border:1px solid #000;background:#fff;font-size:13px','width:198mm;min-height:139mm;padding:9mm 10mm 8mm;border:1px solid #000;background:#fff;font-size:13px;display:flex;flex-direction:column')
    t=t.replace('width:198mm;min-height:139mm;padding:9mm 10mm 8mm;border:1px solid #000;background:#fff;','width:198mm;min-height:139mm;padding:9mm 10mm 8mm;border:1px solid #000;background:#fff;display:flex;flex-direction:column;')
    p.write_text(t, encoding='utf-8')
    print(f"fixed {path}")
print("done")
