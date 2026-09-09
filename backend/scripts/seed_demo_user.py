"""Crea o actualiza el usuario demo de la base SQLite local."""
import hashlib
import os
import sqlite3
import uuid
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent.parent / "cu002.db"
USERNAME = "demo"
PASSWORD = os.getenv("DEMO_USER_PASSWORD")


def main() -> None:
    if not PASSWORD:
        raise SystemExit("DEMO_USER_PASSWORD is required to seed the local demo user")

    connection = sqlite3.connect(DATABASE_PATH)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(64) PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                username_normalized VARCHAR(80) UNIQUE NOT NULL,
                email VARCHAR(200) NOT NULL,
                email_normalized VARCHAR(200) NOT NULL,
                password_hash VARCHAR(200) NOT NULL,
                nombre_completo VARCHAR(200) NOT NULL DEFAULT '',
                rol VARCHAR(32) NOT NULL DEFAULT 'socio',
                activo BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        password_hash = hashlib.sha256(PASSWORD.encode()).hexdigest()
        connection.execute(
            """
            INSERT INTO users (
                id, username, username_normalized, email, email_normalized,
                password_hash, nombre_completo, rol, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                email = excluded.email,
                email_normalized = excluded.email_normalized,
                password_hash = excluded.password_hash,
                nombre_completo = excluded.nombre_completo,
                rol = excluded.rol,
                activo = excluded.activo
            """,
            (
                str(uuid.uuid4()),
                USERNAME,
                USERNAME,
                "demo@local.test",
                "demo@local.test",
                password_hash,
                "Usuario Demo",
                "admin",
                True,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    print(f"Usuario demo listo en {DATABASE_PATH}: {USERNAME}")


if __name__ == "__main__":
    main()
