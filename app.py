import os
import json
import threading
import time
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, make_response
import sqlite3
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash

import db

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "desenvolvimento-altere-esta-chave"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)

_ultima_verificacao_vencimentos = 0.0

@app.before_request
def _verificar_vencimentos_startup():
    global _ultima_verificacao_vencimentos
    agora = time.time()
    if agora - _ultima_verificacao_vencimentos > 1800:
        _ultima_verificacao_vencimentos = agora
        threading.Thread(target=verificar_vencimentos, daemon=True).start()

BANCO = None  # reservado (backward compatibility)
USAR_POSTGRES = db.banco_eh_postgres()
STATUS_OS = {"Em andamento", "Aguardando peça", "Aguardando cliente", "Aguardando retirada", "Orçamento", "Aprovado", "Em análise", "Pronta", "Finalizada", "Cancelada", "Entregue"}
PAPEIS = {"DONO", "GERENTE", "FINANCEIRO", "VENDEDOR"}
PAPEIS_GESTAO = {"DONO", "GERENTE"}
PAPEIS_FINANCEIRO = {"DONO", "GERENTE", "FINANCEIRO"}
AUTORIZADORES = {"BRENO", "VINICIUS"}
DESCONTO_MAXIMO_PERCENTUAL = 5
COMISSAO_PERCENTUAL = 2
HIERARQUIA_NIVEL = {"VENDEDOR": 1, "FINANCEIRO": 2, "GERENTE": 3, "DONO": 4}
USUARIOS_INICIAIS = [
    ("BRENO", "GERENTE"),
    ("GABRIEL", "VENDEDOR"),
    ("YAN", "VENDEDOR"),
    ("SONIA", "FINANCEIRO"),
    ("VINICIUS", "VENDEDOR"),
    ("WILLIAN", "DONO"),
]
SENHA_TEMPORARIA_PADRAO = os.environ.get("DEFAULT_USER_PASSWORD", "Trocar@123")

# Logins por setor (cada setor possui senha própria de 4 dígitos).
# Valor default é sobrescrito por variável de ambiente, se definida.
def _senha_setor(chave, padrao):
    return os.environ.get("SETOR_SENHA_" + chave, padrao)

SETORES_LOGIN = [
    {"nome": "VENDAS",      "papel": "VENDEDOR",   "senha": _senha_setor("VENDAS", "1111")},
    {"nome": "GERENCIA",    "papel": "GERENTE",    "senha": _senha_setor("GERENCIA", "2222")},
    {"nome": "DONO",        "papel": "DONO",       "senha": _senha_setor("DONO", "3333")},
    {"nome": "FINANCEIRO",  "papel": "FINANCEIRO", "senha": _senha_setor("FINANCEIRO", "4444")},
]


# =========================
# BANCO DE DADOS
# =========================

def conectar():
    """Retorna uma conexão SQLite (local) ou PostgreSQL (Neon) unificada."""
    return db.conectar()


def json_body():
    """Retorna um objeto JSON ou uma resposta 400 que as rotas podem devolver."""
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return None
    return dados


def agora_sp():
    """Data/hora atual no fuso America/Sao_Paulo (UTC-3, sem DST).

    O servidor (Vercel) roda em UTC; usar este helper em todo lugar
    que precise da hora local da loja (criacao, hoje, mes, etc.).
    """
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=-3)))


def senha_valida(senha):
    return isinstance(senha, str) and len(senha) >= 4


def normalizar_usuario(usuario):
    return str(usuario or "").strip().upper()


def obter_papel_usuario(usuario):
    conexao = conectar()
    registro = conexao.execute(
        "SELECT papel FROM usuarios WHERE upper(usuario) = upper(?)",
        (usuario,)
    ).fetchone()
    conexao.close()
    return registro["papel"] if registro else None


def _acessar(registro, chave):
    try:
        return registro[chave]
    except (KeyError, IndexError, TypeError):
        return None


def usuario_e_setor(usuario):
    """Retorna True apenas se o usuário for um login de setor (VENDAS,
    GERENCIA, DONO, FINANCEIRO). Logins individuais são bloqueados."""
    conexao = conectar()
    reg = conexao.execute(
        "SELECT tipo FROM usuarios WHERE upper(usuario) = upper(?)",
        (usuario,)
    ).fetchone()
    conexao.close()
    return bool(reg and str(_acessar(reg, "tipo") or "PESSOA").upper() == "SETOR")


def nivel_do_papel(papel):
    return HIERARQUIA_NIVEL.get(str(papel or "").upper(), 0)


def usuario_tem_gestao(usuario):
    papel = obter_papel_usuario(usuario)
    return papel in PAPEIS_GESTAO


def usuario_pode_ver_financeiro(usuario):
    papel = obter_papel_usuario(usuario)
    return (papel or "").upper() in PAPEIS_FINANCEIRO


def usuario_tem_nivel_minimo(usuario, papel_minimo):
    return nivel_do_papel(obter_papel_usuario(usuario)) >= nivel_do_papel(papel_minimo)


def pode_gerenciar_usuario_alvo(papel_atual, papel_alvo_atual, papel_desejado=None):
    """Retorna None se permitido, ou mensagem de erro.
    Regras:
    - DONO pode gerenciar todos.
    - GERENTE pode gerenciar VENDEDOR, FINANCEIRO e outros GERENTES (mais poder),
      mas nunca DONO e nunca promove a DONO.
    - FINANCEIRO/VENDEDOR não gerenciam ninguém.
    - Ninguém pode promover a DONO exceto DONO.
    """
    atual = (papel_atual or "").upper()
    alvo = (papel_alvo_atual or "").upper()
    desejado = (papel_desejado or alvo).upper() if papel_desejado else alvo
    if atual == "DONO":
        return None
    if atual == "GERENTE":
        if alvo == "DONO":
            return "Gerente não pode alterar usuário Dono."
        if desejado == "DONO":
            return "Apenas Dono pode promover a Dono."
        return None
    return "Seu perfil não tem permissão para gerenciar usuários."


def desconto_maximo_por_papel(papel):
    p = str(papel or "").upper()
    if p in {"GERENTE", "DONO"}:
        return 100
    if p == "FINANCEIRO":
        return 10
    return DESCONTO_MAXIMO_PERCENTUAL


def validar_desconto_percentual(desconto, papel):
    if desconto < 0:
        return "Desconto não pode ser negativo."
    desconto_maximo = desconto_maximo_por_papel(papel)
    if desconto > desconto_maximo:
        return f"O desconto máximo permitido para {papel.lower()} é de {desconto_maximo}%."
    return None


def _autorizar_desconto(dados, desconto, papel):
    """Se o desconto ultrapassar o limite do papel logado, exige no payload as
    credenciais de um usuário autorizado (GERENTE/DONO ou AUTORIZADORES), valida
    no servidor e registra a aprovação. Retorna (erro, gerente_aprovador)."""
    limite = desconto_maximo_por_papel(papel)
    if desconto <= limite:
        return None, None
    login = str(dados.get("gerente_login") or "").strip().upper()
    senha = str(dados.get("gerente_senha") or "")
    if not login or not senha:
        return f"Desconto acima do limite ({limite}%) — é necessária a aprovação de um gerente.", None
    conexao = conectar()
    gerente = conexao.execute(
        "SELECT * FROM usuarios WHERE upper(usuario) = upper(?)", (login,)
    ).fetchone()
    if not gerente:
        conexao.close()
        return "Usuário autorizador não encontrado.", None
    papel_g = str(gerente["papel"] or "").upper()
    if papel_g not in PAPEIS_GESTAO and login not in AUTORIZADORES:
        conexao.close()
        return "Apenas usuários autorizados podem aprovar.", None
    hash_s = gerente["senha"]
    ok_senha = check_password_hash(hash_s, senha) if hash_s.startswith(("pbkdf2:", "scrypt:")) else hash_s == senha
    if not ok_senha:
        conexao.close()
        return "Senha do autorizador inválida.", None
    vendedor = session.get("usuario") or "?"
    agora = agora_sp().strftime("%d/%m/%Y %H:%M")
    conexao.execute(
        "INSERT INTO aprovacoes (acao, referencia, vendedor, detalhe, gerente, status, criacao, aprovado_em) VALUES (?,?,?,?,?,?,?,?)",
        ("Desconto acima do limite", "", vendedor, "Desconto de %s%% (limite %s%%)" % (desconto, limite), login, "APROVADO", agora, agora)
    )
    conexao.commit()
    conexao.close()
    return None, login


def validar_itens(itens, campo_nome):
    if not isinstance(itens, list):
        return None, "A lista de itens é inválida."
    resultado = []
    for item in itens:
        if not isinstance(item, dict):
            return None, "Um item informado é inválido."
        nome = str(item.get(campo_nome, "")).strip()
        try:
            quantidade = float(item.get("quantidade", 1))
            valor = float(item.get("valor", 0))
        except (TypeError, ValueError):
            return None, "Quantidade e valor devem ser numéricos."
        if not nome or quantidade <= 0 or valor < 0:
            return None, "Preencha itens com nome, quantidade positiva e valor válido."
        resultado.append((nome, quantidade, valor))
    return resultado, None


def verificar_vencimentos():
    """Marca como 'vencida' todas as vendas a prazo cujo vencimento já passou."""
    from datetime import datetime
    hoje = agora_sp().strftime("%Y-%m-%d")
    try:
        conexao = conectar()
        cur = conexao.cursor()
        if USAR_POSTGRES:
            cur.execute(
                "UPDATE vendas SET status = 'vencida' WHERE condicao = 'aprazo' AND status <> 'vencida' AND COALESCE(vencimento,'') <> '' AND vencimento < %s",
                (hoje,)
            )
        else:
            cur.execute(
                "UPDATE vendas SET status = 'vencida' WHERE condicao = 'aprazo' AND status <> 'vencida' AND COALESCE(vencimento,'') <> '' AND vencimento < ?",
                (hoje,)
            )
        alteradas = cur.rowcount
        conexao.commit()
        conexao.close()
        if alteradas:
            print(f"[VENCIMENTOS] {alteradas} venda(s) marcada(s) como vencida(s).")
    except Exception as e:
        print(f"[VENCIMENTOS] Erro ao verificar vencimentos: {e}")


def _loop_vencimentos():
    """Thread em background que verifica vencimentos a cada 60 segundos."""
    import time
    while True:
        time.sleep(60)
        verificar_vencimentos()


@app.after_request
def cabecalhos_seguranca(resposta):
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "SAMEORIGIN"
    resposta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resposta


@app.errorhandler(413)
def requisicao_grande(_erro):
    return jsonify({"erro": "A requisição excede o limite de 1 MB."}), 413


def _erro_coluna_duplicada(erro):
    texto = str(erro).lower()
    if "duplicate column" in texto:
        return True
    if "duplicate column name" in texto:
        return True
    if "already exists" in texto and "column" in texto:
        return True
    if "duplicate_column" in texto:
        return True
    return False


def _erro_duplicado(erro):
    """Retorna True quando o erro indica violação de unicidade (SQLite ou PG)."""
    texto = str(erro).lower()
    if "unique constraint" in texto:
        return True
    if "duplicate key" in texto or "duplicate_key" in texto:
        return True
    if "unique_violation" in texto:
        return True
    if "integrityerror" in texto:
        return True
    return False


def criar_banco():

    if USAR_POSTGRES:
        _criar_banco_postgres()
    else:
        _criar_banco_sqlite()


def _garantir_setores_sqlite(cursor):
    for setor in SETORES_LOGIN:
        cursor.execute(
            "SELECT id, senha, papel FROM usuarios WHERE upper(usuario) = ?",
            (setor["nome"],)
        )
        existente = cursor.fetchone()
        senha_hash = generate_password_hash(setor["senha"])
        if existente:
            cursor.execute(
                "UPDATE usuarios SET senha = ?, papel = ?, tipo = 'SETOR' WHERE id = ?",
                (senha_hash, setor["papel"], existente["id"])
            )
        else:
            cursor.execute(
                "INSERT INTO usuarios (usuario, senha, papel, tipo) VALUES (?, ?, ?, 'SETOR')",
                (setor["nome"], senha_hash, setor["papel"])
            )


