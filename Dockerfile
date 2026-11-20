FROM python:3.12-slim

# uv本体を公式イメージからコピーする（慣れたら :latest をバージョン番号に固定する）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 1. 依存だけ先に入れる（コードを変えてもこの層は再利用される）
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

# 2. アプリのコードを入れる
COPY . .
RUN uv sync --locked --no-dev

# 仮想環境のコマンドをそのまま使えるようにする
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]