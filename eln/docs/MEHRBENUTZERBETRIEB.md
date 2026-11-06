# Vorbereitung auf Mehrbenutzerbetrieb im Firmennetz

Die erste Version läuft lokal mit SQLite. Für den Betrieb durch mehrere Anwender im Firmennetz sind die folgenden
Schritte vorgesehen. Die Anwendung ist bereits darauf ausgelegt (SQLAlchemy, Alembic, Konfiguration über `.env`,
serverseitige Sitzungen, keine lokalen Pfade in der Datenbank).

## 1. Risiken von SQLite bei gleichzeitigem Zugriff

- SQLite erlaubt **nur einen Schreiber gleichzeitig**. Im lokalen Betrieb mit WAL-Modus und `busy_timeout` ist das
  für wenige Benutzer unproblematisch.
- **Eine SQLite-Datei auf einem Netzlaufwerk (SMB) darf nicht von mehreren Rechnern gleichzeitig geöffnet werden.**
  Dateisperren über SMB sind unzuverlässig; es drohen Sperrfehler und Datenbankbeschädigung. Der WAL-Modus
  funktioniert auf Netzlaufwerken grundsätzlich nicht.
- Die Anwendung bietet deshalb **keinen** „Mehrbenutzerbetrieb mit gemeinsamer SQLite-Datei“ an.
- Zulässig ist: **ein** Server-PC betreibt das ELN mit lokaler SQLite-Datei, die anderen Benutzer greifen per Browser
  zu (siehe Abschnitt 4). Für mehr als ca. 5–10 gleichzeitig schreibende Benutzer wird PostgreSQL empfohlen.

## 2. Umstieg auf PostgreSQL oder Microsoft SQL Server

1. Datenbank und technischen Benutzer anlegen (DBA).
2. Treiber in die virtuelle Umgebung installieren:
   - PostgreSQL: `pip install "psycopg[binary]>=3.1"`
   - SQL Server: `pip install pyodbc` und „ODBC Driver 18 for SQL Server“ installieren
3. In `.env` setzen (Zugangsdaten nur dort bzw. als Umgebungsvariable, nie im Quellcode):
   ```
   ELN_DATABASE_URL=postgresql+psycopg://eln_app:GEHEIM@dbserver:5432/eln
   ELN_DATABASE_URL=mssql+pyodbc://eln_app:GEHEIM@dbserver/eln?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes
   ```
4. `python manage.py migrate` legt das Schema über die Alembic-Migrationen an.
5. Daten übernehmen: JSON-Export je Datensatztyp aus der alten Installation und Import in die neue, oder mit einem
   Migrationsskript per SQLAlchemy (Tabelle für Tabelle, gleiche Modelle). Anhänge: Ordner `files` kopieren
   (Pfade in der Datenbank sind relativ).
6. Notwendige Anpassungen im Code:
   - **Audit-Trail-Schutz:** Die Trigger gegen UPDATE/DELETE sind für SQLite implementiert. Für PostgreSQL eine
     Migration ergänzen (`CREATE RULE`/`BEFORE UPDATE`-Trigger mit `RAISE EXCEPTION`) bzw. für SQL Server
     `INSTEAD OF UPDATE, DELETE`-Trigger; zusätzlich dem Anwendungsbenutzer `UPDATE/DELETE` auf `audit_log` entziehen.
   - **Datensicherung:** `services/backup.py` sichert SQLite-Dateien. Für Datenbankserver die Sicherung über
     `pg_dump` bzw. SQL-Server-Agent einrichten; die Dateiablage weiterhin mit der ELN-Sicherung (oder Dateisicherung).
   - **Suche:** optional Volltextindex (PostgreSQL `tsvector`/GIN, SQL Server Full-Text) in `services/search.py`.
   - **Nummernkreise:** `services/numbering.py` arbeitet mit `UPDATE … SET value = value + 1` innerhalb der Transaktion
     und ist damit auch auf Datenbankservern atomar.
   - Groß-/Kleinschreibung: `ilike` wird von SQLAlchemy für alle Datenbanken passend übersetzt.

