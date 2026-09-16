"""Importa os dados existentes do feira_tech.json para o Postgres. Rodar UMA VEZ.

Uso:
    DATABASE_URL="postgresql://...url-externa-do-render..." python migrar_json_para_postgres.py feira_tech.json
"""

import json
import os
import sys

import psycopg2

# Garante que as tabelas já existem antes de inserir.
import db_store  # noqa: F401  (import só para rodar o init_db() do módulo)

JSON_PATH = sys.argv[1] if len(sys.argv) > 1 else "feira_tech.json"

DATABASE_URL = os.environ["DATABASE_URL"]
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

with open(JSON_PATH, "r", encoding="utf-8") as file:
    data = json.load(file)

conn = psycopg2.connect(DATABASE_URL, sslmode="require")
cur = conn.cursor()

for stand in data.get("stands", []):
    cur.execute(
        """
        INSERT INTO stands (id, name, name_normalized, course, code_salt, code_hash, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            stand["id"],
            stand["name"],
            " ".join(stand["name"].split()).casefold(),
            stand["course"],
            stand["code_salt"],
            stand["code_hash"],
            stand["created_at"],
        ),
    )

for visita in data.get("visitas", []):
    cur.execute(
        """
        INSERT INTO visitas
            (id, stand_id, stand_nome, curso, visitor_hash, started_at, finished_at, duration_seconds, stars)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            visita["id"],
            visita["stand_id"],
            visita["stand_nome"],
            visita["curso"],
            visita["visitor_hash"],
            visita["started_at"],
            visita.get("finished_at"),
            visita.get("duration_seconds"),
            visita.get("stars"),
        ),
    )

for eng in data.get("engajamentos", []):
    cur.execute(
        """
        INSERT INTO engajamentos
            (id, stand_id, stand_nome, visitor_hash, type, message, stars, status, created_at, moderated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
        """,
        (
            eng["id"],
            eng["stand_id"],
            eng["stand_nome"],
            eng["visitor_hash"],
            eng["type"],
            eng.get("message"),
            eng.get("stars"),
            eng.get("status"),
            eng["created_at"],
            eng.get("moderated_at"),
        ),
    )

conn.commit()
cur.close()
conn.close()
print(
    f"Importação concluída: {len(data.get('stands', []))} stands, "
    f"{len(data.get('visitas', []))} visitas, {len(data.get('engajamentos', []))} engajamentos."
)
