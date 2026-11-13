# GitHub Telegram Monitor

Serviço independente que recebe webhooks do GitHub e envia notificações de Pull Requests, reviews, comentários em PRs e execuções de workflow para um chat do Telegram.

O webhook é validado e gravado em uma fila persistente SQLite antes de a API responder. Um worker separado processa a fila e pode tentar novamente envios que falhem temporariamente. O projeto não depende do código-fonte do Chat Mia.

## Arquitetura

```text
GitHub
  │ HTTPS POST + HMAC SHA-256
  ▼
FastAPI ── valida assinatura, repositório, formato e X-GitHub-Delivery
  │ transação SQLite: registra a notificação antes de responder 202
  ▼
Fila persistente em SQLite ── deduplicação por delivery ID e controle de tentativas
  │
  ▼
Worker ── formata/envia mensagem HTML ── Telegram Bot API
```

O serviço é preparado para uma VM única e volume baixo/moderado. SQLite não é uma fila distribuída: mantenha o arquivo em disco local persistente e não escale os containers para hosts diferentes. O worker mantém o envio fora do caminho HTTP; Compose executa API e worker em processos separados, compartilhando o mesmo volume.

## Tecnologias

- Python 3.12 ou superior.
- FastAPI e Uvicorn para a API.
- Pydantic e pydantic-settings para validação e configuração.
- `aiosqlite` para operações SQLite assíncronas.
- `httpx` para a Telegram Bot API.
- pytest e Ruff para testes e qualidade.
- Docker Compose para execução em servidor.

As dependências e limites de versão estão em `pyproject.toml`.

## Eventos notificados

- `pull_request`: `opened`, `reopened`, `synchronize`, `ready_for_review`, `converted_to_draft`, `closed` e `edited` quando título ou descrição mudarem. Fechamento com `merged=true` é diferenciado de fechamento sem merge.
- `pull_request_review`: revisão submetida (`approved`, `changes_requested`, `commented`) ou descartada.
- `issue_comment`: somente comentários criados (`action=created`) em uma Issue que tenha o campo `pull_request`.
- `workflow_run`: `requested`, `in_progress` e `completed`, incluindo conclusões como `success`, `failure`, `cancelled`, `neutral`, `skipped`, `timed_out` e `action_required`.
- Tipos de evento e ações não suportados são registrados como `ignored`; não geram mensagem.

Campos externos são escapados antes de compor HTML. Links só são emitidos para `https://github.com`. O texto dos comentários é limitado; o banco guarda o texto da notificação até o envio.

## Requisitos

- Python 3.12+ para execução local; a imagem de produção usa Python 3.12.
- Docker Engine e Docker Compose para execução em container.
- Um bot do Telegram e um webhook configurado no GitHub.

## Configuração do Telegram

1. Crie um bot com o `@BotFather` no Telegram e guarde o token em local seguro.
2. Adicione o bot ao grupo/canal de destino e conceda a ele permissão para enviar mensagens.
3. Obtenha o `chat_id` da conversa usando a API `getUpdates` depois de enviar uma mensagem ao bot, ou por uma ferramenta confiável de administração. Grupos normalmente usam um identificador negativo; não confunda o `chat_id` com o ID de tópico.
4. Em supergrupos com tópicos, configure `TELEGRAM_MESSAGE_THREAD_ID` com o ID do tópico. Deixe vazio se não for necessário.

O token aparece na URL usada pela Bot API. Não compartilhe essa URL, não a salve em documentação e não a deixe em histórico de shell ou logs. Se o token for exposto, revogue-o no BotFather e gere outro.

## Configuração do webhook GitHub

1. Gere um segredo aleatório forte e configure o mesmo valor em `GITHUB_WEBHOOK_SECRET` e no campo **Secret** do webhook no GitHub. Por exemplo, para gerar um valor localmente:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. No repositório, abra **Settings → Webhooks → Add webhook**.
3. Configure como **Payload URL** o endpoint público HTTPS terminado em `/webhooks/github`; escolha `application/json`.
4. Selecione os eventos `Pull requests`, `Pull request reviews`, `Issue comments` e `Workflow runs`.
5. Habilite a verificação de certificado SSL e salve. O serviço aceita somente o repositório definido em `GITHUB_REPOSITORY`.

A assinatura `X-Hub-Signature-256` é validada sobre o corpo original. Uma assinatura inválida recebe `401`. Entregas repetidas com o mesmo `X-GitHub-Delivery` ou com o mesmo corpo não criam novo item; o hash do corpo também evita replay com um delivery ID alterado. O serviço não registra o payload bruto.

## Variáveis de ambiente

Copie `.env.example` para `.env` e preencha os valores:

