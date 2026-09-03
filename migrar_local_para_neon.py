import os, sqlite3, psycopg
from psycopg.rows import dict_row

# carrega DATABASE_URL do arquivo temporário do vercel
env_file = os.path.join(os.environ["TEMP"], "sistemaos.env")
db_url = None
with open(env_file, encoding="utf-8") as f:
    for line in f:
        line=line.strip()
        if line.startswith('DATABASE_URL="'):
            db_url = line.split('"')[1]
            break
if not db_url:
    raise SystemExit("DATABASE_URL não encontrado em sistemaos.env")

print("Conectando local SQLite e Neon Postgres...")
con_lt = sqlite3.connect("ordens.db")
con_lt.row_factory = sqlite3.Row
cur_lt = con_lt.cursor()

con_pg = psycopg.connect(db_url, row_factory=dict_row)
cur_pg = con_pg.cursor()

def migrate_table_sqlite_to_pg(table, columns, unique_key=None):
    cur_lt.execute(f"SELECT * FROM {table}")
    rows = cur_lt.fetchall()
    if not rows:
        print(f"{table}: 0 linhas locais")
        return 0
    cur_pg.execute(f"SELECT COUNT(*) as c FROM {table}")
    antes = cur_pg.fetchone()["c"]
    inseridos = 0
    for r in rows:
        vals = [r[c] for c in columns]
        placeholders = ",".join(["%s"]*len(columns))
        cols = ",".join(columns)
        # verifica se já existe por id
        id_val = r["id"] if "id" in r.keys() else None
        if id_val is not None:
            cur_pg.execute(f"SELECT 1 FROM {table} WHERE id=%s", (id_val,))
            if cur_pg.fetchone():
                continue
        # para usuarios, verifica por usuario único
        if table=="usuarios":
            cur_pg.execute("SELECT 1 FROM usuarios WHERE upper(usuario)=upper(%s)", (r["usuario"],))
            if cur_pg.fetchone():
                continue
        try:
            cur_pg.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", vals)
            inseridos += 1
        except Exception as e:
            print(f" erro insert {table} id={id_val}: {e}")
            con_pg.rollback()
    con_pg.commit()
    # reset sequence
    if inseridos>0 or True:
        try:
            cur_pg.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE((SELECT MAX(id) FROM {table}),1))")
            con_pg.commit()
        except Exception as e:
            # controle_* não tem serial, ignora
            con_pg.rollback()
    cur_pg.execute(f"SELECT COUNT(*) as c FROM {table}")
    depois = cur_pg.fetchone()["c"]
    print(f"{table}: antes {antes} -> depois {depois} (inseridos {inseridos})")
    return inseridos

# ordem importa por FK
migrate_table_sqlite_to_pg("usuarios", ["id","usuario","senha","papel"])
migrate_table_sqlite_to_pg("ordens", ["id","numero","data_entrada","cliente","telefone","problema","solucao","responsavel","mao_obra","total","status"])
migrate_table_sqlite_to_pg("itens", ["id","ordem_id","nome","quantidade","valor"])
migrate_table_sqlite_to_pg("vendas", ["id","numero","cliente","fantasia","vendedor","data","condicao","vencimento","desconto","observacao","total","comissao"])
migrate_table_sqlite_to_pg("venda_itens", ["id","venda_id","quantidade","descricao","valor"])

# atualiza controles
for tbl, col in [("controle_os","ultimo_numero"),("controle_vendas","ultimo_numero")]:
    cur_lt.execute(f"SELECT * FROM {tbl} WHERE id=1")
    row = cur_lt.fetchone()
    if row:
        cur_pg.execute(f"UPDATE {tbl} SET {col}=%s WHERE id=1", (row[col],))
        print(f"{tbl} atualizado para {row[col]}")
con_pg.commit()

# verificação final
for tbl in ["usuarios","ordens","itens","vendas","venda_itens","controle_os","controle_vendas"]:
    cur_pg.execute(f"SELECT COUNT(*) as c FROM {tbl}")
    print(f"FINAL {tbl}: {cur_pg.fetchone()['c']}")

con_lt.close()
con_pg.close()
print("Migração concluída")
