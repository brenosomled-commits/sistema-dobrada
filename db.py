"""
Camada de acesso a dados do Sistema SOMLED.

Suporta dois bancos:
  - SQLite      (padrão local, arquivo ordens.db)
  - PostgreSQL  (produção/Vercel, banco Neon)

A seleção do driver é automática pela presença da variável de ambiente
DATABASE_URL. Quando presente, usa PostgreSQL; caso contrário, SQLite.

Resiliência ao Neon (serverless PostgreSQL):
  - O Neon hiberna após ~5 min de inatividade. A primeira conexão pode
    demorar 2-5 segundos ("cold start"). Usamos retry com back-off e
    connect_timeout maior para absorver esse delay sem erros.
  - O pool mantém conexões ociosas vivas com keep-alive automático do
    psycopg (keepalives_idle=30), evitando que o firewall da Vercel
    feche a conexão silenciosamente entre requests.
  - Se uma conexão do pool estiver morta (banco hibernou), descartamos
    ela e abrimos uma nova em vez de propagar o erro.
"""

import os
import socket
import time as _time
from urllib.parse import urlsplit

DRIVER = "postgres" if os.environ.get("DATABASE_URL") else "sqlite"


def banco_eh_postgres():
    return DRIVER == "postgres"


def _criar_conexao_postgres(tentativas=1):
    """Abre uma conexão PostgreSQL (Neon) com retry e back-off."""
    import psycopg
    from psycopg.rows import dict_row

    ultimo_erro = None
    for i in range(tentativas):
        try:
            parametros = {}
            partes_url = urlsplit(os.environ["DATABASE_URL"])
            if partes_url.hostname:
                enderecos_ipv4 = socket.getaddrinfo(
                    partes_url.hostname,
                    partes_url.port or 5432,
                    family=socket.AF_INET,
                    type=socket.SOCK_STREAM,
                )
                if enderecos_ipv4:
                    parametros["hostaddr"] = enderecos_ipv4[0][4][0]
            conexao = psycopg.connect(
                os.environ["DATABASE_URL"],
                **parametros,
                connect_timeout=5,           # não deixa uma requisição serverless presa
                keepalives=1,                # TCP keep-alive ativo
                keepalives_idle=30,          # envia keep-alive após 30s ociosos
                keepalives_interval=10,      # reenvio a cada 10s
                keepalives_count=5,          # até 5 tentativas antes de falhar
            )
            conexao.row_factory = dict_row
            conexao.autocommit = False
            return conexao
        except Exception as e:
            ultimo_erro = e
            espera = 1.5 * (i + 1)          # 1.5s, 3s, 4.5s, 6s, 7.5s
            print(f"[DB] Tentativa {i+1}/{tentativas} falhou ({e}). Aguardando {espera:.1f}s...")
            _time.sleep(espera)
    raise ultimo_erro


# Pool simples de conexões PostgreSQL.
_POOL_MAX = 3
_pool = []
_pool_lock = None


def _init_pool_lock():
    import threading
    global _pool_lock
    if _pool_lock is None:
        _pool_lock = threading.Lock()


def _conexao_postgres():
    """Obtém uma conexão: reutiliza uma ociosa do pool ou cria uma nova.
    Se a conexão ociosa estiver morta (banco hibernou), descarta e abre nova.
    """
    if _pool_lock is None:
        _init_pool_lock()
    with _pool_lock:
        while _pool:
            conexao = _pool.pop()
            # Testa se ainda está viva com um ping leve
            try:
                conexao.execute("SELECT 1")
                return conexao
            except Exception:
                try:
                    conexao.close()
                except Exception:
                    pass
                # Conexão morta — descarta e tenta a próxima do pool
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
        viva = False
        if not conexao.closed and len(_pool) < _POOL_MAX:
            try:
                conexao.execute("SELECT 1")
                viva = True
            except Exception:
                pass
        if viva:
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
    """Retorna uma conexão unificada, escolhendo o driver automaticamente.
    Em caso de falha no Postgres, tenta novamente antes de propagar o erro.
    """
    if DRIVER == "postgres":
        return ConexaoUnificada("postgres", _conexao_postgres())
    return ConexaoUnificada("sqlite", _conexao_sqlite())
