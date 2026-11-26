"""Pinned, offline CPU embeddings; optional dependency, loaded only when needed."""
from functools import lru_cache
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import struct
from threading import RLock

from app.kb_contracts import EmbeddingProfile


def checked_vector(values, dimension):
    try:
        values = [float(v) for v in values]
        if len(values) != dimension or not all(math.isfinite(v) for v in values):
            raise ValueError("Embedding dimension or finiteness mismatch")
        norm = math.sqrt(sum(v * v for v in values))
        if not math.isfinite(norm) or norm == 0:
            raise ValueError("Embedding must be finite and nonzero")
        # pgvector stores float32. Canonicalize before hashing/caching to match its precision.
        return [struct.unpack("f", struct.pack("f", v / norm))[0] for v in values]
    except (TypeError, OverflowError) as error:
        raise ValueError("Invalid embedding") from error


def vector_literal(values):
    return json.dumps(values, separators=(",", ":"), allow_nan=False)


def vector_hash(values):
    return hashlib.sha256(b"".join(struct.pack("<f", float(v)) for v in values)).hexdigest()


class LocalEmbedder:
    def __init__(self, profile: EmbeddingProfile, model_dir):
        if profile.provider != "fastembed":
            raise ValueError("LocalEmbedder requires a pinned FastEmbed profile")
        self.profile = profile
        self.model_dir = Path(model_dir).resolve()
        self._model = None
        self._lock = RLock()
        self.calls = 0

    def _load(self):
        with self._lock:
            if self._model is not None:
                return self._model
            for name, expected in self.profile.files_sha256.items():
                # HF snapshots link files to a blob cache outside the snapshot directory.
                # The allowlisted basename + pinned hash is the boundary; follow valid cache links.
                path = self.model_dir / name
                if path.parent != self.model_dir:
                    raise ValueError("Invalid model file path")
                with path.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
                if actual != expected:
                    raise ValueError("Embedding weights/tokenizer checksum mismatch")
            for package, expected in self.profile.runtime_versions.items():
                if version(package) != expected:
                    raise ValueError("Embedding inference runtime differs from pinned profile")
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.profile.model_name, specific_model_path=str(self.model_dir),
                threads=2, providers=["CPUExecutionProvider"], local_files_only=True)
            return self._model

    def embed_many(self, texts):
        if not texts:
            return []
        model = self._load()
        vectors = [checked_vector(v, self.profile.dimension) for v in model.embed(texts, batch_size=32)]
        if len(vectors) != len(texts):
            raise ValueError("Embedding provider returned an incomplete batch")
        self.calls += len(texts)
        return vectors

    @lru_cache(maxsize=128)
    def _cached_query(self, text):
        return tuple(self.embed_many([text])[0])

    def embed_query(self, text):
        # Only vectors are cached; every retrieval still reapplies all authorization/review filters.
        return list(self._cached_query(text))
