"""
FIL: app/database.py
FORMÅL: Alt der har med databasen at gøre — oprette forbindelse, oprette tabeller.

Når du præsenterer: "Her styrer vi databasen. Vi bruger SQLite lokalt,
men koden er skrevet så den nemt kan skifte til Azure SQL i produktion —
det kræver kun én linje i .env-filen."
"""

import os
import sqlite3
from contextlib import contextmanager
from dotenv import load_dotenv  # Læser værdier fra .env-filen

# Indlæs .env-filen så vi kan bruge dens værdier som miljøvariabler
load_dotenv()

# DB_PATH bestemmer hvor databasefilen ligger.
# Vi henter den fra miljøvariablerne — ALDRIG hardkodet.
# Lokalt: "voltedge.db" (en fil på computeren)
# Produktion: en Azure SQL connection string
DB_PATH = os.getenv("DB_PATH", "voltedge.db")


def get_connection() -> sqlite3.Connection:
    """
    Åbner en forbindelse til databasen.

    row_factory = sqlite3.Row betyder at vi kan tilgå kolonner ved navn
    i stedet for nummer — fx row["session_id"] i stedet for row[0].
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # WAL-mode giver bedre performance når flere brugere læser samtidig
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db():
    """
    Context manager til databaseforbindelser.

    'with db() as conn:' sikrer at forbindelsen altid lukkes bagefter —
    selv hvis der opstår en fejl. Det svarer til at bruge 'try/finally'
    uden at vi skal skrive det manuelt hver gang.

    Hvis noget går galt undervejs, rulles ændringerne tilbage (rollback),
    så databasen ikke ender i en inkonsistent tilstand.
    """
    conn = get_connection()
    try:
        yield conn          # Her kører den kode der er inde i 'with'-blokken
        conn.commit()       # Gem ændringerne permanent
    except Exception:
        conn.rollback()     # Noget gik galt — fortryd alle ændringer
        raise               # Send fejlen videre op til den der kaldte os
    finally:
        conn.close()        # Luk forbindelsen uanset hvad


def init_db():
    """
    Opretter databasetabellerne hvis de ikke allerede findes.

    Denne funktion kaldes automatisk når applikationen starter.
    'CREATE TABLE IF NOT EXISTS' betyder at den er sikker at kalde
    flere gange — den gør ingenting hvis tabellerne allerede findes.

    Vi opretter to tabeller som svarer til ER-diagrammet i rapporten:
      charging_sessions  — én række per ladesession
      session_events     — én række per hændelse (audit log)
    """
    with db() as conn:
        conn.executescript("""

            -- Tabel 1: charging_sessions
            -- Her gemmes én række for hver ladesession.
            -- session_id er PRIMARY KEY — det er det unikke ID (UUID).
            CREATE TABLE IF NOT EXISTS charging_sessions (
                session_id    TEXT PRIMARY KEY,   -- Unikt ID, fx "a3f9-..."
                charger_id    TEXT NOT NULL,       -- Hvilken ladestander, fx "CHR-01"
                customer_id   TEXT NOT NULL,       -- Hvilken kunde, fx "CUST-42"
                started_at    TEXT NOT NULL,       -- Starttidspunkt (ISO-format)
                ended_at      TEXT,                -- Sluttidspunkt (tomt indtil sessionen afsluttes)
                status        TEXT NOT NULL DEFAULT 'active',  -- 'active' eller 'completed'
                energy_kwh    REAL,                -- Energiforbrug i kWh
                amount        REAL,                -- Beregnet beløb i kr.
                load_signal   TEXT                 -- BOOST, NORMAL eller REDUCE
            );

            -- Tabel 2: session_events (audit log)
            -- Her gemmes én række for hver hændelse der sker i en session.
            -- Det er vores "uforanderlige log" — vi sletter aldrig herfra.
            -- FOREIGN KEY sikrer at vi ikke kan have events uden en tilhørende session.
            CREATE TABLE IF NOT EXISTS session_events (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,  -- Løbenummer
                session_id    TEXT NOT NULL,       -- Hvilken session hændelsen tilhører
                event_type    TEXT NOT NULL,       -- Fx "SessionStarted" eller "SessionCompleted"
                payload       TEXT NOT NULL,       -- Detaljer om hændelsen (JSON-format)
                created_at    TEXT NOT NULL DEFAULT (datetime('now')),  -- Tidsstempel
                FOREIGN KEY (session_id) REFERENCES charging_sessions(session_id)
            );
        """)
