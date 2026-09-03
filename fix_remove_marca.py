import pathlib
import re

files = [
    "acompanhamento_notas.html",
    "controle_comissao.html",
    "dashboard.html",
    "devolucoes.html",
    "editar_venda.html",
    "index.html",
    "login.html",
    "minha_senha.html",
    "nota_dobrada.html",
    "usuarios.html",
]

# Nas notas: <span style="..."><img logo ...><b>SOMLED OS</b></span> -> manter so o img (remover o <b>)
# O span tem a logo e depois <b>SOMLED OS</b>. Remover o <b>SOMLED OS</b>, mantendo so a logo.

def limpar_barra_json(t):
    # remover <b>SOMLED OS</b> dentro de strings JS (notas)
    t = t.replace("<b>SOMLED OS</b>", "")
    return t

for f in files:
    p = "C:\\SistemaOS\\templates\\" + f
    t = pathlib.Path(p).read_text(encoding="utf-8")
    t2 = limpar_barra_json(t)
    # alt="SOMLED OS" -> alt=""
    t2 = t2.replace('alt="SOMLED OS"', 'alt=""')
    # titulo " - SOMLED OS</title>" -> remove
    t2 = re.sub(r'- SOMLED OS</title>', '</title>', t2)
    # nota-topo-titulo "SOMLED OS - X" / "SOMLED OS — X" -> so X
    t2 = t2.replace("SOMLED OS — NOTA DE ORÇAMENTO SEM VALOR FISCAL", "NOTA DE ORÇAMENTO SEM VALOR FISCAL")
    t2 = t2.replace("SOMLED OS - NOTA DE ORÇAMENTO SEM VALOR FISCAL", "NOTA DE ORÇAMENTO SEM VALOR FISCAL")
    t2 = t2.replace("SOMLED OS — DEVOLUÇÃO DE PRODUTO", "DEVOLUÇÃO DE PRODUTO")
    t2 = t2.replace("SOMLED OS - DEVOLUÇÃO DE PRODUTO", "DEVOLUÇÃO DE PRODUTO")
    # rodapés de marca
    t2 = t2.replace("SOMLED OS · Colatina - ES", "Colatina - ES")
    t2 = t2.replace("© SOMLED OS · Colatina - ES", "© Colatina - ES")
    t2 = t2.replace("SOMLED OS · Colatina - ES · Controle de Comissão", "Controle de Comissão")
    # index logo-text
    t2 = t2.replace('<div class="logo-text">SOMLED OS</div>', '')
    if t2 != t:
        pathlib.Path(p).write_text(t2, encoding="utf-8")
        print(f"updated {f}")
    else:
        print(f"no change {f}")
print("done")
