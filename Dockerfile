FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .

# Pakiety gcc i g++ sa potrzebne tylko podczas budowania zaleznosci.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ libmupdf-dev \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_lg \
    && apt-get purge -y --auto-remove gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Staly UID/GID ulatwia kontrolowanie uprawnien takze z Docker Compose.
RUN groupadd --gid 10001 presidio \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --no-create-home \
        --home-dir /nonexistent \
        --shell /usr/sbin/nologin \
        presidio

COPY --chown=root:root . .

# Slowniki powstaja na etapie budowania obrazu. Kod, konfiguracja i raport
# generatora pozostaja tylko do odczytu. Zapisywalna jest wylacznie baza runtime.
RUN python scripts/update_dictionaries.py \
    && mkdir -p /app/instance /app/data/reports /app/migrations \
    && chmod -R go-w /app \
    && chown -R presidio:presidio /app/instance \
    && chmod -R u=rwX,go= /app/instance

USER 10001:10001

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]