"""Optional standalone model process. Cache weights explicitly before starting."""
from contextlib import asynccontextmanager
import hmac
import logging
import os
from pathlib import Path
from threading import Lock

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.qwen_query import ENCODER, MODEL_ID, MODEL_REVISION, normalized, query_key


class Query(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=600)


class Runtime:
    """Same tokenizer/revision/pooling as the verified experiment, one query at a time."""
    def __init__(self, cache_folder, device):
        import torch
        from transformers import AutoModel, AutoTokenizer
        if device not in ('cpu', 'cuda'):
            raise ValueError('invalid_device')
        kwargs = {}
        if device == 'cuda':
            if not torch.cuda.is_available():
                raise ValueError('gpu_unavailable')
            budgets = {i: torch.cuda.mem_get_info(i)[0] - 2 * 1024**3 for i in range(torch.cuda.device_count())
                       if torch.cuda.mem_get_info(i)[0] >= 4 * 1024**3}
            if sum(budgets.values()) < 9 * 1024**3:
                raise ValueError('insufficient_free_vram')
            kwargs = {'device_map': 'balanced' if len(budgets) > 1 else {'': next(iter(budgets))},
                      'max_memory': {**budgets, 'cpu': 0}}
        else:
            kwargs = {'device_map': {'': 'cpu'}}
        common = dict(revision=MODEL_REVISION, cache_dir=str(cache_folder),
                      local_files_only=True, trust_remote_code=False)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, padding_side='left', **common)
        self.model = AutoModel.from_pretrained(MODEL_ID, dtype=torch.float16, use_safetensors=True,
                    attn_implementation='sdpa', use_cache=False, **kwargs, **common)
        self.model.eval()
        if self.model.config.hidden_size != 2560 or self.tokenizer.padding_side != 'left':
            raise ValueError('wrong_model_configuration')
        if any(p.dtype != torch.float16 for p in self.model.parameters() if p.is_floating_point()):
            raise ValueError('wrong_model_precision')
        if device == 'cuda' and any(str(v) in ('cpu','disk','meta') for v in self.model.hf_device_map.values()):
            raise ValueError('unexpected_model_offload')
        self.device = self.model.get_input_embeddings().weight.device
        self.info = {'device': str(self.device), 'precision': 'float16', 'torch': torch.__version__,
                     'runtime_loader': 'qwen_service_cache_only_fp16_v1',
                     'device_map': {k: str(v) for k,v in self.model.hf_device_map.items()}}

    def encode(self, text):
        import torch
        import torch.nn.functional as functional
        text = ENCODER['query_prefix'] + text
        batch = self.tokenizer([text], padding=True, truncation=False, return_tensors='pt')
        if batch['input_ids'].shape[1] > 512:
            raise ValueError('embedding_input_too_long')
        if not batch['attention_mask'][:, -1].all().item():
            raise ValueError('invalid_padding')
        with torch.inference_mode():
            hidden = self.model(**batch.to(self.device), use_cache=False, return_dict=True).last_hidden_state[:, -1, :].float()
            if not torch.isfinite(hidden).all().item():
                raise ValueError('nonfinite_hidden_state')
            return normalized(functional.normalize(hidden, p=2, dim=1).cpu().tolist()[0])


def configured_token():
    token = os.getenv('QWEN_SERVICE_TOKEN', '')
    return token if len(token) >= 24 and token.isascii() and not any(c.isspace() for c in token) else None


def require_token(authorization: str | None = Header(default=None)):
    token = configured_token()
    if not token or not authorization or not authorization.isascii() or not hmac.compare_digest(authorization, 'Bearer ' + token):
        raise HTTPException(401, 'embedding_unauthorized')


def initialize_runtime(application):
    application.state.runtime = None
    application.state.load_error = 'disabled'
    if os.getenv('QWEN_MODEL_ENABLED', 'false').lower() == 'true' and configured_token():
        try:
            application.state.runtime = Runtime(
                Path(os.getenv('QWEN_MODEL_CACHE', 'data/models/qwen3-4b')),
                os.getenv('QWEN_SERVICE_DEVICE', 'cpu'))
            application.state.load_error = None
        except Exception as error:
            # No model paths, credentials or exception message text in public diagnostics.
            allowed = {'invalid_device','gpu_unavailable','insufficient_free_vram',
                       'wrong_model_configuration','wrong_model_precision','unexpected_model_offload'}
            if isinstance(error, ValueError) and str(error) in allowed:
                reason = str(error)
            elif isinstance(error, OSError):
                reason = 'model_cache_unavailable'
            elif type(error).__name__ == 'ModuleNotFoundError':
                reason = 'model_dependencies_unavailable'
            elif type(error).__name__ == 'OutOfMemoryError':
                reason = 'model_out_of_memory'
            else:
                reason = 'model_load_failed'
            application.state.load_error = reason
            logging.getLogger('mo.qwen').warning('Model not ready: %s',reason)


@asynccontextmanager
async def lifespan(application):
    initialize_runtime(application)
    yield


app = FastAPI(title='Internal Qwen query encoder', lifespan=lifespan)
app.state.runtime = None
app.state.load_error = 'not_started'
_lock = Lock()


@app.get('/health/ready', dependencies=[Depends(require_token)])
def ready():
    runtime = app.state.runtime
    if runtime is None:
        raise HTTPException(503, {'code':'embedding_not_ready','reason':app.state.load_error})
    return {'status': 'ready', 'encoder': ENCODER, 'runtime': runtime.info}


@app.post('/v1/embed-query', dependencies=[Depends(require_token)])
def encode(body: Query):
    if not body.text.strip():
        raise HTTPException(422, 'empty_query')
    runtime = app.state.runtime
    if runtime is None:
        raise HTTPException(503, 'embedding_not_ready')
    if not _lock.acquire(blocking=False):
        raise HTTPException(503, 'embedding_busy')
    try:
        vector = runtime.encode(body.text)
        return {'encoder': ENCODER, 'query_sha256': query_key(body.text), 'vector': normalized(vector)}
    except ValueError:
        raise HTTPException(422, 'embedding_query_unverified') from None
    except Exception:
        raise HTTPException(503, 'embedding_inference_failed') from None
    finally:
        _lock.release()
