import os, psycopg
from psycopg.rows import dict_row
env_file = os.path.join(os.environ["TEMP"], "sistemaos.env")
url=None
with open(env_file) as f:
    for line in f:
        if 'DATABASE_URL="' in line:
            url=line.split('"')[1]
            break
con=psycopg.connect(url, row_factory=dict_row)
cur=con.cursor()
cur.execute('DELETE FROM venda_itens')
print('venda_itens pg apagados', cur.rowcount)
cur.execute('DELETE FROM vendas')
print('vendas pg apagadas', cur.rowcount)
cur.execute('UPDATE controle_vendas SET ultimo_numero=0 WHERE id=1')
print('controle pg resetado')
cur.execute("SELECT setval(pg_get_serial_sequence('vendas','id'), 1, false)")
cur.execute("SELECT setval(pg_get_serial_sequence('venda_itens','id'), 1, false)")
con.commit()
cur.execute('SELECT COUNT(*) as c FROM vendas')
print('vendas pg', cur.fetchone()['c'])
cur.execute('SELECT ultimo_numero FROM controle_vendas WHERE id=1')
print('controle', cur.fetchone())
con.close()
print("zerado Neon")