| Variável | Obrigatória | Descrição |
| --- | --- | --- |
| `APP_ENV` | Não | `development`, `production` ou `test`. |
| `APP_HOST` / `APP_PORT` | Não | Host e porta locais; padrões `0.0.0.0` e `8000`. |
| `GITHUB_WEBHOOK_SECRET` | Sim | Segredo HMAC compartilhado com o webhook GitHub. |
| `GITHUB_REPOSITORY` | Não | Allowlist `owner/repository`; padrão `healthdevio/projeto-itia-dois`. |
| `TELEGRAM_BOT_TOKEN` | Sim | Token do bot. |
| `TELEGRAM_CHAT_ID` | Sim | ID do chat de destino. |
| `TELEGRAM_MESSAGE_THREAD_ID` | Não | ID do tópico em um supergrupo. |
| `DATABASE_PATH` | Não | Arquivo SQLite; padrão `data/events.sqlite3`. |
| `LOG_LEVEL` | Não | `DEBUG`, `INFO`, `WARNING`, `ERROR` ou `CRITICAL`. |
| `WEBHOOK_MAX_BODY_BYTES` | Não | Limite de payload, padrão 1 MiB. |
| `WORKER_POLL_INTERVAL_SECONDS` | Não | Intervalo de consulta da fila. |
| `WORKER_LEASE_SECONDS` | Não | Tempo para recuperar um item preso após queda do worker. |
| `WORKER_MAX_ATTEMPTS` | Não | Tentativas máximas de envio. |
| `WORKER_RETRY_BASE_SECONDS` | Não | Base do backoff exponencial. |
| `DEDUP_RETENTION_DAYS` | Não | Retenção de entregas concluídas/ignoradas; padrão 90 dias. |

As configurações obrigatórias são validadas na inicialização do processo correspondente: a API exige `GITHUB_WEBHOOK_SECRET`; o worker exige `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Valores secretos são mascarados pelo tipo `SecretStr`. No Compose, cada serviço recebe apenas os segredos de que precisa. Nunca versione `.env`.

## Execução local

No PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
# Edite .env e preencha os segredos e IDs.
python -m app
```

Em outro terminal, no mesmo ambiente e pasta:

```powershell
python -m app.worker
```

A API fica na porta configurada. O worker é um processo independente; se ele parar, os eventos aceitos continuam persistidos no SQLite. Em ambiente local, use um túnel HTTPS confiável para testar webhooks reais e remova o túnel depois do uso.

## Testes e lint

Os testes usam payloads locais, SQLite temporário e `httpx.MockTransport`; não enviam mensagens reais nem exigem acesso ao GitHub.

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

## Execução com Docker Compose

```powershell
Copy-Item .env.example .env
# Edite .env.
docker compose up -d --build
docker compose logs -f
```

O Compose mantém o SQLite em um volume nomeado e expõe a API somente em `127.0.0.1:8000`, adequada para um proxy reverso local. O worker não publica portas. A imagem roda como usuário não privilegiado, com filesystem raiz somente leitura e `/tmp` temporário.

Para parar sem remover o banco:

```powershell
docker compose down
```

Não use `docker compose down -v` se quiser preservar a fila e o histórico de deduplicação.

## Implantação em Linux/Oracle Cloud

- Configure DNS e HTTPS em um proxy reverso (por exemplo, Nginx ou Caddy) apontando para `127.0.0.1:8000`.
- Na Security List/NSG e no firewall do host, permita entrada somente em `443` (e `80` apenas se necessário para emissão/renovação do certificado). Não publique a porta 8000 diretamente na internet nem exponha o arquivo SQLite.
- Permita saída HTTPS para a Telegram Bot API.
- Restrinja permissões do `.env`, proteja o volume Docker e faça backup periódico do banco. O banco contém notificações e pode incluir trechos de comentários de PR.
- Monitore `docker compose ps`, `/health/ready`, o tamanho/idade dos itens pendentes e os logs JSON. A readiness verifica SQLite, não Telegram; uma falha no Telegram deve acumular fila, não derrubar a API.

## Endpoints

- `POST /webhooks/github`: valida assinatura, allowlist, formato e delivery ID; persiste o evento e responde `202`.
- `GET /health`: liveness simples.
- `GET /health/ready`: confirma que o SQLite está acessível.
- `GET /`: nome e versão do serviço.

Não há endpoints administrativos.

## Entrega, retries e limitações

- A API confirma somente depois da persistência. Se o banco não estiver disponível, retorna `503` para permitir nova tentativa do GitHub.
- O worker aplica backoff exponencial com jitter; em `429`, respeita `retry_after`. Erros permanentes ou após o limite ficam como `failed` para investigação manual.
- A fila oferece entrega **pelo menos uma vez**, não exatamente uma vez. Se o Telegram aceitar uma mensagem e a resposta se perder, uma nova tentativa pode gerar duplicata; a Bot API não fornece chave de idempotência para `sendMessage`.
- Entregas `sent` e `ignored` são removidas depois do período de retenção configurado. Registros `failed` são mantidos até intervenção.
- SQLite atende uma VM e volume limitado. Para múltiplas VMs ou alta concorrência, migre para um banco/fila distribuídos antes de escalar.
- O serviço não é considerado integrado até configurar credenciais, publicar o endpoint HTTPS e validar a entrega de um webhook real.
