# VoltEdge MVP — Smart Charging Platform

> Teknisk MVP til 6. semester eksamensprojekt.
> Demonstrerer Smart Charging-domænet fra rapporten i en fungerende løsning.

---

## Hvad løsningen gør

| Trin | Handling | Kobling til rapporten |
|------|----------|----------------------|
| 1 | Ladestander starter session via `POST /sessions` | Afsnit 3.1 — Event: `SessionStarted` |
| 2 | Smart Charging domain service beregner styresignal | Afsnit 4.2 + 8 — `calculate_load_signal()` |
| 3 | Session afsluttes og billing beregnes automatisk | Afsnit 4.2 — `BillingLine` value object |
| 4 | Alle hændelser logges som domain events | Afsnit 6.1 — `session_events` audit log |
| 5 | Data tilgængeligt via analytics-endpoint | Afsnit 6.3 — Deskriptiv analyse |

---

## Krav

- Python 3.11+
- **eller** Docker + Docker Compose

---

## Kom hurtigt i gang

### Mulighed A — Python lokalt

```bash
# 1. Klon repo
git clone https://github.com/<dit-brugernavn>/voltedge-mvp.git
cd voltedge-mvp

# 2. Sæt secrets op (kopier .env.example)
cp .env.example .env
# Rediger .env om nødvendigt

# 3. Installer afhængigheder
pip install -r requirements.txt

# 4. Start API
uvicorn app.main:app --reload

# API kører nu på http://localhost:8000
# Dokumentation:  http://localhost:8000/docs
```

### Mulighed B — Docker Compose

```bash
cp .env.example .env
docker compose up --build
# API kører på http://localhost:8000
```

---

## Kør tests

```bash
pytest tests/ -v
```

Forventet output:

```
tests/test_smart_charging.py::TestSmartChargingDomainService::test_peak_high_load_returns_reduce PASSED
tests/test_smart_charging.py::TestSmartChargingDomainService::test_peak_low_load_returns_normal  PASSED
tests/test_smart_charging.py::TestSmartChargingDomainService::test_off_peak_returns_boost        PASSED
...
tests/test_api.py::test_health_returns_ok                  PASSED
tests/test_api.py::test_start_session_returns_201          PASSED
tests/test_api.py::test_complete_session_calculates_billing PASSED
...
```

---

## API-oversigt

| Method | Endpoint | Beskrivelse |
|--------|----------|-------------|
| `POST` | `/sessions` | Start ladesession |
| `POST` | `/sessions/{id}/complete` | Afslut + billing + smart charging |
| `GET`  | `/sessions/{id}` | Hent sessionstatus |
| `GET`  | `/analytics/summary` | Deskriptiv analyse (afsnit 6.3) |
| `GET`  | `/health` | Driftsstatus (afsnit 5.4) |
| `GET`  | `/docs` | Automatisk OpenAPI-dokumentation |

### Eksempel: Start og afslut en session

```bash
# Start session
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{"charger_id": "CHR-01", "customer_id": "CUST-42"}'

# Afslut session (erstat SESSION_ID)
curl -X POST http://localhost:8000/sessions/SESSION_ID/complete \
  -H "Content-Type: application/json" \
  -d '{"energy_kwh": 25.0}'

# Hent analyse
curl http://localhost:8000/analytics/summary
```

---

## Projektstruktur

```
voltedge-mvp/
├── app/
│   ├── main.py              # FastAPI routes + logging
│   ├── database.py          # SQLite — kan byttes med Azure SQL
│   └── domain/
│       ├── models.py        # ChargingSession (Aggregate Root), EnergyAmount, BillingLine
│       └── smart_charging.py # Domain Service: calculate_load_signal()
├── tests/
│   ├── test_smart_charging.py  # Unit tests (7 cases)
│   └── test_api.py             # API-tests (7 cases)
├── .github/workflows/ci.yml    # GitHub Actions CI/CD
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## DDD-objekter i koden

| DDD-begreb | Implementering | Fil |
|------------|---------------|-----|
| Aggregate Root | `ChargingSession` | `app/domain/models.py` |
| Value Object | `EnergyAmount`, `BillingLine` | `app/domain/models.py` |
| Domain Event | `SessionStarted`, `SessionCompleted` | `app/database.py` + `app/main.py` |
| Domain Service | `calculate_load_signal()` | `app/domain/smart_charging.py` |

---

## Smart Charging-logik

```
REDUCE  →  peak-tidspunkt (07-09 / 17-19)  OG  forbrug > 20 kWh
NORMAL  →  peak-tidspunkt                  OG  forbrug ≤ 20 kWh
BOOST   →  off-peak (al anden tid)
```

---

## CI/CD — GitHub Actions

Pipeline køres automatisk ved hvert push:

1. **Secret scan** (Gitleaks) — stoppes ved fund af hardkodede secrets
2. **Tests** — pytest køres med in-memory SQLite
3. **Docker build** — image bygges og smoke-testes

Secrets håndteres via GitHub Secrets i CI og `.env`-fil lokalt.
`.env` er i `.gitignore` og committes **aldrig**.

---

## Afgrænsninger i forhold til rapporten

Disse elementer er beskrevet i rapporten men ikke implementeret i MVP:

| Element fra rapporten | Begrundelse for afgrænsning |
|-----------------------|-----------------------------|
| Azure Event Hubs (messaging) | Kræver Azure-abonnement; SQLite event-log demonstrerer princippet |
| Azure SQL / Azure App Service | Erstattes af SQLite + lokal Docker for kørbarhed |
| Power BI-dashboards | Rapporten anvender dummy-data; `/analytics/summary` leverer samme metrics via API |
| Token-baseret autentificering (API Management) | Scope-mæssig afgrænsning; struktur er klar til udvidelse |
| Prædiktiv analyse / ML | Kræver historisk datasæt; deskriptiv analyse er implementeret |
| Azure Monitor | Erstattes af struktureret Python-logging lokalt |

---

## Teknisk stack

| Komponent | Teknologi | Begrundelse |
|-----------|-----------|-------------|
| API-framework | FastAPI | Asynkront, høj ydeevne, automatisk OpenAPI-docs |
| Database | SQLite (→ Azure SQL i prod) | Nul opsætning lokalt; samme interface i produktion |
| Container | Docker + Compose | Miljøuafhængig deployment |
| CI/CD | GitHub Actions | Integreret med versionsstyring |
| Secrets | `.env` lokalt / GitHub Secrets i CI | Shift-left sikkerhed (afsnit 5.2) |
