# sendNewOfClub

Automação diária que coleta notícias do Atlético Mineiro no YouTube e no X/Twitter, resume com Gemini e entrega um relatório (MVP: console, simulando WhatsApp).

## Arquitetura

```
config/sources.yaml  →  Collectors (YouTube + X)  →  SQLite dedup  →  Gemini  →  Console
```

## Pré-requisitos

- Python 3.11+ (twikit exige 3.10+)
- Chave da [YouTube Data API v3](https://console.cloud.google.com/)
- Chave do [Google AI Studio (Gemini)](https://aistudio.google.com)

## Setup local

```bash
cd sendNewOfClub
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Preencha o `.env`:

```env
YOUTUBE_API_KEY=sua_chave_youtube
GEMINI_API_KEY=sua_chave_gemini
```

## Configurar fontes

Edite [`config/sources.yaml`](config/sources.yaml) com os canais e perfis que deseja monitorar:

```yaml
youtube:
  lookback_hours: 24
  channels:
    - handle: "@canaldofrossard"   # handle do YouTube (com ou sem @)
      name: "Canal do Frossard"
    - handle: "@LucasTanaka13"
      name: "Lucas Tanaka"

twitter:
  lookback_hours: 24
  profiles:
    - username: "Atletico"
      display_name: "Atlético Mineiro Oficial"
```

Você pode usar **`handle`** (ex.: `@canaldofrossard`) ou **`id`** (Channel ID `UC...`). Se usar handle, o sistema resolve o ID automaticamente via YouTube API.

### Como obter o handle ou Channel ID

- **Handle:** está na URL do canal — `https://www.youtube.com/@canaldofrossard` → `@canaldofrossard`
- **Channel ID:** canal → **Sobre** → **Compartilhar canal** → **Copiar ID do canal**

## Executar manualmente

```bash
source .venv/bin/activate
python -m src.main
```

Com config alternativo:

```bash
python -m src.main config/sources.yaml
```

## Agendamento diário (cron no macOS)

```bash
mkdir -p logs
crontab -e
```

Adicione (ajuste o horário conforme seu fuso):

```cron
0 8 * * * cd /Users/marcotuliovilacadiniz/sendNewOfClub && .venv/bin/python -m src.main >> logs/cron.log 2>&1
```

## Obtenção de API keys

### YouTube Data API v3

1. Acesse [Google Cloud Console](https://console.cloud.google.com/)
2. Crie um projeto (ou use um existente)
3. Ative **YouTube Data API v3**
4. Em **Credenciais**, crie uma **Chave de API**
5. Cole em `YOUTUBE_API_KEY` no `.env`

Quota gratuita: 10.000 unidades/dia (suficiente para ~10 canais × 1 execução/dia).

### Gemini

1. Acesse [Google AI Studio](https://aistudio.google.com)
2. Clique em **Get API key**
3. Cole em `GEMINI_API_KEY` no `.env`

Free tier: ~1.500 requisições/dia com `gemini-2.0-flash`.

## X/Twitter (sem API paga)

O collector usa [twikit](https://github.com/d60/twikit) com `GuestClient` para perfis públicos configurados em `sources.yaml`. Não exige API key, mas pode ser instável se o X alterar suas defesas anti-bot.

## Estrutura do projeto

```
sendNewOfClub/
├── config/sources.yaml       # canais YT + perfis X
├── src/
│   ├── main.py               # orquestrador
│   ├── config_loader.py      # leitura do YAML
│   ├── collectors/           # YouTube + Twitter
│   ├── ai/                   # prompts + Gemini
│   ├── delivery/             # console (WhatsApp na fase 2)
│   └── storage/              # dedup SQLite
├── data/state.db             # gerado automaticamente
├── .env.example
└── requirements.txt
```

## Próximas fases

- **Fase 2:** fallback RSS (Google News), transcrições YouTube, WhatsApp via Evolution API
- **Fase 3:** GitHub Actions schedule, dashboard Streamlit para editar fontes

## Licença

MIT