def _criar_banco_sqlite():
    conexao = conectar()
    cursor = conexao.cursor()    # =========================
    # USUÁRIOS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            papel TEXT NOT NULL DEFAULT 'VENDEDOR'
        )
    """)

    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN papel TEXT NOT NULL DEFAULT 'VENDEDOR'")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise
    # Migração da hierarquia: administrador e Breno (gerente) mantêm acesso
    # completo sem interromper a operação atual.
    cursor.execute("UPDATE usuarios SET papel = 'VENDEDOR' WHERE papel = 'TRIAGEM'")
    cursor.execute("UPDATE usuarios SET papel = 'DONO' WHERE papel = 'ADMIN'")

    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN tipo TEXT NOT NULL DEFAULT 'PESSOA'")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise

    for nome, papel in USUARIOS_INICIAIS:
        cursor.execute(
            "SELECT id FROM usuarios WHERE upper(usuario) = ?",
            (nome,)
        )
        existente = cursor.fetchone()
        if existente:
            cursor.execute(
                "UPDATE usuarios SET usuario = ?, papel = ? WHERE id = ?",
                (nome, papel, existente["id"])
            )
        else:
            cursor.execute(
                "INSERT INTO usuarios (usuario, senha, papel) VALUES (?, ?, ?)",
                (nome, generate_password_hash(SENHA_TEMPORARIA_PADRAO), papel)
            )

    _garantir_setores_sqlite(cursor)

    # O primeiro administrador é criado somente quando a senha é definida no
    # ambiente. Isso evita publicar uma credencial conhecida em produção.
    cursor.execute("SELECT id FROM usuarios WHERE usuario = ?", ("admin",))
    if not cursor.fetchone() and os.environ.get("ADMIN_PASSWORD"):
        cursor.execute(
            "INSERT INTO usuarios (usuario, senha) VALUES (?, ?)",
            ("admin", generate_password_hash(os.environ["ADMIN_PASSWORD"]))
        )

    # =========================
    # ORDENS DE SERVIÇO
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER UNIQUE,
            data_entrada TEXT,
            cliente TEXT,
            telefone TEXT,
            problema TEXT,
            solucao TEXT,
            responsavel TEXT,
            mao_obra REAL,
            total REAL,
            status TEXT DEFAULT 'Em andamento'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ordem_id INTEGER,
            nome TEXT,
            quantidade REAL DEFAULT 1,
            valor REAL,
            FOREIGN KEY (ordem_id) REFERENCES ordens(id)
        )
    """)

    # ATUALIZAÇÕES BANCO ANTIGO
    for comando in [
        "ALTER TABLE ordens ADD COLUMN status TEXT DEFAULT 'Em andamento'",
        "ALTER TABLE ordens ADD COLUMN responsavel TEXT",
        "ALTER TABLE ordens ADD COLUMN cliente TEXT",
        "ALTER TABLE ordens ADD COLUMN telefone TEXT",
        "ALTER TABLE itens ADD COLUMN quantidade REAL DEFAULT 1"
    ]:
        try:
            cursor.execute(comando)
        except sqlite3.OperationalError as erro:
            if not _erro_coluna_duplicada(erro):
                raise

    _inicializar_controle_os(cursor)

    # =========================
    # NOTA DOBRADA - VENDAS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER UNIQUE NOT NULL,
            cliente TEXT,
            fantasia TEXT,
            telefone TEXT,
            vendedor TEXT,
            data TEXT,
            condicao TEXT,
            vencimento TEXT,
            desconto REAL DEFAULT 0,
            observacao TEXT,
            endereco TEXT,
            total REAL DEFAULT 0,
            comissao REAL DEFAULT 0,
            status TEXT DEFAULT 'ativa'
        )
    """)

    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN telefone TEXT")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise

    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN endereco TEXT")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS venda_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venda_id INTEGER NOT NULL,
            quantidade REAL DEFAULT 1,
            descricao TEXT,
            valor REAL DEFAULT 0,
            FOREIGN KEY (venda_id) REFERENCES vendas(id)
        )
    """)

    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN comissao REAL DEFAULT 0")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise

    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN status TEXT DEFAULT 'ativa'")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise

    # Mantém vendas existentes compatíveis com a comissão fixa.
    cursor.execute(
        "UPDATE vendas SET comissao = ROUND(COALESCE(total, 0) * ? / 100, 2)",
        (COMISSAO_PERCENTUAL,)
    )

    _inicializar_controle_vendas(cursor)

    # =========================
    # DEVOLUÇÕES
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devolucoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER UNIQUE NOT NULL,
            venda_id INTEGER,
            data TEXT,
            motivo TEXT,
            observacao TEXT,
            total REAL DEFAULT 0,
            vendedor TEXT,
            cliente TEXT,
            FOREIGN KEY (venda_id) REFERENCES vendas(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devolucao_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            devolucao_id INTEGER NOT NULL,
            quantidade REAL DEFAULT 1,
            descricao TEXT,
            valor REAL DEFAULT 0,
            FOREIGN KEY (devolucao_id) REFERENCES devolucoes(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_devolucoes (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT id FROM controle_devolucoes WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO controle_devolucoes (id, ultimo_numero) VALUES (1, 0)")

    try:
        cursor.execute("ALTER TABLE devolucoes ADD COLUMN cliente TEXT")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER UNIQUE NOT NULL,
            venda_id INTEGER,
            ordem_id INTEGER,
            cliente TEXT,
            telefone TEXT,
            endereco TEXT,
            bairro TEXT,
            entregador TEXT,
            data_entrega TEXT,
            horario TEXT,
            taxa REAL DEFAULT 0,
            status TEXT DEFAULT 'Pendente',
            observacao TEXT,
            comprovante TEXT,
            criacao TEXT,
            FOREIGN KEY (venda_id) REFERENCES vendas(id),
            FOREIGN KEY (ordem_id) REFERENCES ordens(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_entregas (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT id FROM controle_entregas WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO controle_entregas (id, ultimo_numero) VALUES (1, 0)")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aprovacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            acao TEXT NOT NULL,
            referencia TEXT,
            vendedor TEXT,
            detalhe TEXT,
            gerente TEXT,
            status TEXT DEFAULT 'PENDENTE',
            criacao TEXT,
            aprovado_em TEXT
        )
    """)

    try:
        cursor.execute("ALTER TABLE entregas ADD COLUMN qr_token TEXT")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise
    try:
        cursor.execute("ALTER TABLE entregas ADD COLUMN data_saida TEXT")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise
    try:
        cursor.execute("ALTER TABLE entregas ADD COLUMN data_entregue TEXT")
    except sqlite3.OperationalError as erro:
        if not _erro_coluna_duplicada(erro):
            raise

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entrega_historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entrega_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            data_hora TEXT NOT NULL,
            usuario TEXT,
            FOREIGN KEY (entrega_id) REFERENCES entregas(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    # config padrão da Zebra
    cursor.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", ("zebra_nome", "ELGIN i9 (USB)"))
    cursor.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", ("zebra_largura", "80"))
    cursor.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", ("zebra_auto", "1"))

    # =========================
    # ORÇAMENTOS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER UNIQUE NOT NULL,
            vendedor TEXT,
            cliente TEXT,
            telefone TEXT,
            endereco TEXT,
            condicao TEXT,
            validade_dias INTEGER DEFAULT 30,
            observacao TEXT,
            total REAL DEFAULT 0,
            status TEXT DEFAULT 'aberto',
            venda_id INTEGER,
            criacao TEXT,
            created_by TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamento_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER NOT NULL,
            tipo TEXT DEFAULT 'PRODUTO',
            quantidade REAL DEFAULT 1,
            descricao TEXT,
            valor REAL DEFAULT 0,
            FOREIGN KEY (orcamento_id) REFERENCES orcamentos(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_orcamentos (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT id FROM controle_orcamentos WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO controle_orcamentos (id, ultimo_numero) VALUES (1, 0)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orcamentos_numero ON orcamentos(numero DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orcamento_itens_orcamento ON orcamento_itens(orcamento_id)")

    # Índices mantêm as telas de triagem e acompanhamento rápidas quando a
    # base crescer.
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ordens_numero ON ordens(numero DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ordens_status ON ordens(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_itens_ordem ON itens(ordem_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vendas_numero ON vendas(numero DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_venda_itens_venda ON venda_itens(venda_id)")

    conexao.commit()
    conexao.close()


def _inicializar_controle_os(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_os (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT ultimo_numero FROM controle_os WHERE id = 1")
    controle = cursor.fetchone()
    if controle is None:
        cursor.execute("SELECT MAX(numero) FROM ordens")
        maior_numero = cursor.fetchone()[0]
        ultimo_numero = 0 if maior_numero is None else maior_numero
        cursor.execute(
            "INSERT INTO controle_os (id, ultimo_numero) VALUES (1, ?)",
            (ultimo_numero,)
        )


def _inicializar_controle_vendas(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_vendas (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT id FROM controle_vendas WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO controle_vendas (id, ultimo_numero) VALUES (1, 0)"
        )


def _garantir_setores_postgres(cursor):
    for setor in SETORES_LOGIN:
        cursor.execute(
            "SELECT id, senha, papel FROM usuarios WHERE upper(usuario) = %s",
            (setor["nome"],)
        )
        existente = cursor.fetchone()
        senha_hash = generate_password_hash(setor["senha"])
        if existente:
            cursor.execute(
                "UPDATE usuarios SET senha = %s, papel = %s, tipo = 'SETOR' WHERE id = %s",
                (senha_hash, setor["papel"], existente["id"])
            )
        else:
            cursor.execute(
                "INSERT INTO usuarios (usuario, senha, papel, tipo) VALUES (%s, %s, %s, 'SETOR')",
                (setor["nome"], senha_hash, setor["papel"])
            )


def _criar_banco_postgres():

    conexao = conectar()
    cursor = conexao.cursor()

    # =========================
    # USUÁRIOS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            usuario TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            papel TEXT NOT NULL DEFAULT 'VENDEDOR',
            tipo TEXT NOT NULL DEFAULT 'PESSOA'
        )
    """)

    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'PESSOA'")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ativa'")
    except Exception:
        pass

    for nome, papel in USUARIOS_INICIAIS:
        cursor.execute("SELECT id FROM usuarios WHERE upper(usuario) = %s", (nome,))
        existente = cursor.fetchone()
        if existente:
            cursor.execute(
                "UPDATE usuarios SET usuario = %s, papel = %s WHERE id = %s",
                (nome, papel, existente["id"])
            )
        else:
            cursor.execute(
                "INSERT INTO usuarios (usuario, senha, papel) VALUES (%s, %s, %s)",
                (nome, generate_password_hash(SENHA_TEMPORARIA_PADRAO), papel)
            )

    _garantir_setores_postgres(cursor)

    cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", ("admin",))
    if not cursor.fetchone() and os.environ.get("ADMIN_PASSWORD"):
        cursor.execute(
            "INSERT INTO usuarios (usuario, senha) VALUES (%s, %s)",
            ("admin", generate_password_hash(os.environ["ADMIN_PASSWORD"]))
        )

    # =========================
    # ORDENS DE SERVIÇO
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordens (
            id SERIAL PRIMARY KEY,
            numero INTEGER UNIQUE,
            data_entrada TEXT,
            cliente TEXT,
            telefone TEXT,
            problema TEXT,
            solucao TEXT,
            responsavel TEXT,
            mao_obra DOUBLE PRECISION,
            total DOUBLE PRECISION,
            status TEXT DEFAULT 'Em andamento'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS itens (
            id SERIAL PRIMARY KEY,
            ordem_id INTEGER,
            nome TEXT,
            quantidade DOUBLE PRECISION DEFAULT 1,
            valor DOUBLE PRECISION,
            FOREIGN KEY (ordem_id) REFERENCES ordens(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_os (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT ultimo_numero FROM controle_os WHERE id = 1")
    controle = cursor.fetchone()
    if controle is None:
        cursor.execute("SELECT COALESCE(MAX(numero), 0) AS max FROM ordens")
        maior_numero = list(cursor.fetchone().values())[0]
        cursor.execute(
            "INSERT INTO controle_os (id, ultimo_numero) VALUES (%s, %s)",
            (1, maior_numero)
        )

    # =========================
    # NOTA DOBRADA - VENDAS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id SERIAL PRIMARY KEY,
            numero INTEGER UNIQUE NOT NULL,
            cliente TEXT,
            fantasia TEXT,
            telefone TEXT,
            vendedor TEXT,
            data TEXT,
            condicao TEXT,
            vencimento TEXT,
            desconto DOUBLE PRECISION DEFAULT 0,
            observacao TEXT,
            endereco TEXT,
            total DOUBLE PRECISION DEFAULT 0,
            comissao DOUBLE PRECISION DEFAULT 0,
            status TEXT DEFAULT 'ativa'
        )
    """)
    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN IF NOT EXISTS telefone TEXT")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE vendas ADD COLUMN IF NOT EXISTS endereco TEXT")
    except Exception:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS venda_itens (
            id SERIAL PRIMARY KEY,
            venda_id INTEGER NOT NULL,
            quantidade DOUBLE PRECISION DEFAULT 1,
            descricao TEXT,
            valor DOUBLE PRECISION DEFAULT 0,
            FOREIGN KEY (venda_id) REFERENCES vendas(id)
        )
    """)

    cursor.execute(
        "UPDATE vendas SET comissao = ROUND(CAST(COALESCE(total, 0) * %s / 100 AS numeric), 2)",
        (COMISSAO_PERCENTUAL,)
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_vendas (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT id FROM controle_vendas WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO controle_vendas (id, ultimo_numero) VALUES (%s, %s)",
            (1, 0)
        )

    # =========================
    # DEVOLUÇÕES
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devolucoes (
            id SERIAL PRIMARY KEY,
            numero INTEGER UNIQUE NOT NULL,
            venda_id INTEGER,
            data TEXT,
            motivo TEXT,
            observacao TEXT,
            total DOUBLE PRECISION DEFAULT 0,
            vendedor TEXT,
            cliente TEXT,
            FOREIGN KEY (venda_id) REFERENCES vendas(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devolucao_itens (
            id SERIAL PRIMARY KEY,
            devolucao_id INTEGER NOT NULL,
            quantidade DOUBLE PRECISION DEFAULT 1,
            descricao TEXT,
            valor DOUBLE PRECISION DEFAULT 0,
            FOREIGN KEY (devolucao_id) REFERENCES devolucoes(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_devolucoes (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT id FROM controle_devolucoes WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO controle_devolucoes (id, ultimo_numero) VALUES (%s, %s)", (1, 0))

    cursor.execute("ALTER TABLE devolucoes ADD COLUMN IF NOT EXISTS cliente TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entregas (
            id SERIAL PRIMARY KEY,
            numero INTEGER UNIQUE NOT NULL,
            venda_id INTEGER,
            ordem_id INTEGER,
            cliente TEXT,
            telefone TEXT,
            endereco TEXT,
            bairro TEXT,
            entregador TEXT,
            data_entrega TEXT,
            horario TEXT,
            taxa DOUBLE PRECISION DEFAULT 0,
            status TEXT DEFAULT 'Pendente',
            observacao TEXT,
            comprovante TEXT,
            criacao TEXT,
            FOREIGN KEY (venda_id) REFERENCES vendas(id),
            FOREIGN KEY (ordem_id) REFERENCES ordens(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_entregas (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT id FROM controle_entregas WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO controle_entregas (id, ultimo_numero) VALUES (%s, %s)", (1, 0))

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS aprovacoes (
            id SERIAL PRIMARY KEY,
            acao TEXT NOT NULL,
            referencia TEXT,
            vendedor TEXT,
            detalhe TEXT,
            gerente TEXT,
            status TEXT DEFAULT 'PENDENTE',
            criacao TEXT,
            aprovado_em TEXT
        )
    """)

    try:
        cursor.execute("ALTER TABLE entregas ADD COLUMN IF NOT EXISTS qr_token TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE entregas ADD COLUMN IF NOT EXISTS data_saida TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE entregas ADD COLUMN IF NOT EXISTS data_entregue TEXT")
    except Exception:
        pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entrega_historico (
            id SERIAL PRIMARY KEY,
            entrega_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            data_hora TEXT NOT NULL,
            usuario TEXT,
            FOREIGN KEY (entrega_id) REFERENCES entregas(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    """)
    cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES (%s, %s) ON CONFLICT (chave) DO NOTHING", ("zebra_nome", "ELGIN i9 (USB)"))
    cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES (%s, %s) ON CONFLICT (chave) DO NOTHING", ("zebra_largura", "80"))
    cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES (%s, %s) ON CONFLICT (chave) DO NOTHING", ("zebra_auto", "1"))

    # =========================
    # ORÇAMENTOS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos (
            id SERIAL PRIMARY KEY,
            numero INTEGER UNIQUE NOT NULL,
            vendedor TEXT,
            cliente TEXT,
            telefone TEXT,
            endereco TEXT,
            condicao TEXT,
            validade_dias INTEGER DEFAULT 30,
            observacao TEXT,
            total DOUBLE PRECISION DEFAULT 0,
            status TEXT DEFAULT 'aberto',
            venda_id INTEGER,
            criacao TEXT,
            created_by TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamento_itens (
            id SERIAL PRIMARY KEY,
            orcamento_id INTEGER NOT NULL,
            tipo TEXT DEFAULT 'PRODUTO',
            quantidade DOUBLE PRECISION DEFAULT 1,
            descricao TEXT,
            valor DOUBLE PRECISION DEFAULT 0,
            FOREIGN KEY (orcamento_id) REFERENCES orcamentos(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_orcamentos (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)
    cursor.execute("SELECT id FROM controle_orcamentos WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO controle_orcamentos (id, ultimo_numero) VALUES (%s, %s)", (1, 0))
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orcamentos_numero ON orcamentos(numero DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orcamento_itens_orcamento ON orcamento_itens(orcamento_id)")
    except Exception:
        pass

    # Índices
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ordens_numero ON ordens(numero DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ordens_status ON ordens(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_itens_ordem ON itens(ordem_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vendas_numero ON vendas(numero DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_venda_itens_venda ON venda_itens(venda_id)")
    except Exception:
        conexao.rollback()
        conexao.close()
        raise

    conexao.commit()
    conexao.close()


criar_banco()


# =========================
# LOGIN OBRIGATÓRIO
# =========================

def login_obrigatorio(funcao):

    @wraps(funcao)
    def verificar(*args, **kwargs):

        if "usuario" not in session or not usuario_e_setor(session["usuario"]):
            session.clear()
            return redirect(url_for("login"))

        return funcao(*args, **kwargs)

    return verificar


# =========================
# CONTROLE DE ACESSO POR PAPEL
# =========================

def requer_papeis(*papeis_permitidos):
    permitidos = {str(p).upper() for p in papeis_permitidos}
    def decorador(funcao):
        @wraps(funcao)
        def verificar(*args, **kwargs):
            if "usuario" not in session:
                return redirect(url_for("login"))
            papel = obter_papel_usuario(session["usuario"])
            if not papel or papel.upper() not in permitidos:
                return jsonify({"erro": f"Acesso permitido somente para: {', '.join(sorted(permitidos))}."}), 403
            return funcao(*args, **kwargs)
        return verificar
    return decorador


def requer_nivel_minimo(papel_minimo):
    nivel_min = nivel_do_papel(papel_minimo)
    def decorador(funcao):
        @wraps(funcao)
        def verificar(*args, **kwargs):
            if "usuario" not in session:
                return redirect(url_for("login"))
            papel = obter_papel_usuario(session["usuario"])
            if nivel_do_papel(papel) < nivel_min:
                return jsonify({"erro": f"Acesso requer nível mínimo: {papel_minimo}."}), 403
            return funcao(*args, **kwargs)
        return verificar
    return decorador


# Compatibilidade: gestao = DONO + GERENTE
def admin_obrigatorio(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        conexao = conectar()
        usuario = conexao.execute(
            "SELECT papel FROM usuarios WHERE upper(usuario) = upper(?)",
            (session["usuario"],)
        ).fetchone()
        conexao.close()
        if not usuario or usuario["papel"] not in PAPEIS_GESTAO:
            return jsonify({"erro": "Acesso permitido somente para Dono ou Gerente."}), 403
        return funcao(*args, **kwargs)
    return verificar


def financeiro_obrigatorio(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        papel = obter_papel_usuario(session["usuario"])
        if not papel or papel.upper() not in PAPEIS_FINANCEIRO:
            return jsonify({"erro": "Acesso permitido somente para Dono, Gerente ou Financeiro."}), 403
        return funcao(*args, **kwargs)
    return verificar


def dono_obrigatorio(funcao):
    @wraps(funcao)
    def verificar(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        papel = obter_papel_usuario(session["usuario"])
        if not papel or papel.upper() != "DONO":
            return jsonify({"erro": "Acesso permitido somente para Dono."}), 403
        return funcao(*args, **kwargs)
    return verificar


# =========================
# LOGIN - LISTA PÚBLICA PARA SELEÇÃO RÁPIDA
# =========================

@app.route("/api/public/usuarios")
def api_public_usuarios():
    conexao = conectar()
    usuarios = conexao.execute(
        "SELECT usuario, papel FROM usuarios WHERE tipo = 'SETOR' ORDER BY usuario"
    ).fetchall()
    conexao.close()
    return jsonify([{"usuario": u["usuario"], "papel": u["papel"]} for u in usuarios])


@app.route("/manifest.webmanifest")
def servir_manifest():
    from flask import send_from_directory
    return send_from_directory("static", "manifest.webmanifest", mimetype="application/manifest+json")


@app.route("/sw.js")
def servir_sw():
    from flask import send_from_directory
    return send_from_directory("static", "sw.js", mimetype="application/javascript")


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        usuario = normalizar_usuario(request.form.get("usuario", ""))
        senha = request.form.get("senha", "")

        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute(
            "SELECT * FROM usuarios WHERE upper(usuario) = upper(?)",
            (usuario,)
        )

        resultado = cursor.fetchone()

        conexao.close()

        if (
            resultado
            and usuario_e_setor(usuario)
            and (
                check_password_hash(resultado["senha"], senha)
                if resultado["senha"].startswith(("pbkdf2:", "scrypt:"))
                else resultado["senha"] == senha
            )
        ):

            # Migração transparente das senhas legadas em texto puro.
            if not resultado["senha"].startswith(("pbkdf2:", "scrypt:")):
                conexao = conectar()
                conexao.execute(
                    "UPDATE usuarios SET senha = ? WHERE id = ?",
                    (generate_password_hash(senha), resultado["id"])
                )
                conexao.commit()
                conexao.close()

            session["usuario"] = normalizar_usuario(usuario)

            return redirect(url_for("inicio"))

        resp = make_response(render_template(
            "login.html",
            erro="Usuário ou senha incorretos!"
        ))
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    resp = make_response(render_template("login.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()
    resp = make_response(redirect(url_for("login")))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
@login_obrigatorio
def dashboard():

    return render_template(
        "dashboard.html",
        usuario=session["usuario"],
        papel=obter_papel_usuario(session["usuario"])
    )


# =========================
# PÁGINA PRINCIPAL
# =========================

@app.route("/")
@login_obrigatorio
def inicio():

    return render_template(
        "index.html",
        usuario=session["usuario"],
        papel=obter_papel_usuario(session["usuario"]),
        pode_gerenciar_usuarios=usuario_tem_gestao(session["usuario"])
    )


# =========================
# MINHA SENHA
# =========================

@app.route("/minha_senha")
@login_obrigatorio
def minha_senha():

    return render_template(
        "minha_senha.html",
        usuario=session["usuario"],
        papel=obter_papel_usuario(session["usuario"])
    )


@app.route("/api/minha_senha", methods=["PUT"])
@login_obrigatorio
def alterar_minha_senha():

    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400

    senha_atual = dados.get("senha_atual", "").strip()
    nova_senha = dados.get("nova_senha", "").strip()

    if not senha_atual or not nova_senha:

        return jsonify({
            "erro": "Preencha todos os campos."
        }), 400

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT senha FROM usuarios WHERE usuario = ?",
        (session["usuario"],)
    )

    usuario = cursor.fetchone()

    senha_confere = usuario and (
        check_password_hash(usuario["senha"], senha_atual)
        if usuario["senha"].startswith(("pbkdf2:", "scrypt:"))
        else usuario["senha"] == senha_atual
    )
    if not senha_confere:

        conexao.close()

        return jsonify({
            "erro": "A senha atual está incorreta."
        }), 400

    if not senha_valida(nova_senha):
        conexao.close()
        return jsonify({"erro": "A nova senha deve ter ao menos 4 caracteres."}), 400

    cursor.execute(
        "UPDATE usuarios SET senha = ? WHERE usuario = ?",
        (generate_password_hash(nova_senha), session["usuario"])
    )

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Senha alterada com sucesso!"
    })


# =========================
# GERENCIAMENTO DE USUÁRIOS
# =========================

@app.route("/usuarios")
@admin_obrigatorio
def usuarios():

    return render_template(
        "usuarios.html",
        usuario_logado=session["usuario"],
        papel_logado=obter_papel_usuario(session["usuario"])
    )


@app.route("/api/usuarios")
@admin_obrigatorio
def listar_usuarios():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
            "SELECT id, usuario, papel FROM usuarios ORDER BY usuario"
    )

    usuarios = cursor.fetchall()

    conexao.close()

    return jsonify([
        {
            "id": usuario["id"],
            "usuario": usuario["usuario"],
            "papel": usuario["papel"]
        }
        for usuario in usuarios
    ])


@app.route("/api/vendedores")
@login_obrigatorio
def listar_vendedores():
    conexao = conectar()
    vendedores = conexao.execute(
        "SELECT id, usuario, papel FROM usuarios "
        "WHERE papel IN ('VENDEDOR', 'GERENTE', 'DONO') AND lower(usuario) <> 'admin' "
        "AND (tipo IS NULL OR tipo <> 'SETOR') ORDER BY usuario"
    ).fetchall()
    conexao.close()

    return jsonify([
        {
            "id": vendedor["id"],
            "usuario": vendedor["usuario"],
            "papel": vendedor["papel"]
        }
        for vendedor in vendedores
    ])


@app.route("/api/usuarios", methods=["POST"])
@admin_obrigatorio
def criar_usuario():

    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400

    usuario = normalizar_usuario(dados.get("usuario", ""))
    senha = dados.get("senha", "").strip()
    papel = str(dados.get("papel", "VENDEDOR")).upper()

    if not usuario or not senha:

        return jsonify({
            "erro": "Preencha usuário e senha."
        }), 400

    if not senha_valida(senha):
        return jsonify({"erro": "A senha deve ter ao menos 4 caracteres."}), 400
    if papel not in PAPEIS:
        return jsonify({"erro": "Perfil de acesso inválido."}), 400

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            "INSERT INTO usuarios (usuario, senha, papel) VALUES (?, ?, ?)",
            (usuario, generate_password_hash(senha), papel)
        )

        conexao.commit()

    except Exception as erro:

        conexao.close()

        if _erro_duplicado(erro):
            return jsonify({
                "erro": "Este usuário já existe."
            }), 400

        raise

    conexao.close()

    return jsonify({
        "mensagem": "Usuário criado com sucesso!"
    })


@app.route("/api/usuarios/<int:id>/papel", methods=["PUT"])
@admin_obrigatorio
def alterar_papel_usuario(id):
    dados = json_body()
    papel = str((dados or {}).get("papel", "")).upper()
    if papel not in PAPEIS:
        return jsonify({"erro": "Perfil de acesso inválido."}), 400

    conexao = conectar()
    usuario = conexao.execute("SELECT usuario FROM usuarios WHERE id = ?", (id,)).fetchone()
    if not usuario:
        conexao.close()
        return jsonify({"erro": "Usuário não encontrado."}), 404
    if usuario["usuario"] == "admin" and papel != "DONO":
        conexao.close()
        return jsonify({"erro": "O administrador principal deve permanecer administrador."}), 400
    conexao.execute("UPDATE usuarios SET papel = ? WHERE id = ?", (papel, id))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Permissão atualizada com sucesso!"})


@app.route("/api/usuarios/<int:id>/senha", methods=["PUT"])
@admin_obrigatorio
def alterar_senha_usuario(id):

    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400

    nova_senha = dados.get("senha", "").strip()

    if not senha_valida(nova_senha):

        return jsonify({
            "erro": "Digite uma senha com ao menos 4 caracteres."
        }), 400

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "UPDATE usuarios SET senha = ? WHERE id = ?",
        (generate_password_hash(nova_senha), id)
    )

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Senha alterada com sucesso!"
    })


@app.route("/api/usuarios/<int:id>", methods=["DELETE"])
@admin_obrigatorio
def excluir_usuario(id):

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT usuario FROM usuarios WHERE id = ?",
        (id,)
    )

    usuario = cursor.fetchone()

    if not usuario:

        conexao.close()

        return jsonify({
            "erro": "Usuário não encontrado."
        }), 404

    if usuario["usuario"] == "admin":

        conexao.close()

        return jsonify({
            "erro": "O usuário admin não pode ser excluído."
        }), 400

    cursor.execute(
        "DELETE FROM usuarios WHERE id = ?",
        (id,)
    )

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Usuário excluído com sucesso!"
    })


# =========================
# USUÁRIOS PARA OS
# =========================

@app.route("/usuarios_os")
@login_obrigatorio
def usuarios_os():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT usuario FROM usuarios ORDER BY usuario"
    )

    usuarios = cursor.fetchall()

    conexao.close()

    return jsonify([
        usuario["usuario"]
        for usuario in usuarios
    ])


# =========================
# PRÓXIMO NÚMERO DA OS
# =========================

@app.route("/proximo_numero")
@login_obrigatorio
def proximo_numero():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT ultimo_numero FROM controle_os WHERE id = 1"
    )

    resultado = cursor.fetchone()

    ultimo_numero = (
        0 if resultado is None
        else resultado["ultimo_numero"]
    )

    conexao.close()

    return jsonify({
        "numero": ultimo_numero + 1
    })


# =========================
# SALVAR OS
# =========================

@app.route("/salvar_os", methods=["POST"])
@login_obrigatorio
def salvar_os():

    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400
    if not str(dados.get("cliente", "")).strip():
        return jsonify({"erro": "Informe o cliente da OS."}), 400
    if not str(dados.get("responsavel", "")).strip():
        return jsonify({"erro": "Selecione o responsável."}), 400
    if not str(dados.get("data_entrada", "")).strip() or not str(dados.get("problema", "")).strip():
        return jsonify({"erro": "Data de entrada e problema são obrigatórios."}), 400
    itens, erro = validar_itens(dados.get("itens"), "nome")
    if erro:
        return jsonify({"erro": erro}), 400
    try:
        mao_obra = float(dados.get("mao_obra", 0))
    except (TypeError, ValueError):
        return jsonify({"erro": "Mão de obra inválida."}), 400
    if mao_obra < 0:
        return jsonify({"erro": "Mão de obra não pode ser negativa."}), 400

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute("BEGIN IMMEDIATE")

    cursor.execute(
        "SELECT ultimo_numero FROM controle_os WHERE id = 1"
    )

    controle = cursor.fetchone()

    ultimo_numero = (
        0 if controle is None
        else controle["ultimo_numero"]
    )

    novo_numero = ultimo_numero + 1

    cursor.execute("""
        INSERT INTO ordens
        (
            numero,
            data_entrada,
            cliente,
            telefone,
            problema,
            solucao,
            responsavel,
            mao_obra,
            total,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        novo_numero,
        dados["data_entrada"],
        dados.get("cliente", ""),
        dados.get("telefone", ""),
        dados["problema"],
        dados.get("solucao", ""),
        dados.get("responsavel", ""),
        mao_obra,
        sum(quantidade * valor for _, quantidade, valor in itens) + mao_obra,
        "Em andamento"
    ))

    ordem_id = cursor.lastrowid

    cursor.execute("""
        UPDATE controle_os
        SET ultimo_numero = ?
        WHERE id = 1
    """, (
        novo_numero,
    ))

    for nome, quantidade, valor in itens:

        cursor.execute("""
            INSERT INTO itens
            (ordem_id, nome, quantidade, valor)
            VALUES (?, ?, ?, ?)
        """, (
            ordem_id,
            nome, quantidade, valor
        ))

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Ordem salva com sucesso!",
        "numero": novo_numero
    })


# =========================
# LISTAR ORDENS
# =========================

@app.route("/ordens")
@login_obrigatorio
def listar_ordens():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT * FROM ordens ORDER BY numero DESC"
    )

    ordens = cursor.fetchall()

    conexao.close()

    resultado = []

    for ordem in ordens:

        resultado.append({
            "id": ordem["id"],
            "numero": ordem["numero"],
            "data_entrada": ordem["data_entrada"],
            "cliente": ordem["cliente"],
            "telefone": ordem["telefone"],
            "problema": ordem["problema"],
            "responsavel": ordem["responsavel"],
            "total": ordem["total"],
            "status": ordem["status"]
        })

    return jsonify(resultado)


# =========================
# BUSCAR OS
# =========================

@app.route("/ordem/<int:id>")
@login_obrigatorio
def buscar_ordem(id):

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT * FROM ordens WHERE id = ?",
        (id,)
    )

    ordem = cursor.fetchone()

    if not ordem:

        conexao.close()

        return jsonify({
            "erro": "Ordem não encontrada"
        }), 404

    cursor.execute(
        "SELECT * FROM itens WHERE ordem_id = ?",
        (id,)
    )

    itens = cursor.fetchall()

    conexao.close()

    return jsonify({
        "id": ordem["id"],
        "numero": ordem["numero"],
        "data_entrada": ordem["data_entrada"],
        "cliente": ordem["cliente"],
        "telefone": ordem["telefone"],
        "problema": ordem["problema"],
        "solucao": ordem["solucao"],
        "responsavel": ordem["responsavel"],
        "mao_obra": ordem["mao_obra"],
        "total": ordem["total"],
        "status": ordem["status"],
        "itens": [
            {
                "id": item["id"],
                "nome": item["nome"],
                "quantidade": item["quantidade"],
                "valor": item["valor"]
            }
            for item in itens
        ]
    })


# =========================
# ATUALIZAR OS
# =========================

@app.route("/atualizar_os/<int:id>", methods=["PUT"])
@login_obrigatorio
def atualizar_os(id):

    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400
    if not str(dados.get("cliente", "")).strip():
        return jsonify({"erro": "Informe o cliente da OS."}), 400
    if not str(dados.get("responsavel", "")).strip():
        return jsonify({"erro": "Selecione o responsável."}), 400
    if not str(dados.get("data_entrada", "")).strip() or not str(dados.get("problema", "")).strip():
        return jsonify({"erro": "Data de entrada e problema são obrigatórios."}), 400
    itens, erro = validar_itens(dados.get("itens"), "nome")
    if erro:
        return jsonify({"erro": erro}), 400
    try:
        mao_obra = float(dados.get("mao_obra", 0))
    except (TypeError, ValueError):
        return jsonify({"erro": "Mão de obra inválida."}), 400
    if mao_obra < 0:
        return jsonify({"erro": "Mão de obra não pode ser negativa."}), 400

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE ordens
        SET
            cliente = ?,
            telefone = ?,
            problema = ?,
            solucao = ?,
            responsavel = ?,
            mao_obra = ?,
            total = ?
        WHERE id = ?
    """, (
        dados.get("cliente", ""),
        dados.get("telefone", ""),
        dados["problema"],
        dados.get("solucao", ""),
        dados.get("responsavel", ""),
        mao_obra,
        sum(quantidade * valor for _, quantidade, valor in itens) + mao_obra,
        id
    ))

    if cursor.rowcount == 0:
        conexao.close()
        return jsonify({"erro": "Ordem não encontrada."}), 404

    cursor.execute(
        "DELETE FROM itens WHERE ordem_id = ?",
        (id,)
    )

    for nome, quantidade, valor in itens:

        cursor.execute("""
            INSERT INTO itens
            (ordem_id, nome, quantidade, valor)
            VALUES (?, ?, ?, ?)
        """, (
            id,
            nome, quantidade, valor
        ))

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Ordem atualizada com sucesso!"
    })


# =========================
# ALTERAR STATUS OS
# =========================

@app.route("/alterar_status/<int:id>", methods=["POST"])
@login_obrigatorio
def alterar_status(id):

    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400

    novo_status = dados.get("status")
    if novo_status not in STATUS_OS:
        return jsonify({"erro": "Status inválido."}), 400

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "UPDATE ordens SET status = ? WHERE id = ?",
        (novo_status, id)
    )

    if cursor.rowcount == 0:
        conexao.close()
        return jsonify({"erro": "Ordem não encontrada."}), 404

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Status atualizado!"
    })


# =========================
# EXCLUIR OS
# =========================

@app.route("/excluir_os/<int:id>", methods=["DELETE"])
@admin_obrigatorio
def excluir_os(id):

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "DELETE FROM itens WHERE ordem_id = ?",
        (id,)
    )

    cursor.execute(
        "DELETE FROM ordens WHERE id = ?",
        (id,)
    )

    if cursor.rowcount == 0:
        conexao.close()
        return jsonify({"erro": "Ordem não encontrada."}), 404

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Ordem excluída com sucesso!"
    })


# ==================================================
# NOTA DOBRADA
# ==================================================

@app.route("/nota_dobrada")
@login_obrigatorio
def pagina_nota_dobrada():

    return render_template(
        "nota_dobrada.html",
        usuario=session["usuario"],
        papel=obter_papel_usuario(session["usuario"])
    )


@app.route("/editar_venda")
@login_obrigatorio
def pagina_editar_venda():

    return render_template(
        "editar_venda.html",
        usuario=session["usuario"],
        papel=obter_papel_usuario(session["usuario"])
    )


@app.route("/acompanhamento_notas")
@login_obrigatorio
def pagina_acompanhamento_notas():

    return render_template(
        "acompanhamento_notas.html",
        usuario=session["usuario"],
        pode_visualizar_comissao=usuario_tem_gestao(session["usuario"])
    )


# =========================
# PRÓXIMO NÚMERO DA VENDA
# =========================

@app.route("/api/proxima_venda")
@login_obrigatorio
def proxima_venda():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT ultimo_numero
        FROM controle_vendas
        WHERE id = 1
    """)

    resultado = cursor.fetchone()

    ultimo_numero = (
        0 if resultado is None
        else resultado["ultimo_numero"]
    )

    conexao.close()

    return jsonify({
        "numero": ultimo_numero + 1
    })


# =========================
# SALVAR VENDA
# =========================

@app.route("/api/vendas", methods=["POST"])
@login_obrigatorio
def salvar_venda():

    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400
    if not str(dados.get("vendedor", "")).strip():
        return jsonify({"erro": "Selecione o vendedor."}), 400
    if not str(dados.get("data", "")).strip():
        return jsonify({"erro": "Informe a data da venda."}), 400
    if not str(dados.get("condicao", "")).strip():
        return jsonify({"erro": "Selecione a condição de pagamento."}), 400
    if str(dados.get("condicao", "")).strip()=="aprazo" and not str(dados.get("vencimento", "")).strip():
        return jsonify({"erro": "Informe o vencimento para vendas a prazo."}), 400
    if not str(dados.get("cliente", "")).strip():
        return jsonify({"erro": "Informe o cliente."}), 400
    itens, erro = validar_itens(dados.get("itens", []), "descricao")
    if erro:
        return jsonify({"erro": erro}), 400
    if not itens:
        return jsonify({"erro": "Adicione pelo menos um produto."}), 400
    try:
        desconto = float(dados.get("desconto", 0))
    except (TypeError, ValueError):
        return jsonify({"erro": "Desconto inválido."}), 400
    papel_usuario = obter_papel_usuario(session["usuario"]) or "VENDEDOR"
    erro_desconto, _ = _autorizar_desconto(dados, desconto, papel_usuario)
    if erro_desconto:
        return jsonify({"erro": erro_desconto, "precisa_aprovacao": True}), 403

    total = max(0, sum(quantidade * valor for _, quantidade, valor in itens) * (1 - desconto / 100))
    comissao = round(total * COMISSAO_PERCENTUAL / 100, 2)

    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute("BEGIN IMMEDIATE")

    cursor.execute("""
        SELECT ultimo_numero
        FROM controle_vendas
        WHERE id = 1
    """)

    resultado = cursor.fetchone()

    ultimo_numero = (
        0 if resultado is None
        else resultado["ultimo_numero"]
    )

    novo_numero = ultimo_numero + 1

    cliente_final = str(dados.get("cliente") or "").strip() or "CONSUMIDOR FINAL"
    cursor.execute("""
        INSERT INTO vendas (
            numero,
            cliente,
            fantasia,
            telefone,
            vendedor,
            data,
            condicao,
            vencimento,
            desconto,
            observacao,
            endereco,
            total,
            comissao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        novo_numero,
        cliente_final,
        dados.get("fantasia", ""),
        dados.get("telefone", ""),
        dados.get("vendedor", ""),
        dados.get("data", ""),
        dados.get("condicao", ""),
        dados.get("vencimento", ""),
        desconto,
        dados.get("observacao", ""),
        dados.get("endereco", ""),
        total,
        comissao
    ))

    venda_id = cursor.lastrowid

    for descricao, quantidade, valor in itens:

        cursor.execute("""
            INSERT INTO venda_itens (
                venda_id,
                quantidade,
                descricao,
                valor
            )
            VALUES (?, ?, ?, ?)
        """, (
            venda_id,
            quantidade, descricao, valor
        ))

    cursor.execute("""
        UPDATE controle_vendas
        SET ultimo_numero = ?
        WHERE id = 1
    """, (
        novo_numero,
    ))

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Venda salva com sucesso!",
        "id": venda_id,
        "numero": novo_numero,
        "comissao": comissao
    })


