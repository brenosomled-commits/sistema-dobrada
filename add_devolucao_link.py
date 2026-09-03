import pathlib

files = [
    "acompanhamento_notas.html",
    "controle_comissao.html",
    "dashboard.html",
    "editar_venda.html",
    "index.html",
    "minha_senha.html",
    "nota_dobrada.html",
    "usuarios.html",
]

LINK = '<a class="sidebar-link" href="/devolucoes"><span class="link-icon">↩️</span> Devolução</a>'

for f in files:
    p = "C:\\SistemaOS\\templates\\" + f
    t = pathlib.Path(p).read_text(encoding="utf-8")
    if "href=\"/devolucoes\"" in t:
        print(f"already has {f}")
        continue
    # Insert right after the acompanhamento_notas link in the Vendas section
    anchor = '<a class="sidebar-link" href="/acompanhamento_notas"><span class="link-icon">📈</span> Acompanhar Notas</a>'
    if anchor in t:
        t = t.replace(anchor, anchor + LINK, 1)
    else:
        # fallback: find any acompanhamento_notas link
        import re
        m = re.search(r'<a class="sidebar-link[^"]*" href="/acompanhamento_notas"[^>]*>[^<]*</a>', t)
        if m:
            t = t.replace(m.group(0), m.group(0) + LINK, 1)
        else:
            print(f"could not find anchor in {f}")
            continue
    pathlib.Path(p).write_text(t, encoding="utf-8")
    print(f"added link to {f}")
print("done")
