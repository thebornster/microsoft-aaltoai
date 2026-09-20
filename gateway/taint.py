"""Deterministic taint tracking: exact w=5 shingles + entity-level identifiers.

No AI in the decision loop. A source's labels are inherited by any outgoing
argument whose token shingles intersect that source's index by >= MIN_SHINGLE_OVERLAP,
or that contains one of the source's indexed entity identifiers.
"""
import re
from dataclasses import dataclass, field
from typing import Any

SHINGLE_WIDTH = 5
MIN_SHINGLE_OVERLAP = 3

STRUCTURAL_TOKENS = {"{", "}", "[", "]", ":", ",", '"', "'"}
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are",
    "was", "were", "be", "this", "that", "it", "with", "as", "at", "by",
}

_WORD_RE = re.compile(r"[A-Za-z0-9_.\-@]+")

# entity extraction: employee IDs, emails, machine serials, ticket ids.
# Operator names are matched separately against the known-operator list
# supplied by the caller (tools.yaml), since they're multi-token.
_ENTITY_PATTERNS = [
    re.compile(r"\bEMP-\d{3,6}\b"),
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b[A-Z]{2,4}-\d{3,8}\b"),
]


def tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    return [t for t in tokens if t not in STOPWORDS and t not in STRUCTURAL_TOKENS]


def shingles(tokens: list[str], width: int = SHINGLE_WIDTH) -> set[tuple[str, ...]]:
    if len(tokens) < width:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + width]) for i in range(len(tokens) - width + 1)}


def extract_entities(text: str, known_names: list[str]) -> set[str]:
    found: set[str] = set()
    for pattern in _ENTITY_PATTERNS:
        found.update(m.group(0) for m in pattern.finditer(text))
    lowered = text.lower()
    for name in known_names:
        if name.lower() in lowered:
            found.add(name)
    return found


def flatten_to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    if isinstance(value, dict):
        return " ".join(flatten_to_text(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(flatten_to_text(v) for v in value)
    return str(value)


@dataclass
class SourceEntry:
    source_id: str
    trust: str
    residency: str
    shingle_index: set[tuple[str, ...]] = field(default_factory=set)
    entities: set[str] = field(default_factory=set)


@dataclass
class MatchResult:
    source_id: str
    trust: str
    residency: str
    shingle_overlap: int
    matched_entities: list[str]


class TaintStore:
    """Per-session fingerprint index. One instance per session_id.

    Optionally backed by a gateway.db.StateDB for restart durability: when
    `db`/`session_id` are given, sources ingested this process are written
    through immediately, and any sources from a prior process are loaded
    back in on construction (see gateway.gateway.RajaGateway._session).
    """

    def __init__(self, db: Any | None = None, session_id: str | None = None) -> None:
        self.sources: dict[str, SourceEntry] = {}
        self.untrusted_ingested: bool = False
        self._db = db
        self._session_id = session_id
        if db is not None and session_id is not None:
            for row in db.load_sources(session_id):
                self.sources[row["source_id"]] = SourceEntry(
                    source_id=row["source_id"],
                    trust=row["trust"],
                    residency=row["residency"],
                    shingle_index={tuple(s) for s in row["shingle_index"]},
                    entities=set(row["entities"]),
                )
            self.untrusted_ingested = db.is_untrusted(session_id)

    def ingest(
        self,
        source_id: str,
        text: str,
        trust: str,
        residency: str,
        known_names: list[str] | None = None,
    ) -> None:
        entry = SourceEntry(
            source_id=source_id,
            trust=trust,
            residency=residency,
            shingle_index=shingles(tokenize(text)),
            entities=extract_entities(text=text, known_names=known_names or []),
        )
        self.sources[source_id] = entry
        if trust == "untrusted":
            self.untrusted_ingested = True
        if self._db is not None and self._session_id is not None:
            self._db.save_source(
                session_id=self._session_id,
                source_id=source_id,
                trust=trust,
                residency=residency,
                shingle_index=[list(t) for t in entry.shingle_index],
                entities=list(entry.entities),
            )
            if trust == "untrusted":
                self._db.set_untrusted(self._session_id)

    def resolve(self, value: Any) -> list[MatchResult]:
        text = flatten_to_text(value)
        arg_tokens = tokenize(text)
        arg_shingles = shingles(arg_tokens)
        arg_entities = extract_entities(text=text, known_names=[])
        lowered = text.lower()

        results: list[MatchResult] = []
        for entry in self.sources.values():
            overlap = arg_shingles & entry.shingle_index
            matched_entities = sorted(
                e for e in entry.entities if e in arg_entities or e.lower() in lowered
            )
            if len(overlap) >= MIN_SHINGLE_OVERLAP or matched_entities:
                results.append(
                    MatchResult(
                        source_id=entry.source_id,
                        trust=entry.trust,
                        residency=entry.residency,
                        shingle_overlap=len(overlap),
                        matched_entities=matched_entities,
                    )
                )
        return results
