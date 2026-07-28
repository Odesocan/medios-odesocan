#!/usr/bin/env python3
"""
Construye agregados de word cloud a partir de noticias almacenadas en Supabase.

Fuente esperada por fila:
- id
- medio
- fecha
- temas (array o string separada por comas)
- titulo
- resumen
- contenido_limpio

Destino:
- tabla wordcloud_terms con agregados por:
  - global
  - medio
  - tema
  - medio + tema
"""

from __future__ import annotations

import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Sequence, Tuple

from supabase import Client, create_client


SOURCE_SCHEMA = os.getenv("SUPABASE_SOURCE_SCHEMA", "medios")
SOURCE_TABLE = os.getenv("SUPABASE_SOURCE_TABLE", "noticias")
TARGET_SCHEMA = os.getenv("SUPABASE_TARGET_SCHEMA", "medios")
TARGET_TABLE = os.getenv("SUPABASE_TARGET_TABLE", "wordcloud_terms")

MAX_TERMS_PER_SCOPE = int(os.getenv("WORDCLOUD_MAX_TERMS", "80"))
MIN_DOC_FREQ = int(os.getenv("WORDCLOUD_MIN_DOC_FREQ", "2"))
BATCH_SIZE = int(os.getenv("SUPABASE_BATCH_SIZE", "1000"))
UPSERT_CHUNK_SIZE = int(os.getenv("WORDCLOUD_UPSERT_CHUNK_SIZE", "500"))

SOURCE_COLUMNS = [
    "id",
    "fecha",
    "medio",
    "temas",
    "titulo",
    "resumen",
    "contenido_limpio",
]

FIELD_WEIGHTS = {
    "titulo": 3.0,
    "resumen": 2.0,
    "contenido_limpio": 1.0,
}

SPANISH_STOPWORDS = {
    "a", "al", "algo", "algun", "alguna", "algunas", "alguno", "algunos",
    "ante", "antes", "asi", "aun", "aunque", "bajo", "bien", "cada", "casi",
    "como", "con", "contra", "cual", "cuales", "cualquier", "cuando", "cuanto",
    "de", "del", "desde", "donde", "dos", "el", "ella", "ellas", "ello", "ellos",
    "en", "entre", "era", "erais", "eran", "eras", "eres", "es", "esa", "esas",
    "ese", "eso", "esos", "esta", "estaba", "estaban", "estado", "estais", "estamos",
    "estan", "estar", "estas", "este", "esto", "estos", "fue", "fueron", "fui",
    "fuimos", "ha", "habia", "han", "hasta", "hay", "incluso", "la", "las", "le",
    "les", "lo", "los", "mas", "me", "mi", "mis", "mucho", "muy", "nada", "ni",
    "no", "nos", "nosotras", "nosotros", "nuestra", "nuestras", "nuestro", "nuestros",
    "o", "os", "otra", "otras", "otro", "otros", "para", "pero", "poco", "por",
    "porque", "que", "quien", "quienes", "se", "sea", "segun", "ser", "si", "sin",
    "sobre", "solo", "su", "sus", "tambien", "te", "tenia", "tiene", "todo", "todos",
    "tras", "tu", "tus", "un", "una", "uno", "unos", "y", "ya",
    "ano", "anos", "canarias", "canario", "canaria", "isla", "islas",
    "hoy", "ayer", "manana", "europa", "press", "foto", "fotos", "video",
}

TOKEN_RE = re.compile(r"[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{3,}")


@dataclass(frozen=True)
class NewsItem:
    record_id: str
    medio: str
    temas: Tuple[str, ...]
    titulo: str
    resumen: str
    contenido_limpio: str


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {name}")
    return value


