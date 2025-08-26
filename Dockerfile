FROM python:3.12-alpine AS builder

RUN apk add --no-cache gcc musl-dev git

RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --compile-bytecode --no-dev

ARG bot_version
ENV TLDBOTTO_VERSION=$bot_version

COPY . .

RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
   uv sync --locked --compile-bytecode --no-dev

CMD [ ".venv/bin/python", "." ]