# =========================
# LISTAR VENDAS
# =========================

@app.route("/api/vendas")
@login_obrigatorio
def listar_vendas():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT *
        FROM vendas
        ORDER BY numero DESC
    """)

    vendas = cursor.fetchall()

    conexao.close()

    return jsonify([
        {
            "id": venda["id"],
            "numero": venda["numero"],
            "cliente": venda["cliente"],
            "fantasia": venda["fantasia"],
            "telefone": venda["telefone"],
            "vendedor": venda["vendedor"],
            "data": venda["data"],
            "condicao": venda["condicao"],
            "vencimento": venda["vencimento"],
            "desconto": venda["desconto"],
            "observacao": venda["observacao"],
            "total": venda["total"],
            "comissao": venda["comissao"]
        }
        for venda in vendas
    ])


def _normalizar_data(d):
    """Normaliza datas para YYYY-MM-DD (aceita DD/MM/YYYY ou YYYY-MM-DD)."""
    if not d:
        return None
    s = str(d).strip()
    if len(s) == 10 and "/" in s:
        p = s.split("/")
        if len(p) == 3:
            return f"{p[2]}-{p[1]}-{p[0]}"
    return s


@app.route("/api/acompanhar")
@login_obrigatorio
def acompanhar_unificado():
    conexao = conectar()
    cursor = conexao.cursor()

    resultado = []

    # Ordens de serviço
    cursor.execute("SELECT * FROM ordens ORDER BY numero DESC")
    for o in cursor.fetchall():
        resultado.append({
            "tipo": "OS",
            "id": o["id"],
            "numero": o["numero"],
            "data": _normalizar_data(o["data_entrada"]),
            "cliente": o["cliente"],
            "profissional": o["responsavel"],
            "status": o["status"],
            "total": o["total"],
            "condicao": None,
            "comissao": None,
            "vendedor": None
        })

    # Vendas
    cursor.execute("SELECT * FROM vendas ORDER BY numero DESC")
    for v in cursor.fetchall():
        resultado.append({
            "tipo": "VENDA",
            "id": v["id"],
            "numero": v["numero"],
            "data": _normalizar_data(v["data"]),
            "cliente": v["cliente"],
            "telefone": v["telefone"],
            "profissional": v["vendedor"],
            "status": v["status"],
            "total": v["total"],
            "condicao": v["condicao"],
            "comissao": v["comissao"],
            "vendedor": v["vendedor"]
        })

    conexao.close()

    resultado.sort(key=lambda x: (x["data"] or "")[:10], reverse=True)
    return jsonify(resultado)


# =========================
# RESUMO DO DASHBOARD
# =========================

@app.route("/api/dashboard/resumo")
@login_obrigatorio
def resumo_dashboard():
    from datetime import datetime
    mes = (request.args.get("mes") or "").strip()
    if not mes:
        mes = agora_sp().strftime("%Y-%m")
    conexao = conectar()
    cursor = conexao.cursor()

    filtro = f"{mes}%" 
    cursor.execute("""
        SELECT
            COALESCE(vendedor, 'SEM VENDEDOR') AS vendedor,
            COUNT(*) AS vendas,
            ROUND(CAST(COALESCE(SUM(total), 0) AS NUMERIC), 2) AS total_vendas,
            ROUND(CAST(COALESCE(SUM(comissao), 0) AS NUMERIC), 2) AS total_comissao
        FROM vendas
        WHERE COALESCE(vendedor, '') <> '' AND COALESCE(data,'') LIKE ?
        GROUP BY vendedor
        ORDER BY total_vendas DESC, vendas DESC, vendedor ASC
    """, (filtro,))

    vendas_por_vendedor = cursor.fetchall()
    conexao.close()

    total_vendas = sum(int(item["vendas"]) for item in vendas_por_vendedor)
    total_arrecadado = round(sum(float(item["total_vendas"]) for item in vendas_por_vendedor), 2)
    total_comissao = round(sum(float(item["total_comissao"]) for item in vendas_por_vendedor), 2)
    melhor_vendedor = (
        {
            "vendedor": vendas_por_vendedor[0]["vendedor"],
            "vendas": vendas_por_vendedor[0]["vendas"],
            "total_vendas": vendas_por_vendedor[0]["total_vendas"],
            "total_comissao": vendas_por_vendedor[0]["total_comissao"],
        }
        if vendas_por_vendedor else None
    )

    return jsonify({
        "total_vendas": total_vendas,
        "total_arrecadado": total_arrecadado,
        "total_comissao": total_comissao,
        "melhor_vendedor": melhor_vendedor,
        "por_vendedor": [
            {
                "vendedor": item["vendedor"],
                "vendas": item["vendas"],
                "total_vendas": float(item["total_vendas"]),
                "total_comissao": float(item["total_comissao"]),
            }
            for item in vendas_por_vendedor
        ],
    })


# =========================
# BUSCAR VENDA
# =========================

@app.route("/api/vendas/<int:id>")
@login_obrigatorio
def buscar_venda(id):

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT * FROM vendas WHERE id = ?",
        (id,)
    )

    venda = cursor.fetchone()

    if not venda:

        conexao.close()

        return jsonify({
            "erro": "Venda não encontrada."
        }), 404

    cursor.execute(
        "SELECT * FROM venda_itens WHERE venda_id = ? ORDER BY id",
        (id,)
    )

    itens = cursor.fetchall()

    conexao.close()

    return jsonify({
        "id": venda["id"],
        "numero": venda["numero"],
        "cliente": venda["cliente"],
        "fantasia": venda["fantasia"],
        "telefone": venda["telefone"],
        "vendedor": venda["vendedor"],
        "data": venda["data"],
        "condicao": venda["condicao"],
        "vencimento": venda["vencimento"],
        "desconto": venda["desconto"],
        "observacao": venda["observacao"],
        "total": venda["total"],
        "comissao": venda["comissao"],
        "itens": [
            {
                "id": item["id"],
                "quantidade": item["quantidade"],
                "descricao": item["descricao"],
                "valor": item["valor"]
            }
            for item in itens
        ]
    })


# =========================
# ATUALIZAR VENDA
# =========================

@app.route("/api/vendas/<int:id>", methods=["PUT"])
@login_obrigatorio
def atualizar_venda(id):

    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400
    if not str(dados.get("vendedor", "")).strip():
        return jsonify({"erro": "Selecione o vendedor."}), 400
    if not str(dados.get("data", "")).strip():
        return jsonify({"erro": "Informe a data da venda."}), 400
    if not str(dados.get("condicao", "")).strip():
        return jsonify({"erro": "Selecione a condição de pagamento."}), 400
    if str(dados.get("condicao", "")).strip()=="aprazo" and not str(dados.get("vencimento", "")).strip():
        return jsonify({"erro": "Informe o vencimento para vendas a prazo."}), 400
    if not str(dados.get("cliente", "")).strip():
        return jsonify({"erro": "Informe o cliente."}), 400
    itens, erro = validar_itens(dados.get("itens", []), "descricao")
    if erro:
        return jsonify({"erro": erro}), 400
    if not itens:
        return jsonify({"erro": "Adicione pelo menos um produto."}), 400
    try:
        desconto = float(dados.get("desconto", 0))
    except (TypeError, ValueError):
        return jsonify({"erro": "Desconto inválido."}), 400
    papel_usuario = obter_papel_usuario(session["usuario"]) or "VENDEDOR"
    erro_desconto, _ = _autorizar_desconto(dados, desconto, papel_usuario)
    if erro_desconto:
        return jsonify({"erro": erro_desconto, "precisa_aprovacao": True}), 403

    total = max(0, sum(quantidade * valor for _, quantidade, valor in itens) * (1 - desconto / 100))
    comissao = round(total * COMISSAO_PERCENTUAL / 100, 2)

    conexao = conectar()
    cursor = conexao.cursor()

    cliente_final = str(dados.get("cliente") or "").strip() or "CONSUMIDOR FINAL"
    cursor.execute("""
        UPDATE vendas
        SET
            cliente = ?,
            fantasia = ?,
            telefone = ?,
            vendedor = ?,
            data = ?,
            condicao = ?,
            vencimento = ?,
            desconto = ?,
            observacao = ?,
            endereco = ?,
            total = ?,
            comissao = ?
        WHERE id = ?
    """, (
        cliente_final,
        dados.get("fantasia", ""),
        dados.get("telefone", ""),
        dados.get("vendedor", ""),
        dados.get("data", ""),
        dados.get("condicao", ""),
        dados.get("vencimento", ""),
        desconto,
        dados.get("observacao", ""),
        dados.get("endereco", ""),
        total,
        comissao,
        id
    ))

    if cursor.rowcount == 0:
        conexao.close()
        return jsonify({"erro": "Venda não encontrada."}), 404

    cursor.execute(
        "DELETE FROM venda_itens WHERE venda_id = ?",
        (id,)
    )

    for descricao, quantidade, valor in itens:

        cursor.execute("""
            INSERT INTO venda_itens (
                venda_id,
                quantidade,
                descricao,
                valor
            )
            VALUES (?, ?, ?, ?)
        """, (
            id,
            quantidade, descricao, valor
        ))

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Venda atualizada com sucesso!",
        "comissao": comissao
    })


# =========================
# EXCLUIR VENDA
# =========================

@app.route("/api/vendas/<int:id>", methods=["DELETE"])
@admin_obrigatorio
def excluir_venda(id):

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "DELETE FROM venda_itens WHERE venda_id = ?",
        (id,)
    )

    cursor.execute(
        "DELETE FROM vendas WHERE id = ?",
        (id,)
    )

    if cursor.rowcount == 0:
        conexao.close()
        return jsonify({"erro": "Venda não encontrada."}), 404

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Venda excluída com sucesso!"
    })


# =========================
# CONTROLE DE COMISSÃO (só Dono/Gerente)
# =========================

@app.route("/controle_comissao")
@login_obrigatorio
def controle_comissao():
    papel = obter_papel_usuario(session["usuario"])
    return render_template(
        "controle_comissao.html",
        usuario=session["usuario"],
        papel=papel,
        eh_gerente=(papel or "").upper() in ("GERENTE","DONO")
    )


@app.route("/aprovacoes")
@login_obrigatorio
def pagina_aprovacoes():
    papel = obter_papel_usuario(session["usuario"])
    if papel not in PAPEIS_GESTAO:
        return jsonify({"erro": "Acesso restrito à gerência"}), 403
    return render_template("aprovacoes.html", usuario=session["usuario"], papel=papel)


@app.route("/api/aprovacoes", methods=["POST"])
@login_obrigatorio
def aprovar_acao():
    dados = json_body()
    if not dados:
        return jsonify({"erro": "Dados inválidos"}), 400
    acao = str(dados.get("acao") or "").strip()
    referencia = str(dados.get("referencia") or "").strip()
    vendedor = str(dados.get("vendedor") or "").strip() or session["usuario"]
    detalhe = dados.get("detalhe")
    if isinstance(detalhe, dict) or isinstance(detalhe, list):
        detalhe = json.dumps(detalhe, ensure_ascii=False, default=str)
    else:
        detalhe = str(detalhe or "")
    login = str(dados.get("gerente_login") or "").strip().upper()
    senha = str(dados.get("gerente_senha") or "")
    if not acao:
        return jsonify({"erro": "Ação não informada"}), 400
    conexao = conectar()
    gerente = conexao.execute(
        "SELECT * FROM usuarios WHERE upper(usuario) = upper(?)",
        (login,)
    ).fetchone()
    if not gerente:
        conexao.close()
        return jsonify({"erro": "Gerente não encontrado"}), 400
    papel_gerente = str(gerente["papel"] or "").upper()
    if papel_gerente not in PAPEIS_GESTAO and login not in AUTORIZADORES:
        conexao.close()
        return jsonify({"erro": "Apenas usuários autorizados podem aprovar"}), 403
    senha_hash = gerente["senha"]
    if not (check_password_hash(senha_hash, senha) if senha_hash.startswith(("pbkdf2:", "scrypt:")) else senha_hash == senha):
        conexao.close()
        return jsonify({"erro": "Senha do gerente inválida"}), 400
    agora = agora_sp().strftime("%d/%m/%Y %H:%M")
    conexao.execute(
        "INSERT INTO aprovacoes (acao, referencia, vendedor, detalhe, gerente, status, criacao, aprovado_em) VALUES (?,?,?,?,?,?,?,?)",
        (acao, referencia, vendedor, detalhe, login, "APROVADO", agora, agora)
    )
    conexao.commit()
    conexao.close()
    return jsonify({"ok": True, "mensagem": "Aprovação registrada e ação liberada."})


@app.route("/api/aprovacoes", methods=["GET"])
@login_obrigatorio
def lista_aprovacoes():
    if obter_papel_usuario(session["usuario"]) not in PAPEIS_GESTAO:
        return jsonify({"erro": "Acesso restrito à gerência"}), 403
    conexao = conectar()
    registros = conexao.execute(
        "SELECT * FROM aprovacoes ORDER BY id DESC LIMIT 200"
    ).fetchall()
    conexao.close()
    return jsonify({"aprovacoes": [dict(r) for r in registros]})


@app.route("/api/comissoes")
@login_obrigatorio
def api_comissoes():
    mes = (request.args.get("mes") or "").strip()  # YYYY-MM
    if mes and len(mes) != 7:
        return jsonify({"erro": "Mês inválido. Use YYYY-MM."}), 400
    papel = (obter_papel_usuario(session["usuario"]) or "").upper()
    eh_gerente = papel in ("GERENTE","DONO")
    # Vendedor vê só a própria comissão (já somada 2%), gerente vê todos
    vendedor_filtro = None if eh_gerente else session["usuario"]
    conexao = conectar()
    cursor = conexao.cursor()
    filtro_mes = f"{mes}%" if mes else "%"
    if vendedor_filtro:
        cursor.execute("""
            SELECT
                COALESCE(vendedor, 'SEM VENDEDOR') AS vendedor,
                COUNT(*) AS vendas,
                ROUND(CAST(COALESCE(SUM(total), 0) AS NUMERIC), 2) AS total_vendas,
                ROUND(CAST(COALESCE(SUM(comissao), 0) AS NUMERIC), 2) AS total_comissao
            FROM vendas
            WHERE COALESCE(vendedor,'') <> '' AND COALESCE(data,'') LIKE ? AND upper(vendedor)=upper(?)
            GROUP BY vendedor
            ORDER BY total_comissao DESC, vendas DESC, vendedor ASC
        """, (filtro_mes, vendedor_filtro))
        por_vendedor = cursor.fetchall()
        cursor.execute("""
            SELECT
                COUNT(*) AS qtd,
                ROUND(CAST(COALESCE(SUM(total), 0) AS NUMERIC), 2) AS total,
                ROUND(CAST(COALESCE(SUM(comissao), 0) AS NUMERIC), 2) AS comissao
            FROM vendas
            WHERE COALESCE(data,'') LIKE ? AND upper(vendedor)=upper(?)
        """, (filtro_mes, vendedor_filtro))
        tot = cursor.fetchone()
    else:
        cursor.execute("""
            SELECT
                COALESCE(vendedor, 'SEM VENDEDOR') AS vendedor,
                COUNT(*) AS vendas,
                ROUND(CAST(COALESCE(SUM(total), 0) AS NUMERIC), 2) AS total_vendas,
                ROUND(CAST(COALESCE(SUM(comissao), 0) AS NUMERIC), 2) AS total_comissao
            FROM vendas
            WHERE COALESCE(vendedor,'') <> '' AND COALESCE(data,'') LIKE ?
            GROUP BY vendedor
            ORDER BY total_comissao DESC, vendas DESC, vendedor ASC
        """, (filtro_mes,))
        por_vendedor = cursor.fetchall()
        cursor.execute("""
            SELECT
                COUNT(*) AS qtd,
                ROUND(CAST(COALESCE(SUM(total), 0) AS NUMERIC), 2) AS total,
                ROUND(CAST(COALESCE(SUM(comissao), 0) AS NUMERIC), 2) AS comissao
            FROM vendas
            WHERE COALESCE(data,'') LIKE ?
        """, (filtro_mes,))
        tot = cursor.fetchone()
    conexao.close()
    return jsonify({
        "mes": mes,
        "eh_gerente": eh_gerente,
        "total_vendas": int(tot["qtd"] or 0),
        "total_arrecadado": float(tot["total"] or 0),
        "total_comissao": float(tot["comissao"] or 0),
        "por_vendedor": [
            {"vendedor": r["vendedor"], "vendas": int(r["vendas"]), "total_vendas": float(r["total_vendas"] or 0), "total_comissao": float(r["total_comissao"] or 0)}
            for r in por_vendedor
        ]
    })


# =========================
# DEVOLUÇÕES
# =========================

@app.route("/devolucoes")
@login_obrigatorio
def pagina_devolucoes():
    return render_template(
        "devolucoes.html",
        usuario=session["usuario"],
        papel=obter_papel_usuario(session["usuario"])
    )


@app.route("/api/devolucoes/proximo_numero")
@login_obrigatorio
def proximo_numero_devolucao():
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT ultimo_numero FROM controle_devolucoes WHERE id=1")
    r = cur.fetchone()
    conexao.close()
    return jsonify({"numero": (r["ultimo_numero"] if r else 0) + 1})


# =========================
# ORÇAMENTOS
# =========================

@app.route("/orcamentos")
@login_obrigatorio
def pagina_orcamentos():
    return render_template(
        "orcamentos.html",
        usuario=session["usuario"],
        papel=obter_papel_usuario(session["usuario"])
    )


@app.route("/api/orcamentos/proximo_numero")
@login_obrigatorio
def proximo_numero_orcamento():
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT ultimo_numero FROM controle_orcamentos WHERE id=1")
    r = cur.fetchone()
    conexao.close()
    return jsonify({"numero": (r["ultimo_numero"] if r else 0) + 1})


@app.route("/api/orcamentos", methods=["GET"])
@login_obrigatorio
def listar_orcamentos():
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT * FROM orcamentos ORDER BY numero DESC")
    orcs = cur.fetchall()
    conexao.close()
    return jsonify([{
        "id": o["id"], "numero": o["numero"], "vendedor": o["vendedor"],
        "cliente": o["cliente"], "telefone": o["telefone"], "endereco": o["endereco"],
        "condicao": o["condicao"], "validade_dias": o["validade_dias"],
        "observacao": o["observacao"], "total": o["total"], "status": o["status"],
        "venda_id": o["venda_id"], "criacao": o["criacao"]
    } for o in orcs])


@app.route("/api/orcamentos/<int:id>")
@login_obrigatorio
def buscar_orcamento(id):
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT * FROM orcamentos WHERE id=?", (id,))
    o = cur.fetchone()
    if not o:
        conexao.close()
        return jsonify({"erro": "Orçamento não encontrado"}), 404
    cur.execute("SELECT * FROM orcamento_itens WHERE orcamento_id=? ORDER BY id", (id,))
    its = cur.fetchall()
    conexao.close()
    return jsonify({
        "id": o["id"], "numero": o["numero"], "vendedor": o["vendedor"],
        "cliente": o["cliente"], "telefone": o["telefone"], "endereco": o["endereco"],
        "condicao": o["condicao"], "validade_dias": o["validade_dias"],
        "observacao": o["observacao"], "total": o["total"], "status": o["status"],
        "venda_id": o["venda_id"], "criacao": o["criacao"],
        "itens": [{"id": it["id"], "tipo": it["tipo"], "quantidade": it["quantidade"], "descricao": it["descricao"], "valor": it["valor"]} for it in its]
    })


def _orcamento_tipo_do_item(dados_itens, idx):
    """Retorna o tipo (PRODUTO/SERVIÇO) do item alinhado por índice."""
    if idx < len(dados_itens) and isinstance(dados_itens[idx], dict):
        t = str(dados_itens[idx].get("tipo") or "").strip().upper().replace("SERVICO", "SERVIÇO")
        if t == "SERVIÇO":
            return "SERVIÇO"
    return "PRODUTO"


@app.route("/api/orcamentos", methods=["POST"])
@login_obrigatorio
def criar_orcamento():
    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400
    cliente = str(dados.get("cliente") or "").strip()
    if not cliente:
        return jsonify({"erro": "Informe o cliente."}), 400
    itens, erro = validar_itens(dados.get("itens", []), "descricao")
    if erro:
        return jsonify({"erro": erro}), 400
    if not itens:
        return jsonify({"erro": "Adicione pelo menos um item."}), 400
    total = sum(q * valor for _, q, valor in itens)
    try:
        validade_dias = int(dados.get("validade_dias") or 30)
    except (TypeError, ValueError):
        validade_dias = 30
    validade_dias = min(max(validade_dias, 0), 365)
    origem_itens = dados.get("itens", [])
    conexao = conectar()
    cur = conexao.cursor()
    vendedor = str(dados.get("vendedor") or "").strip() or session["usuario"]
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT ultimo_numero FROM controle_orcamentos WHERE id=1")
    ctrl = cur.fetchone()
    ultimo = 0 if not ctrl else ctrl["ultimo_numero"]
    novo = ultimo + 1
    cur.execute("""
        INSERT INTO orcamentos (numero, vendedor, cliente, telefone, endereco, condicao, validade_dias, observacao, total, status, criacao, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'aberto', ?, ?)
    """, (novo, vendedor, cliente, dados.get("telefone", ""), dados.get("endereco", ""), dados.get("condicao", ""), validade_dias, dados.get("observacao", ""), total, agora_sp().strftime("%Y-%m-%d %H:%M:%S"), session["usuario"]))
    orc_id = cur.lastrowid
    for idx, (desc, q, v) in enumerate(itens):
        cur.execute("INSERT INTO orcamento_itens (orcamento_id, tipo, quantidade, descricao, valor) VALUES (?, ?, ?, ?, ?)", (orc_id, _orcamento_tipo_do_item(origem_itens, idx), q, desc, v))
    cur.execute("UPDATE controle_orcamentos SET ultimo_numero=? WHERE id=1", (novo,))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Orçamento criado!", "numero": novo, "id": orc_id, "total": total})


@app.route("/api/orcamentos/<int:id>", methods=["PUT"])
@login_obrigatorio
def editar_orcamento(id):
    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400
    cliente = str(dados.get("cliente") or "").strip()
    if not cliente:
        return jsonify({"erro": "Informe o cliente."}), 400
    itens, erro = validar_itens(dados.get("itens", []), "descricao")
    if erro:
        return jsonify({"erro": erro}), 400
    if not itens:
        return jsonify({"erro": "Adicione pelo menos um item."}), 400
    total = sum(q * valor for _, q, valor in itens)
    try:
        validade_dias = int(dados.get("validade_dias") or 30)
    except (TypeError, ValueError):
        validade_dias = 30
    validade_dias = min(max(validade_dias, 0), 365)
    origem_itens = dados.get("itens", [])
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT * FROM orcamentos WHERE id=?", (id,))
    o = cur.fetchone()
    if not o:
        conexao.close()
        return jsonify({"erro": "Orçamento não encontrado"}), 404
    if o["status"] == "convertido":
        conexao.close()
        return jsonify({"erro": "Orçamento já convertido em venda não pode ser alterado."}), 400
    cur.execute("""
        UPDATE orcamentos SET cliente=?, telefone=?, endereco=?, condicao=?, validade_dias=?, observacao=?, total=?
        WHERE id=?
    """, (cliente, dados.get("telefone", ""), dados.get("endereco", ""), dados.get("condicao", ""), validade_dias, dados.get("observacao", ""), total, id))
    cur.execute("DELETE FROM orcamento_itens WHERE orcamento_id=?", (id,))
    for idx, (desc, q, v) in enumerate(itens):
        cur.execute("INSERT INTO orcamento_itens (orcamento_id, tipo, quantidade, descricao, valor) VALUES (?, ?, ?, ?, ?)", (id, _orcamento_tipo_do_item(origem_itens, idx), q, desc, v))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Orçamento atualizado!", "id": id, "total": total})


@app.route("/api/orcamentos/<int:id>", methods=["DELETE"])
@login_obrigatorio
def excluir_orcamento(id):
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT * FROM orcamentos WHERE id=?", (id,))
    o = cur.fetchone()
    if not o:
        conexao.close()
        return jsonify({"erro": "Orçamento não encontrado"}), 404
    if o["status"] == "convertido":
        conexao.close()
        return jsonify({"erro": "Orçamento convertido em venda não pode ser excluído."}), 400
    cur.execute("DELETE FROM orcamento_itens WHERE orcamento_id=?", (id,))
    cur.execute("DELETE FROM orcamentos WHERE id=?", (id,))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Orçamento excluído!"})


@app.route("/api/orcamentos/<int:id>/converter", methods=["POST"])
@login_obrigatorio
def converter_orcamento_em_venda(id):
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT * FROM orcamentos WHERE id=?", (id,))
    o = cur.fetchone()
    if not o:
        conexao.close()
        return jsonify({"erro": "Orçamento não encontrado"}), 404
    if o["status"] == "convertido":
        conexao.close()
        return jsonify({"erro": "Orçamento já foi convertido em venda."}), 400
    cur.execute("SELECT * FROM orcamento_itens WHERE orcamento_id=? ORDER BY id", (id,))
    its = cur.fetchall()
    if not its:
        conexao.close()
        return jsonify({"erro": "Orçamento sem itens."}), 400
    total = o["total"]
    vendedor = o["vendedor"] or session["usuario"]
    cliente_final = o["cliente"] or "CONSUMIDOR FINAL"
    hoje = agora_sp().strftime("%Y-%m-%d")
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT ultimo_numero FROM controle_vendas WHERE id=1")
    ctrl = cur.fetchone()
    ultimo = 0 if not ctrl else ctrl["ultimo_numero"]
    novo = ultimo + 1
    cur.execute("""
        INSERT INTO vendas (numero, cliente, fantasia, telefone, vendedor, data, condicao, vencimento, desconto, observacao, endereco, total, comissao, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 'ativa')
    """, (novo, cliente_final, "", o["telefone"], vendedor, hoje, o["condicao"] or "dinheiro", "", o["observacao"], o["endereco"], total, round(total * COMISSAO_PERCENTUAL / 100, 2)))
    venda_id = cur.lastrowid
    for item in its:
        cur.execute("INSERT INTO venda_itens (venda_id, quantidade, descricao, valor) VALUES (?, ?, ?, ?)", (venda_id, item["quantidade"], item["descricao"], item["valor"]))
    cur.execute("UPDATE controle_vendas SET ultimo_numero=? WHERE id=1", (novo,))
    cur.execute("UPDATE orcamentos SET status='convertido', venda_id=? WHERE id=?", (venda_id, id))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Orçamento convertido em venda!", "venda_id": venda_id, "venda_numero": novo})


@app.route("/api/devolucoes", methods=["GET"])
@login_obrigatorio
def listar_devolucoes():
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT * FROM devolucoes ORDER BY numero DESC")
    devs = cur.fetchall()
    conexao.close()
    return jsonify([{"id": d["id"], "numero": d["numero"], "venda_id": d["venda_id"], "data": d["data"], "motivo": d["motivo"], "observacao": d["observacao"], "total": d["total"], "vendedor": d["vendedor"], "cliente": d["cliente"]} for d in devs])


@app.route("/api/devolucoes/<int:id>")
@login_obrigatorio
def buscar_devolucao(id):
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT * FROM devolucoes WHERE id=?", (id,))
    dev = cur.fetchone()
    if not dev:
        conexao.close()
        return jsonify({"erro": "Devolução não encontrada"}), 404
    cur.execute("SELECT * FROM devolucao_itens WHERE devolucao_id=? ORDER BY id", (id,))
    itens = cur.fetchall()
    venda_numero = None
    venda_cliente = None
    if dev["venda_id"]:
        cur.execute("SELECT numero, cliente FROM vendas WHERE id=?", (dev["venda_id"],))
        v = cur.fetchone()
        if v:
            venda_numero = v["numero"]
            venda_cliente = v["cliente"]
    conexao.close()
    return jsonify({"id": dev["id"], "numero": dev["numero"], "venda_id": dev["venda_id"], "venda_numero": venda_numero, "venda_cliente": venda_cliente, "data": dev["data"], "motivo": dev["motivo"], "observacao": dev["observacao"], "total": dev["total"], "vendedor": dev["vendedor"], "cliente": dev["cliente"], "itens": [{"id": it["id"], "quantidade": it["quantidade"], "descricao": it["descricao"], "valor": it["valor"]} for it in itens]})


@app.route("/api/devolucoes", methods=["POST"])
@login_obrigatorio
def criar_devolucao():
    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400
    venda_id = dados.get("venda_id") or None
    motivo = str(dados.get("motivo") or "").strip()
    if not motivo:
        return jsonify({"erro": "Informe o motivo da devolução."}), 400
    itens, erro = validar_itens(dados.get("itens", []), "descricao")
    if erro:
        return jsonify({"erro": erro}), 400
    if not itens:
        return jsonify({"erro": "Adicione pelo menos um item devolvido."}), 400
    total = sum(q*valor for _, q, valor in itens)
    conexao = conectar()
    cur = conexao.cursor()
    vendedor = str(dados.get("vendedor") or "").strip() or session["usuario"]
    cliente = str(dados.get("cliente") or "").strip()
    # se vinculada, valida venda e usa o vendedor da venda como fallback
    if venda_id:
        cur.execute("SELECT id, vendedor FROM vendas WHERE id=?", (venda_id,))
        venda = cur.fetchone()
        if not venda:
            conexao.close()
            return jsonify({"erro": "Venda original não encontrada."}), 404
        vendedor = vendedor or venda["vendedor"]
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT ultimo_numero FROM controle_devolucoes WHERE id=1")
    ctrl = cur.fetchone()
    ultimo = 0 if not ctrl else ctrl["ultimo_numero"]
    novo = ultimo + 1
    from datetime import datetime
    data = dados.get("data") or agora_sp().strftime("%Y-%m-%d")
    cur.execute("""
        INSERT INTO devolucoes (numero, venda_id, data, motivo, observacao, total, vendedor, cliente)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (novo, venda_id, data, motivo, dados.get("observacao",""), total, vendedor, cliente))
    dev_id = cur.lastrowid
    for desc, q, v in itens:
        cur.execute("INSERT INTO devolucao_itens (devolucao_id, quantidade, descricao, valor) VALUES (?, ?, ?, ?)", (dev_id, q, desc, v))
    cur.execute("UPDATE controle_devolucoes SET ultimo_numero=? WHERE id=1", (novo,))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Devolução registrada!", "numero": novo, "id": dev_id, "total": total})


