"""Metadata-first ranking over a bounded teaching corpus, with explicit fallbacks."""
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import unicodedata

from app.local_embedding import ENCODER, EmbeddingUnavailable, encode_query
from app.retrieval_contracts import KnowledgeChunk, RetrievalRequest, RetrievalResult, RetrievedChunk

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT/'data/retrieval/bge-m3-v1/index.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def corpus(registry, bank):
    """Positive projection: answers, worked examples and error fixtures are excluded."""
    concepts = {c.concept_id: c for c in registry.concepts}
    chunks = []
    for pack in bank.packs:
        c = concepts[pack.concept_id]
        approved = (pack.review.status == c.review.status == c.alignment.status == 'human_approved')
        # E02 authoring explanation includes a separate engineering note, not teaching content.
        explanation = ' '.join(s.strip()+'.' for s in pack.explanation.split('.') if s.strip() and 'MVP' not in s)
        parts = [(f'{c.concept_id}-explanation', 'explanation', 0, 'conceptual', explanation),
                 *[(f'{c.concept_id}-hint-{h.level}', 'hint', h.level, h.disclosure, h.text) for h in pack.hints]]
        for content_id, kind, level, disclosure, text in parts:
            chunks.append(KnowledgeChunk(content_id=content_id, concept_id=c.concept_id,
                skill_ids=[s.skill_id for s in c.skills], title=c.title, text=text, kind=kind,
                hint_level=level, disclosure=disclosure, grade_levels=c.alignment.grade_levels,
                source=pack.review.source, curriculum_source_id=c.alignment.source_id,
                content_version=pack.content_version, review_status=pack.review.status,
                approved=approved, text_sha256=hashlib.sha256(text.encode()).hexdigest()))
    return sorted(chunks, key=lambda c: c.content_id)


def corpus_hash(chunks):
    return digest([c.model_dump(mode='json') for c in sorted(chunks, key=lambda c:c.content_id)])


def embedding_text(chunk):
    return f'{chunk.title}\n{chunk.text}'


def candidates(chunks, request, *, authoring=False):
    return [c for c in chunks if (authoring or c.approved) and c.concept_id in request.concept_ids
            and c.kind == request.purpose and (c.kind != 'hint' or c.hint_level <= request.hint_level)]


def tokens(text):
    text = unicodedata.normalize('NFD', text.lower()).replace('đ', 'd')
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    stop = {'em', 'toi', 'va', 'la', 'cua', 'cho', 'mot', 'cac', 'nhung', 'de', 'thi', 'co', 'nay'}
    return [t for t in re.findall(r'[a-z0-9]+', text) if t not in stop]


def lexical_scores(query, chunks):
    """Small-corpus BM25 baseline; never described as semantic embeddings."""
    docs = [Counter(tokens(embedding_text(c))) for c in chunks]
    n = len(docs)
    average = sum(sum(d.values()) for d in docs)/max(1, n)
    scores = []
    for doc in docs:
        score = 0.
        for term in sorted(set(tokens(query))):
            frequency = doc[term]
            df = sum(term in d for d in docs)
            idf = math.log(1+(n-df+.5)/(df+.5))
            if frequency:
                score += idf*frequency*2.2/(frequency+1.2*(.25+.75*sum(doc.values())/max(1, average)))
        scores.append(score)
    return scores


def normalized(vector):
    if not isinstance(vector, list) or len(vector) != ENCODER['dimensions'] or any(
            isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in vector):
        raise EmbeddingUnavailable('invalid_vector')
    length = math.sqrt(sum(v*v for v in vector))
    if length <= 0 or not math.isfinite(length):
        raise EmbeddingUnavailable('invalid_vector')
    return [v/length for v in vector]


def build_index(chunks, vectors, *, environment=None):
    if len(vectors) != len(chunks):
        raise EmbeddingUnavailable('vector_count_mismatch')
    return {'schema_version':'1.0.0', 'encoder':ENCODER, 'corpus_sha256':corpus_hash(chunks),
            'environment':environment or {}, 'records':[
                {'content_id':c.content_id, 'text_sha256':digest(embedding_text(c)), 'vector':normalized(v)}
                for c,v in zip(chunks, vectors)]}


def validate_index(data, chunks):
    try:
        if data['schema_version'] != '1.0.0' or data['encoder'] != ENCODER or data['corpus_sha256'] != corpus_hash(chunks):
            raise EmbeddingUnavailable('index_stale_or_wrong_model')
        records = data['records']
        if len(records) != len(chunks) or len({r['content_id'] for r in records}) != len(chunks):
            raise EmbeddingUnavailable('index_content_mismatch')
        by_id = {r['content_id']:r for r in records}
        for c in chunks:
            if by_id[c.content_id]['text_sha256'] != digest(embedding_text(c)):
                raise EmbeddingUnavailable('index_text_mismatch')
        return {c.content_id:normalized(by_id[c.content_id]['vector']) for c in chunks}
    except EmbeddingUnavailable:
        raise
    except Exception:
        raise EmbeddingUnavailable('index_unavailable') from None


def load_index(path, chunks):
    try:
        if path.stat().st_size > 5*1024*1024:
            raise EmbeddingUnavailable('index_too_large')
        return validate_index(json.loads(path.read_text(encoding='utf-8')), chunks)
    except EmbeddingUnavailable:
        raise
    except Exception:
        raise EmbeddingUnavailable('index_unavailable') from None


def retrieve(chunks, request: RetrievalRequest, *, authoring=False, index_path=None, query_encoder=None,
             query_vector=None, allow_fallback=True, index_document=None):
    pool = candidates(chunks, request, authoring=authoring)
    common = dict(requested_method=request.method, query=request.query, corpus_sha256=corpus_hash(chunks),
                  candidate_count=len(pool), mode='internal_authoring_preview' if authoring else 'approved_only')
    if not pool:
        return RetrievalResult(**common, actual_method='none', hits=[], reason='no_eligible_content')
    fallback = None
    method = request.method
    if method == 'semantic':
        try:
            vectors = (validate_index(index_document, chunks) if index_document is not None else
                       load_index(Path(index_path or os.getenv('RETRIEVAL_INDEX_PATH') or DEFAULT_INDEX), chunks))
            q = normalized(query_vector if query_vector is not None else (query_encoder or encode_query)(request.query))
            scores = [sum(a*b for a,b in zip(q,vectors[c.content_id])) for c in pool]
        except EmbeddingUnavailable as error:
            if not allow_fallback:
                raise
            fallback = str(error)
            method = 'lexical'
    if method == 'lexical':
        scores = lexical_scores(request.query, pool)
    if method == 'metadata':
        # Same candidate filter as semantic; stable IDs only, no relevance ranking.
        ordered = [(c,None) for c in sorted(pool, key=lambda c:c.content_id)]
    else:
        ordered = sorted(zip(pool,scores), key=lambda item:(-item[1], item[0].content_id))
        if method == 'lexical':
            ordered = [item for item in ordered if item[1] > 0]
    hits = [RetrievedChunk(chunk=c,score=s) for c,s in ordered[:request.top_k]]
    return RetrievalResult(**common, actual_method=method, hits=hits,
        reason='ranked' if hits else 'no_lexical_overlap', fallback_reason=fallback,
        embedding_model=ENCODER['model_id'] if method == 'semantic' else None,
        embedding_revision=ENCODER['revision'] if method == 'semantic' else None)
