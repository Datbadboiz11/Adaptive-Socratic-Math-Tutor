# Knowledge Graph nối Agent, bản v1

**Trạng thái:** chạy được với registry thật (40 concept, 68 cạnh), cả bản đọc từ file lẫn Neo4j. **Cả 68 cạnh và 40 concept vẫn là nháp, chưa có người duyệt**, nên hệ thống hiện chỉ dùng được KG ở chế độ dev (xem §3).
**Căn cứ:** plan §8.4, PRD FR-08. **Hợp đồng dữ liệu:** [pedagogical-decision.v1.md](pedagogical-decision.v1.md). **Luồng một lượt:** [langgraph-skeleton.v1.md](langgraph-skeleton.v1.md).

## 1. Thành phần

| File | Việc |
|---|---|
| `backend/app/kg/graph.py` | Đọc `content/curriculum/registry.v1.json`, kiểm tra đồ thị, truy vấn trong bộ nhớ |
| `backend/app/kg/neo4j_store.py` | Đồng bộ registry sang Neo4j, truy vấn bằng Cypher; trả cùng kiểu kết quả với bản đọc từ file |
| `backend/app/agent/kg_tool.py` | Tool của Agent: Neo4j trước, lỗi thì rơi về bản đọc từ file; đổi kết quả sang `GraphEdge` / `NextConcept` của `TurnContext` |
| `scripts/checks/check_kg.py` | Báo cáo kiểm tra đồ thị; xuất bảng rà soát cạnh |
| `scripts/dev/sync_kg_neo4j.py` | Kiểm tra registry → ghi Neo4j → đối chiếu Neo4j với file trên cả 40 concept |

Registry là nguồn chuẩn. Neo4j chỉ là bản sao để truy vấn: mỗi lần đồng bộ ghi đè toàn bộ trong một transaction.

Module KG tự đọc những trường nó cần từ registry và bỏ qua trường khác, không dùng schema authoring trong `backend/app/curriculum.py`.

## 2. Kiểm tra khi nạp (FR08-AC1)

`KnowledgeGraph` không tạo được nếu registry có **lỗi**; script đồng bộ cũng từ chối ghi Neo4j.

| Loại | Mã | Nội dung |
|---|---|---|
| Lỗi | `duplicate_concept_id`, `duplicate_skill_id`, `duplicate_edge_id`, `duplicate_source_id`, `duplicate_edge` | ID trùng, hoặc hai cạnh cùng loại nối cùng một cặp concept |
| Lỗi | `unknown_concept`, `unknown_source` | Cạnh trỏ tới concept hoặc nguồn không tồn tại |
| Lỗi | `self_loop`, `reversed_edge`, `cycle` | Tự trỏ; có cả A → B lẫn B → A; chu trình (thông báo ghi rõ đường đi) |
| Lỗi | `edge_id_direction_mismatch` | ID dạng `PRE-A-B` không khớp chiều A → B của cạnh |
| Lỗi | `approved_without_reviewer` | Ghi `human_approved` nhưng thiếu người duyệt hoặc thời điểm duyệt |
| Lỗi | `concept_without_skill` | Concept không có skill |
| Cảnh báo | `transitive_redundant` | Cạnh A → C đã suy ra được qua đường khác (ví dụ N01 → N03 qua N02) |
| Cảnh báo | `grade_order` | Concept nền được xếp lớp cao hơn concept cần nó |
| Cảnh báo | `isolated_concept` | Concept không có cạnh prerequisite nào |
| Cảnh báo | `generic_rationale` | Cạnh dùng chung một câu căn cứ mẫu |
| Cảnh báo | `not_approved` | Cạnh (hoặc concept ở hai đầu) chưa được duyệt |

Kết quả trên registry hiện tại (14/11/2026): **0 lỗi**. Cảnh báo: 9 cạnh `transitive_redundant`, 68/68 cạnh `generic_rationale`, 68/68 cạnh `not_approved`. Concept gốc là N01 và N04; có 13 concept cuối.

## 3. Cạnh nháp và cạnh đã duyệt

Một cạnh chỉ được coi là đã duyệt khi **cạnh và cả hai concept ở hai đầu** đều có trạng thái `human_approved`.

- Mặc định, mọi truy vấn và `KGTool` chỉ trả cạnh đã duyệt. Với registry hiện tại, kết quả là **không có cạnh nào**: Agent không backtrack và không chuyển concept qua KG được.
- `KGTool(include_drafts=True)` trả cả cạnh nháp. Đây là lựa chọn phải bật tường minh, dành cho dev và đánh giá nội bộ. `StubTools` trong khung LangGraph đang bật chế độ này.
- Mỗi cạnh trả về mang `review_status`, và decision log ghi `graph_version`, nên luôn truy được quyết định nào dựa trên cạnh nháp.

