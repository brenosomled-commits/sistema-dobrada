# Sistema OS

Sistema de triagem de ordens de serviço, acompanhamento, responsáveis e vendas. As rotas e telas existentes foram preservadas.

## Executar localmente

Clique duas vezes em `iniciar_local.bat`. Na primeira execução ele cria `.venv`, instala as dependências e abre `http://127.0.0.1:5000`.

Para uma base nova, o iniciador cria o primeiro acesso com `admin` e senha `admin1234`. Troque a senha imediatamente em **Minha senha**. Em produção, defina `ADMIN_PASSWORD` antes do primeiro deploy.

## Publicar na Vercel

O arquivo `vercel.json` e `requirements.txt` já configuram a função Flask. Antes de publicar, defina em **Settings → Environment Variables**:

- `SECRET_KEY`: valor longo, aleatório e exclusivo.
- `ADMIN_PASSWORD`: senha forte do administrador inicial, se o banco estiver vazio.

> Importante: SQLite é adequado ao teste local, mas o disco da Vercel é efêmero. Em produção o app usa **PostgreSQL (Neon)**:
>
> - A integração Neon no Vercel injeta automaticamente a variável `DATABASE_URL` no projeto.
> - Quando `DATABASE_URL` está presente, `db.py` usa PostgreSQL (Neon); caso contrário, usa SQLite local (`ordens.db`).
> - As tabelas e o usuário inicial são criados automaticamente no primeiro boot (`criar_banco()` roda no import). Não é preciso migrar dados do `ordens.db` local.

## Controles incluídos

- Senhas com hash e migração automática das senhas antigas no primeiro login.
- Chave de sessão por variável de ambiente, cookies protegidos e cabeçalhos básicos de segurança.
- Validação de payloads, valores e status; totais recalculados no servidor.
- Numeração de OS e vendas serializada e índices para listagens maiores.
- Exclusão limitada ao administrador.