@app.route("/api/devolucoes/<int:id>", methods=["PUT"])
@login_obrigatorio
def editar_devolucao(id):
    dados = json_body()
    if dados is None:
        return jsonify({"erro": "Envie um JSON válido."}), 400
    venda_id = dados.get("venda_id") or None
    motivo = str(dados.get("motivo") or "").strip()
    if not motivo:
        return jsonify({"erro": "Informe o motivo da devolução."}), 400
    itens, erro = validar_itens(dados.get("itens", []), "descricao")
    if erro:
        return jsonify({"erro": erro}), 400
    if not itens:
        return jsonify({"erro": "Adicione pelo menos um item devolvido."}), 400
    total = sum(q*valor for _, q, valor in itens)

    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT id FROM devolucoes WHERE id=?", (id,))
    if not cur.fetchone():
        conexao.close()
        return jsonify({"erro": "Devolução não encontrada."}), 404

    vendedor = str(dados.get("vendedor") or "").strip() or session["usuario"]
    cliente = str(dados.get("cliente") or "").strip()
    if venda_id:
        cur.execute("SELECT id, vendedor FROM vendas WHERE id=?", (venda_id,))
        venda = cur.fetchone()
        if not venda:
            conexao.close()
            return jsonify({"erro": "Venda original não encontrada."}), 404
        vendedor = vendedor or venda["vendedor"]

    cur.execute("BEGIN IMMEDIATE")
    from datetime import datetime
    data = dados.get("data") or agora_sp().strftime("%Y-%m-%d")
    cur.execute("""
        UPDATE devolucoes
        SET venda_id=?, data=?, motivo=?, observacao=?, total=?, vendedor=?, cliente=?
        WHERE id=?
    """, (venda_id, data, motivo, dados.get("observacao",""), total, dados.get("vendedor") or venda["vendedor"], cliente, id))
    cur.execute("DELETE FROM devolucao_itens WHERE devolucao_id=?", (id,))
    for desc, q, v in itens:
        cur.execute("INSERT INTO devolucao_itens (devolucao_id, quantidade, descricao, valor) VALUES (?, ?, ?, ?)", (id, q, desc, v))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Devolução atualizada!", "id": id, "total": total})


