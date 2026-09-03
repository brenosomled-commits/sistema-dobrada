import pathlib

files = [
    "acompanhamento_notas.html",
    "controle_comissao.html",
    "dashboard.html",
    "editar_venda.html",
    "index.html",
    "login.html",
    "minha_senha.html",
    "nota_dobrada.html",
    "usuarios.html",
]

def read(p):
    return pathlib.Path(p).read_text(encoding="utf-8")

def write(p, t):
    pathlib.Path(p).write_text(t, encoding="utf-8")

# Replace standalone brand "SOMLED" -> "SOMLED OS" in visible text/alt
# But avoid replacing inside word "SOMLED" when followed by OS already (SOMLED OS -> SOMLED OS OS).
import re

def replace_brand(t):
    # alt="SOMLED" -> alt="SOMLED OS"
    t = re.sub(r'alt="SOMLED(?!\sOS)"', 'alt="SOMLED OS"', t)
    # <b>SOMLED</b> -> <b>SOMLED OS</b>
    t = re.sub(r'<b>SOMLED</b>', '<b>SOMLED OS</b>', t)
    # title "... - SOMLED</title>"
    t = re.sub(r'- SOMLED</title>', '- SOMLED OS</title>', t)
    # logo-text SOMLED
    t = re.sub(r'<div class="logo-text">SOMLED</div>', '<div class="logo-text">SOMLED OS</div>', t)
    # "SOMLED — NOTA" and "SOMLED — NOTA"
    t = t.replace("SOMLED — NOTA DE ORÇAMENTO SEM VALOR FISCAL", "SOMLED OS — NOTA DE ORÇAMENTO SEM VALOR FISCAL")
    # "SOMLED · Colatina - ES"
    t = t.replace("SOMLED · Colatina - ES", "SOMLED OS · Colatina - ES")
    # "© SOMLED · Colatina - ES"
    t = t.replace("© SOMLED · Colatina - ES", "© SOMLED OS · Colatina - ES")
    return t

for f in files:
    p = "C:\\SistemaOS\\templates\\" + f
    t = read(p)
    nt = replace_brand(t)
    if nt != t:
        write(p, nt)
        print(f"updated {f}")
    else:
        print(f"no change {f}")
print("done")
