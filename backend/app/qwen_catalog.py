"""Exact-query Kaggle vectors; never substitute a vector for unseen learner text."""
import json
import os
from pathlib import Path

from app.curriculum_graph import snapshot_id
from app.grounding_queries import POLICY_VERSION, grounding_query
from app.local_embedding import EmbeddingUnavailable
from app.qwen_query import ENCODER, digest, normalized, query_key
from app.retrieval import corpus, corpus_hash

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / 'data/retrieval/qwen3-4b-runtime/catalog.json'


def specification(registry, bank):
    concepts = {c.concept_id: c for c in registry.concepts}
    texts = set()
    for pack in bank.packs:
        concept = concepts[pack.concept_id]
        texts.add(grounding_query(concept))
        problems = {p.case_id for p in pack.problems}
        for error in pack.errors:
            if error.problem_id in problems and error.diagnostic_question:
                texts.add(grounding_query(concept, error.diagnostic_question))
    return {'schema_version': '1.0.0', 'encoder': ENCODER,
            'query_policy': POLICY_VERSION, 'registry_snapshot_id': snapshot_id(registry),
            'corpus_sha256': corpus_hash(corpus(registry, bank)),
            'queries': [{'query_sha256': query_key(t), 'text': t} for t in sorted(texts)]}


def validate(document, spec):
    try:
        if (document['schema_version'] != '1.0.0' or document['specification'] != spec
                or document['specification_sha256'] != digest(spec)):
            raise ValueError()
        expected = {q['query_sha256'] for q in spec['queries']}
        records = document['records']
        if len(records) != len(expected) or {r['query_sha256'] for r in records} != expected:
            raise ValueError()
        return {r['query_sha256']: normalized(r['vector']) for r in records}
    except EmbeddingUnavailable:
        raise
    except Exception:
        raise EmbeddingUnavailable('qwen_catalog_stale_or_invalid') from None


class QueryCatalog:
    source = 'kaggle_catalog'

    def __init__(self, registry, bank, path=None):
        self.spec = specification(registry, bank)
        self.path = Path(path or os.getenv('QWEN_QUERY_CATALOG_PATH', str(DEFAULT_PATH)))
        self.vectors = None

    def ready(self):
        if self.vectors is None:
            try:
                if self.path.stat().st_size > 10 * 1024**2:
                    raise ValueError()
                document = json.loads(self.path.read_text(encoding='utf-8'))
            except FileNotFoundError:
                raise EmbeddingUnavailable('qwen_catalog_missing') from None
            except Exception:
                raise EmbeddingUnavailable('qwen_catalog_unreadable') from None
            self.vectors = validate(document, self.spec)
        return {'source': self.source, 'query_count': len(self.vectors),
                'specification_sha256': digest(self.spec)}

    def encode(self, text):
        self.ready()
        if query_key(text) not in self.vectors:
            raise EmbeddingUnavailable('qwen_query_not_in_catalog')
        return list(self.vectors[query_key(text)])
