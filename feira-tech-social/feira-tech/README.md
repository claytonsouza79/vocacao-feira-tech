# Feira Tech Vocação

Webserver local para a feira tecnológica, com dois fluxos:

- **Visitante:** acessa o stand por QR Code, tem o tempo contado automaticamente e envia uma avaliação de 1 a 5 estrelas.
- **Expositor:** cadastra o stand, recebe um código secreto e acompanha visitantes, tempo de permanência e notas.
- **Divulgação:** após avaliar, o visitante cria um card com foto no próprio celular, compartilha nas redes e pode enviar uma mensagem para o mural público.

## Tecnologias

- Python + Flask no servidor
- HTML, CSS e JavaScript puros no navegador
- Arquivo `feira_tech.json` para persistência local

## Executar no Visual Studio Code

Abra o terminal na pasta `feira-tech` e execute:

```bash
python -m venv .venv
```

Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Linux/macOS:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Abra `http://localhost:5000` no navegador.

## Uso na rede local

O servidor aceita conexões de outros dispositivos na mesma rede Wi-Fi. Descubra o IP do computador e abra `http://IP-DO-COMPUTADOR:5000` nos celulares. Os QR Codes usarão automaticamente o endereço pelo qual o painel foi aberto; portanto, abra o painel pelo IP da rede antes de baixar os códigos.

## Dados e segurança

- O arquivo `feira_tech.json` é criado automaticamente na pasta do projeto.
- A gravação usa arquivo temporário e substituição atômica para reduzir risco de corrupção.
- O código secreto não é salvo diretamente: somente uma derivação criptográfica é armazenada.
- Faça cópias do JSON durante eventos longos.
- O bloqueio de avaliações repetidas identifica o navegador; limpar os dados do navegador permite uma nova avaliação.
- As fotos usadas nos cards sociais são processadas somente no navegador: não são enviadas nem gravadas no JSON.
- Mensagens do mural só ficam públicas depois da aprovação do expositor responsável.
- O número de compartilhamentos representa tentativas iniciadas; redes sociais não informam ao sistema se a publicação foi concluída.

## Rotas principais

- `/` — escolha de perfil e lista de stands
- `/visitar/<id>` — avaliação do visitante
- `/expositor` — cadastro ou entrada do expositor
- `/stand/<id>` — painel privado do stand