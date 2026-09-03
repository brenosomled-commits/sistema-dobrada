import sqlite3, os, psycopg
from psycopg.rows import dict_row
con_lt=sqlite3.connect('ordens.db')
con_lt.row_factory=sqlite3.Row
cur=con_lt.cursor()
cur.execute("SELECT usuario, senha, papel FROM usuarios WHERE usuario='BRENO'")
r=cur.fetchone()
print('local BRENO hash', r['senha'][:60], 'papel', r['papel'])
env_file=os.path.join(os.environ["TEMP"],"sistemaos.env")
url=None
with open(env_file,encoding='utf-8') as f:
    for line in f:
        if 'DATABASE_URL="' in line:
            url=line.split('"')[1]
            break
con_pg=psycopg.connect(url, row_factory=dict_row)
cur_pg=con_pg.cursor()
cur_pg.execute("SELECT usuario, senha, papel FROM usuarios WHERE upper(usuario)=upper(%s)", ('BRENO',))
r2=cur_pg.fetchone()
print('remote BRENO hash', r2['senha'][:60], 'papel', r2['papel'])
print('hash igual?', r['senha']==r2['senha'])
# test check_password_hash
from werkzeug.security import check_password_hash
for pwd in ["Trocar@123","12345678","breno","BRENO"]:
    print(pwd, check_password_hash(r2['senha'], pwd) if r2['senha'].startswith(('pbkdf2:','scrypt:')) else (r2['senha']==pwd))
