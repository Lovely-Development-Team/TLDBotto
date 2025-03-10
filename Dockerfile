FROM python:3.12-alpine
LABEL org.opencontainers.image.source=https://github.com/Lovely-Development-Team/TLDBotto

RUN apk add --no-cache gcc musl-dev git

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

ARG bot_version
ENV TLDBOTTO_VERSION=$bot_version

COPY . .

CMD [ "python", "." ]
