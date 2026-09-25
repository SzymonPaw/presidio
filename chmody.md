## Uprawnienia plików na Ubuntu Server

Poniższe polecenia zakładają, że:

- aplikacja znajduje się w `/opt/bezsladu`;
- działa jako użytkownik i grupa `www-data`;
- `scripts/setup_ubuntu.sh` został już uruchomiony;
- katalog `.venv` i słowniki zostały już wygenerowane.

## 1. Użytkownik aplikacji

Jeżeli użytkownik jeszcze nie istnieje:

```bash
sudo useradd --system \
    --no-create-home \
    --home-dir /nonexistent \
    --shell /usr/sbin/nologin \
    www-data
```

## 2. Właściciel kodu

Kod i środowisko wirtualne powinny należeć do `root`, a grupa `www-data`
powinna mieć możliwość ich odczytu i uruchamiania:

```bash
sudo chown -R root:www-data /opt/bezsladu
```

## 3. Katalogi i zwykłe pliki

Katalogi otrzymują `750`, a zwykłe pliki `640`:

```bash
sudo find /opt/bezsladu -type d -exec chmod 750 {} \;
sudo find /opt/bezsladu -type f -exec chmod 640 {} \;
```

Znaczenie:

- właściciel `root` ma pełny dostęp;
- grupa `www-data` może odczytywać pliki i wchodzić do katalogów;
- pozostali użytkownicy nie mają dostępu.

## 4. Skrypty i programy w `.venv`

Skrypty startowe oraz pliki wykonywalne środowiska wirtualnego muszą mieć
prawo wykonania:

```bash
sudo chmod 750 /opt/bezsladu/scripts/setup_ubuntu.sh
sudo chmod 750 /opt/bezsladu/scripts/run_ubuntu.sh
sudo find /opt/bezsladu/.venv/bin -type f -exec chmod 750 {} \;
```

## 5. Plik `.env`

Plik z sekretami powinien być dostępny wyłącznie dla `root` i grupy
uruchamiającej aplikację:

```bash
sudo chown root:www-data /opt/bezsladu/.env
sudo chmod 640 /opt/bezsladu/.env
```

Wartość `ADMIN_PASSWORD_HASH` powinna pozostać ujęta w pojedyncze apostrofy,
ponieważ hash może zawierać znak `$`.

## 6. Katalog bazy SQLite

Proces aplikacji musi mieć możliwość tworzenia i modyfikowania bazy w
`instance/metrics.sqlite3`. Tylko ten katalog powinien należeć do użytkownika
aplikacji:

```bash
sudo mkdir -p /opt/bezsladu/instance
sudo chown -R www-data:www-data /opt/bezsladu/instance
sudo chmod 750 /opt/bezsladu/instance
sudo find /opt/bezsladu/instance -type f -exec chmod 640 {} \;
```

Konfiguracja odpowiadająca tej lokalizacji:

```dotenv
DATABASE_URL=sqlite:///instance/metrics.sqlite3
```

Skrypt `run_ubuntu.sh` przechodzi przed startem do `/opt/bezsladu`, dlatego
ścieżka względna wskazuje właściwy plik.

## 7. Uruchomienie

Aplikację można uruchomić jako użytkownik `www-data`:

```bash
sudo -u www-data /opt/bezsladu/scripts/run_ubuntu.sh
```

Gunicorn nasłuchuje wyłącznie na `127.0.0.1:5000`. Nie należy otwierać portu
`5000` w firewallu — dostęp użytkowników powinien prowadzić przez Nginx.