Không được bật `include_drafts` cho phiên với học sinh thật trước khi cạnh được duyệt (README của `content/curriculum`, mục Review và công bố).

## 4. Truy vấn (FR08-AC2)

| Truy vấn | Kết quả |
|---|---|
| `prerequisites(concept_id, max_depth=1 hoặc 2)` | Các cạnh A → B kèm `depth`: 1 nếu B là concept đang hỏi, 2 nếu B là một prerequisite trực tiếp của nó. Mỗi cạnh có `edge_id`, skill của concept nguồn, `review_status` |
| `successors(concept_id)` | Các concept nhận concept đang hỏi làm prerequisite, kèm `edge_id` và skill của **các prerequisite trực tiếp khác** của concept đó |
| `neighbourhood(concept_id)` | Cả hai, trong một lần gọi (tính là một tool call) |

Trong `TurnContext`: `edges` (≤ 24) là prerequisite 1–2 tầng, `next_concepts` (≤ 12) là concept kế tiếp, `kg_source` và `graph_version` cho biết nơi trả lời và phiên bản đồ thị. Trên registry hiện tại, concept nhiều cạnh nhất có 11 cạnh prerequisite trong 2 tầng và 6 concept kế tiếp; test kiểm tra cả 40 concept đều nằm trong giới hạn.

Không có cạnh `NEXT_CONCEPT`: concept kế tiếp được suy từ cạnh `PREREQUISITE_OF` đi ra.

## 5. Agent dùng KG như thế nào

| Việc | Cách làm | Luật gate |
|---|---|---|
| Ôn prerequisite (`backtrack`) | Chỉ lùi **một tầng mỗi bước**, tới prerequisite trực tiếp của concept đang học. Lùi tiếp tầng nữa là một bước backtrack khác; return stack tối đa 2 | G05, G08 |
| Không coi cả graph là điểm yếu (FR08-AC3) | `backtrack` chỉ hợp lệ khi có bằng chứng về **đúng skill nền đó**: lỗi vừa chấm được quy cho skill đó, câu trả lời cho câu hỏi kiểm tra skill đó đã được xác minh là chưa đạt, có giả thuyết lỗi đang mở trên skill đó, hoặc ước lượng thấp từ lịch sử (≥ 2 observation) | G18 |
| Chưa có bằng chứng | Rule-policy hỏi kiểm tra trước (`diagnose` / `probe_prerequisite`), mỗi skill một lần trên một bài. **Đã hỏi chưa phải là bằng chứng**: xem bảng bên dưới. Prerequisite mà học sinh đã có ước lượng tốt thì bỏ qua | |
| Hỏi kiểm tra skill ở tầng 2 | Được phép, nhưng `edge_ids` phải là cả đường đi từ concept đang học (2 cạnh nối nhau) | G05 |
| Chuyển concept (`advance_concept`) | Là đi theo KG: phải trích đúng một cạnh trong `next_concepts` và bài được chọn phải thuộc concept đó; bỏ `edge_ids` hoặc không có KG thì bị từ chối. Rule-policy bỏ concept còn prerequisite khác đang yếu và ưu tiên concept mà các prerequisite khác đã có bằng chứng tốt | G05, G07, G19 |
| Không lặp concept trong một nhánh (FR08-AC4) | Không backtrack tới concept đang nằm trong return stack | G08 |
| Ghi ứng viên được dùng và bị bỏ (FR08-AC2) | Decision log có `candidate_edge_ids` (mọi cạnh KG trả về trong lượt) và `final.edge_ids` (cạnh được dùng) | |
| No-KG | Không gọi tool KG: `edges` và `next_concepts` rỗng, không backtrack, không chuyển concept (chỉ luyện tiếp hoặc tăng độ khó trong concept hiện tại) | G19 |

Tầng 2 hiện chỉ để Agent tham khảo và hỏi kiểm tra. Rule-policy không dùng tầng 2.

**Câu hỏi kiểm tra prerequisite và kết quả** (`StudentState.probes`, xóa khi đổi bài). Mỗi câu hỏi được gắn với quyết định đã hỏi, lượt trả lời và kết quả xác minh:

