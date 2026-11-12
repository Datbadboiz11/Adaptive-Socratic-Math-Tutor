"""Build a separate Kaggle notebook/input for the trusted runtime query catalog."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.retrieval.qwen3_4b import runtime_catalog as batch


def cell(kind, text):
    result = {'cell_type': kind, 'metadata': {}, 'source': text.splitlines(keepends=True)}
    if kind == 'code':
        result.update(execution_count=None, outputs=[])
    return result


def main():
    info = batch.prepare()
    raw, spec = batch.read_input(info['archive'])
    manifest_sha = hashlib.sha256(raw['manifest.json']).hexdigest()
    notebook = {'nbformat': 4, 'nbformat_minor': 5,
        'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                     'language_info': {'name': 'python'},
                     'kaggle': {'isInternetEnabled': True, 'accelerator': 'gpu'}},
        'cells': [cell('markdown', f'''# Qwen4B — vector truy vấn runtime trên Kaggle

Notebook mới, tách khỏi thí nghiệm BGE/Qwen cũ. Tạo **{len(spec['queries'])} vector** cho mục tiêu kiến thức và câu hỏi chẩn đoán đã biên soạn của 10 concept pilot. Không huấn luyện model, không đánh giá lại Recall, không mở dịch vụ/tunnel. Không tải dữ liệu học sinh, lời giải chuẩn, `.env` hoặc toàn bộ repo.

1. Import notebook này vào Kaggle; chọn **GPU T4 ×2**, bật **Internet**.
2. Add Input → upload **`{batch.INPUT_NAME}`** từ `data/exports/`. Kaggle có thể tự giải nén ZIP; cả hai dạng đều được hỗ trợ.
3. Bắt đầu **session mới**, Save Version → Save & Run All. Không chạy chung model BGE/Qwen của notebook khác để tránh hết VRAM.
4. Tải **`{batch.OUTPUT_NAME}`** trong Output. Đặt vào `data/exports/`, chạy lệnh import bên dưới.

Model pin revision và FP16/last-token/L2 như lần chạy Qwen thành công. Lần đầu Kaggle vẫn cần tải khoảng 8 GB trọng số; không tải chúng về máy cá nhân. Batch nhỏ nên phần encode ngắn, phần tải/nạp model có thể chiếm phần lớn thời gian.

Backend chỉ lấy vector khi query khớp chính xác danh mục và phiên bản nội dung. Query mới ngoài danh mục dùng lexical fallback có nhãn; đây không phải encode online mọi câu hỏi tự do.
'''), cell('code', f'''# Validate local-generated manifest and every file BEFORE executing bundled code.
from pathlib import Path
import hashlib, json, sys, uuid, zipfile
PREFIX = {batch.PREFIX!r}
INPUT_FILES = {batch.INPUT_FILES!r}
EXPECTED_MANIFEST_SHA256 = {manifest_sha!r}
candidates = list(Path('/kaggle/input').rglob({batch.INPUT_NAME!r}))
if not candidates:
    candidates = [p.parent for p in Path('/kaggle/input').rglob('manifest.json')
                  if hashlib.sha256(p.read_bytes()).hexdigest() == EXPECTED_MANIFEST_SHA256]
if len(candidates) != 1:
    raise ValueError('Add exactly one matching runtime input ZIP/dataset; remove old or duplicate input versions.')
SOURCE = candidates[0]
limit = 5 * 1024**2
if SOURCE.is_file():
    if SOURCE.stat().st_size > limit:
        raise ValueError('Input ZIP too large')
    with zipfile.ZipFile(SOURCE) as z:
        expected = {{PREFIX + n for n in INPUT_FILES}}
        if set(z.namelist()) != expected or len(z.namelist()) != len(expected) or sum(i.file_size for i in z.infolist()) > limit:
            raise ValueError('Input allowlist/size mismatch')
        raw = {{n: z.read(PREFIX + n) for n in INPUT_FILES}}
else:
    if {{p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob('*') if p.is_file()}} != set(INPUT_FILES):
        raise ValueError('Input directory allowlist mismatch')
    if sum((SOURCE/n).stat().st_size for n in INPUT_FILES) > limit:
        raise ValueError('Input contents too large')
    raw = {{n: (SOURCE/n).read_bytes() for n in INPUT_FILES}}
if hashlib.sha256(raw['manifest.json']).hexdigest() != EXPECTED_MANIFEST_SHA256:
    raise ValueError('Notebook/input mismatch: upload the pair generated together.')
manifest = json.loads(raw['manifest.json'])
if manifest['sha256'] != {{n: hashlib.sha256(v).hexdigest() for n,v in raw.items() if n != 'manifest.json'}}:
    raise ValueError('Input hash mismatch')
WORK = Path('/kaggle/working') / ('qwen-runtime-' + uuid.uuid4().hex)
for n,v in raw.items():
    target = WORK/n
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(v)
sys.path[:0] = [str(WORK/'backend'), str(WORK)]
print('Validated input; queries:', len(json.loads(raw['specification.json'])['queries']))
'''), cell('code', '''# Keep Kaggle's preinstalled CUDA PyTorch. Do not install the CPU torch build.
import subprocess
subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', '-r',
    str(WORK/'research/retrieval/qwen3_4b/requirements.txt')])
'''), cell('code', f'''from research.retrieval.qwen3_4b.runtime_catalog import run
from research.retrieval.qwen3_4b.experiment import gpu_memory
print(gpu_memory())
OUTPUT = Path('/kaggle/working') / {batch.OUTPUT_NAME!r}
result = run(SOURCE, OUTPUT, Path('/kaggle/working/qwen3-4b-model-cache'))
print(json.dumps(result, ensure_ascii=False, indent=2))
'''), cell('code', '''from IPython.display import FileLink, display
display(FileLink(str(OUTPUT)))
'''), cell('markdown', f'''## Sau khi tải về máy

Đặt ZIP trong `data/exports/`. Từ thư mục gốc dự án chạy:

```powershell
.\\.venv\\Scripts\\python.exe research/retrieval/qwen3_4b/runtime_catalog.py import --input data/exports/{batch.OUTPUT_NAME}
```

Importer chỉ đọc JSON, kiểm tra hash/model/revision/danh mục/phiên bản hiện tại trước khi lưu `data/retrieval/qwen3-4b-runtime/catalog.json`. Không ghi đè catalog khác. Không nạp code tải về và không sửa corpus/index/kết quả nghiên cứu cũ. Backend dùng `QWEN_QUERY_PROVIDER=catalog`; pgvector chứa 40 vector nội dung cần được nạp riêng bằng `rag-init`.
''')]}
    target = ROOT / 'research/retrieval/qwen3_4b/qwen3_runtime_queries_kaggle.ipynb'
    target.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({**info, 'notebook': str(target)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
