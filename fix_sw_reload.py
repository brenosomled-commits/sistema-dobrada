import re
import os

arquivos = [
    'templates/acompanhamento_notas.html',
    'templates/aprovacoes.html',
    'templates/controle_comissao.html',
    'templates/dashboard.html',
    'templates/devolucoes.html',
    'templates/editar_venda.html',
    'templates/index.html',
    'templates/login.html',
    'templates/minha_senha.html',
    'templates/nota_dobrada.html',
    'templates/usuarios.html',
    'templates/entregas.html',
]

# Captura o bloco .then(...) completo que contém controllerchange/reload
padrao = re.compile(
    r'navigator\.serviceWorker\.register\([^)]+\)\.then\(function\(reg\)\{.*?controllerchange.*?\}\);\s*\}\);',
    re.DOTALL
)

def versao_do_registro(texto):
    m = re.search(r'register\("(/sw\.js\?v=\d+)"\)', texto)
    if m:
        return m.group(1)
    m = re.search(r"register\('(/sw\.js\?v=\d+)'\)", texto)
    if m:
        return m.group(1)
    return '/sw.js?v=8'

total = 0
for caminho in arquivos:
    if not os.path.exists(caminho):
        print(f'NAO EXISTE: {caminho}')
        continue
    with open(caminho, 'r', encoding='utf-8') as f:
        conteudo = f.read()

    match = padrao.search(conteudo)
    if match:
        v = versao_do_registro(match.group(0))
        sub = 'navigator.serviceWorker.register("' + v + '").catch(function(e){ console.warn("SW:", e); });'
        novo = padrao.sub(sub, conteudo)
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write(novo)
        print(f'CORRIGIDO: {caminho}  (versao SW: {v})')
        total += 1
    else:
        print(f'sem match : {caminho}')

print(f'\nTotal corrigido: {total} arquivo(s)')
