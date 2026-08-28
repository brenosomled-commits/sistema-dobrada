from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import sqlite3
from functools import wraps

app = Flask(__name__)
app.secret_key = "somled_os_2026_chave_secreta"

BANCO = "ordens.db"


def conectar():
    conexao = sqlite3.connect(BANCO)
    conexao.row_factory = sqlite3.Row
    return conexao


def criar_banco():

    conexao = conectar()
    cursor = conexao.cursor()

    # TABELA DE USUÁRIOS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    """)

    cursor.execute(
        "SELECT id FROM usuarios WHERE usuario = ?",
        ("admin",)
    )

    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO usuarios (usuario, senha) VALUES (?, ?)",
            ("admin", "1234")
        )

    # TABELA DE ORDENS
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

    # TABELA DE ITENS
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

    # CONTROLE DO ÚLTIMO NÚMERO DA OS
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

        cursor.execute("SELECT MAX(numero) FROM ordens")

        maior_numero = cursor.fetchone()[0]

        ultimo_numero = 0 if maior_numero is None else maior_numero

        cursor.execute(
            "INSERT INTO controle_os (id, ultimo_numero) VALUES (1, ?)",
            (ultimo_numero,)
        )

    # ATUALIZAÇÕES PARA BANCOS ANTIGOS
    for comando in [
        "ALTER TABLE ordens ADD COLUMN status TEXT DEFAULT 'Em andamento'",
        "ALTER TABLE ordens ADD COLUMN responsavel TEXT",
        "ALTER TABLE ordens ADD COLUMN cliente TEXT",
        "ALTER TABLE ordens ADD COLUMN telefone TEXT",
        "ALTER TABLE itens ADD COLUMN quantidade REAL DEFAULT 1"
    ]:
        try:
            cursor.execute(comando)
        except:
            pass

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

        if session["usuario"] != "admin":
            return jsonify({
                "erro": "Acesso permitido somente para o administrador."
            }), 403

        return funcao(*args, **kwargs)

    return verificar


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        usuario = request.form.get("usuario")
        senha = request.form.get("senha")

        conexao = conectar()
        cursor = conexao.cursor()

        cursor.execute(
            "SELECT * FROM usuarios WHERE usuario = ? AND senha = ?",
            (usuario, senha)
        )

        resultado = cursor.fetchone()

        conexao.close()

        if resultado:

            session["usuario"] = usuario

            return redirect(url_for("inicio"))

        return render_template(
            "login.html",
            erro="Usuário ou senha incorretos!"
        )

    return render_template("login.html")
@app.route("/nota_dobrada")
@login_obrigatorio
def nota_dobrada():
    return render_template("nota_dobrada.html")

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
        usuario=session["usuario"]
    )


# =========================
# PÁGINA PRINCIPAL
# =========================

@app.route("/")
@login_obrigatorio
def inicio():

    return render_template(
        "index.html",
        usuario=session["usuario"]
    )


# =========================
# MINHA SENHA
# =========================

@app.route("/minha_senha")
@login_obrigatorio
def minha_senha():

    return render_template(
        "minha_senha.html",
        usuario=session["usuario"]
    )


@app.route("/api/minha_senha", methods=["PUT"])
@login_obrigatorio
def alterar_minha_senha():

    dados = request.json

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

    if not usuario or usuario["senha"] != senha_atual:

        conexao.close()

        return jsonify({
            "erro": "A senha atual está incorreta."
        }), 400

    cursor.execute(
        "UPDATE usuarios SET senha = ? WHERE usuario = ?",
        (nova_senha, session["usuario"])
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
        usuario_logado=session["usuario"]
    )


@app.route("/api/usuarios")
@admin_obrigatorio
def listar_usuarios():

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "SELECT id, usuario FROM usuarios ORDER BY usuario"
    )

    usuarios = cursor.fetchall()

    conexao.close()

    return jsonify([
        {
            "id": usuario["id"],
            "usuario": usuario["usuario"]
        }
        for usuario in usuarios
    ])


@app.route("/api/usuarios", methods=["POST"])
@admin_obrigatorio
def criar_usuario():

    dados = request.json

    usuario = dados.get("usuario", "").strip()
    senha = dados.get("senha", "").strip()

    if not usuario or not senha:

        return jsonify({
            "erro": "Preencha usuário e senha."
        }), 400

    conexao = conectar()
    cursor = conexao.cursor()

    try:

        cursor.execute(
            "INSERT INTO usuarios (usuario, senha) VALUES (?, ?)",
            (usuario, senha)
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


@app.route("/api/usuarios/<int:id>/senha", methods=["PUT"])
@admin_obrigatorio
def alterar_senha_usuario(id):

    dados = request.json

    nova_senha = dados.get("senha", "").strip()

    if not nova_senha:

        return jsonify({
            "erro": "Digite uma nova senha."
        }), 400

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "UPDATE usuarios SET senha = ? WHERE id = ?",
        (nova_senha, id)
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
# USUÁRIOS PARA RESPONSÁVEL DA OS
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

    ultimo_numero = 0 if resultado is None else resultado["ultimo_numero"]

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

    dados = request.json

    conexao = conectar()
    cursor = conexao.cursor()

    # GARANTE QUE O NÚMERO RECEBIDO NÃO SEJA MENOR
    cursor.execute(
        "SELECT ultimo_numero FROM controle_os WHERE id = 1"
    )

    controle = cursor.fetchone()

    ultimo_numero = 0 if controle is None else controle["ultimo_numero"]

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
        dados["solucao"],
        dados.get("responsavel", ""),
        dados["mao_obra"],
        dados["total"],
        "Em andamento"
    ))

    ordem_id = cursor.lastrowid

    # ATUALIZA O ÚLTIMO NÚMERO UTILIZADO
    cursor.execute("""
        UPDATE controle_os
        SET ultimo_numero = ?
        WHERE id = 1
    """, (
        novo_numero,
    ))

    for item in dados["itens"]:

        cursor.execute("""
            INSERT INTO itens
            (ordem_id, nome, quantidade, valor)
            VALUES (?, ?, ?, ?)
        """, (
            ordem_id,
            item["nome"],
            item.get("quantidade", 1),
            item["valor"]
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
# BUSCAR UMA OS
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

    dados = request.json

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
        dados["solucao"],
        dados.get("responsavel", ""),
        dados["mao_obra"],
        dados["total"],
        id
    ))

    cursor.execute(
        "DELETE FROM itens WHERE ordem_id = ?",
        (id,)
    )

    for item in dados["itens"]:

        cursor.execute("""
            INSERT INTO itens
            (ordem_id, nome, quantidade, valor)
            VALUES (?, ?, ?, ?)
        """, (
            id,
            item["nome"],
            item.get("quantidade", 1),
            item["valor"]
        ))

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Ordem atualizada com sucesso!"
    })


# =========================
# ALTERAR STATUS
# =========================
@app.route("/alterar_status/<int:id>", methods=["POST"])
@login_obrigatorio
def alterar_status(id):

    dados = request.json

    novo_status = dados.get("status")

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute(
        "UPDATE ordens SET status = ? WHERE id = ?",
        (novo_status, id)
    )

    conexao.commit()
    conexao.close()

    return jsonify({
        "mensagem": "Status atualizado!"
    })
# =========================
# EXCLUIR OS
# =========================

@app.route("/excluir_os/<int:id>", methods=["DELETE"])
@login_obrigatorio
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


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )