import pathlib
footer = '<div style="margin-top:10px;text-align:center;font-size:7px;color:#6b7280;border-top:1px dashed #9ca3af;padding-top:6px;letter-spacing:.06em">CUPOM NÃO FISCAL — DOCUMENTO SEM VALOR FISCAL — APENAS ORÇAMENTO</div>'
for path in [r"C:\SistemaOS\templates\nota_dobrada.html", r"C:\SistemaOS\templates\editar_venda.html", r"C:\SistemaOS\templates\acompanhamento_notas.html"]:
    p=pathlib.Path(path)
    t=p.read_text(encoding='utf-8')
    # Add footer to viaHTML after TOTAL FINAL - we insert before the closing of via
    # For nota_dobrada, the via ends with signature or totals, we can ensure footer is added in prepararImpressao and reimprimir
    # Simplest: ensure every via that has TOTAL FINAL also gets footer
    # We'll inject footer string after the total final div's closing
    # Find pattern: TOTAL FINAL...</div></div> and add footer before final </div>
    # For now, just ensure that after each via generation, we add footer via JS
    # Instead of complex, we add JS to append footer: modify the JS that builds via to also append footer
    # For each file, add footer insertion after the signature block
    if 'CUPOM NÃO FISCAL' in t:
        print(f"already has {path}")
        continue
    # For each file, find where via is completed and append footer
    # For nota_dobrada prepararImpressao: after assinaturaHTML, add footer
    # We'll add a JS line to append footer: primeiraVia.innerHTML += footer; segundaVia...
    # Easiest: add footer HTML directly after gerarResumo
    # Insert after gerarResumo() call
    if 'primeiraVia.innerHTML += gerarResumo()' in t:
        t=t.replace('primeiraVia.innerHTML += gerarResumo();', 'primeiraVia.innerHTML += gerarResumo();\n        primeiraVia.innerHTML += \''+footer+'\';')
        t=t.replace('segundaVia.innerHTML += gerarResumo();', 'segundaVia.innerHTML += gerarResumo();\n        segundaVia.innerHTML += \''+footer+'\';')
        # For reimprimir where viaHTML already includes totals
        # Add after v1/v2 creation for other templates
        # For editar/acompanhamento, they use viaHTML() that includes totals
        # We add after v1/v2 creation
        t=t.replace("pagina.appendChild(v1.firstElementChild); pagina.appendChild(v2.firstElementChild);", "v1.firstElementChild.innerHTML += '"+footer+"';\n        v2.firstElementChild.innerHTML += '"+footer+"';\n        pagina.appendChild(v1.firstElementChild); pagina.appendChild(v2.firstElementChild);")
    else:
        # For editar/acompanhamento where totals inside viaHTML, add footer there
        t=t.replace("pagina.appendChild(v1.firstElementChild); pagina.appendChild(v2.firstElementChild);", "v1.firstElementChild.innerHTML += '"+footer+"';\n        v2.firstElementChild.innerHTML += '"+footer+"';\n        pagina.appendChild(v1.firstElementChild); pagina.appendChild(v2.firstElementChild);")
    p.write_text(t, encoding='utf-8')
    print(f"patched {path}")
print("done")
