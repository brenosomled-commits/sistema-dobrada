import os
from pathlib import Path

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "desenvolvimento-altere-esta-chave"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,
)

BANCO = os.environ.get(
    "SQLITE_DATABASE",
    "/tmp/ordens.db" if os.environ.get("VERCEL") else str(Path(__file__).with_name("ordens.db")),
)
STATUS_OS = {"Em andamento", "Pronta", "Finalizada"}
PAPEIS = {"DONO", "GERENTE", "FINANCEIRO", "VENDEDOR"}
PAPEIS_GESTAO = {"DONO", "GERENTE"}
DESCONTO_MAXIMO_PERCENTUAL = 5
USUARIOS_INICIAIS = [
    ("BRENO", "GERENTE"),
    ("GABRIEL", "VENDEDOR"),
    ("YAN", "VENDEDOR"),
    ("SONIA", "FINANCEIRO"),
    ("VINICIUS", "VENDEDOR"),
    ("WILLIAN", "DONO"),
]
SENHA_TEMPORARIA_PADRAO = os.environ.get("DEFAULT_USER_PASSWORD", "Trocar@123")


# =========================
# BANCO DE DADOS
# =========================

def conectar():
    conexao = sqlite3.connect(BANCO, timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.execute("PRAGMA journal_mode = WAL")
    return conexao


def json_body():
    """Retorna um objeto JSON ou uma resposta 400 que as rotas podem devolver."""
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return None
    return dados


def senha_valida(senha):
    return isinstance(senha, str) and len(senha) >= 8


def normalizar_usuario(usuario):
    return str(usuario or "").strip().upper()


def obter_papel_usuario(usuario):
    conexao = conectar()
    registro = conexao.execute(
        "SELECT papel FROM usuarios WHERE usuario = ?",
        (usuario,)
    ).fetchone()
    conexao.close()
    return registro["papel"] if registro else None


def usuario_tem_gestao(usuario):
    papel = obter_papel_usuario(usuario)
    return papel in PAPEIS_GESTAO


def desconto_maximo_por_papel(papel):
    if papel in {"GERENTE", "DONO"}:
        return 100
    return DESCONTO_MAXIMO_PERCENTUAL


def validar_desconto_percentual(desconto, papel):
    if desconto < 0:
        return "Desconto não pode ser negativo."
    desconto_maximo = desconto_maximo_por_papel(papel)
    if desconto > desconto_maximo:
        return f"O desconto máximo permitido para {papel.lower()} é de {desconto_maximo}%."
    return None


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


@app.after_request
def cabecalhos_seguranca(resposta):
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["X-Frame-Options"] = "SAMEORIGIN"
    resposta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resposta


@app.errorhandler(413)
def requisicao_grande(_erro):
    return jsonify({"erro": "A requisição excede o limite de 1 MB."}), 413


def criar_banco():

    conexao = conectar()
    cursor = conexao.cursor()

    # =========================
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
        if "duplicate column" not in str(erro).lower():
            raise
    # Migração da hierarquia: administrador e Breno (gerente) mantêm acesso
    # completo sem interromper a operação atual.
    cursor.execute("UPDATE usuarios SET papel = 'VENDEDOR' WHERE papel = 'TRIAGEM'")
    cursor.execute("UPDATE usuarios SET papel = 'DONO' WHERE papel = 'ADMIN'")

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_os (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)

    cursor.execute(
        "SELECT ultimo_numero FROM controle_os WHERE id = 1"
    )

    controle = cursor.fetchone()

    if controle is None:

        cursor.execute(
            "SELECT MAX(numero) FROM ordens"
        )

        maior_numero = cursor.fetchone()[0]

        ultimo_numero = (
            0 if maior_numero is None
            else maior_numero
        )

        cursor.execute(
            "INSERT INTO controle_os (id, ultimo_numero) VALUES (1, ?)",
            (ultimo_numero,)
        )

    # =========================
    # ATUALIZAÇÕES BANCO ANTIGO
    # =========================

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
            # A coluna já existe em bancos criados por versões anteriores.
            if "duplicate column" not in str(erro).lower():
                raise

    # =========================
    # NOTA DOBRADA - VENDAS
    # =========================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero INTEGER UNIQUE NOT NULL,
            cliente TEXT,
            fantasia TEXT,
            vendedor TEXT,
            data TEXT,
            condicao TEXT,
            vencimento TEXT,
            desconto REAL DEFAULT 0,
            observacao TEXT,
            total REAL DEFAULT 0
        )
    """)

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS controle_vendas (
            id INTEGER PRIMARY KEY,
            ultimo_numero INTEGER DEFAULT 0
        )
    """)

    cursor.execute(
        "SELECT id FROM controle_vendas WHERE id = 1"
    )

    if not cursor.fetchone():

        cursor.execute("""
            INSERT INTO controle_vendas
            (id, ultimo_numero)
            VALUES (1, 0)
        """)

    # Índices mantêm as telas de triagem e acompanhamento rápidas quando a
    # base crescer.
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ordens_numero ON ordens(numero DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ordens_status ON ordens(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_itens_ordem ON itens(ordem_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vendas_numero ON vendas(numero DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_venda_itens_venda ON venda_itens(venda_id)")

    conexao.commit()
    conexao.close()


criar_banco()


# =========================
# LOGIN OBRIGATÓRIO
# =========================

def login_obrigatorio(funcao):

    @wraps(funcao)
    def verificar(*args, **kwargs):

        if "usuario" not in session:
            return redirect(url_for("login"))

        return funcao(*args, **kwargs)

    return verificar


# =========================
# SOMENTE ADMIN
# =========================

def admin_obrigatorio(funcao):

    @wraps(funcao)
    def verificar(*args, **kwargs):

        if "usuario" not in session:
            return redirect(url_for("login"))

        conexao = conectar()
        usuario = conexao.execute(
            "SELECT papel FROM usuarios WHERE usuario = ?", (session["usuario"],)
        ).fetchone()
        conexao.close()

        if not usuario or usuario["papel"] not in PAPEIS_GESTAO:

            return jsonify({
                "erro": "Acesso permitido somente para dono ou gerente."
            }), 403

        return funcao(*args, **kwargs)

    return verificar


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")

        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,))

        resultado = cursor.fetchone()

        conexao.close()

        if resultado and (
            check_password_hash(resultado["senha"], senha)
            if resultado["senha"].startswith(("pbkdf2:", "scrypt:"))
            else resultado["senha"] == senha
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

        return render_template(
            "login.html",
            erro="Usuário ou senha incorretos!"
        )

    return render_template("login.html")


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


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
        return jsonify({"erro": "A nova senha deve ter ao menos 8 caracteres."}), 400

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
        "WHERE papel IN ('VENDEDOR', 'GERENTE', 'DONO') AND lower(usuario) <> 'admin' ORDER BY usuario"
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
        return jsonify({"erro": "A senha deve ter ao menos 8 caracteres."}), 400
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

    except sqlite3.IntegrityError:

        conexao.close()

        return jsonify({
            "erro": "Este usuário já existe."
        }), 400

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
            "erro": "Digite uma senha com ao menos 8 caracteres."
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
    if not str(dados.get("problema", "")).strip():
        return jsonify({"erro": "Problema é obrigatório."}), 400
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
        usuario=session["usuario"]
    )


@app.route("/acompanhamento_notas")
@login_obrigatorio
def pagina_acompanhamento_notas():

    return render_template(
        "acompanhamento_notas.html",
        usuario=session["usuario"]
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
    itens, erro = validar_itens(dados.get("itens", []), "descricao")
    if erro:
        return jsonify({"erro": erro}), 400
    try:
        desconto = float(dados.get("desconto", 0))
    except (TypeError, ValueError):
        return jsonify({"erro": "Desconto inválido."}), 400
    papel_usuario = obter_papel_usuario(session["usuario"]) or "VENDEDOR"
    erro_desconto = validar_desconto_percentual(desconto, papel_usuario)
    if erro_desconto:
        return jsonify({"erro": erro_desconto}), 400

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

    cursor.execute("""
        INSERT INTO vendas (
            numero,
            cliente,
            fantasia,
            vendedor,
            data,
            condicao,
            vencimento,
            desconto,
            observacao,
            total
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        novo_numero,
        dados.get("cliente", ""),
        dados.get("fantasia", ""),
        dados.get("vendedor", ""),
        dados.get("data", ""),
        dados.get("condicao", ""),
        dados.get("vencimento", ""),
        desconto,
        dados.get("observacao", ""),
        max(0, sum(quantidade * valor for _, quantidade, valor in itens) * (1 - desconto / 100))
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
        "numero": novo_numero
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
            "vendedor": venda["vendedor"],
            "data": venda["data"],
            "condicao": venda["condicao"],
            "vencimento": venda["vencimento"],
            "desconto": venda["desconto"],
            "observacao": venda["observacao"],
            "total": venda["total"]
        }
        for venda in vendas
    ])


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
        "vendedor": venda["vendedor"],
        "data": venda["data"],
        "condicao": venda["condicao"],
        "vencimento": venda["vencimento"],
        "desconto": venda["desconto"],
        "observacao": venda["observacao"],
        "total": venda["total"],
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
    itens, erro = validar_itens(dados.get("itens", []), "descricao")
    if erro:
        return jsonify({"erro": erro}), 400
    try:
        desconto = float(dados.get("desconto", 0))
    except (TypeError, ValueError):
        return jsonify({"erro": "Desconto inválido."}), 400
    papel_usuario = obter_papel_usuario(session["usuario"]) or "VENDEDOR"
    erro_desconto = validar_desconto_percentual(desconto, papel_usuario)
    if erro_desconto:
        return jsonify({"erro": erro_desconto}), 400

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        UPDATE vendas
        SET
            cliente = ?,
            fantasia = ?,
            vendedor = ?,
            data = ?,
            condicao = ?,
            vencimento = ?,
            desconto = ?,
            observacao = ?,
            total = ?
        WHERE id = ?
    """, (
        dados.get("cliente", ""),
        dados.get("fantasia", ""),
        dados.get("vendedor", ""),
        dados.get("data", ""),
        dados.get("condicao", ""),
        dados.get("vencimento", ""),
        desconto,
        dados.get("observacao", ""),
        max(0, sum(quantidade * valor for _, quantidade, valor in itens) * (1 - desconto / 100)),
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
        "mensagem": "Venda atualizada com sucesso!"
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

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Venda excluída com sucesso!"
    })


# =========================
# INICIAR SERVIDOR
# =========================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=os.environ.get("FLASK_DEBUG") == "1"
    )
