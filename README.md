# 1ª Feira Tech dos Jovens da Vocação — Sistema de Gestão e Avaliação

Sistema web completo para cadastro de stands, avaliação de projetos e geração de relatórios da 1ª Feira Tech dos Jovens da Vocação. Desenvolvido em Python + Flask, pronto para deploy no Render.com.

---

## Estrutura do Projeto

```
feira-tech/
├── app.py              # Servidor Flask + todas as rotas da API
├── database.py         # Modelos SQLAlchemy (4 tabelas)
├── store.py            # Camada de negócio + travas de segurança
├── index.html          # SPA — Single Page Application (7 telas)
├── static/
│   ├── style.css       # CSS completo (design responsivo)
│   └── script.js       # JavaScript do front-end
├── requirements.txt    # Dependências Python
├── Procfile            # Configuração do Render.com (gunicorn)
├── .env.example        # Template de variáveis de ambiente
└── README.md           # Esta documentação
```

---

## Banco de Dados — Tabelas

| Tabela | Descrição |
|---|---|
| `stands` | Stand/projeto de um grupo (único por `group_id`) |
| `visitors` | Perfil do visitante por hash de visitor_key |
| `avaliacoes` | Avaliações com nota, duração e perfil do visitante |
| `engajamentos` | Compartilhamentos (share) e apoios ao mural (support) |

---

## Regras de Negócio e Travas de Segurança

### 1. Stand único por grupo (`store.py: create_stand`)
O nome do grupo é normalizado para um slug (`normalize_group()`), verificado antes do `INSERT` e protegido por `UNIQUE constraint` no banco. Nenhum grupo pode ter mais de 1 stand.

### 2. Perfil do visitante obrigatório
Antes de acessar qualquer stand, o visitante deve selecionar seu perfil:
- **Aluno Vocação** — informa também seu curso e nome do grupo
- **Funcionário Vocação**
- **Visitante Externo**
- **Empresa**

### 3. Trava de Ouro — Aluno não avalia o próprio stand (`store.py: start_visit`)
Quando um aluno tenta iniciar uma visita, o sistema compara o slug do grupo do aluno com o `group_id` do stand. Se forem idênticos, a visita é bloqueada com HTTP 403.

### 4. Um voto por stand por dispositivo
O `visitor_hash` (SHA-256 da visitor_key do browser) impede que o mesmo dispositivo avalie o mesmo stand duas vezes.

### 5. Código de acesso do expositor
O código de 6 caracteres nunca é salvo em texto plano — apenas o salt e o hash PBKDF2-HMAC-SHA256. A comparação usa `hmac.compare_digest` para evitar timing attacks.

### 6. Moderação do mural público
Mensagens de apoio ficam com status `pending` até o expositor aprovar ou rejeitar via painel.

---

## Instalação e Execução Local

### 1. Clonar / abrir a pasta do projeto

```
cd c:\xampp\htdocs\feira-tech-social\feira-tech
```

### 2. Criar ambiente virtual e instalar dependências

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente (opcional para teste local)

```powershell
# Windows PowerShell
$env:ADMIN_PASSWORD="minhasenha"
$env:SECRET_KEY="qualquer-string-longa"
```

```bash
# Linux / macOS
export ADMIN_PASSWORD="minhasenha"
export SECRET_KEY="qualquer-string-longa"
```

### 4. Executar o servidor de desenvolvimento

```bash
python app.py
```

Acesse: **http://localhost:5000**

---

## Rotas Principais

| Rota | Descrição |
|---|---|
| `/` | Home — seleção de perfil + lista de stands + mural |
| `/visitar/<id>` | Avaliação do visitante no stand |
| `/expositor` | Cadastro ou login do expositor |
| `/stand/<id>` | Painel privado do stand (métricas + moderação) |
| `/admin` | Painel administrativo global (requer senha) |

### API REST

| Método | Endpoint | Descrição |
|---|---|---|
| `POST` | `/api/visitors/profile` | Salvar perfil do visitante |
| `GET` | `/api/stands` | Listar todos os stands |
| `POST` | `/api/stands` | Cadastrar novo stand |
| `POST` | `/api/stands/<id>/visits/start` | Iniciar visita/avaliação |
| `POST` | `/api/stands/<id>/visits/<vid>/finish` | Finalizar com nota |
| `POST` | `/api/stands/<id>/engagement/share` | Registrar compartilhamento |
| `POST` | `/api/stands/<id>/engagement/support` | Enviar apoio ao mural |
| `GET` | `/api/stands/<id>/dashboard?code=` | Métricas do expositor |
| `GET` | `/api/stands/<id>/qr?code=` | QR Code do stand |
| `GET` | `/api/stands/<id>/export?code=` | CSV do stand |
| `GET` | `/api/mural` | Apoios aprovados (mural público) |
| `GET` | `/api/admin/dashboard?password=` | Métricas globais (admin) |
| `GET` | `/api/admin/export?password=` | CSV global (admin) |

---

## Deploy no Render.com (Passo a Passo)

### 1. Criar repositório Git e fazer push

```bash
git init
git add .
git commit -m "primeira versão - feira tech"
git remote add origin https://github.com/SEU_USUARIO/feira-tech.git
git push -u origin main
```

### 2. Criar o serviço no Render.com

1. Acesse [render.com](https://render.com) e faça login
2. Clique em **New → Web Service**
3. Conecte seu repositório GitHub
4. Preencha:
   - **Name:** `feira-tech-vocacao`
   - **Environment:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT`
5. Em **Environment Variables**, adicione:
   | Variável | Valor |
   |---|---|
   | `SECRET_KEY` | *(string aleatória longa)* |
   | `ADMIN_PASSWORD` | *(senha forte para o admin)* |
   | `DATABASE_URL` | `sqlite:///feira_tech.db` *(ou URL do PostgreSQL)* |
6. Clique em **Create Web Service**

### 3. Persistência do banco de dados

> **⚠️ Atenção:** O plano gratuito do Render usa disco efêmero. O arquivo `feira_tech.db` é perdido a cada novo deploy.
>
> Para o evento de um dia, isso é aceitável — o banco é recriado vazio a cada deploy.
>
> Para persistência permanente, adicione um **PostgreSQL** no Render e use a `DATABASE_URL` fornecida.

---

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
|---|---|---|
| `PORT` | Porta do servidor (injetada pelo Render) | `5000` |
| `SECRET_KEY` | Chave secreta Flask | *(gerada aleatoriamente)* |
| `DATABASE_URL` | URL do banco de dados | `sqlite:///feira_tech.db` |
| `ADMIN_PASSWORD` | Senha do painel administrativo | `admin@feira2025` |

---

## Tecnologias

- **Python 3.11+** + **Flask 3.1**
- **SQLAlchemy 2.0** com SQLite (compatível com PostgreSQL)
- **Gunicorn** como servidor WSGI de produção
- **qrcode + Pillow** para geração de QR Codes
- **HTML + CSS + JavaScript** puros no navegador (sem frameworks)
- **Canvas API** para geração de cards sociais no cliente