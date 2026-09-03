# -*- coding: utf-8 -*-
import io, re, os

BASE = r"C:\SistemaOS\templates"

def substituir(path, pares):
    p = os.path.join(BASE, path)
    with io.open(p, "r", encoding="utf-8") as f:
        conteudo = f.read()
    original = conteudo
    for antigo, novo in pares:
        if antigo not in conteudo:
            print(f"[AVISO] nao encontrado em {path}: {antigo[:60]!r}")
        conteudo = conteudo.replace(antigo, novo)
    if conteudo != original:
        with io.open(p, "w", encoding="utf-8") as f:
            f.write(conteudo)
        print(f"[OK] {path}")

# Expressao de mapeamento de condicao (inclui legado pix/sicoob -> PIX SICOOB)
MAP = "(({dinheiro:'DINHEIRO',cartadebito:'CARTAO DEBITO',cartocredito:'CARTAO CREDITO',pix:'PIX SICOOB',sicoob:'PIX SICOOB',pixinter:'PIX INTER',pixmaq:'PIX MAQUINA',avista:'A VISTA',aprazo:'A PRAZO'}[c])||(c||'').toUpperCase())"

# nota_dobrada: via de reimpressao - CONDICAO em negrito + mapeamento
substituir("nota_dobrada.html", [
    ("<b>CONDIÇÃO:</b> ${v.condicao||''}",
     "<b>CONDIÇÃO:</b> <b style=\"font-weight:900;letter-spacing:.04em\">" + MAP.replace("[c]", "[v.condicao]") + "</b>"),
])

# nota_dobrada: impressao ao vivo - badge ja uppercase/negrito, mas garantir mapeamento legado
substituir("nota_dobrada.html", [
    ("condicaoRaw==='aprazo' ? 'A PRAZO' : (condicao.toUpperCase()||'-')",
     "condicaoRaw==='aprazo' ? 'A PRAZO' : " + MAP.replace("[c]", "[condicaoRaw]")),
])

# editar_venda: span de condicao uppercase -> mapeamento + negrito
substituir("editar_venda.html", [
    ("<span style=\"display:inline-block;background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:999px;font-size:9px;font-weight:800\">${(v.condicao||\"\").toUpperCase()===\"APRAZO\" ? \"A PRAZO\" : (v.condicao||\"\").toUpperCase()||\"-\"}</span>",
     "<span style=\"display:inline-block;background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:999px;font-size:9px;font-weight:800\">${(v.condicao||\"\")===\"aprazo\" ? \"A PRAZO\" : " + MAP.replace("[c]", "[String(v.condicao)]") + "}</span>"),
])

# acompanhamento_notas: span de condicao uppercase -> mapeamento + negrito
substituir("acompanhamento_notas.html", [
    ("<span style=\"display:inline-block;background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:999px;font-size:9px;font-weight:800\">${(v.condicao||\"\").toUpperCase()===\"APRAZO\" ? \"A PRAZO\" : (v.condicao||\"\").toUpperCase()||\"-\"}</span>",
     "<span style=\"display:inline-block;background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:999px;font-size:9px;font-weight:800\">${(v.condicao||\"\")===\"aprazo\" ? \"A PRAZO\" : " + MAP.replace("[c]", "[String(v.condicao)]") + "}</span>"),
])

print("Concluido.")