def get_client() -> Client:
    url = env_required("SUPABASE_URL")
    key = env_required("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def normalize_key(text: str) -> str:
    lowered = strip_accents(text.lower())
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def normalize_display(text: str) -> str:
    lowered = text.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    tokens = []
    for match in TOKEN_RE.findall(text):
        display = normalize_display(match)
        key = normalize_key(display)
        if len(key) < 3 or key in SPANISH_STOPWORDS:
            continue
        tokens.append(display)
    return tokens


def tokenize_phrases(tokens: Sequence[str], n: int) -> List[str]:
    if len(tokens) < n:
        return []
    phrases = []
    for idx in range(len(tokens) - n + 1):
        phrase = " ".join(tokens[idx:idx + n])
        key = normalize_key(phrase)
        if not key or all(part in SPANISH_STOPWORDS for part in key.split()):
            continue
        phrases.append(phrase)
    return phrases


def parse_topics(value: object) -> Tuple[str, ...]:
    if value is None:
        return tuple()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return tuple()
        if cleaned.startswith("{") and cleaned.endswith("}"):
            items = cleaned.strip("{}").split(",")
            return tuple(item.strip().strip('"') for item in items if item.strip())
        return tuple(
            item.strip() for item in cleaned.split(",")
            if item.strip()
        )
    return tuple()


def fetch_all_news(client: Client) -> List[NewsItem]:
    rows = []
    offset = 0
    while True:
        query = (
            client.schema(SOURCE_SCHEMA)
            .table(SOURCE_TABLE)
            .select(",".join(SOURCE_COLUMNS))
            .order("fecha", desc=True)
            .range(offset, offset + BATCH_SIZE - 1)
        )
        response = query.execute()
        batch = response.data or []
        if not batch:
            break
        for row in batch:
            rows.append(
                NewsItem(
                    record_id=str(row.get("id")),
                    medio=str(row.get("medio") or "").strip(),
                    temas=parse_topics(row.get("temas")),
                    titulo=str(row.get("titulo") or "").strip(),
                    resumen=str(row.get("resumen") or "").strip(),
                    contenido_limpio=str(row.get("contenido_limpio") or "").strip(),
                )
            )
        if len(batch) < BATCH_SIZE:
            break
        offset += BATCH_SIZE
    return rows


def weighted_terms(news: NewsItem) -> List[Tuple[str, str, str, float]]:
    scored_terms: List[Tuple[str, str, str, float]] = []
    for field_name, weight in FIELD_WEIGHTS.items():
        value = getattr(news, field_name)
        tokens = tokenize(value)
        for token in tokens:
            key = normalize_key(token)
            scored_terms.append((key, token, "unigram", weight))
        for phrase in tokenize_phrases(tokens, 2):
            key = normalize_key(phrase)
            scored_terms.append((key, phrase, "bigram", weight * 1.15))
    return scored_terms


def scope_keys(news: NewsItem) -> List[Tuple[str | None, str | None]]:
    keys = [(None, None)]
    if news.medio:
        keys.append((news.medio, None))
    for tema in news.temas:
        keys.append((None, tema))
        if news.medio:
            keys.append((news.medio, tema))
    return keys


def make_scope_key(medio: str | None, tema: str | None) -> str:
    if medio is None and tema is None:
        return "__all__"
    if medio is not None and tema is None:
        return f"medio:{medio}"
    if medio is None and tema is not None:
        return f"tema:{tema}"
    return f"medio:{medio}|tema:{tema}"


def build_aggregates(news_items: Sequence[NewsItem]) -> List[Dict[str, object]]:
    generated_at = datetime.now(timezone.utc).isoformat()
    scope_tf: Dict[Tuple[str | None, str | None], Counter] = defaultdict(Counter)
    scope_df: Dict[Tuple[str | None, str | None], Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    scope_examples: Dict[Tuple[str | None, str | None], Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    term_meta: Dict[str, Tuple[str, str]] = {}
    scope_totals: Dict[Tuple[str | None, str | None], set] = defaultdict(set)

    for item in news_items:
        terms = weighted_terms(item)
        if not terms:
            continue
        scopes = scope_keys(item)
        unique_terms_by_scope: Dict[Tuple[str | None, str | None], set] = defaultdict(set)
        for scope in scopes:
            scope_totals[scope].add(item.record_id)
            for key, display, gram_type, weight in terms:
                term_meta[key] = (display, gram_type)
                scope_tf[scope][key] += weight
                unique_terms_by_scope[scope].add(key)
                examples = scope_examples[scope][key]
                if item.titulo and item.titulo not in examples and len(examples) < 3:
                    examples.append(item.titulo)
        for scope, keys in unique_terms_by_scope.items():
            for key in keys:
                scope_df[scope][key].add(item.record_id)

    rows: List[Dict[str, object]] = []
    for scope, tf_counter in scope_tf.items():
        total_docs = len(scope_totals[scope])
        medio, tema = scope
        ranked_rows = []
        for key, term_freq in tf_counter.items():
            doc_freq = len(scope_df[scope][key])
            if doc_freq < MIN_DOC_FREQ:
                continue
            display_term, gram_type = term_meta[key]
            score = round(term_freq * math.log(1 + (total_docs / max(doc_freq, 1))), 4)
            ranked_rows.append(
                {
                    "scope_key": make_scope_key(medio, tema),
                    "medio": medio,
                    "tema": tema,
                    "term": display_term,
                    "normalized_term": key,
                    "gram_type": gram_type,
                    "score": score,
                    "doc_freq": doc_freq,
                    "term_freq": round(term_freq, 4),
                    "sample_titles": scope_examples[scope][key],
                    "n_noticias": total_docs,
                    "generated_at": generated_at,
                }
            )
        ranked_rows.sort(
            key=lambda row: (
                row["score"],
                row["doc_freq"],
                row["term_freq"],
            ),
            reverse=True,
        )
        rows.extend(ranked_rows[:MAX_TERMS_PER_SCOPE])
    return rows


def truncate_target_table(client: Client) -> None:
    client.rpc(
        "truncate_wordcloud_terms",
        {
            "target_schema": TARGET_SCHEMA,
            "target_table": TARGET_TABLE,
        },
    ).execute()


def chunked(items: Sequence[Dict[str, object]], size: int) -> Iterable[Sequence[Dict[str, object]]]:
    for idx in range(0, len(items), size):
        yield items[idx:idx + size]


def upsert_rows(client: Client, rows: Sequence[Dict[str, object]]) -> None:
    if not rows:
        return
    for batch in chunked(rows, UPSERT_CHUNK_SIZE):
        (
            client.schema(TARGET_SCHEMA)
            .table(TARGET_TABLE)
            .upsert(
                list(batch),
                on_conflict="scope_key,gram_type,normalized_term",
            )
            .execute()
        )


def main() -> int:
    client = get_client()
    news_items = fetch_all_news(client)
    if not news_items:
        print("No se recuperaron noticias desde Supabase.", file=sys.stderr)
        return 1

    aggregates = build_aggregates(news_items)
    if not aggregates:
        print("No se generaron agregados de términos.", file=sys.stderr)
        return 1

    truncate_target_table(client)
    upsert_rows(client, aggregates)
    print(
        f"Word cloud generada: {len(news_items)} noticias procesadas, "
        f"{len(aggregates)} filas agregadas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
