"""Upsert synthetic procedures using the same normalized hashing features as offline search."""

import os
from pathlib import Path

import psycopg

from .rag import VECTOR, documents


def main() -> None:
    docs = documents(Path("data/synthetic_docs"))
    vectors = VECTOR.transform([doc["text"] for doc in docs]).toarray()
    with psycopg.connect(os.environ["PROCEDURE_DATABASE_URL"]) as db:
        db.execute("CREATE EXTENSION IF NOT EXISTS vector")
        db.execute("""CREATE TABLE IF NOT EXISTS procedures (
            id text PRIMARY KEY,title text NOT NULL,body text NOT NULL,embedding vector(512) NOT NULL)""")
        for doc, vector in zip(docs, vectors, strict=True):
            literal = "[" + ",".join(map(str, vector)) + "]"
            db.execute(
                """INSERT INTO procedures VALUES (%s,%s,%s,%s::vector)
                          ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                          body=excluded.body,embedding=excluded.embedding""",
                (doc["id"], doc["title"], doc["text"], literal),
            )
    print(f"Indexed {len(docs)} synthetic procedures")


if __name__ == "__main__":
    main()
