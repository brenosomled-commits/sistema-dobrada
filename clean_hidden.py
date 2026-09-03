import pathlib, re
for path in [r"C:\SistemaOS\templates\editar_venda.html", r"C:\SistemaOS\templates\acompanhamento_notas.html"]:
    p=pathlib.Path(path)
    t=p.read_text(encoding='utf-8')
    # remove hidden span leftover
    # pattern: <span style="display:none">${v.condicao...}</div>
    # Find and remove
    if '<span style="display:none">${v.condicao' in t:
        # Use regex to remove the hidden span and keep closing div
        import re
        t = re.sub(r'<span style="display:none">\$\{v\.condicao.*?\}</div>', '</div>', t, flags=re.DOTALL)
        p.write_text(t, encoding='utf-8')
        print(f'cleaned {path}')
    else:
        print(f'no hidden for {path}')
    # verify
    snippet = t[t.find('CONDIÇÃO'):t.find('CONDIÇÃO')+400] if 'CONDIÇÃO' in t else 'not found'
    print(snippet[:500])
