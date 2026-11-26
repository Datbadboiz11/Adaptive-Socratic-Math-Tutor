# Code nghiên cứu

Thư mục này chứa pipeline dữ liệu và công cụ thí nghiệm theo [kế hoạch tổng](../docs/planning/project-plan.md). Source code được version trong Git; dataset và kết quả chứa bản ghi học sinh lưu trong `data/` đã ignore.

Đã có audit, pipeline action → observation và BKT baseline train/dev. Chạy từ gốc repo:

```powershell
python research/data/audit_assistments_2017.py
python -m research.data.preprocess_assistments_2017
python -m research.bkt.benchmark
```

Đánh giá phần của Member 3 trên bộ dev tự soạn (không phải kết quả báo cáo). Mặc định không gọi API; gọi model thật phải thêm `--yes` và có key trong `.env`:

```powershell
python research/agent/compare_proposers.py --agent fake        # Agent LLM so với Rule-policy
python research/extraction/evaluate_extraction.py --llm fake   # LLM extraction
python research/generation/evaluate_generation.py --llm fake   # verifier và LLM viết câu phản hồi
```

Ablation và chấm rubric Socratic ẩn cấu hình:

```powershell
python research/evaluation/run_ablation.py --out data/ablation/dev-fake   # 7 cấu hình plan §18.1 (6 qua LangGraph + Socratic LLM baseline); mặc định LLM giả
python research/evaluation/run_dev_repeat.py --out data/ablation/dev-repeat-fake   # hai lần lặp, chia phần và gộp có kiểm tra; mặc định LLM giả
python research/evaluation/build_rating_packet.py --pilot --raters r1 r2 --out data/rating/pilot-01
python research/evaluation/score_ratings.py --packet data/rating/pilot-01
python research/evaluation/select_thresholds.py --out data/thresholds/dev-01   # sàng lọc ngưỡng mastery BKT/Heuristic bằng Rule-policy; không gọi API
```

`run_ablation.py` ghi câu của từng cấu hình (`outputs.jsonl`) cùng quyết định, latency và chi phí từng lượt; `--llm openai --yes` mới gọi model thật. `build_rating_packet.py` tạo bộ bài cho người chấm, `score_ratings.py` tính độ đồng thuận và tổng hợp điểm; hai script này không gọi API. Xem [script ablation](../docs/implementation/evaluation/ablation-runner.v1.md), [hướng dẫn chấm](../docs/implementation/evaluation/socratic-rubric.v1.md) và [quy trình chấm](../docs/implementation/evaluation/rating-workflow.v1.md).

Công cụ dựng tình huống từ lịch sử, chia dev/test theo nhóm bài và xuất độ phủ nằm trong
`scenarios/`. Đọc [hướng dẫn biên soạn](../docs/implementation/evaluation/adaptive-scenarios.v1.md).

```powershell
python -m research.scenarios.build --input contracts/scenarios/examples.dev.v1.json --out data/scenarios/examples-v3
python -m research.scenarios.pilot_dev --check                                        # bộ dev pilot 33 ca khớp nguồn
python -m research.scenarios.pilot_dev --sheet data/scenarios/pilot-dev-review.md     # phiếu rà soát nhãn nháp; thêm --blind để gán nhãn độc lập
python -m research.scenarios.build --input contracts/scenarios/pilot.dev.v1.json --out data/scenarios/pilot-v1
```

Bộ dev pilot soạn bằng code ở `scenarios/pilot_dev.py` (dùng `scenarios/authoring.py`); nhãn là nháp, chưa duyệt.

Phần dùng chung của các script có gọi LLM (đọc `.env`, xác nhận trước khi gọi, thống kê token/chi phí) nằm ở `llm_support.py`. Client, kiểu usage và client giả dùng chung nằm ở `backend/app/llm/`. Thiết kế và giới hạn: [Agent LLM](../docs/implementation/agent/llm-agent.v1.md), [LLM extraction](../docs/implementation/extraction/llm-extraction.v1.md), [sinh phản hồi](../docs/implementation/generation/response-generation.v1.md).

Audit và preprocess dùng thư viện chuẩn Python. Benchmark cần [requirements riêng](requirements.txt) gồm NumPy/SciPy; đọc [hướng dẫn chạy](../docs/research/data/RUNBOOK.md), [protocol](../docs/research/data/observation-protocol.md) và [kết quả dev v1](../docs/research/data/bkt-dev-v1.md). Test được giữ lại, không đọc trong lệnh benchmark. Không thay tham số bootstrap sản phẩm bằng kết quả trên dữ liệu công khai.