@app.route("/api/devolucoes/<int:id>", methods=["DELETE"])
@login_obrigatorio
def cancelar_devolucao(id):
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT id FROM devolucoes WHERE id=?", (id,))
    if not cur.fetchone():
        conexao.close()
        return jsonify({"erro": "Devolução não encontrada."}), 404
    cur.execute("DELETE FROM devolucao_itens WHERE devolucao_id=?", (id,))
    cur.execute("DELETE FROM devolucoes WHERE id=?", (id,))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem": "Devolução cancelada!"})


# =========================
# ENTREGAS — SISTEMA DE ENTREGA
# =========================
STATUSES_ENTREGA = ["Pendente","SAIU PARA ROTA","Em rota","Entregue","Falha","Cancelada","Reagendada"]

@app.route("/entregas")
@login_obrigatorio
def pagina_entregas():
    papel = obter_papel_usuario(session["usuario"])
    return render_template("entregas.html", usuario=session["usuario"], papel=papel)

@app.route("/api/entregas/proximo_numero")
@login_obrigatorio
def proximo_numero_entrega():
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT ultimo_numero FROM controle_entregas WHERE id=1")
    row = cur.fetchone()
    prox = (row["ultimo_numero"] if row else 0) + 1
    conexao.close()
    return jsonify({"numero": prox})

