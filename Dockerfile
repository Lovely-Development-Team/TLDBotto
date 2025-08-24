FROM python:3.12-alpine
LABEL org.opencontainers.image.source=https://github.com/Lovely-Development-Team/TLDBotto

RUN apk add --no-cache gcc musl-dev git

COPY pyproject.toml .
COPY uv.lock .

RUN --mount=from=ghcr.io/astral-sh/uv,source=/uv,target=/bin/uv \
    uv sync --locked --compile-bytecode --no-dev

ARG bot_version
ENV TLDBOTTO_VERSION=$bot_version

COPY . .

CMD [ "python", "." ]
