import pathlib, re
templates = [
    r"C:\SistemaOS\templates\dashboard.html",
    r"C:\SistemaOS\templates\acompanhamento_notas.html",
    r"C:\SistemaOS\templates\editar_venda.html",
    r"C:\SistemaOS\templates\nota_dobrada.html",
    r"C:\SistemaOS\templates\controle_comissao.html",
    r"C:\SistemaOS\templates\minha_senha.html",
]
for path in templates:
    p=pathlib.Path(path)
    t=p.read_text(encoding='utf-8')
    # Check if already has condition for Gerenciar
    if 'Gerenciar Logins' in t:
        # If already has {% if ... %} around it, skip
        if '{% if' in t and 'Gerenciar Logins' in t:
            # Check if the specific line has condition
            # Simple: if the file has a line with Gerenciar without if, add
            # Find the anchor
            if 'href="/usuarios"' in t:
                # Check surrounding 200 chars
                idx=t.find('href="/usuarios"')
                snippet=t[max(0,idx-300):idx+300]
                if '{% if' not in snippet:
                    # wrap
                    old='<a class="sidebar-link" href="/usuarios"><span class="link-icon">👥</span> Gerenciar Logins</a>'
                    new='{% if papel in ["GERENTE","DONO"] or papel_logado in ["GERENTE","DONO"] or usuario_tem_gestao %}<a class="sidebar-link" href="/usuarios"><span class="link-icon">👥</span> Gerenciar Logins</a>{% endif %}'
                    # But need to handle different papel variables per template
                    # Simpler: just add condition for GERENTE/DONO check via JS? No, use Jinja with papel variable
                    # For templates that have `papel` variable, use `papel in ["GERENTE","DONO"]`
                    # For those with `papel_logado`, use that
                    # For generic, add both
                    if path.endswith('usuarios.html'):
                        continue  # usuarios page itself should show
                    # Determine variable name
                    if 'papel_logado' in t:
                        cond = '{% if papel_logado in ["GERENTE","DONO"] %}'
                    elif 'papel' in t:
                        cond = '{% if papel in ["GERENTE","DONO"] %}'
                    else:
                        cond = '{% if True %}'  # fallback
                    # Find the exact anchor string
                    for cand in ['<a class="sidebar-link" href="/usuarios"><span class="link-icon">👥</span> Gerenciar Logins</a>', '<a class="sidebar-link" href="/usuarios">', 'href="/usuarios"']:
                        if cand in t:
                            # Replace the line with conditioned version
                            t=t.replace(cand, cond+cand)
                            # Find closing </a> after and add endif
                            # Simple: after the anchor, add endif
                            # Find the first </a> after idx
                            # We'll just add endif after the anchor string
                            # For our cand, we need to find the full anchor
                            break
                    # Add endif after the anchor
                    # Find first occurrence after cond
                    idx2=t.find('Gerenciar Logins</a>')
                    if idx2!=-1:
                        insert_pos = idx2 + len('Gerenciar Logins</a>')
                        t=t[:insert_pos] + '{% endif %}' + t[insert_pos:]
                    p.write_text(t, encoding='utf-8')
                    print(f"patched {path}")
        else:
            print(f"skip {path} no Gerenciar")
    else:
        print(f"no Gerenciar in {path}")

# Also handle index.html which already has condition, ensure it stays
print("done")
