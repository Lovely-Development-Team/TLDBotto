FROM python:3.9-alpine
LABEL org.opencontainers.image.source=https://github.com/Lovely-Development-Team/TLDBotto

RUN apk add --no-cache gcc musl-dev

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "." ]
