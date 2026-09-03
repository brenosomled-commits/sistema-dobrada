import pathlib, re
for path in [r"C:\SistemaOS\templates\nota_dobrada.html", r"C:\SistemaOS\templates\editar_venda.html", r"C:\SistemaOS\templates\acompanhamento_notas.html"]:
    p=pathlib.Path(path)
    t=p.read_text(encoding='utf-8')
    # melhora exibição da condição: transforma "aprazo" em "A PRAZO" com badge e vencimento
    # substitui a linha que mostra CONDIÇÃO
    # procura padrão <b>CONDIÇÃO:</b> ${...}
    # vamos substituir a lógica JS que monta condicao
    # Para nota_dobrada: condicaoRaw e vencimento
    # Para editar/acompanhamento: v.condicao
    # Vamos garantir que vencimento seja calculado se vazio e condicao aprazo
    # Adiciona estilo melhor para via
    if 'VENC:' in t:
        # melhora fonte da via: adiciona font-family e peso
        t=t.replace('CONDIÇÃO:</b> ${v.condicao||', 'CONDIÇÃO:</b> <span style="display:inline-block;background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:999px;font-size:10px;font-weight:800;letter-spacing:.04em;vertical-align:middle">${(v.condicao||"").toUpperCase()==="APRAZO" ? "A PRAZO" : (v.condicao||"").toUpperCase() || "-"}${v.condicao==="aprazo" ? (v.vencimento ? " · VENC "+v.vencimento.split("-").reverse().join("/")+" (30 DIAS)" : " · 30 DIAS") : ""}</span><span style="display:none">${v.condicao||')
        # também para nota_dobrada que usa condicao variável, não v
        t=t.replace('CONDIÇÃO:</b> ${condicao}', 'CONDIÇÃO:</b> <span style="display:inline-block;background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:999px;font-size:10px;font-weight:800">${condicaoRaw==="aprazo" ? "A PRAZO" : condicao.toUpperCase()}</span>${condicaoRaw==="aprazo" ? " <span style=\\"font-size:10px;color:#92400e;font-weight:700\\">· VENC "+(vencimento? vencimento.split("-").reverse().join("/"): "30 DIAS")+" </span>" : ""}<span style="display:none">${condicao}')
        # fallback para casos onde ainda mostra aprazo simples
        t=t.replace('>aprazo<','>A PRAZO<')
        t=t.replace('>avista<','>A VISTA<')
        t=t.replace('CONDIÇÃO:</b> aprazo','CONDIÇÃO:</b> <span style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:999px;font-size:10px;font-weight:800">A PRAZO</span>')
    p.write_text(t, encoding='utf-8')
    print(f"fixed {path}")
print("done")