| Lượt tiếp theo của học sinh | Trạng thái câu hỏi | Tính là bằng chứng thiếu skill nền |
|---|---|---|
| Xin gợi ý, tạm dừng, tiếp tục | `pending` (chưa trả lời) | Không |
| Nộp bài làm (không trả lời câu hỏi) | `unverified` | Không; bài nộp vẫn được chấm như thường |
| Nhắn tin trả lời, không xác minh được | `unverified` | Không |
| Nhắn tin trả lời, xác minh là đạt | `demonstrated` | Không; không hỏi lại skill đó trên bài này |
| Nhắn tin trả lời, xác minh là chưa đạt | `not_demonstrated` | **Có** (`probe_failed`) |

Bộ xác minh câu trả lời (`Services.probe_checker`) hiện là stub luôn trả `unverified`. Vì vậy trong khung hiện tại, hỏi kiểm tra chưa bao giờ dẫn tới backtrack; đường `not_demonstrated` mới chỉ được test bằng bộ xác minh giả.

## 6. Neo4j

Lược đồ:

```text
(:Concept {concept_id, title, strand, objective, grade_levels, skill_ids, pilot,
           review_status, alignment_source_id, content_version})
(:Concept)-[:PREREQUISITE_OF {edge_id, rationale, source_id, review_status,
                              effective_status, human_reviewer, reviewed_at}]->(:Concept)
(:KGMeta {id: 'registry', content_version, fingerprint, concepts, edges, synced_at})
```

`RELATED_TO` và `PART_OF` được đồng bộ cùng cách nếu registry có; hiện registry chỉ có `PREREQUISITE_OF`. `effective_status` là trạng thái duyệt đã tính cả hai concept đầu mút.

Khi Neo4j có vấn đề, lượt dạy vẫn chạy:

| Tình huống | Xử lý | Ghi trong decision log |
|---|---|---|
| Neo4j không kết nối được hoặc truy vấn lỗi | Dùng bản đọc từ file; nghỉ gọi Neo4j 30 giây | `tool_errors = ["kg_neo4j:<tên lỗi>"]`, `kg_source = "registry_file"` |
| Neo4j đang giữ bản registry cũ (dấu vân tay khác file trên đĩa) | Dùng bản đọc từ file | `tool_errors = ["kg_neo4j:stale_sync"]` |
| Không cấu hình Neo4j | Dùng bản đọc từ file | `kg_source = "registry_file"` |
| Concept không có trong registry | Không trả cạnh nào | `tool_errors = ["kg:unknown_concept"]` |

Đo trên máy dev (14/11/2026, 200 truy vấn mỗi loại, Neo4j 5.26 chạy Docker cùng máy): bản đọc từ file trung vị 0,04 ms; Neo4j trung vị 11 ms, p95 21 ms. Khi Neo4j tắt, lượt đầu tiên chờ khoảng 1 giây (timeout kết nối), các lượt trong 30 giây sau không chờ. Đây là số đo một lần trên một máy, chưa phải kết quả đánh giá latency của hệ thống.

Mật khẩu mặc định `local-dev-only` trong `compose.yaml` và `neo4j_store.py` chỉ dùng cho máy cá nhân (cổng chỉ mở ở 127.0.0.1). Môi trường khác phải đặt `NEO4J_PASSWORD`.

## 7. Rà soát 68 cạnh

[kg-edge-review.v1.csv](kg-edge-review.v1.csv) liệt kê từng cạnh: concept nền, concept cần nền, lớp, cảnh báo tự động, căn cứ hiện tại, và các cột trống để người duyệt điền (giữ / sửa / bỏ, căn cứ chương trình, người duyệt, ngày). File mở được bằng Excel; khi lưu chọn dạng **CSV UTF-8**.

Chạy lại `check_kg.py --worksheet` trên file đã có sẽ **giữ nguyên các cột người duyệt đã điền** (ghép theo `edge_id`) và chỉ cập nhật các cột thông tin. Cạnh đã bị gỡ khỏi registry mà có nội dung duyệt được giữ ở cuối bảng với trạng thái `removed_from_registry`. Nếu file không đọc lại được (sai mã hóa, thiếu cột, trùng `edge_id`) thì script từ chối ghi đè.

**Hiện trạng (14/11/2026): 0/68 cạnh có căn cứ chương trình.** Bảng mới chỉ là danh sách cần rà soát. Việc còn lại là đọc chương trình môn Toán 2018, ghi mục/trang và lý do cho từng quan hệ, và đánh dấu quan hệ nào là suy luận thiết kế của nhóm để người khác review.

