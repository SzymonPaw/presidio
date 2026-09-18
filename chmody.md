# Uprawnienia plików na Ubuntu Server

Poniższe polecenia zakładają, że:

- aplikacja znajduje się w `/opt/presidio`;
- działa jako użytkownik i grupa `presidio`;
- `scripts/setup_ubuntu.sh` został już uruchomiony;
- katalog `.venv` i słowniki zostały już wygenerowane.

## 1. Użytkownik aplikacji

Jeżeli użytkownik jeszcze nie istnieje:

```bash
sudo useradd --system \
    --no-create-home \
    --home-dir /nonexistent \
    --shell /usr/sbin/nologin \
    presidio
```

## 2. Właściciel kodu

Kod i środowisko wirtualne powinny należeć do `root`, a grupa `presidio`
powinna mieć możliwość ich odczytu i uruchamiania:

```bash
sudo chown -R root:presidio /opt/presidio
```

## 3. Katalogi i zwykłe pliki

Katalogi otrzymują `750`, a zwykłe pliki `640`:

```bash
sudo find /opt/presidio -type d -exec chmod 750 {} \;
sudo find /opt/presidio -type f -exec chmod 640 {} \;
```

Znaczenie:

- właściciel `root` ma pełny dostęp;
- grupa `presidio` może odczytywać pliki i wchodzić do katalogów;
- pozostali użytkownicy nie mają dostępu.

## 4. Skrypty i programy w `.venv`

Skrypty startowe oraz pliki wykonywalne środowiska wirtualnego muszą mieć
prawo wykonania:

```bash
sudo chmod 750 /opt/presidio/scripts/setup_ubuntu.sh
sudo chmod 750 /opt/presidio/scripts/run_ubuntu.sh
sudo find /opt/presidio/.venv/bin -type f -exec chmod 750 {} \;
```

## 5. Plik `.env`

Plik z sekretami powinien być dostępny wyłącznie dla `root` i grupy
uruchamiającej aplikację:

```bash
sudo chown root:presidio /opt/presidio/.env
sudo chmod 640 /opt/presidio/.env
```

Wartość `ADMIN_PASSWORD_HASH` powinna pozostać ujęta w pojedyncze apostrofy,
ponieważ hash może zawierać znak `$`.

## 6. Katalog bazy SQLite

Proces aplikacji musi mieć możliwość tworzenia i modyfikowania bazy w
`instance/metrics.sqlite3`. Tylko ten katalog powinien należeć do użytkownika
aplikacji:

```bash
sudo mkdir -p /opt/presidio/instance
sudo chown -R presidio:presidio /opt/presidio/instance
sudo chmod 750 /opt/presidio/instance
sudo find /opt/presidio/instance -type f -exec chmod 640 {} \;
```

Konfiguracja odpowiadająca tej lokalizacji:

```dotenv
DATABASE_URL=sqlite:///instance/metrics.sqlite3
```

Skrypt `run_ubuntu.sh` przechodzi przed startem do `/opt/presidio`, dlatego
ścieżka względna wskazuje właściwy plik.

## 7. Uruchomienie

Aplikację można uruchomić jako użytkownik `presidio`:

```bash
sudo -u presidio /opt/presidio/scripts/run_ubuntu.sh
```

Gunicorn nasłuchuje wyłącznie na `127.0.0.1:5000`. Nie należy otwierać portu
`5000` w firewallu — dostęp użytkowników powinien prowadzić przez Nginx.
