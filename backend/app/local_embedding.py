"""Optional BGE-M3 runtime. No downloads during API requests, no paid API calls."""
from functools import lru_cache
import os
from pathlib import Path
from threading import Lock

MODEL_ID = 'BAAI/bge-m3'
MODEL_REVISION = '5617a9f61b028005a4858fdac845db406aefb181'
ENCODER = {'model_id': MODEL_ID, 'revision': MODEL_REVISION, 'dimensions': 1024,
           'max_length': 512, 'pooling': 'model_sentence_transformers', 'normalize': True,
           'query_prefix': '', 'passage_prefix': ''}
ROOT = Path(__file__).resolve().parents[2]
MODEL_CACHE = ROOT / 'data/models'
_lock = Lock()
_model_lock = Lock()


class EmbeddingUnavailable(ValueError):
    pass


def load_model(*, download=False, device='cpu', cache_folder=None):
    try:
        from sentence_transformers import SentenceTransformer
        import torch
        if device == 'cuda' and not torch.cuda.is_available():
            raise EmbeddingUnavailable('gpu_unavailable')
        model = SentenceTransformer(MODEL_ID, revision=MODEL_REVISION, device=device,
            cache_folder=str(cache_folder or MODEL_CACHE), trust_remote_code=False,
            local_files_only=not download)
        model.max_seq_length = ENCODER['max_length']
        if device == 'cuda':
            model.half()
        model.eval()
        return model
    except EmbeddingUnavailable:
        raise
    except Exception:
        raise EmbeddingUnavailable('local_model_unavailable') from None


@lru_cache(maxsize=1)
def _cached_runtime_model():
    device = os.getenv('EMBEDDING_DEVICE', 'cpu')
    if device not in ('cpu', 'cuda'):
        raise EmbeddingUnavailable('invalid_embedding_device')
    return load_model(device=device, cache_folder=os.getenv('EMBEDDING_MODEL_CACHE') or MODEL_CACHE)


def runtime_model():
    # lru_cache alone can run multiple loaders on concurrent first misses.
    with _model_lock:
        return _cached_runtime_model()


def encode_texts(model, texts, *, batch_size=8):
    if not texts or any(not t.strip() or len(t) > 2600 for t in texts):
        raise EmbeddingUnavailable('invalid_embedding_input')
    # Reject truncation silently changing the corpus meaning.
    try:
        if any(len(model.tokenizer.encode(t, add_special_tokens=True)) > ENCODER['max_length'] for t in texts):
            raise EmbeddingUnavailable('embedding_input_too_long')
        with _lock:
            values = model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                                  convert_to_numpy=True, show_progress_bar=False)
        return values.tolist()
    except EmbeddingUnavailable:
        raise
    except Exception:
        raise EmbeddingUnavailable('local_inference_failed') from None


def encode_query(text):
    if os.getenv('LOCAL_EMBEDDING_ENABLED', 'false').lower() != 'true':
        raise EmbeddingUnavailable('local_embedding_disabled')
    return encode_texts(runtime_model(), [text], batch_size=1)[0]
