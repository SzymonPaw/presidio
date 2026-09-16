FROM python:3.11-slim

WORKDIR /app

# Zależności systemowe dla lxml, PyMuPDF i narzędzi kompilacji
RUN apt-get update && apt-get install -y gcc g++ libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Wymagane przez presidio-analyzer (domyślnie angielski, zmień w razie potrzeby)
RUN python -m spacy download en_core_web_lg

COPY . .

EXPOSE 5000

# Uruchomienie przez Gunicorn (zmień "app:app" na odpowiednią nazwę pliku i instancji)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]