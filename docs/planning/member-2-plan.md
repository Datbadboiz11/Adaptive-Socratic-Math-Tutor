# Kế hoạch thực hiện cho Member 2

Kế hoạch gốc được rà soát ngày 16/11/2026, dựa trên phân công cập nhật ngày 12/11/2026 ở [plan tổng, mục 23](project-plan.md).

**Mục 1–6 trình bày toàn bộ phạm vi công việc, sáu chặng triển khai, lịch gợi ý, đầu ra và tiêu chí nghiệm thu của Member 2.** Sau khi liệt kê đầy đủ kế hoạch, [mục 7 — Trạng thái đã hoàn thiện](#7-trạng-thái-đã-hoàn-thiện) mới tổng hợp tiến độ, bằng chứng kiểm tra và các phần còn thiếu.

## 1. Mục tiêu và vai trò của bạn

Bạn chịu trách nhiệm chính cho chuỗi **nội dung có kiểm duyệt → truy xuất phù hợp → trải nghiệm học → báo cáo có bằng chứng**, cùng phần đánh giá retrieval của RQ3.

| Bạn làm đầu mối | Phối hợp bắt buộc |
|---|---|
| Taxonomy, concept–skill registry, chuẩn nội dung và ma trận độ phủ | Member 1 chốt hành vi có thể chấm; Member 3 chốt cách dùng trong Agent/KG |
| Pipeline LLM tạo nháp, checker và quy trình review | Cả ba cùng biên soạn, review chéo; người có chuyên môn rà nội dung khó |
| Đồng bộ registry/KB sang PostgreSQL và pgvector | Member 1 review migration, cấu hình DB/CI và tương thích session |
| Embedding, retrieval, API/tool cho Agent | Member 3 tích hợp tool, sử dụng kết quả và kiểm tra phản hồi |
| Student UI, hiển thị trạng thái, nội dung learning report | Member 1 cung cấp API/số liệu; Member 3 cung cấp response/decision contract |
| Query set, relevance labels, đánh giá retrieval | Cùng Member 3 chạy Full/No-RAG và chấm chất lượng hint |

Mỗi người biên soạn khoảng 13–14 concept cho mục tiêu 40. Bạn quản lý template, tiến độ và chất lượng chung; khối lượng biên soạn và gán nhãn được chia cho cả nhóm. Member 3 sở hữu Neo4j, policy, LangGraph và backtrack; Member 1 sở hữu validator, observation/BKT và backend phiên học.

### Phạm vi biên soạn và review của Member 2

Phân công trong [workboard v1](../../content/curriculum/member2-workboard.v1.json) được ghi nhận cùng [xác nhận của nhóm ngày 23/11/2026](../../content/curriculum/member2-workboard-confirmation.v1.json).

| Công việc | Số concept | Danh sách |
|---|---:|---|
| Biên soạn/hoàn thiện nội dung; Member 3 review chéo | 13 | N02, N05, N08, A01, A04, A07, A10, E03, E06, E09, F02, F05, F08 |
| Review chéo nhóm concept Member 1 phụ trách | 13 | N01, N04, N07, N10, A03, A06, A09, E02, E05, E08, F01, F04, F07 |

Member 2 đồng thời điều phối template, nguồn, chất lượng và tiến độ nội dung cho toàn bộ danh mục 40 concept. Review phục vụ xuất bản cần xem mục tiêu/phạm vi, alignment và pack khi có đủ nội dung, đồng thời ghi người và thời điểm duyệt thực tế.

## 2. Các điểm giao cần chốt khi triển khai

Thống nhất các điểm giao dưới đây với Member 1 và Member 3 trước khi đưa chức năng tương ứng vào luồng học. Quyền quyết định, dữ liệu đầu vào/đầu ra và khả năng tương thích phiên cũ phải được ghi rõ.

1. **ID cũ và mới:** web/BKT đang dùng `CON-LINEAR-01` / `SK-LIN-SOLVE`; registry đề xuất `E02` / `SK-E02-SOLVE`. Mapping hiện chỉ là `proposed`. Cùng Member 1 quyết định adapter/version và cách xử lý lịch sử trước khi đồng bộ; không gộp mastery chỉ vì tên gần giống.
2. **Định dạng bài:** `ProblemPublic` còn bắt buộc `equation`, miền `real_numbers`; pilot có `numeric`, `evaluate`, `polynomial`, `linear_equation`, `quadratic_vertex`. Cần contract phân biệt loại task và khả năng chấm. Checker authoring cho năm loại không đồng nghĩa online validator đã hỗ trợ năm loại.
3. **Mức hint:** PRD có 0–4; contracts, DB và UI hiện 0–3. Member 3 quyết định semantics, Member 1 xử lý contract/migration; bạn cập nhật content và UI sau khi thống nhất. Nếu tạm giữ 0–3 cho mốc tích hợp, ghi rõ phần FR-13 còn thiếu.
4. **Response/report contracts:** schema `TutorResponse` khai báo `reviewed_fallback`, còn runtime dùng `draft_template`; report runtime cũng rộng hơn `SessionReport` nền tảng. Dùng OpenAPI runtime làm cơ sở đối chiếu frontend, chuẩn hóa có version cùng nhóm.
5. **Trạng thái chủ đề:** `/topics` hiện lấy khả năng validator từ cờ tutor chung. Khi mở rộng phải có capability theo task/concept; chỉ đưa chủ đề vào luồng chấm khi nội dung, validator và policy đều sẵn sàng.

## 3. Thứ tự triển khai

Đường phụ thuộc chính:

```text
Chốt ID, task và mức hỗ trợ
    → Chuẩn hóa nội dung + duyệt một nhóm nhỏ
    → Đồng bộ KB + embedding + retrieval
    → Member 3 nối Agent/generator + kiểm tra đầu ra
    → UI/report chạy xuyên suốt
    → Mở rộng 10 → 20 → 30 → 40 concept và thực nghiệm
```

Việc soạn nội dung và chuẩn bị relevance labels có thể chạy đồng thời với lập trình sau khi schema đã ổn định. Đánh giá retrieval trên dev bắt đầu ngay từ bản đầu, không đợi đủ 40 concept.

### Chặng 1 — Chốt hợp đồng và tiêu chí sẵn sàng

**Ưu tiên P0. Đầu ra cần có:** một bản contract được ba người review, fixtures chung và bảng công việc có owner.

- Đọc [PRD FR-03/09/16/18](../product/prd.md), [hướng dẫn curriculum](../../content/curriculum/README.md), rồi đối chiếu các điểm giao ở mục 2.
- Chốt `concept_id`, `skill_id`, `problem_id`, `content_id`, version, task type, difficulty, review status, disclosure và provenance. Chốt rõ trường nào chỉ server/validator được thấy.
- Với Member 1, chốt `ProblemPublic` mới, readiness API và report contract. Giữ adapter cho session cũ hoặc tạo version mới khi thay đổi không tương thích.
- Với Member 3, chốt `RetrievalRequest/Result`, response của `different_example`, action/hint level và trace IDs. Tool do server kiểm soát disclosure, không nhận quyền truy cập private reference từ đề xuất của LLM.
- Tạo ma trận 40 concept: owner, reviewer, skill/hành vi đo, task, số bài/họ mẫu, ví dụ, lỗi, hint, nguồn, trạng thái duyệt, validator, test, ngày cập nhật.
- Ghi mức độ sẵn sàng theo từng chiều. Một concept chỉ được bật để học khi nội dung đã duyệt, validator hỗ trợ và luồng UI/policy tương ứng đã được kiểm tra.

**Nghiệm thu:** các fixtures về ID/task/hint/report dùng chung được; không còn mỗi module diễn giải trường dữ liệu theo một cách. Số concept “có registry”, “có pack”, “đã duyệt” và “chạy được end-to-end” được báo riêng.

### Chặng 2 — Hoàn thiện pipeline nội dung và review

**Ưu tiên P0; là phần AI bạn cần thể hiện ngoài retrieval.**

Pipeline đề xuất:

```text
Yêu cầu của concept + scope được duyệt
    → LLM sinh nháp có cấu trúc
    → Pydantic + kiểm tra tham chiếu + checker toán
    → Người khác review toán, sư phạm, nguồn và mức tiết lộ
    → Ghi phiên bản nội dung được duyệt
    → Đồng bộ vào KB phục vụ runtime
```

Cách thực hiện:

1. Tận dụng `ConceptPack` và template đang có. Tạo CLI soạn nháp, ví dụ `scripts/authoring/draft_content.py`; prompt có mục tiêu, supported/excluded forms, task kind, số họ mẫu, quy tắc hint và nguồn.
2. Mỗi lượt tạo một concept hoặc một họ bài để dễ kiểm tra và sửa lỗi. Lưu model ID, prompt version, cấu hình, thời điểm, usage và kết quả kiểm tra; không ghi key vào artifact.
3. Output đi vào vùng nháp riêng có version. Chỉ hợp nhất vào registry/bank sau review; pipeline không tự sửa nội dung đã duyệt hoặc gán `human_approved`.
4. Kiểm tra ID trùng, skill reference, family/source group, đáp án/bước tương đương, điều kiện áp dụng, ví dụ sai, hint và ngôn ngữ tiếng Việt. Schema hợp lệ chưa chứng minh nội dung đúng.
5. Review thêm chất lượng phép đo: bài N04 phải thực sự kiểm tra rút gọn, không chỉ giá trị phân số tương đương; F05 hiện mới đo tọa độ đỉnh, còn trục đối xứng phải được đặc tả/test riêng nếu tính là hoàn thành toàn concept.
6. Với dạng chưa được checker hỗ trợ, cùng Member 1 bổ sung phương pháp kiểm tra và test trước khi mở rộng. Không ép nội dung căn, phân thức, bất phương trình, mũ/logarit vào checker đa thức hiện tại.
7. Review chéo theo vòng, chia lại quota theo độ khó và số giờ pilot. Duyệt concept, alignment, pack và cạnh graph là các việc riêng; pack được duyệt chưa đủ để `safe_chunks()` công bố.

**Phạm vi nghiệm thu cập nhật ngày 25/11/2026:** 13 concept theo phân công Member 2. Bộ check chạy đủ 13 cấu hình và các dạng số, đại số, phương trình, hàm. N02 dùng để nghiệm thu gọi LLM thật. A02/E02 thuộc các hồ sơ pilot lịch sử.

**Nghiệm thu:** tái tạo được nháp từ config; checker báo lỗi có vị trí; có reviewer và lịch sử sửa; nội dung chưa duyệt vẫn không xuất hiện trong retrieval cho học sinh. Các test dùng dữ liệu được duyệt giả lập phải ghi rõ đó là fixture synthetic.

### Chặng 3 — Đồng bộ KB và xây retrieval thực sự

**Ưu tiên P0. Bạn triển khai; Member 1 review DB/CI, Member 3 review tool contract.**

#### 3.1. Nguồn chuẩn và đồng bộ

- Registry và bank có version là nguồn nội dung chuẩn; PostgreSQL/pgvector là bản phục vụ runtime, Neo4j do Member 3 đồng bộ từ cùng nguồn.
- Thêm migration mới theo thứ tự còn trống, ví dụ `003_curriculum_kb.sql`. Giữ checksum migration và tính bất biến của version theo thiết kế `manage.py` hiện có.
- Các bảng tối thiểu: concept/skill và mapping có version; `kb_chunks`; embeddings có model/dimension/version; `kb_sync_runs` hoặc manifest tương đương.
- Chốt rõ khóa chunk/version và liên kết embedding → chunk. Cùng content ID nhưng nội dung mới cần version/hash mới; không để session hoặc citation cũ trỏ sang văn bản đã thay đổi.
- CLI sync có `--dry-run`, kiểm tra trước khi ghi, diff số lượng/hash, chạy lại không tạo trùng. Tạo embedding theo lô ngoài transaction dài rồi publish một snapshot hoàn chỉnh.
- Chỉ kích hoạt snapshot khi nội dung và embeddings đầy đủ. Nếu bị ngắt giữa chừng, runtime tiếp tục dùng snapshot trước đó; version bị rút duyệt phải bị loại khỏi snapshot phục vụ mới.
- Chuẩn bị PostgreSQL có extension vector và môi trường CI tương ứng. Khai báo extension trong migration, chọn image pgvector phù hợp và kiểm tra tương thích version; nghiệm thu riêng lượt chạy local, Docker và CI từ xa.

#### 3.2. Chunk và ranh giới dữ liệu

Metadata tối thiểu: `content_id`, `content_version`, `concept_id`, `skill_ids`, `kind`, grade, difficulty/applicability, nguồn, review, disclosure/hint level, text hash và provenance. Nội dung không áp dụng cho một difficulty cụ thể cần biểu diễn rõ, không tự bịa độ khó.

- Chunk theo ý nghĩa: một giải thích, một hint hoặc một ví dụ, giữ nguyên công thức và điều kiện. Với KB nhỏ, chưa cần chia cứng theo số ký tự.
- Giữ private references trong kho dành cho validator. Retrieval cho generator mặc định chỉ có nội dung đã duyệt và được phép ở mức hỗ trợ hiện tại.
- Ví dụ khác cần định danh và scope riêng; loại bài hiện tại và biến thể quá gần theo problem/family/source group ở nhánh lấy ví dụ. Explanation chung cùng concept vẫn có thể hợp lệ.
- `safe_chunks()` có thể làm nền cho baseline metadata/direct lookup. Khi bổ sung examples, thêm projector và test riêng; không trả thẳng toàn bộ `ConceptPack`.

#### 3.3. Chiến lược retrieval

1. ID đã biết và nội dung xác định rõ: lấy trực tiếp, không gọi embedding.
2. Truy vấn theo mục đích: xác định explanation/hint/example và concept/skill ứng viên từ state hợp lệ.
3. Áp điều kiện review, phiên bản, scope, disclosure, grade/difficulty và loại trừ nội dung bị cấm **trước khi chọn kết quả cuối**.
4. Xếp hạng ngữ nghĩa trong tập hợp đủ điều kiện; bắt đầu bằng pgvector exact search. K thử trên dev: 1, 3, 5. Không dùng cosine score như xác suất đúng.
5. Chỉ bổ sung lexical/hybrid ranking nếu phân tích dev cho thấy lỗi đáng kể với ký hiệu, thuật ngữ hoặc tên concept. Chốt reranker sau khi có phép đo cho thấy đáng thêm latency/cost.
6. Không có chunk đủ điều kiện: trả kết quả rỗng kèm reason; Member 3 dùng template đã duyệt hoặc hỏi làm rõ. Không mượn nguồn chưa lấy được và không tự hạ review/disclosure filter.

Theo [tài liệu pgvector](https://github.com/pgvector/pgvector#filtering), exact search và ANN có đánh đổi tốc độ/recall; filter với ANN cần được đo riêng. Với KB ban đầu nhỏ, exact search là lựa chọn khởi đầu để kiểm chứng chất lượng. Chỉ thử HNSW khi phép đo cho thấy truy vấn là nút thắt; so kết quả với exact làm mốc.

#### 3.4. Contract gợi ý cho Member 3

```text
retrieve_teaching_content(
    query, concept_id, target_skill_id, purpose,
    allowed_hint_level, learner_scope,
    active_problem_id, active_source_group, kb_snapshot_version
) → {
    retrieval_id, chunks: [content_id, version, text, source, kind, disclosure],
    retrieval_config_version, embedding_version, elapsed_ms, fallback_reason
}
```

Contract cần có version và giữ khả năng đối chiếu với contract đề xuất. Tool chỉ nhận query; server bind scope từ state đáng tin cậy. Client/LLM không cấp `learner_scope`, hint permissions, snapshot hoặc exclusions. Log nội bộ ghi ranking/distance; dữ liệu đưa vào generator/UI phải được chọn trường. Chặng 4 chịu trách nhiệm tạo state từ session canonical/legacy và đưa context thực sự vào generator.

**Nghiệm thu:** sync hai lần không trùng; không publish snapshot dở; đổi model/dimension không trộn embeddings; draft/private/out-of-scope không lọt kết quả; có direct lookup, semantic retrieval và nhánh rỗng; mỗi kết quả truy vết được về đúng phiên bản.

### Chặng 4 — Nối Agent, hoàn thiện UI và learning report

**Ưu tiên P0; tích hợp sau bản retrieval nhỏ đầu tiên.**

#### 4.1. Tích hợp cùng Member 3

- Member 3 thêm node/tool retrieval và luồng sử dụng nội dung; bạn cung cấp tool, fixtures và cách đọc lỗi. `model_wording()` hiện chỉ chọn câu trong enum nên cần thay đổi có chủ đích ở phía generator/policy/guard.
- Ghi riêng content IDs được truy xuất và content IDs thực sự đưa vào generator. Không suy ra nguồn “đã dùng” từ danh sách top-K rồi gắn citation vào mọi câu.
- Giữ pipeline inference ngoài transaction dài của session theo `tutor_service.py`; retrieval lỗi không tạo assessment sai hay observation mới.
- Khi replay/resume, sử dụng result/content version đã ghi theo request; không chạy lại embedding và truy xuất với KB mới cho một turn đã commit.
- Chốt feature flag/config để chạy Full/No-RAG trên cùng state. No-RAG phải bỏ retrieval context thật sự, kể cả cache hoặc metadata chứa nội dung dạy.
- Member 3 tiếp tục chịu trách nhiệm kiểm tra toán/mức tiết lộ của đầu ra. Metadata filter chỉ kiểm soát tài liệu đầu vào.

#### 4.2. Student UI

Tách dần `workspace.tsx` khi sửa chức năng: lớp API/types, hook quản lý session/request, màn bài làm, tutor feedback và report. Giữ ổn định hành vi retry/state version đã có.

- Render theo task type từ server; bỏ nhãn “PHƯƠNG TRÌNH BẬC NHẤT”, mô tả “6 bài” và tên skill cố định khi hỗ trợ nhiều miền.
- Dùng types từ OpenAPI hoặc contract dùng chung có kiểm tra drift. Frontend không lấy private schema làm type bài công khai.
- Chọn cách render công thức sau một spike nhỏ về phân số, số mũ, hệ phương trình và tiếng Việt; kiểm tra accessibility và nội dung không tin cậy. Thư viện cụ thể chốt khi triển khai.
- Phân biệt bài hiện tại, câu hỏi gợi mở, ví dụ hỗ trợ và bài kiểm tra mới. Hiển thị rõ `unverified`, `needs_clarification`, đúng tự làm và đúng sau hỗ trợ.
- Giữ `request_id` khi retry cùng lần gửi; request mới khi sửa bài; flush draft trước điều hướng. Nếu thêm dự phòng nháp ở client, giới hạn theo hồ sơ/session và không trình bày là đã lưu server.
- Chỉ hiển thị nguồn/version của nội dung thực sự được trả về; ưu tiên tên nguồn dễ đọc, không bắt học sinh xử lý ID kỹ thuật.
- Kiểm tra mobile 390px, desktop 1440px, bàn phím/focus, loading, timeout, hai tab, pause/resume và đổi hồ sơ.

#### 4.3. Learning report

Member 1 tính toán/trả dữ liệu; bạn chốt nội dung và hiển thị. Nâng contract report theo từng skill/concept với:

- Số bài tự làm đúng, đúng sau hỗ trợ, bài lặp, bài chưa xác minh; tách kết quả bài khỏi số observation.
- Mastery trước/sau khi có observation hợp lệ, evidence count trước/sau, parameter version/source và thời điểm cập nhật. Ghi rõ count trong phiên và count tích lũy nếu hiển thị cả hai.
- Snapshot tại cuối phiên: không lấy mastery hiện tại từ một phiên sau để vẽ lại mức tiến bộ của report cũ. Đây là tính chất đã có cần giữ khi mở rộng.
- Lỗi có evidence và trạng thái `suspected`/`supported`/bác bỏ; thiếu dữ liệu thì hiển thị thiếu dữ liệu.
- Gợi ý ôn với lý do, evidence IDs hoặc nguồn tương ứng. Prerequisite do graph đề xuất chưa tự trở thành phần học sinh đã được xác nhận là yếu.
- Report chỉ tổng hợp dữ liệu có thể đối soát; LLM nếu dùng chỉ diễn đạt các facts được cấp, không tự tính số liệu hoặc kết luận thành thạo.

**Nghiệm thu:** nộp sai → hint từ KB → sửa đúng có hỗ trợ → bài độc lập mới → report → reload/resume chạy được; report khớp API/log, không đổi số khi retry và không trộn dữ liệu hai hồ sơ. Chạy thêm concept số/hàm khi validator tương ứng sẵn sàng.

### Chặng 5 — Mở rộng độ phủ và chuẩn bị relevance dataset

**Phạm vi triển khai hiện hành theo yêu cầu người dùng ngày 26/11/2026:** Member 2 làm tiếp trên đúng 13 concept được phân công. Nội dung của 27 concept Member 1/3 chờ chủ sở hữu hoàn thành rồi tiếp nhận sau. Các mục tiêu 40 concept bên dưới là mục tiêu toàn nhóm; không coi phần còn thiếu của hai thành viên khác là việc Member 2 phải tự biên soạn hoặc điều kiện chặn gói 13 concept hiện tại.

Triển khai theo lô **10 → 20 → 30 → 40 concept**, kiểm tra end-to-end và chất lượng từng lô. Sau lô đầu, điều chỉnh giờ công bằng thời gian thực tế cho một concept và một ca gán nhãn. Cột mốc tham chiếu dưới đây ghi số liệu khi lập kế hoạch ngày 16/11/2026; tiến độ và các đầu ra đã có được tổng hợp riêng tại mục 7.

| Hạng mục | Mốc tham chiếu khi lập kế hoạch | Mục tiêu theo plan tổng |
|---|---:|---:|
| Concept trong registry | 40 | 40 được chốt và có ma trận nghiệm thu |
| Concept có pack nháp | 10 | 40 đủ nội dung và kiểm duyệt |
| Bài authoring | 60 | 240–300; ít nhất 6/concept và 3 họ mẫu/concept |
| Ví dụ giải | 30 | 120–160; ít nhất 3/concept |
| Mẫu lỗi | 20 error fixtures | Taxonomy chi tiết mục tiêu 50–100; cần chuẩn hóa ID/nhãn trước khi tính số kiểu độc lập |
| Query có relevance labels | Chưa thấy bộ riêng | 120–200, có phân tầng và split được khóa |

Với mốc ban đầu 10 pack nháp, phần bổ sung cho 30 concept cần ít nhất 180 bài và 90 ví dụ để đạt mức tối thiểu. Ngoài việc bổ sung, 10 pack đang có cũng cần review và kiểm tra độ phủ hành vi đo.

Bạn sở hữu bộ query retrieval; Member 1 và Member 3 làm đầu mối các bộ bước giải/tình huống. Dùng chung `family_id`/`source_group` và manifest để tránh mẫu gần nhau lọt qua các split.

Cách làm relevance set:

1. Pilot 20–30 query dev để viết guideline: paraphrase tiếng Việt, lỗi thuật ngữ, yêu cầu giải thích, hint, ví dụ khác, query mơ hồ, ngoài scope và không có tài liệu hợp lệ.
2. Query ghi concept/skill, mục đích, hint level, điều kiện lọc, bài/source group cần loại và tập chunk-version hợp lệ.
3. Gán relevance có thứ bậc, ví dụ 0 = không phù hợp, 1 = hữu ích một phần, 2 = phù hợp trực tiếp. Vi phạm review/disclosure/scope được ghi riêng và không được coi là kết quả chấp nhận được dù giống nghĩa.
4. Relevance do người đánh giá xác nhận; score của retriever không phải nhãn chuẩn. Với KB nhỏ, có thể rà toàn bộ ứng viên hợp lệ; nếu pooling kết quả nhiều retriever phải ghi giới hạn tài liệu chưa được chấm.
5. Chia theo nhóm nguồn/tình huống/họ bài; các paraphrase cùng ý định không nằm cả dev và test. Chốt độ phủ 40 concept và các mục đích, không chỉ chốt tổng số query.
6. Đóng băng query test, qrels, KB snapshot, embedding và config trước chạy chính thức. Hai người gán test độc lập, lưu nhãn trước hòa giải và mức đồng thuận.
7. Không dùng nguyên đề/nhãn/lời giải test làm tài liệu generator truy xuất. KB chỉ chứa nội dung tổng quát phù hợp và bài authoring được phép.

**Nghiệm thu:** có coverage matrix query/concept/purpose, split manifest và qrels trỏ đúng content version; người khác chạy lại được trên cùng KB. Không dùng 60 bài authoring làm bằng chứng test độc lập.

### Chặng 6 — Đánh giá RQ3, tối ưu và bàn giao

**Phạm vi hiện hành:** thực hiện trên đúng 13 concept Member 2; phần của Member 1/3 tiếp nhận sau khi bàn giao. Ngày 27/11/2026 đã hoàn tất pipeline và lượt đo dev local theo [bàn giao Chặng 6](../implementation/member2/part6/README.md). Nhãn xác nhận/test độc lập và chấm cặp chất lượng vẫn là điều kiện riêng trước nghiệm thu RQ3 chính thức.

So sánh tối thiểu:

| Cấu hình | Mục đích |
|---|---|
| Metadata/direct lookup có thứ tự xác định | Mốc so sánh trên KB nhỏ |
| Metadata + semantic ranking | Đo giá trị thêm của embedding |
| Hybrid, nếu đã chứng minh cần trên dev | Kiểm tra cải thiện lỗi retrieval cụ thể |
| Full vs No-RAG với cùng state/generator | Cùng Member 3 đánh giá tác động lên hint thực tế |

Mọi retriever áp cùng bộ lọc bắt buộc. Truy vấn ID trực tiếp nên báo riêng để không làm đẹp điểm semantic retrieval.

- Báo Recall@K, nDCG@K và Hit@K; định nghĩa relevance threshold cho Recall/Hit trước khi chạy. Với nDCG, công bố gain dùng cho nhãn 0/1/2.
- Query không có tài liệu phù hợp: đo khả năng trả rỗng/fallback riêng; Recall/nDCG không xác định thì báo N/A và số lượng, không tự chấm là đạt.
- Phân tích theo concept/purpose, K, số chunk hợp lệ, trường hợp lỗi và nguồn query. Với KB chỉ có vài chunk mỗi concept, Recall@5 có thể cao dù ranking yếu; xem thêm K nhỏ và nDCG.
- Đo tỷ lệ vi phạm scope/disclosure/review, p50/p95, lỗi/fallback và chi phí. Mục tiêu test kiểm soát dữ liệu là không trả draft/private/bị cấm.
- Theo plan tổng, Recall@5 khoảng 0,85 là mục tiêu kỹ thuật ban đầu, p95 toàn lượt khoảng 10 giây. Các mức này chưa phải kết quả hiện tại; chốt lại bằng dev trước test, không hạ sau khi xem test.
- Full/No-RAG cần chấm đúng toán, bám lỗi, phù hợp mức hỗ trợ và tiết lộ đáp án; retrieval tốt chưa đủ chứng minh hint tốt.
- Chấm ghép cặp cùng state, ẩn cấu hình và ngẫu nhiên thứ tự. Báo khoảng tin cậy theo nhóm query/scenario gốc, không coi mọi paraphrase là mẫu độc lập.
- Lưu config, version/hash, raw rankings/outputs, qrels, metric script, thời điểm và môi trường. Phân tích cả kết quả không cải thiện.

Tối ưu theo phép đo:

1. Chỉ embedding lại text mới/đổi; cache theo hash + model/dimension/config, giữ batch có giới hạn và retry có kiểm soát.
2. Cache nội dung tĩnh theo version; nếu cache retrieval, khóa phải chứa query và toàn bộ điều kiện lọc/exclusion/snapshot. Đổi snapshot hoặc rút duyệt phải vô hiệu cache tương ứng.
3. Giới hạn context bằng chunk đã chọn và token budget; không đưa cả pack/reference solution vào prompt.
4. Đo DB query plan và candidate count trước khi thêm ANN/reranker. Thống kê riêng cold/warm cache và các mức tải đã thử.
5. Đo phía UI trước khi thêm thư viện/state framework: render lịch sử dài, request lặp và gói render toán là các chỗ cần kiểm tra khi có dữ liệu.

**Bàn giao:** phương pháp/dữ liệu/kết quả RQ3, lệnh tái lập, source manifests, hướng dẫn sync/review, report UI, regression evidence và giới hạn còn lại.

## 4. Lịch triển khai gợi ý

Chưa có deadline hiện tại hoặc số giờ bạn dành mỗi tuần. Dùng các mốc dưới đây làm kế hoạch tương đối; cập nhật sau pilot authoring/retrieval. Lịch này không thay kế hoạch 12 tuần của toàn nhóm.

| Mốc | Công việc chính của bạn | Điều kiện chuyển bước |
|---|---|---|
| Tuần A | Chặng 1; pipeline draft tối thiểu; review E02/A02; pilot guideline relevance | Contract và nguồn nội dung đã duyệt hoặc fixture synthetic dùng cho phát triển |
| Tuần B | Migration/sync/embedding/retrieval bản đầu; 20–30 query dev | Agent gọi tool được, có filter/fallback và content trace |
| Tuần C | UI/task contract, report, browser acceptance; hoàn thiện lô 10 và tiến tới 20 concept cùng nhóm | Luồng thật chạy được; concept mở cho học có validator/policy đã kiểm tra |
| Tuần D–E | Các lô 20 → 30 → 40; review chéo, qrels, dev comparison và tối ưu | Đủ coverage, không còn lỗi chặn, đủ bộ test được duyệt và khóa cấu hình |
| Tuần F | Retrieval test chính thức, Full/No-RAG, phân tích và artifacts | Có báo cáo tái lập và evidence đúng bản build |

Đây là khung 6 tuần, có thể cần thêm thời gian theo độ khó nội dung và tiến độ validator/Agent. Đặt lịch theo giờ công thực tế, giữ 15–20% quỹ thời gian cho tích hợp/sửa lỗi. Nếu trễ, giảm tính năng ngoài phạm vi như dashboard nâng cao; mọi thay đổi mục tiêu 40 concept phải được nhóm chốt trong giới hạn 30–50 đã đăng ký.

### Danh sách bắt đầu trong 5 buổi đầu

1. Lập coverage matrix 40 concept và issue cho năm điểm giao ở mục 2; thống nhất owner/reviewer với hai thành viên.
2. Tạo fixtures cho public task, retrieval result và report; chốt mapping legacy, hint level và API readiness.
3. Hoàn thiện CLI draft/check/review cho E02/A02; chuẩn bị nội dung để người khác review và 20 query dev đầu tiên.
4. Chuẩn bị migration/sync dry-run và projector chunk an toàn; chạy tests với fixture synthetic trong lúc chờ duyệt thật.
5. Nối retrieval tối thiểu vào nhánh phát triển của Agent, kiểm tra một turn có content trace; review kết quả rồi lập lịch mở rộng.

Đầu ra tuần đầu nên là hợp đồng, nội dung có thể review, một pipeline nội dung chạy được và bản sync/retrieval nhỏ có kiểm tra. Các đầu ra này tạo nền cho cả UI lẫn mở rộng KB.

## 5. Phạm vi mã nguồn và đầu ra cần triển khai

Các vị trí dưới đây xác định phạm vi mã nguồn và đầu ra cần có cho toàn bộ công việc Member 2. Tình trạng triển khai từng phần được ghi tại mục 7. Chỉ tách module khi có trách nhiệm đủ rõ.

| Vị trí | Thay đổi | Review/phối hợp |
|---|---|---|
| `backend/app/curriculum.py`, `contracts.py` | Chuẩn hóa metadata, task và review/public projection | Member 1 + Member 3 |
| `backend/app/kb_contracts.py`, `kb_sync.py` | Schema KB, version/hash, sync idempotent | Member 1 |
| `backend/app/retrieval.py`, `embeddings.py` | Lọc, direct lookup, ranking, embedding/cache và fallback | Member 3 + Member 1 |
| `backend/migrations/003_curriculum_kb.sql` | Registry/KB/vector tables và index phù hợp | Member 1 review DB/CI và thứ tự migration |
| `scripts/authoring/` | CLI draft/check/review và prompt/config | Cả nhóm review nội dung |
| `content/curriculum/` | Pack/registry versions, nguồn và coverage | Cả ba biên soạn |
| `research/retrieval/` | Query/qrels/config, metric và runner tái lập | Member 3 review phương pháp |
| `frontend/app/workspace.tsx` và component/API/types tách ra | UI đa dạng bài, trạng thái, report | Member 1 review API; Member 3 review response |
| `backend/app/session_contracts.py`, `sessions.py` | Dữ liệu report/capability cần thêm | Member 1 làm đầu mối |
| `backend/app/tutor.py`, `tutor_service.py` | Tool/context/content trace và kiểm soát replay | Member 3 làm đầu mối; Member 1 review transaction |
| `tests/`, `.github/workflows/repository-checks.yml` | Kiểm thử KB/retrieval, CI vector và UI evidence | Theo chủ module; Member 1 review CI/DB |

Các PR có ý nghĩa: contract/capability; pipeline authoring; sync/vector; retrieval+dev evaluation; Agent integration; UI/report; expansion theo lô; RQ3/evidence. Mỗi PR có fixtures và kiểm tra liên quan, tránh gộp toàn bộ pipeline vào một thay đổi khó review.

## 6. Kiểm tra và điều kiện hoàn thành của Member 2

Các regression cần có khi triển khai:

- Publish: draft, thiếu alignment review hoặc bị rút duyệt không xuất hiện trong kết quả.
- Retrieval: đúng concept/skill/purpose/level; không có reference solution; ví dụ không trùng bài đang đo; query ngoài scope trả nhánh phù hợp.
- Sync: chạy lại không trùng; hash thay cùng version bị phát hiện; crash giữa sync không kích hoạt snapshot dở; embedding dimension/version được kiểm tra.
- Integration: Agent dùng được nội dung đã lấy và ghi trace; timeout/fallback không làm thay đổi correctness/BKT; replay không đổi kết quả đã commit.
- Report: đúng độc lập và đúng có hỗ trợ tách riêng; phiên không observation không sinh mastery delta; report cũ giữ snapshot; hồ sơ khác không truy cập được.
- UI: draft/retry/state conflict/đổi hồ sơ/pause/resume/finish; render đúng task và tiếng Việt; mobile, bàn phím/focus; không lộ private payload.
- Evaluation: nhóm dữ liệu giữa dev/test không chồng; qrels khớp snapshot; metric có N/A đúng cách; các cấu hình so sánh cùng filters và có raw outputs.

Trước bàn giao, chạy lại các check phù hợp từ repo root, trong môi trường đã cài dependencies:

```powershell
python scripts/checks/check_curriculum.py
python scripts/checks/check_phase1.py
python scripts/exports/export_contracts.py --check
python scripts/exports/export_phase3_openapi.py --check
python -m pytest tests -q
```

Test DB cần PostgreSQL thử nghiệm và `RUN_DB_TESTS=1` cùng cấu hình kết nối. Chạy thêm typecheck/build trong `frontend/`, bộ kiểm tra browser trên đúng build mới và retrieval runner được bổ sung ở chặng 6. Các phép thử trả phí chỉ chạy theo cấu hình/ngân sách nhóm đã thống nhất; CI dùng stub/fixtures cho lời gọi model.

Hoàn thành phần Member 2 khi nội dung được quản lý/duyệt có version; sync và retrieval dùng thật trong Agent; UI/report chạy đúng trên danh mục đã chốt; RQ3 có dữ liệu, so sánh, kết quả và lệnh tái lập. Việc chỉ có 40 tên concept hoặc API retrieval trả một danh sách chưa đáp ứng điều kiện này.

## 7. Trạng thái đã hoàn thiện

Hồ sơ xác nhận ban đầu Chặng 1 và cập nhật Chặng 2 được ghi ngày **23/11/2026**. Nhóm xác nhận bản cập nhật Chặng 1 ngày **24/11/2026**. Chặng 2 được nghiệm thu pipeline cho 13 concept ngày **25/11/2026**. Các số liệu nghiệm thu lịch sử bên dưới được ghi ngày **18/11/2026**.

Các tham chiếu có dấu **†** dẫn đến danh mục hồ sơ lịch sử hiện không còn trong workspace tại mục 7.6. Giữ các số liệu này theo thời điểm ghi nhận; không coi chúng là bằng chứng đã được kiểm tra lại trong lượt cập nhật tài liệu này.

### 7.1. Tổng hợp các chặng và bằng chứng nghiệm thu

**Chặng 1 đã ghi nhận xác nhận của cả ba thành viên cho 40 concept và C01–C05.** Lượt nghiệm thu lịch sử Chặng 3 đạt **303 test, 0 skipped, 0 failed**, gồm 48 test mới và nghiệm thu embedding/pgvector thật. Nội dung và nhãn ở Chặng 2 đã qua AI review cho mục đích phát triển.

| Chặng | Phần đã hoàn thiện | Trạng thái hiện tại |
|---|---|---|
| **Chặng 1 — hợp đồng và tiêu chí sẵn sàng** | Contract 0.2.0, contract bài công khai 0.3.0 với 15 dạng authoring, adapter đọc bài legacy, capability theo chủ đề, ma trận 40 concept | **Nhóm đã xác nhận bản cập nhật**, gồm 68 cạnh đồ thị và một ánh xạ legacy–canonical trong registry v2. Có 20/40 concept có pack và 15/40 có pack đã duyệt. Ma trận ghi 13 concept có luồng demo từ lô đã duyệt. [Hồ sơ xác nhận](../../content/curriculum/member2-stage1-update-confirmation.v1.json) |
| **Chặng 2 — pipeline nội dung và review** | 13 cấu hình Member 2, prompt 2.2.0, CLI theo snapshot version, checker và review gắn hash; 13 pack đã duyệt | **Hoàn thành phạm vi 13 concept ngày 25/11.** 188 test đạt. OpenAI thật sinh pack N02 qua checker sau khi chỉnh prompt; có model/usage/artifact. Bộ kiểm mặc định nghiệm thu 13 concept. [Bàn giao Chặng 2](../implementation/member2/part2/README.md) |
| **Chặng 3 — KB và retrieval runtime** | Migration 003; projector có review/exclusion; sync dry-run/idempotent; cache CPU embedding ghim hash; snapshot nguyên tử, chống race và withdrawal; direct/metadata/exact semantic; tool bind quyền server; 7 schema và test DB thật | **Hoàn thiện phạm vi 13 concept ngày 26/11.** Runtime active có 40 concept/40 skill, 13 pack, 52 explanation/hint và 39 example, tổng 91 chunk. Benchmark mới chạy 104 query trên đủ 13 concept trong schema nghiệm thu cô lập. Retrieval đã nối vào Agent/response/UI trong Chặng 4 |
| **Chặng 4 — Agent, UI và learning report** | LangGraph có retrieval node, assembler nguyên văn teaching text, guard, receipt/ref giao nội dung; Full/No-RAG và snapshot ghim theo session; UI source/explanation/example; report theo skill có snapshot | **Đã hoàn thiện các thiếu sót kỹ thuật được rà soát ngày 26/11.** Có hook phiên/request, report 2.1 với chẩn đoán/evidence và provenance BKT, MathML hệ/phân thức, bàn phím/focus và timeout/replay. Nghiệm thu 149 test backend/runtime, 4 test công thức, 10 nhóm Chromium. Chờ review độc lập Member 1/3 và bằng chứng Docker/remote CI. Sinh lời tự do, graph điều hướng, session trộn skill và RQ3 là phạm vi riêng. [Bàn giao Chặng 4](../implementation/member2/part4/README.md) |
| **Chặng 5 — mở rộng nội dung và relevance dataset** | Hoàn thiện gói 13 concept Member 2; tích hợp phần còn lại sau khi chủ sở hữu bàn giao | **Đã triển khai kỹ thuật theo phạm vi mới ngày 26/11/2026.** 13 pack đã duyệt, 78 bài/39 ví dụ/91 chunk; 156 query dev có đủ nội dung, 195 judgment chưa chấm, pilot 26 query và mapping 39 mẫu lỗi vào 32 nhóm đề xuất. CLI/CI mặc định dùng gói 13 concept; 27 concept khác chờ bàn giao, không chặn phạm vi này. Còn review nhãn/taxonomy và thiết kế/khóa test độc lập. [Bàn giao Chặng 5](../implementation/member2/part5/README.md) |
| **Chặng 6 — RQ3, tối ưu và bàn giao** | Pipeline đánh giá, đo dev và bàn giao trong phạm vi 13 concept; nghiệm thu nghiên cứu sau khi đủ nhãn/test độc lập | **Hoàn tất kỹ thuật/dev local ngày 27/11/2026.** So metadata/semantic trên 104 query có nhãn dev, đo scope/cache/latency trên 156 query chưa chấm; có bootstrap theo concept, query plan và 104 cặp Full/No-RAG. Semantic nDCG@1/@3 đạt 0,8828/0,9634; không vi phạm scope, warm cache tính lại 0 embedding. Có công cụ review cặp, 92 test offline và 1 test DB bao phủ đủ 104 cặp. **Chưa nghiệm thu RQ3 chính thức**: còn nhãn/chấm độc lập, hòa giải và test được khóa. [Bàn giao Chặng 6](../implementation/member2/part6/README.md) |

**Bằng chứng Chặng 3 hiện hành:** [bàn giao và tự review](../implementation/member2/part3/README.md), `acceptance-2026-11-26.json`, `retrieval-evaluation-2026-11-26.json` và `completion-2026-11-26.json` trong cùng thư mục. Direct lookup không tạo embedding; sync lặp tính lại 0 embedding; 13/13 fallback đúng ở metadata và semantic. Sau khi dùng nguyên văn lời giải đã duyệt cho 39 ví dụ, trên 91 query có target, semantic Recall@1 đạt 0,8242, nDCG@1 đạt 0,8828 và nDCG@3 đạt 0,9634. Đây là dev labels tất định, không phải human gold/RQ3 cuối. [Hồ sơ kỹ thuật để Member 1/3 review](../implementation/member2/part3/technical-review-2026-11-26.md) ghi rõ phần chờ nghiệm thu Docker/CI và chữ ký độc lập.

**Kết luận AI review được ủy quyền:** cả 5 quyết định C01–C05 có trạng thái `adopted_for_development`; nội dung A02/E02 được chấp nhận cho authoring/phát triển với ghi chú; đã rà đủ query và ứng viên. Giảm grade 2 → 1 cho `DEV-A02-01`/A02 explanation và `DEV-E02-10`/E02 hint-3 vì nội dung mới hỗ trợ một phần wording yêu cầu. Hồ sơ review và ghi chú query hiện được lưu cùng snapshot nhãn sau AI review (`../../research/retrieval/dev/a02-e02.ai-review.v1/manifest.json`; retired source), không còn phụ thuộc thư mục lịch sử đã mất. Đây là hai góc nhìn của cùng Codex, không phải hai người đánh giá độc lập hoặc chữ ký của Member 1/3 thật; các snapshot gốc được giữ nguyên.

**Bằng chứng Chặng 1–2 trước lượt nghiệm thu Chặng 3:** 115 test đạt (39 foundation + 30 authoring + 18 import/pilot + 28 completion), cùng 8 checker/schema checks đạt. SymPy độc lập xác nhận 21 bài/ví dụ, 47 bước chuẩn và 7 lỗi mẫu, tính cả phần chuyển sang A07. Kiểm tra checksum xác nhận 59 tệp canonical/nguồn/lô v1 giữ nguyên. Xem [bằng chứng chạy lại ngày 18/11/2026†](#76-hồ-sơ-lịch-sử-không-còn-trong-workspace), [bàn giao Chặng 1](../implementation/member2/part1/README.md) và [bàn giao, tự review Chặng 2†](#76-hồ-sơ-lịch-sử-không-còn-trong-workspace).

**Trạng thái nghiệm thu.** Năm cổng hợp đồng đã chuyển `accepted` trong ma trận hiện hành. Nhóm xác nhận nội dung và alignment A02/E02 cho M2-OAT02 v2 vào ngày 23/11/2026. Chữ ký ghi nhận là **Codex — ghi nhận theo ủy quyền của người dùng**. Hai pack chờ xác minh quyền nguồn riêng cho 8 bài. Lượt Gemini wording lịch sử đã đạt, còn lượt Gemini authoring chưa sinh được pack. [Bằng chứng Chặng 2](../implementation/member2/part2/verification-update.json)

**Mốc hiện tại:** Chặng 3 đã có snapshot runtime 91 chunk. Chặng 4 đã nối retrieval vào lượt gia sư thật với assembler nguyên văn, nguồn đã giao, assistance đơn điệu và report đóng băng. Phần còn lại gồm generator diễn đạt tự do có guard/review, đồ thị điều hướng và nghiệm thu đầy đủ RQ3. [Bàn giao bản đầu Chặng 4](../implementation/member2/part4/README.md)

**Ghi chú bàn giao Chặng 1–3:**

**Cập nhật 23/11/2026.** Xác nhận của cả ba thành viên cho danh mục 40 concept và C01–C05 đã được ghi nhận theo yêu cầu của người dùng. [Ma trận hiện hành](../implementation/member2/part1/coverage.md) · [Hồ sơ xác nhận](../../content/curriculum/member2-workboard-confirmation.v1.json)

**Cập nhật 24/11/2026.** Codex ký ghi nhận theo ủy quyền của người dùng cho bản cập nhật Chặng 1. Phạm vi gồm contract bài công khai 0.3.0, adapter legacy, capability theo chủ đề, ma trận độ phủ, đồ thị và ánh xạ trong registry v2. [Hồ sơ cập nhật](../../content/curriculum/member2-stage1-update-confirmation.v1.json)

**Cập nhật 23/11/2026.** Đã ghi nhận nhóm duyệt nội dung và alignment A02/E02 trên đúng hash. Bộ pilot tự biên soạn đạt kiểm toán cho cả 13 concept Member 2 phụ trách. [Bàn giao Chặng 2](../implementation/member2/part2/README.md)

**Cập nhật 24/11/2026.** Người dùng xác nhận duyệt nội dung `0.4.0-member2-review` cho đủ 13 concept Member 2, gồm 78 bài qua checker và 39 ví dụ có lời giải. Hồ sơ phê duyệt gắn với hash từng pack. [Hồ sơ phê duyệt 13 concept](../../content/authoring/batches/member2-original.v2/manifest.json)

**Cập nhật 25/11/2026.** Đã nối CLI với nguồn `member2-v2`, bổ sung đủ 13 cấu hình và prompt 2.2.0. Run OpenAI N02 đã đạt checker bằng `gpt-4o-mini`, sau hai run bị chặn do lỗi định dạng/nhãn. Mẫu sinh thêm chờ review theo hash trước khi dùng. Lượt nghiệm thu tự động đạt 188 test không cần DB. [Bằng chứng Chặng 2](../implementation/member2/part2/verification-2026-11-25.json)

**Cập nhật 18/11/2026: đã hoàn thiện kỹ thuật, tự review và nghiệm thu trên PostgreSQL/pgvector/weights thật.** Có 48 test mới, full suite 303 test và 12 checker/schema checks đạt. [Bàn giao Chặng 3](../implementation/member2/part3/README.md) ghi từng yêu cầu, lệnh chạy, bằng chứng và giới hạn. Runtime hiện có 0 teaching chunk do source draft; ca retrieval dương chỉ dùng review fixture trong namespace riêng. **Dừng sau chặng này theo yêu cầu.**

**Cập nhật 26/11/2026:** nguồn mặc định Chặng 3 đã chuyển sang 13 pack M2-ORIG02 được duyệt. Đã xuất bản 39 example có teaching text/family/source/lineage/hash, đồng bộ và kích hoạt snapshot 91 chunk. Checker DB dùng schema mới độc lập; benchmark mới phủ đủ 13 concept. Dòng 18/11 phía trên được giữ làm lịch sử, không mô tả runtime hiện hành.

- Đã chuẩn bị PostgreSQL có extension vector; migration 003 tạo extension trong `public`. Compose/CI dùng `pgvector/pgvector:pg17`; đã kiểm YAML và chạy DB thật cục bộ PG16.15/pgvector0.8.6, chưa chạy Docker hoặc remote CI.

Đã hiện thực contract runtime `kb-1.0.0` trong [kb_contracts.py](../../backend/app/kb_contracts.py) và [kb_tool.py](../../backend/app/kb_tool.py), giữ nguyên contract đề xuất cũ. Tool nhận query; scope được bind từ `TrustedKBState` do server tạo. Client/LLM không cấp `learner_scope`, hint permissions, snapshot hoặc exclusions. Log nội bộ có ranking/distance; `for_generator()` chọn trường cần thiết. Việc tạo state từ session canonical/legacy và đưa context vào generator thuộc Chặng 4.

**Nghiệm thu Chặng 3:** các điều kiện của Chặng 3 đã đạt trong [tests/evidence](../implementation/member2/part3/verification.json), có thêm kiểm thử concurrency, rút duyệt trong lúc inference, payload corruption và trace persistence failure. Không ghi observation/mastery/assistance khi chỉ truy xuất. Chưa mở rộng sang việc sinh phản hồi có RAG hoặc UI citation.

### 7.2. Hiện trạng theo thành phần và việc còn thiếu

| Thành phần | Bằng chứng trong code/tài liệu | Việc còn thiếu |
|---|---|---|
| Registry | [registry.v2.json](../../content/curriculum/registry.v2.json) có 40 concept và alignment đã duyệt. Nhóm đã xác nhận 68 cạnh và một ánh xạ legacy–canonical ghi trong registry | Đưa cạnh và ánh xạ vào phiên bản tích hợp phù hợp. Kiểm chứng đặc tả và dạng đo của các concept chưa có pack |
| Nội dung pilot | [pilot.v1.json](../../content/curriculum/pilot.v1.json): 10 pack, 60 bài, 30 ví dụ, 20 mẫu lỗi, 30 mức hint | Tất cả còn nháp; 30 concept chưa có pack; chưa có bộ retrieval evaluation độc lập |
| Kiểm tra authoring | [curriculum.py](../../backend/app/curriculum.py), [authoring_math.py](../../backend/app/authoring_math.py), [test_curriculum.py](../../tests/test_curriculum.py) | Mở rộng theo dạng bài; kiểm tra authoring chưa phải bộ chấm input học sinh |
| Lấy nội dung an toàn | [kb_projection.py](../../backend/app/kb_projection.py), [retrieval.py](../../backend/app/retrieval.py): review gate, direct/metadata/exact semantic, scope và exclusions | Runtime có 91 chunk đã duyệt cho 13 concept. Bản đầu Chặng 4 đã nối vào assembler nguyên văn, ghi riêng retrieved/generator/delivered refs; generator tự do còn chờ review |
| Database | [003_curriculum_kb.sql](../../backend/migrations/003_curriculum_kb.sql) bổ sung registry/concept/skill/mapping/chunk/embedding/snapshot/withdrawal/trace | Đã migrate/sync runtime 40 concept/40 skill và kích hoạt snapshot 91 chunk. Seed bài sản phẩm vẫn legacy; mapping canonical chưa tự đổi mastery/session |
| Gia sư | [tutor.py](../../backend/app/tutor.py), [teaching_runtime.py](../../backend/app/teaching_runtime.py): graph có retrieval, assembler teaching text đã duyệt và exact guard; session pin Full/No-RAG/snapshot | Bản đầu đã dùng KB cho 13 concept. Còn generator tự do có review và điều hướng graph; legacy giữ baseline riêng |
| UI sản phẩm | [workspace.tsx](../../frontend/app/workspace.tsx): hồ sơ demo, chủ đề, bài làm, hint/explanation/example, draft, retry và history/report; tách API/types/feedback/report | Types public có drift check; đã tách `useTutorSession`, report và formula theo task; MathML có phân thức lồng/hệ. Đã nghiệm thu mobile/desktop, bàn phím/focus và timeout; ký hiệu ngoài grammar giữ văn bản an toàn |
| Báo cáo | [sessions.py](../../backend/app/sessions.py), [session_contracts.py](../../backend/app/session_contracts.py) | Report 2.1 có summary theo skill, chẩn đoán với evidence/status, link về bài nộp, provenance BKT và snapshot bất biến; tương thích report 2.0. Session trộn skill và prerequisite từ graph là phạm vi riêng |
| Nghiệm thu UI | [Hồ sơ Chromium Chặng 4 ngày 26/11/2026](../implementation/member2/part4/browser-stage4-2026-11-26.json) | Đạt 10 nhóm trên build hiện hành, DB/embedding thật và 0 model API call; có report legacy thật, hệ E09/phân thức A10, bàn phím/focus, timeout 45 giây qua đồng hồ ảo. Hồ sơ cũ chỉ là lịch sử |
| Nghiên cứu BKT | [bkt-dev-v1.md](../research/data/bkt-dev-v1.md) | Có kết quả train/dev được lưu; kết quả này không phải RQ3 và chưa hiệu chỉnh mastery cho học sinh Việt Nam |

Điểm xuất phát hợp lý là hoàn thiện và nối các nền tảng này vào luồng thật. Mốc 10 pack nháp là độ phủ authoring, chưa phải 10 concept đã sẵn sàng dạy học.

### 7.3. Nhật ký nghiệm thu trước Chặng 3 — DB, retrieval nghiên cứu và browser thật

Các số liệu 255/303 test và store nghiên cứu trong mục này thuộc các lượt nghiệm thu lịch sử. Số test và snapshot hiện hành nằm trong hồ sơ Chặng 3 ngày 26/11/2026 phía trên.

Theo yêu cầu khép các điểm thiếu, đã thực hiện kiểm thử thực tế trên môi trường cục bộ và thêm lựa chọn Gemini cho API miễn phí. Xem [báo cáo review và giới hạn†](#76-hồ-sơ-lịch-sử-không-còn-trong-workspace), [bằng chứng có hash†](#76-hồ-sơ-lịch-sử-không-còn-trong-workspace).

| Đầu ra bổ sung đã đạt | Bằng chứng/kết quả |
|---|---|
| PostgreSQL/pgvector thật | PostgreSQL 16.15 + pgvector 0.8.6 native Windows; DB bootstrap và kiểm thử transaction/concurrency/retry/report thật |
| Bộ test đầy đủ | **255 passed, 0 skipped, 0 failed**, có `RUN_DB_TESTS=1`; 10 checker nội dung/toán/AI-review/schema đạt |
| Frontend và browser/API/DB | Typecheck và production build đạt; 6/6 kiểm tra browser trên build mới; 6 turn thật, report chính xác, ba viewport không tràn ngang |
| Retrieval dev có phép đo | 24 query ×8 chunk trên schema nghiên cứu riêng; sync idempotent; metadata nDCG@3 0,8980, semantic 0,9720; 4/4 fallback đúng. Nhãn AI review, không phải human gold/final test |
| API Gemini tùy chọn | Adapter bounded wording, guard và 8 test transport. **Lượt API thật đạt HTTP 200** với `gemini-3.1-flash-lite`, `response_source=gemini`, 150 token trên dữ liệu giả; đã sửa model trong `.env` sau khi bản 2.5 trả 404. Xem bằng chứng mới (`../implementation/member2/gemini-live-2026.json`; h? s? l?ch s? kh?ng k?m trong checkout), [hướng dẫn cấu hình†](#76-hồ-sơ-lịch-sử-không-còn-trong-workspace). Backend đang chạy chưa restart để nạp cấu hình mới |
| Chuẩn bị CI vector | Đổi image DB Compose/CI sang pgvector PG17; chưa có quyền GitHub và workspace thiếu `.git` nên chưa có remote CI pass |

Embedding benchmark chạy cục bộ miễn phí, 384 chiều, giữ hash weights/config/corpus/qrels và raw rankings. Không cần trả tiền API để hoàn thành lượt benchmark này. Trong lượt nghiệm thu ngày 18/11/2026, UI chạy tại `http://127.0.0.1:3000`; process backend lúc ghi nhận vẫn dùng template. Key/provider/model đã cấu hình và được kiểm tra riêng thành công; backend cần khởi động lại có bật model để áp dụng cấu hình mới.