@app.route("/api/entregas", methods=["GET"])
@login_obrigatorio
def listar_entregas():
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT * FROM entregas ORDER BY numero DESC")
    rows = cur.fetchall()
    conexao.close()
    out=[]
    for r in rows:
        out.append({k: r[k] for k in r.keys()} if hasattr(r,"keys") else dict(r))
    return jsonify(out)

@app.route("/api/entregas/<int:id>")
@login_obrigatorio
def buscar_entrega(id):
    conexao = conectar()
    cur = conexao.cursor()
    cur.execute("SELECT * FROM entregas WHERE id=?", (id,))
    row = cur.fetchone()
    if not row:
        conexao.close()
        return jsonify({"erro":"Entrega não encontrada."}),404
    d=dict(row) if hasattr(row,"keys") else dict(zip([c[0] for c in cur.description], row))
    # dados da origem para impressao
    if d.get("venda_id"):
        cur.execute("SELECT cliente, numero, vendedor FROM vendas WHERE id=?", (d["venda_id"],))
        v=cur.fetchone()
        if v:
            d["venda_cliente"]=v["cliente"] if hasattr(v,"keys") else v[0]
            d["venda_numero"]=v["numero"] if hasattr(v,"keys") else v[1]
            d["venda_vendedor"]=v["vendedor"] if hasattr(v,"keys") else v[2]
    if d.get("ordem_id"):
        cur.execute("SELECT cliente, numero FROM ordens WHERE id=?", (d["ordem_id"],))
        o=cur.fetchone()
        if o:
            d["ordem_cliente"]=o["cliente"] if hasattr(o,"keys") else o[0]
            d["ordem_numero"]=o["numero"] if hasattr(o,"keys") else o[1]
    conexao.close()
    return jsonify(d)

