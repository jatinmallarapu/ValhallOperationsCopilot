"""Retrieve explicitly synthetic procedures with a reproducible shared vector representation."""

import re
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from .models import Route

# A fixed hash vocabulary allows local and pgvector indexes to use identical embeddings.
VECTOR = HashingVectorizer(n_features=512, alternate_sign=False, norm="l2", stop_words="english")


def documents(root: Path) -> list[dict]:
    return [
        {
            "id": path.stem,
            "title": path.read_text(encoding="utf-8").splitlines()[0].lstrip("# "),
            "text": path.read_text(encoding="utf-8"),
        }
        for path in sorted(root.glob("*.md"))
    ]


def search_docs(question: str, docs: list[dict], dsn: str | None = None) -> list[dict]:
    query = VECTOR.transform([question]).toarray()[0]
    if not np.any(query):
        return []
    if dsn:
        import psycopg

        # pgvector stores local lexical vectors. This path makes no external embedding call.
        literal = "[" + ",".join(map(str, query)) + "]"
        with psycopg.connect(dsn, connect_timeout=5) as db:
            rows = db.execute(
                """SELECT id,title,body,1-(embedding <=> %s::vector) AS similarity
                   FROM procedures WHERE (embedding <=> %s::vector) < 0.95
                   ORDER BY embedding <=> %s::vector,id LIMIT 3""",
                (literal, literal, literal),
            ).fetchall()
        return [
            {"id": row[0], "title": row[1], "text": row[2], "similarity": row[3]} for row in rows
        ]
    if not docs:
        return []
    scores = VECTOR.transform([doc["text"] for doc in docs]).toarray() @ query
    order = sorted(range(len(docs)), key=lambda index: (-scores[index], docs[index]["id"]))
    return [
        {**docs[index], "similarity": float(scores[index])}
        for index in order[:3]
        if scores[index] > 0.05
    ]


def choose_route(question: str) -> Route:
    lower = question.casefold()
    if re.search(
        r"\b(procedures?|manuals?|instructions?|alarms?|checklists?|maintenance|steps|documents?)\b",
        lower,
    ):
        return "docs"
    if re.search(r"\b(health|summary|summarize|executive|overview|vp|report)\b", lower):
        return "report"
    if re.search(
        r"\b(spike|spikes|pressure|temperature|vibration|flow|trend|anomalies|unusual|average|maximum|minimum|datapoints|statistics)\b",
        lower,
    ):
        return "timeseries"
    return "assets"
