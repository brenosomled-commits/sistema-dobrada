"""
Camada de acesso a dados do Sistema SOMLED.

Suporta dois bancos:
  - SQLite      (padrão local, arquivo ordens.db)
  - PostgreSQL  (produção/Vercel, banco Neon)

A seleção do driver é automática pela presença da variável de ambiente
DATABASE_URL. Quando presente, usa PostgreSQL; caso contrário, SQLite.

O módulo expõe uma interface unificada e compatível com o restante do app:
  conectar() -> ConexaoUnificada
  conectar().execute(sql, params).fetchone()/fetchall()
  conectar().cursor()  e  cursor.execute(...)
  .commit(), .close(), .lastrowid, .rowcount

Placeholders "?" (SQLite) são traduzidos para "%s" (PostgreSQL), "BEGIN
IMMEDIATE" é convertido para "BEGIN", e INSERTs no PostgreSQL ganham
"RETURNING id" para que .lastrowid funcione igual ao SQLite.
"""

import os
import time as _time

DRIVER = "postgres" if os.environ.get("DATABASE_URL") else "sqlite"


def banco_eh_postgres():
    return DRIVER == "postgres"


def _criar_conexao_postgres(tentativas=3):
    """Abre uma conexão PostgreSQL (Neon) com retry, configurada para o app."""
    import psycopg
    from psycopg.rows import dict_row

    ultimo_erro = None
    for _ in range(tentativas):
        try:
            conexao = psycopg.connect(
                os.environ["DATABASE_URL"],
                connect_timeout=15,
            )
            conexao.row_factory = dict_row
            conexao.autocommit = False
            return conexao
        except Exception as e:
            ultimo_erro = e
            _time.sleep(1)
    raise ultimo_erro


# Pool simples de conexões PostgreSQL para reutilizar no serverless (Vercel).
# Evita abrir uma conexão nova a cada request, reduzindo o cold start do Neon
# e os erros de conexão intermitentes. O módulo é recarregado a cada execução
# fria; quando a instância está "quente" o pool persiste entre requests.
_POOL_MAX = 3
_pool = []          # conexões ociosas (postgres)
_pool_lock = None


def _init_pool_lock():
    import threading
    global _pool_lock
    if _pool_lock is None:
        _pool_lock = threading.Lock()


def _conexao_postgres():
    """Obtém uma conexão: reutiliza uma ociosa do pool ou cria uma nova."""
    if _pool_lock is None:
        _init_pool_lock()
    with _pool_lock:
        if _pool:
            conexao = _pool.pop()
            return conexao
    return _criar_conexao_postgres()


def _devolver_conexao_postgres(conexao):
    """Devolve a conexão ao pool ou fecha, conforme disponibilidade."""
    try:
        conexao.rollback()
    except Exception:
        pass
    if _pool_lock is None:
        _init_pool_lock()
    with _pool_lock:
        _usar_no_pool = not conexao.closed and len(_pool) < _POOL_MAX
        if _usar_no_pool:
            _pool.append(conexao)
        else:
            try:
                conexao.close()
            except Exception:
                pass


def _conexao_sqlite():
    import sqlite3

    banco = os.environ.get(
        "SQLITE_DATABASE",
        str(Path(__file__).with_name("ordens.db")),
    )
    conexao = sqlite3.connect(banco, timeout=10)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.execute("PRAGMA journal_mode = WAL")
    return conexao


from pathlib import Path  # noqa: E402


class CursorUnificado:
    """Wrapper que unifica os cursors SQLite e PostgreSQL."""

    def __init__(self, cursor, driver, conexao=None):
        self._cursor = cursor
        self._driver = driver
        self._conexao = conexao
        self._lastrowid = None

    @property
    def driver(self):
        return self._driver

    def execute(self, sql, params=None):
        if self._driver == "postgres":
            sql_adaptado = sql.replace("?", "%s")
            cabecalho = sql.strip().upper()
            if cabecalho == "BEGIN IMMEDIATE":
                sql_adaptado = "BEGIN"
            elif cabecalho[:6] == "INSERT":
                # JOIN_ADICIONA_RETURNING: quando o INSERT usa ON CONFLICT/DO NOTHING
                # o RETURNING id pode falhar (ex.: tabela sem coluna "id"), então
                # só adicionamos RETURNING quando não há ON CONFLICT.
                if " ON CONFLICT " not in sql_adaptado.upper():
                    sql_adaptado = sql_adaptado.rstrip().rstrip(";") + " RETURNING id"

            self._cursor.execute(sql_adaptado, params or ())

            if cabecalho[:6] == "INSERT" and " ON CONFLICT " not in sql_adaptado.upper():
                linha = self._cursor.fetchone()
                if linha is None:
                    self._lastrowid = None
                elif isinstance(linha, dict):
                    self._lastrowid = linha.get("id")
                else:
                    self._lastrowid = linha[0]
        else:
            self._cursor.execute(sql, params or ())
        return self

    @property
    def lastrowid(self):
        if self._driver == "sqlite":
            return self._cursor.lastrowid
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class ConexaoUnificada:
    """Wrapper sobre uma conexão SQLite ou PostgreSQL."""

    def __init__(self, driver, conexao):
        self._driver = driver
        self._conexao = conexao

    def cursor(self):
        return CursorUnificado(self._conexao.cursor(), self._driver, self._conexao)

    def execute(self, sql, params=None):
        cursor = self.cursor()
        cursor.execute(sql, params)
        return cursor

    def commit(self):
        try:
            self._conexao.commit()
        except Exception:
            pass

    def rollback(self):
        try:
            self._conexao.rollback()
        except Exception:
            pass

    def close(self):
        try:
            if self._driver == "postgres":
                _devolver_conexao_postgres(self._conexao)
            else:
                self._conexao.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def conectar():
    """Retorna uma conexão unificada, escolhendo o driver automaticamente."""
    if DRIVER == "postgres":
        return ConexaoUnificada("postgres", _conexao_postgres())
    return ConexaoUnificada("sqlite", _conexao_sqlite())