Việc duyệt là của người: script không tự đổi trạng thái. Sau khi duyệt, cập nhật `review` của cạnh và concept trong registry (kèm `human_reviewer`, `reviewed_at`), sửa `rationale` thành căn cứ riêng của cạnh, rồi chạy lại kiểm tra và đồng bộ.

Điểm cần người duyệt quyết định:

- 9 cạnh `transitive_redundant`: giữ làm prerequisite trực tiếp hay bỏ. Cạnh trực tiếp làm concept đó xuất hiện ở tầng 1 khi backtrack; bỏ cạnh thì nó chỉ còn ở tầng 2.
- Cả 68 cạnh đang ghi nguồn `SRC-PROJECT-PLAN` với cùng một câu căn cứ mẫu. Nguồn này là danh mục của dự án, không phải căn cứ chuyên môn cho từng cạnh.

## 8. Giới hạn hiện tại

| Giới hạn | Ảnh hưởng | Khi nào xử lý |
|---|---|---|
| Chưa có cạnh nào được duyệt | KG chỉ dùng được ở chế độ dev (`include_drafts=True`) | Sau khi rà soát theo §7 |
| Chưa có bộ xác minh câu trả lời cho câu hỏi kiểm tra prerequisite (stub luôn trả `unverified`) | Hỏi kiểm tra chưa tạo được bằng chứng, nên chưa dẫn tới backtrack; prerequisite chỉ được ôn khi có bằng chứng loại khác | Bước LLM extraction (Member 3), chốt định dạng với Member 1 |
| Học sinh trả lời câu hỏi kiểm tra bằng lượt `message`; UI chưa có quy ước này | Nếu UI gửi câu trả lời dưới dạng bài nộp thì câu hỏi bị đóng là `unverified` | Chốt với Member 2 |
| Problem bank giả chỉ có bài của E02, A02, N01, E03 | Backtrack và chuyển concept chỉ thử được trên các concept này | Khi Member 2 có problem bank thật |
| Agent chưa phải LLM | Chưa có quyết định "có cần tra KG không"; tool KG được gọi cố định mỗi lượt | Bước nối LLM |
| `advance_concept` chỉ đi được tới concept liền kề trên KG; No-KG không chuyển concept trong phiên | Không chuyển được sang concept không liên quan (ví dụ từ một concept cuối sang concept gốc khác); phiên kết thúc khi hết bài | Chốt cùng nhóm: việc chọn chủ đề mới giữa các phiên thuộc API hay Agent |
| Chưa đánh giá chất lượng gợi ý prerequisite (RQ2) | Chưa có số liệu Full so với No-KG | Bước script đánh giá; nhãn chấp nhận được phải do người duyệt độc lập, không lấy chính graph làm đáp án (plan §18) |
| `KGTool` đọc registry một lần khi khởi động | Sửa registry phải khởi động lại tiến trình và đồng bộ lại Neo4j | Đủ dùng cho hiện tại |
| Bước kiểm tra KG và test Neo4j chưa có trong CI | CI chỉ chạy phần test không cần Neo4j | File workflow dùng chung cả nhóm; cần thống nhất trước khi sửa |

## 9. Lệnh

```powershell
# Kiểm tra đồ thị, không cần Neo4j
.\.venv\Scripts\python.exe scripts/checks/check_kg.py --verbose
.\.venv\Scripts\python.exe scripts/checks/check_kg.py --worksheet docs/implementation/agent/kg-edge-review.v1.csv

# Neo4j
docker compose --profile kg up -d neo4j
.\.venv\Scripts\python.exe scripts/dev/sync_kg_neo4j.py
.\.venv\Scripts\python.exe scripts/dev/sync_kg_neo4j.py --verify-only

# Test (test Neo4j chỉ chạy khi đặt RUN_NEO4J_TESTS=1)
.\.venv\Scripts\python.exe -m pytest tests/test_kg.py tests/test_agent_policy.py tests/test_agent_graph.py -q
$env:RUN_NEO4J_TESTS = "1"; .\.venv\Scripts\python.exe -m pytest tests/test_kg.py -q
```

Dùng Neo4j trong engine:

```python
from app.agent.kg_tool import KGTool
from app.agent.stubs import StubTools
from app.kg.neo4j_store import Neo4jGraph

tools = StubTools(kg=KGTool(neo4j=Neo4jGraph.from_env(), include_drafts=True))
```

`Neo4jGraph.from_env()` trả `None` khi không có biến `NEO4J_URI`; khi đó tool chỉ dùng bản đọc từ file.