@app.route("/api/entregas", methods=["POST"])
@login_obrigatorio
def criar_entrega():
    dados=json_body()
    if dados is None:
        return jsonify({"erro":"Envie um JSON válido."}),400
    venda_id=dados.get("venda_id") or None
    ordem_id=dados.get("ordem_id") or None
    cliente=str(dados.get("cliente") or "").strip()
    endereco=str(dados.get("endereco") or "").strip()
    if not cliente:
        return jsonify({"erro":"Informe o cliente."}),400
    if not endereco:
        return jsonify({"erro":"Informe o endereço."}),400
    if not str(dados.get("entregador") or "").strip():
        return jsonify({"erro":"Selecione o entregador."}),400
    if not str(dados.get("data_entrega") or "").strip():
        return jsonify({"erro":"Informe a data da entrega."}),400
    entregador=str(dados.get("entregador") or "").strip()
    status=str(dados.get("status") or "Pendente").strip()
    if status not in STATUSES_ENTREGA:
        status="Pendente"
    try:
        taxa=float(dados.get("taxa") or 0)
    except: taxa=0
    conexao=conectar()
    cur=conexao.cursor()
    if venda_id:
        cur.execute("SELECT id FROM vendas WHERE id=?",(venda_id,))
        if not cur.fetchone():
            conexao.close()
            return jsonify({"erro":"Venda não encontrada."}),404
    if ordem_id:
        cur.execute("SELECT id FROM ordens WHERE id=?",(ordem_id,))
        if not cur.fetchone():
            conexao.close()
            return jsonify({"erro":"Ordem não encontrada."}),404
    cur.execute("BEGIN IMMEDIATE")
    cur.execute("SELECT ultimo_numero FROM controle_entregas WHERE id=1")
    row=cur.fetchone()
    novo=(row["ultimo_numero"] if row else 0)+1
    from datetime import datetime
    import secrets
    criacao=agora_sp().strftime("%Y-%m-%d %H:%M")
    qr_token=secrets.token_hex(6)
    cur.execute("""INSERT INTO entregas (numero, venda_id, ordem_id, cliente, telefone, endereco, bairro, entregador, data_entrega, horario, taxa, status, observacao, comprovante, criacao, qr_token)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (novo, venda_id, ordem_id, cliente, str(dados.get("telefone") or ""), endereco, str(dados.get("bairro") or ""), entregador, str(dados.get("data_entrega") or ""), str(dados.get("horario") or ""), taxa, status, str(dados.get("observacao") or ""), str(dados.get("comprovante") or ""), criacao, qr_token))
    eid=cur.lastrowid
    cur.execute("INSERT INTO entrega_historico (entrega_id, status, data_hora, usuario) VALUES (?, ?, ?, ?)", (eid, status, criacao, session.get("usuario","")))
    cur.execute("UPDATE controle_entregas SET ultimo_numero=? WHERE id=1",(novo,))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem":"Entrega criada!","id":eid,"numero":novo, "qr_token": qr_token})

@app.route("/api/entregas/<int:id>", methods=["PUT"])
@login_obrigatorio
def editar_entrega(id):
    dados=json_body()
    if dados is None:
        return jsonify({"erro":"Envie um JSON válido."}),400
    conexao=conectar()
    cur=conexao.cursor()
    cur.execute("SELECT id FROM entregas WHERE id=?",(id,))
    if not cur.fetchone():
        conexao.close()
        return jsonify({"erro":"Entrega não encontrada."}),404
    venda_id=dados.get("venda_id") or None
    ordem_id=dados.get("ordem_id") or None
    cliente=str(dados.get("cliente") or "").strip()
    endereco=str(dados.get("endereco") or "").strip()
    if not cliente: 
        conexao.close()
        return jsonify({"erro":"Informe o cliente."}),400
    if not endereco:
        conexao.close()
        return jsonify({"erro":"Informe o endereço."}),400
    status=str(dados.get("status") or "Pendente").strip()
    if status not in STATUSES_ENTREGA: status="Pendente"
    try: taxa=float(dados.get("taxa") or 0)
    except: taxa=0
    if venda_id:
        cur.execute("SELECT id FROM vendas WHERE id=?",(venda_id,))
        if not cur.fetchone():
            conexao.close()
            return jsonify({"erro":"Venda não encontrada."}),404
    if ordem_id:
        cur.execute("SELECT id FROM ordens WHERE id=?",(ordem_id,))
        if not cur.fetchone():
            conexao.close()
            return jsonify({"erro":"Ordem não encontrada."}),404
    cur.execute("""UPDATE entregas SET venda_id=?, ordem_id=?, cliente=?, telefone=?, endereco=?, bairro=?, entregador=?, data_entrega=?, horario=?, taxa=?, status=?, observacao=?, comprovante=? WHERE id=?""",
        (venda_id, ordem_id, cliente, str(dados.get("telefone") or ""), endereco, str(dados.get("bairro") or ""), str(dados.get("entregador") or ""), str(dados.get("data_entrega") or ""), str(dados.get("horario") or ""), taxa, status, str(dados.get("observacao") or ""), str(dados.get("comprovante") or ""), id))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem":"Entrega atualizada!","id":id})

@app.route("/api/entregas/<int:id>/status", methods=["PUT"])
@login_obrigatorio
def atualizar_status_entrega(id):
    dados=json_body()
    if dados is None:
        return jsonify({"erro":"Envie um JSON válido."}),400
    novo=str(dados.get("status") or "").strip()
    if novo not in STATUSES_ENTREGA:
        return jsonify({"erro":"Status inválido. Use: "+", ".join(STATUSES_ENTREGA)}),400
    conexao=conectar()
    cur=conexao.cursor()
    cur.execute("SELECT id FROM entregas WHERE id=?",(id,))
    if not cur.fetchone():
        conexao.close()
        return jsonify({"erro":"Entrega não encontrada."}),404
    cur.execute("UPDATE entregas SET status=? WHERE id=?",(novo, id))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem":f"Status alterado para {novo}!"})

@app.route("/api/entregas/<int:id>", methods=["DELETE"])
@login_obrigatorio
def excluir_entrega(id):
    conexao=conectar()
    cur=conexao.cursor()
    cur.execute("SELECT id FROM entregas WHERE id=?",(id,))
    if not cur.fetchone():
        conexao.close()
        return jsonify({"erro":"Entrega não encontrada."}),404
    cur.execute("DELETE FROM entrega_historico WHERE entrega_id=?",(id,))
    cur.execute("DELETE FROM entregas WHERE id=?",(id,))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem":"Entrega excluída!"})

@app.route("/api/entregas/rota")
@login_obrigatorio
def rota_entregas():
    data=(request.args.get("data") or "").strip()
    conexao=conectar()
    cur=conexao.cursor()
    if data:
        cur.execute("SELECT * FROM entregas WHERE data_entrega=? AND status IN ('Pendente','SAIU PARA ROTA','Em rota','Reagendada') ORDER BY bairro, endereco", (data,))
    else:
        cur.execute("SELECT * FROM entregas WHERE status IN ('Pendente','SAIU PARA ROTA','Em rota','Reagendada') ORDER BY data_entrega, bairro, endereco")
    rows=cur.fetchall()
    conexao.close()
    out=[dict(r) if hasattr(r,"keys") else {k: r[i] for i,k in enumerate([c[0] for c in cur.description])} for r in rows]
    return jsonify(out)

def _fmt_data_br(d):
    """Converte YYYY-MM-DD ou YYYY-MM-DD HH:MM para DD/MM/YYYY ou DD/MM/YYYY HH:MM."""
    if not d:
        return ""
    s = str(d).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        partes = s.split(" ")
        data_part = partes[0]
        p = data_part.split("-")
        resultado = f"{p[2]}/{p[1]}/{p[0]}"
        if len(partes) > 1:
            resultado += " " + partes[1]
        return resultado
    return s

app.jinja_env.filters["fmt_data"] = _fmt_data_br


@app.route("/m/entrega/<int:id>")
@login_obrigatorio
def pagina_entrega_mobile(id):
    conexao=conectar()
    cur=conexao.cursor()
    cur.execute("SELECT * FROM entregas WHERE id=?", (id,))
    row=cur.fetchone()
    if not row:
        conexao.close()
        return "Entrega não encontrada", 404
    entrega=dict(row) if hasattr(row,"keys") else {k: row[i] for i,k in enumerate([c[0] for c in cur.description])}
    # historico
    cur.execute("SELECT * FROM entrega_historico WHERE entrega_id=? ORDER BY id DESC", (id,))
    hist=[dict(r) if hasattr(r,"keys") else {k: r[i] for i,k in enumerate([c[0] for c in cur.description])} for r in cur.fetchall()]
    conexao.close()
    return render_template("entrega_mobile.html", entrega=entrega, historico=hist, usuario=session.get("usuario",""))

@app.route("/api/entregas/<int:id>/avancar", methods=["POST"])
@login_obrigatorio
def avancar_entrega(id):
    conexao=conectar()
    cur=conexao.cursor()
    cur.execute("SELECT * FROM entregas WHERE id=?", (id,))
    row=cur.fetchone()
    if not row:
        conexao.close()
        return jsonify({"erro":"Entrega não encontrada."}),404
    entrega=dict(row) if hasattr(row,"keys") else {k: row[i] for i,k in enumerate([c[0] for c in cur.description])}
    status_atual=(entrega.get("status") or "Pendente").strip()
    if status_atual=="Entregue":
        conexao.close()
        return jsonify({"erro":"Entrega já realizada."}),400
    if status_atual=="Cancelada" or status_atual=="Falha":
        conexao.close()
        return jsonify({"erro":"Entrega cancelada/falha não pode avançar."}),400
    from datetime import datetime
    agora=agora_sp().strftime("%Y-%m-%d %H:%M")
    usuario=session.get("usuario","")
    if status_atual=="Pendente":
        novo="SAIU PARA ROTA"
        cur.execute("UPDATE entregas SET status=?, data_saida=? WHERE id=?", (novo, agora, id))
    elif status_atual in ("SAIU PARA ROTA","Em rota"):
        novo="Entregue"
        cur.execute("UPDATE entregas SET status=?, data_entregue=? WHERE id=?", (novo, agora, id))
    else:
        # Reagendada ou outro -> vai para SAIU PARA ROTA
        novo="SAIU PARA ROTA"
        cur.execute("UPDATE entregas SET status=?, data_saida=? WHERE id=?", (novo, agora, id))
    cur.execute("INSERT INTO entrega_historico (entrega_id, status, data_hora, usuario) VALUES (?, ?, ?, ?)", (id, novo, agora, usuario))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem":f"Status alterado para {novo}!", "status": novo, "data_hora": agora})

@app.route("/api/configuracoes")
@login_obrigatorio
def listar_configuracoes():
    conexao=conectar()
    cur=conexao.cursor()
    cur.execute("SELECT chave, valor FROM configuracoes")
    rows=cur.fetchall()
    conexao.close()
    out={}
    for r in rows:
        k=r["chave"] if hasattr(r,"keys") else r[0]
        v=r["valor"] if hasattr(r,"keys") else r[1]
        out[k]=v
    return jsonify(out)

@app.route("/api/configuracoes/<chave>", methods=["PUT"])
@admin_obrigatorio
def atualizar_configuracao(chave):
    dados=json_body()
    if dados is None:
        return jsonify({"erro":"Envie um JSON válido."}),400
    valor=str(dados.get("valor") or "")
    conexao=conectar()
    cur=conexao.cursor()
    cur.execute("UPDATE configuracoes SET valor=? WHERE chave=?", (valor, chave))
    if cur.rowcount==0:
        if USAR_POSTGRES:
            cur.execute("INSERT INTO configuracoes (chave, valor) VALUES (%s, %s) ON CONFLICT (chave) DO NOTHING", (chave, valor))
        else:
            cur.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)", (chave, valor))
    conexao.commit()
    conexao.close()
    return jsonify({"mensagem":"Configuração atualizada!", "chave": chave, "valor": valor})


# =========================
# INICIAR SERVIDOR
# =========================

if __name__ == "__main__":

    verificar_vencimentos()
    threading.Thread(target=_loop_vencimentos, daemon=True).start()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=os.environ.get("FLASK_DEBUG") == "1"
    )
