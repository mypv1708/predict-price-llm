# Price Predict

Reads prices from Vietnamese shop messages. A session sends `system_prompt.txt` and `Dataset.csv` to Gemini, then later messages continue that conversation with `previous_interaction_id`.

## Docker

Install Docker Engine and the Compose plugin, then log in again so your user can run Docker:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
```

Copy `.env.example` to `.env`. Set `GEMINI_API_KEY`, `API_TOKEN`, `POSTGRES_PASSWORD`, and both database URLs. `DATABASE_URL` is for a process on the host. `DATABASE_URL_DOCKER` is for the API container. Encode `@` in a URL as `%40`. Compose publishes Postgres and the API on `127.0.0.1` only.

```bash
docker compose up --build -d
```

The API container runs `alembic upgrade head` before it starts. API: `http://127.0.0.1:8000`. Stop with `docker compose down`. `docker compose down -v` also deletes the database volume.

## Local

Requires Python 3.12, [uv](https://docs.astral.sh/uv/), and a reachable Postgres. `.env` needs `GEMINI_API_KEY`, `API_TOKEN`, and `DATABASE_URL`.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source "$HOME/.local/bin/env"
uv sync
uv run --env-file .env alembic upgrade head
uv run --env-file .env uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
```

## Migrations

Alembic owns the schema. After changing a model in `app/models`, generate and review a revision, then apply it:

```bash
uv run --env-file .env alembic revision --autogenerate -m "describe the change"
uv run --env-file .env alembic upgrade head
```

`alembic check` fails when the models and the database differ.

## Layout

| Path | Role |
| --- | --- |
| `app/main.py` | App factory, lifespan, CORS, error handler, routers |
| `app/core` | Settings from `.env`, bearer token check, body size limit, errors, logging |
| `app/db` | Declarative base and async engine |
| `app/models` | SQLAlchemy tables `sessions` and `llm_messages` |
| `app/schemas` | Pydantic request and response bodies |
| `app/repositories` | Database queries |
| `app/services` | Gemini client, session flow, price extraction |
| `app/api/routes` | HTTP endpoints |
| `alembic/versions` | Schema migrations |

## Gemini timeouts

`GEMINI_REQUEST_TIMEOUT_SECONDS` caps one call. `GEMINI_TOTAL_TIMEOUT_SECONDS` caps every retry and model fallback together; when it runs out the API returns `504`. The first turn of a session can fall back to `GEMINI_FALLBACK_MODELS`. Later turns stay on the session's model.

## API

Send `Authorization: Bearer <API_TOKEN>` on every `/sessions` request. `GET /health` needs no token.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/sessions` | Start a session from `Dataset.csv`, or from an uploaded CSV |
| `POST` | `/sessions/{session_id}/messages` | Send the next shop message. Returns `results`: each `price` with the `start` and `end` of its signal |
| `GET` | `/sessions/{session_id}` | Session record and stored turns |
| `GET` | `/sessions/{session_id}/messages` | Full transcript: `system`, `user`, `assistant` |
| `GET` | `/health` | Database reachability |

Two messages sent to one session at the same time cannot both continue the same Gemini turn. The one that finishes second gets `409`; send it again. Requests whose `Content-Length` exceeds `MAX_UPLOAD_BYTES` plus 64 KB get `413` before the body is read.

`start` and `end` are Unicode code point offsets with `end` exclusive, so `message[start:end]` in Python is the signal. In JavaScript use `Array.from(message).slice(start, end)`, because string indexes there count UTF-16 units and styled letters such as `𝙎` take two. Both are `null` when the signal is not in the message.

```json
{
  "session_id": "edd58a2324d74dc8abbf5ec3d7503259",
  "results": [{ "price": "310k", "start": 31, "end": 40 }]
}
```

Interactive docs: `/docs`.
