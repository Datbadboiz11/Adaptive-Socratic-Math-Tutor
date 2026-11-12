"""Pinned Qwen query protocol. No model downloads or paid calls in the tutor API."""
import hashlib
import json
import math
import os
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.local_embedding import EmbeddingUnavailable

MODEL_ID = 'Qwen/Qwen3-Embedding-4B'
MODEL_REVISION = '5cf2132abc99cad020ac570b19d031efec650f2b'
TASK = ('Given a Vietnamese math learning question, retrieve relevant explanations or hints '
        'addressing the mathematical concept and the requested level of support.')
ENCODER = dict(model_id=MODEL_ID, revision=MODEL_REVISION, dimensions=2560,
               max_length=512, pooling='last_token', normalize=True,
               query_prefix=f'Instruct: {TASK}\nQuery:', passage_prefix='')


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def query_key(text):
    return digest({'encoder': ENCODER, 'query': text})


def normalized(vector):
    if not isinstance(vector, list) or len(vector) != 2560 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in vector):
        raise EmbeddingUnavailable('qwen_invalid_vector')
    norm = math.sqrt(sum(v * v for v in vector))
    if not math.isfinite(norm) or norm <= 0:
        raise EmbeddingUnavailable('qwen_invalid_vector')
    return [v / norm for v in vector]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class QueryService:
    def __init__(self, url=None, token=None, timeout=None):
        self.url = (url if url is not None else os.getenv('QWEN_SERVICE_URL', '')).rstrip('/')
        self.token = token if token is not None else os.getenv('QWEN_SERVICE_TOKEN', '')
        try:
            parsed = urlparse(self.url)
            parsed.port  # Reject malformed ports/IPv6 before building requests.
        except ValueError:
            raise EmbeddingUnavailable('qwen_service_configuration') from None
        local = parsed.hostname in ('localhost', '127.0.0.1', '::1', 'qwen-embedding', 'host.docker.internal')
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or (parsed.scheme == 'http' and not local)):
            raise EmbeddingUnavailable('qwen_service_configuration')
        if len(self.token) < 24 or not self.token.isascii() or any(c.isspace() for c in self.token):
            raise EmbeddingUnavailable('qwen_service_unconfigured')
        try:
            self.timeout = float(timeout if timeout is not None else os.getenv('QWEN_SERVICE_TIMEOUT_SECONDS', '30'))
            if not math.isfinite(self.timeout) or not 1 <= self.timeout <= 120:
                raise ValueError()
        except ValueError:
            raise EmbeddingUnavailable('qwen_service_configuration') from None

    def encode(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 600:
            raise EmbeddingUnavailable('qwen_invalid_query')
        request = Request(self.url + '/v1/embed-query', method='POST',
            data=json.dumps({'text': text}, ensure_ascii=False).encode(),
            headers={'Authorization': 'Bearer ' + self.token,
                     'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with build_opener(NoRedirect()).open(request, timeout=self.timeout) as response:
                body = response.read(256 * 1024 + 1)
            if len(body) > 256 * 1024:
                raise EmbeddingUnavailable('qwen_service_invalid_response')
            result = json.loads(body)
            if result.get('encoder') != ENCODER or result.get('query_sha256') != query_key(text):
                raise EmbeddingUnavailable('qwen_service_encoder_or_query_mismatch')
            return normalized(result['vector'])
        except EmbeddingUnavailable:
            raise
        except Exception:
            # URLs, tokens, request text and upstream exception bodies stay server-side.
            raise EmbeddingUnavailable('qwen_service_unavailable') from None
