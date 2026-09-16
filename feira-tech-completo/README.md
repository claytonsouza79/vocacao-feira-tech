# Feira Tech Vocação

Webserver para a feira tecnológica, com dois fluxos:

- **Visitante:** acessa o stand por QR Code, tem o tempo contado automaticamente e envia uma avaliação de 1 a 5 estrelas (uma única vez por stand).
- **Expositor:** cadastra o stand uma única vez (nome duplicado é bloqueado), recebe um código secreto e acompanha visitantes, tempo de permanência e notas.
- **Divulgação:** após avaliar, o visitante cria um card com foto no próprio celular, compartilha nas redes e pode enviar uma mensagem para o mural público (mediante aprovação do expositor).

## Tecnologias

- Python + Flask no servidor
- HTML, CSS e JavaScript puros no navegador
- **PostgreSQL** para persistência (antes era um arquivo JSON local — trocado para poder rodar no Render)

## Testar localmente (com Postgres em Docker)

1. Suba um Postgres local:
   ```bash
   docker compose up -d
   ```
2. Crie e ative o ambiente virtual, depois instale as dependências:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\Activate.ps1
   # Linux/macOS: source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Aponte o app para o Postgres do Docker e rode:
   ```bash
   # Windows (PowerShell)
   $env:DATABASE_URL = "postgresql://feira:feira@localhost:5432/feira_tech"
   python app.py

   # Linux/macOS
   export DATABASE_URL="postgresql://feira:feira@localhost:5432/feira_tech"
   python app.py
   ```
4. Abra `http://localhost:5000`. As tabelas são criadas automaticamente na primeira execução.

### Importar os dados já registrados hoje (opcional, uma vez só)

Se quiser recuperar os stands/avaliações que já foram feitos antes desta migração:

```bash
python migrar_json_para_postgres.py feira_tech.json
```
(rode com a mesma `DATABASE_URL` já exportada no passo 3)

## Publicar no Render (plano gratuito)

1. Suba este projeto (sem o `feira_tech.json`, ele não é mais necessário depois da migração) num repositório Git.
2. No Render: **New → PostgreSQL** (plano Free) — guarde a Internal e a External Database URL.
3. No Render: **New → Web Service**, conectando o repositório.
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
4. Em Environment Variables do Web Service, adicione `DATABASE_URL` com a **Internal Database URL** do banco criado no passo 2.
5. Depois do primeiro deploy, rode a importação (se ainda não rodou local) usando a **External Database URL**:
   ```bash
   DATABASE_URL="<external-database-url>" python migrar_json_para_postgres.py feira_tech.json
   ```
6. Teste tudo pela URL pública (`algo.onrender.com`) antes de divulgar o link/QR Codes.

**Avisos do plano gratuito do Render:**
- O Postgres free expira em 30 dias (mais 14 dias de carência antes de apagar) — tranquilo para o evento, mas não é permanente.
- O Web Service free "dorme" após 15 min sem acesso e leva ~1 min para acordar na próxima requisição.

## Dados e segurança

- O código secreto do expositor não é salvo diretamente: só uma derivação criptográfica (PBKDF2) é armazenada.
- Cadastro de stand com nome duplicado é bloqueado pelo próprio banco (índice único, sem depender só da validação da aplicação).
- Avaliação duplicada do mesmo visitante no mesmo stand também é bloqueada pelo banco.
- O bloqueio de avaliações repetidas identifica o navegador (via `localStorage`); limpar os dados do navegador permite uma nova avaliação.
- As fotos usadas nos cards sociais são processadas somente no navegador: não são enviadas nem gravadas no banco.
- Mensagens do mural só ficam públicas depois da aprovação do expositor responsável.

## Rotas principais

- `/` — escolha de perfil e lista de stands
- `/visitar/<id>` — avaliação do visitante
- `/expositor` — cadastro ou entrada do expositor
- `/stand/<id>` — painel privado do stand
