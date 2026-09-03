import sqlite3, os, psycopg
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash
nova = "Trocar@123"
hash_novo = generate_password_hash(nova)
print("novo hash", hash_novo[:60])
# local
con_lt = sqlite3.connect('ordens.db')
cur_lt = con_lt.cursor()
for user in ['BRENO','WILLIAN','admin','SONIA','GABRIEL','YAN','VINICIUS']:
    cur_lt.execute("UPDATE usuarios SET senha=? WHERE upper(usuario)=upper(?)", (hash_novo, user))
    print(f"local {user} -> {cur_lt.rowcount}")
con_lt.commit()
con_lt.close()
print("local atualizado")
# remoto
env_file=os.path.join(os.environ["TEMP"],"sistemaos.env")
url=None
with open(env_file,encoding='utf-8') as f:
    for line in f:
        if 'DATABASE_URL="' in line:
            url=line.split('"')[1]
            break
con_pg=psycopg.connect(url, row_factory=dict_row)
cur_pg=con_pg.cursor()
for user in ['BRENO','WILLIAN','admin','SONIA','GABRIEL','YAN','VINICIUS']:
    cur_pg.execute("UPDATE usuarios SET senha=%s WHERE upper(usuario)=upper(%s)", (hash_novo, user))
    print(f"pg {user} -> {cur_pg.rowcount}")
con_pg.commit()
# verifica
cur_pg.execute("SELECT usuario, papel FROM usuarios ORDER BY id")
for r in cur_pg.fetchall():
    print(r)
con_pg.close()
print("pg atualizado - senha agora Trocar@123 para todos")
