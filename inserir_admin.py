import sqlite3, psycopg, os
from psycopg.rows import dict_row
env_file = os.path.join(os.environ["TEMP"], "sistemaos.env")
url = None
with open(env_file) as f:
    for line in f:
        if 'DATABASE_URL="' in line:
            url = line.split('"')[1]
            break
con_lt=sqlite3.connect('ordens.db')
con_lt.row_factory=sqlite3.Row
cur_lt=con_lt.cursor()
cur_lt.execute("SELECT usuario, senha, papel FROM usuarios WHERE usuario='admin'")
row = cur_lt.fetchone()
print("local admin", dict(row))
con_pg=psycopg.connect(url, row_factory=dict_row)
cur_pg=con_pg.cursor()
cur_pg.execute("SELECT * FROM usuarios WHERE upper(usuario)=upper(%s)", ('admin',))
exists = cur_pg.fetchone()
print("pg admin exists?", exists)
if not exists:
    cur_pg.execute("INSERT INTO usuarios (usuario, senha, papel) VALUES (%s,%s,%s)", (row['usuario'], row['senha'], row['papel']))
    con_pg.commit()
    print("admin inserido")
else:
    print("ja existe")
cur_pg.execute("SELECT id, usuario, papel FROM usuarios ORDER BY id")
for r in cur_pg.fetchall():
    print(r)
con_pg.close()