## 3. Dateien auf einem Netzlaufwerk

- `ELN_FILES_DIR=\\fileserver\eln$\files` (UNC-Pfad) oder ein Laufwerksbuchstabe, der für das Dienstkonto
  verfügbar ist. Nur das Dienstkonto des ELN-Servers erhält Schreibrechte; Benutzer greifen ausschließlich über
  das ELN zu (sonst ist die Nachvollziehbarkeit nicht gegeben).
- Die Datenbank (SQLite) bleibt lokal auf dem Server-PC; nur die Dateiablage liegt im Netz.
- `ELN_BACKUP_DIR` auf ein anderes Ziel als die Dateiablage legen.

## 4. Betrieb als Windows-Dienst

Empfohlen mit [NSSM](https://nssm.cc) oder WinSW:
```bat
nssm install ELN "C:\ELN\eln\.venv\Scripts\python.exe" "C:\ELN\eln\manage.py run --no-browser"
nssm set ELN AppDirectory C:\ELN\eln
nssm set ELN AppEnvironmentExtra ELN_HOST=0.0.0.0 PYTHONUTF8=1
nssm set ELN ObjectName ".\svc-eln" "PASSWORT"
nssm start ELN
```
- Ein eigenes Dienstkonto mit Rechten nur auf Programm-, Daten- und Sicherungsordner verwenden.
- `ELN_HOST=0.0.0.0` macht die Anwendung im Netz erreichbar – **nur hinter HTTPS** (Abschnitt 5) und Firewall.
- Sicherung per Aufgabenplanung (`backup.bat`) weiterhin täglich.

## 5. HTTPS und Reverse Proxy

Die Anwendung selbst spricht HTTP auf `127.0.0.1:8000`. Ein Reverse Proxy terminiert TLS:

**IIS** (mit URL Rewrite + ARR): Website mit Firmenzertifikat, Regel „Reverse Proxy“ auf `http://127.0.0.1:8000`,
`X-Forwarded-For` weiterreichen.

**Caddy** (einfachste Variante):
```
eln.firma.local {
    tls C:\certs\eln.crt C:\certs\eln.key
    reverse_proxy 127.0.0.1:8000
    request_body { max_size 110MB }
}
```
**nginx:**
```
server {
  listen 443 ssl; server_name eln.firma.local;
  ssl_certificate eln.crt; ssl_certificate_key eln.key;
  client_max_body_size 110m;
  location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host;
               proxy_set_header X-Forwarded-For $remote_addr; proxy_set_header X-Forwarded-Proto https; }
}
```
Danach in `.env`: `ELN_COOKIE_SECURE=1`. Für korrekte Client-IP im Audit Trail uvicorn mit
`proxy_headers=True` und `forwarded_allow_ips="127.0.0.1"` starten (in `manage.py cmd_run` anpassen).

## 6. Anmeldung über Microsoft Entra ID (später)

Vorgesehener Weg: OpenID Connect (Authorization Code Flow mit PKCE).
1. App-Registrierung in Entra ID, Redirect-URI `https://eln.firma.local/auth/callback`, Gruppen-Claims aktivieren.
2. Paket `authlib` oder `msal` ergänzen; neue Routen `/auth/login` und `/auth/callback` in `app/web/auth_views.py`.
3. Nach erfolgreicher Anmeldung: Benutzer per `oid`/`preferred_username` in `users` suchen oder anlegen
   (`password_hash` = nicht nutzbarer Zufallswert), Rollen aus Entra-Gruppen abbilden (Konfigurationstabelle
   Gruppe → Rolle), anschließend wie bisher `auth.start_session()` aufrufen.
4. Sitzungen, CSRF, Rechte und Audit Trail bleiben unverändert; die lokale Anmeldung kann als Notfallzugang für
   Administratoren bestehen bleiben.
5. Client-Secret bzw. Zertifikat ausschließlich in `.env`/Windows-Anmeldeinformationen speichern.
