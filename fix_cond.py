import pathlib
for path in [r"C:\SistemaOS\templates\editar_venda.html", r"C:\SistemaOS\templates\acompanhamento_notas.html"]:
    p=pathlib.Path(path)
    t=p.read_text(encoding='utf-8')
    old = '<div><b>CONDIÇÃO:</b> ${v.cliente'  # dummy to check
    # do simple replace for the condicao line
    # we look for the specific div that shows condicao
    if '<div><b>CONDIÇÃO:</b> ${v.condicao' in t:
        # replace with badge version
        t = t.replace(
            '<div><b>CONDIÇÃO:</b> ${v.condicao||',
            '<div><b>CONDIÇÃO:</b> <span style="display:inline-block;background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:999px;font-size:9px;font-weight:800">${(v.condicao||"").toUpperCase()==="APRAZO" ? "A PRAZO" : (v.condicao||"").toUpperCase()||"-"}</span> ${v.condicao==="aprazo" ? \'<span style="font-size:9px;color:#92400e">· VENC \'+(v.vencimento ? v.vencimento.split("-").reverse().join("/") : "30 DIAS")+"</span>" : ""}<span style="display:none">${v.condicao||'
        )
        p.write_text(t, encoding='utf-8')
        print(f"updated {path}")
    else:
        print(f"no match {path}")
        # debug
        import re
        m=re.search(r"CONDIÇÃO:.{0,80}", t)
        print(m.group(0) if m else "not found")
