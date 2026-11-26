# Bộ tình huống thích ứng từ lịch sử

**Trạng thái:** bản nháp của Member 3, công cụ và test xong, không gọi API. Có sáu ca ví dụ và **33 ca dev pilot** (N01, A02, A03, E02, E03, E05): nhãn do AI soạn, Member 3 đã duyệt; chưa có nhãn độc lập của người thứ hai. **Bộ 160–200 ca của plan §12 chưa đủ, và chưa có ca test nào.**
**Căn cứ:** plan §8.3 (observation), §11.5, §12, §18.2. **Dùng ở:** [script ablation](ablation-runner.v1.md) qua `--scenario-set`.

## Các file

| File | Vai trò |
|---|---|
| [`contracts.py`](../../../research/scenarios/contracts.py) | Hợp đồng lịch sử, nguồn bài, tham số, nhãn và dữ liệu đã dựng |
| [`replay.py`](../../../research/scenarios/replay.py) | Dựng Student Model và dấu vết observation từ sự kiện, bằng các hàm ghi state của graph |
| [`build.py`](../../../research/scenarios/build.py) | Kiểm tra registry, lấy context KG, gom nhóm, chia tập và xuất độ phủ |
| [`authoring.py`](../../../research/scenarios/authoring.py) | Soạn lịch sử bằng code: mỗi sự kiện đi qua đúng các bước ghi state của replay |
| [`pilot_dev.py`](../../../research/scenarios/pilot_dev.py) | Nguồn của bộ dev pilot; in state từng ca và xuất phiếu rà soát |
| [`examples.dev.v1.json`](../../../contracts/scenarios/examples.dev.v1.json) | Sáu ví dụ có nguồn và nhãn nháp, cố định dev |
| [`pilot.dev.v1.json`](../../../contracts/scenarios/pilot.dev.v1.json) | 33 ca dev pilot, sinh từ `pilot_dev.py` (không sửa tay) |
| [`ScenarioDataset.schema.json`](../../../contracts/scenarios/ScenarioDataset.schema.json) | Schema đầu vào |
| [`ScenarioSet.schema.json`](../../../contracts/scenarios/ScenarioSet.schema.json) | Schema một split đã replay |
| [`test_scenarios.py`](../../../tests/test_scenarios.py) | Replay khớp graph, observation, chia nhóm và tích hợp CLI ablation |

## Biên soạn đầu vào

`ScenarioDataset` gồm phiên bản dữ liệu, tham số có nguồn cho từng skill, danh mục bài và
những tình huống. Bài có đề công khai, concept/skill, họ mẫu, bài gốc và phiên bản. ID bài gốc
và họ mẫu phải được chuẩn hóa trên toàn bộ dữ liệu, bao gồm các biến thể đổi số hoặc đổi lời văn.

Mỗi tình huống có nguồn `synthetic_authoring`, `student_real` hoặc `student_simulated`,
tham chiếu nguồn, `history_group_id`, lịch sử có thứ tự, context và nhãn chiến lược.

Lịch sử ghi đúng những gì hệ thống đã thấy và đã làm, theo ba quy tắc:

- **Lượt của học sinh và quyết định của tutor xen kẽ nhau**, bắt đầu và kết thúc bằng lượt của học
  sinh. Hệ thống trả lời mọi lượt, nên thiếu một quyết định là thiếu một lần hỗ trợ trong state.
- **Lượt nộp bài** giữ nguyên bài làm cùng assessment do validator hoặc người biên soạn cung cấp.
  Công cụ không tự gán nhãn toán. Giả thuyết lỗi không ghi trong lịch sử: replay suy ra từ
  `misconception_candidate` của assessment như hệ thống.
- **Quyết định của tutor** ghi phần có tác động lên state: `action`, `intent`, `hint_level`,
  `problem_id` khi quyết định giao bài (backtrack, check_transfer, next_problem), và
  `target_skill_id` khi giao bài hoặc hỏi kiểm tra prerequisite. Cặp action/intent và mức hint phải
  là cặp hệ thống cho phép (`ACTION_SPECS`).
- **Quyết định giao bài phải là quyết định policy gate cho qua.** Graph ghi state với giả định đó:
  mọi `check_transfer` được ghi là bài khác họ mẫu (`cross_family`) và lần làm bài đó là bằng chứng
  độc lập mới. Replay chạy đúng `gate_violations` của hệ thống và từ chối khi vi phạm một luật
  chuyển bài:

  | Luật | Nội dung |
  |---|---|
  | G13 | Bài thuộc danh mục, đúng skill đã ghi, khác bài đang làm và chưa giao trong phiên |
  | G12 | `check_transfer` sang bài khác họ mẫu |
  | G20 | `check_transfer`, luyện tiếp, đổi bài, tăng độ khó: cùng concept và skill; tăng độ khó thì bài mới phải khó hơn |
  | G19 | Chuyển concept theo một cạnh tới concept kế tiếp trong registry |
  | G05, G08 | Backtrack xuống một prerequisite trực tiếp trong registry, không lặp vòng, tối đa hai tầng |
  | G09 | Quay lại đúng bài trên đỉnh return stack |

  Các luật còn lại của gate (ví dụ phải có bằng chứng thiếu skill nền mới được backtrack, vừa làm
  sai thì không được chuyển bài) xét quyết định có hợp lý về sư phạm không. Chúng không đổi cách
  state được ghi và cần những trường lịch sử không lưu (evidence, nội dung), nên replay không kiểm.

`task` của mỗi sự kiện là bài hệ thống đang giữ lúc đó. Bài chỉ đổi qua quyết định của tutor, nên
sau một quyết định giao bài, `task` của lượt kế tiếp phải đúng là bài graph tạo ra, kể cả
`relation`: `prerequisite` sau backtrack, `repeat` khi quay lại bài cha (cùng `opportunity_id` cũ),
`near_practice` khi bài mới cùng họ mẫu, `cross_family` khi khác họ mẫu hoặc sau check_transfer,
`initial` khi chuyển concept hoặc tăng độ khó. Ghi sai thì replay dừng và in bài mà hệ thống đang giữ.

Nhãn chiến lược có nhiều action được chấp nhận, action bị cấm, lý do, tác giả và trạng thái review.
`human_approved` cần người duyệt khác tác giả. Nhãn được rà soát độc lập, không lấy Rule-policy
làm đáp án chuẩn. Trường `expected_rule_action` cũ chỉ dành cho bộ hồi quy cũ.

**Nhãn chi tiết cho ca mà action chưa đủ phân biệt.** `next_problem` vừa là luyện tiếp vừa là chuyển
concept; `diagnose` vừa là hỏi cách làm vừa là kiểm tra kiến thức nền. Hai trường tùy chọn:

- `acceptable_intents`: action nào có ít nhất một intent được liệt kê thì chỉ các intent đó được chấp
  nhận; action không có intent nào được liệt kê thì nhận mọi intent của nó.
- `acceptable_target_skill_ids`: skill mà quyết định cần hướng tới.

Để trống là không ràng buộc. Script ablation và công cụ chọn ngưỡng báo riêng số quyết định khớp nhãn
chi tiết (`final_detail_acceptable`), chỉ tính trên các ca có nhãn chi tiết. Chỉ số `final_acceptable`
theo action giữ nguyên nghĩa cũ.

**Nhãn độc lập của hai người (plan §12).** `independent_labels` giữ nhãn ban đầu của từng người
(`rater`, action chấp nhận được, action bị cấm, intent, skill cần hướng tới, lý do). Các trường ở trên là nhãn cuối sau hòa
giải, kèm `adjudication_note`. `review_status = adjudicated` cần ít nhất hai người gán khác nhau.
`build` cảnh báo mọi ca test chưa `adjudicated`, và ghi độ đồng thuận ban đầu vào manifest
(`label_agreement`): số ca có hai nhãn, tỷ lệ cặp trùng hoàn toàn tập action chấp nhận được, Jaccard
trung bình, số cặp mà một người chấp nhận action người kia cấm, và số cặp khác nhau về intent hoặc về
skill cần hướng tới.

Tag tương ứng các trường hợp trong §11.5 gồm `alternative_correct`, `error_propagation`,
`final_answer_only`, `condition_error`, `ambiguous_input`, `insufficient_evidence`,
`requests_answer`. Có thể bổ sung tag về miền kiến thức và ngoại lệ, kèm review nội dung.
Tag do người biên soạn khai, công cụ không kiểm được nội dung có đúng loại đó không; người duyệt
phải kiểm tra tag cùng với nhãn.

Context do người biên soạn cung cấp, trừ phần KG. `edges` và `next_concepts` để trống: `build` lấy
chúng từ registry bằng `KGTool` như hệ thống (dùng cả cạnh nháp vì registry chưa có cạnh đã duyệt,
ghi `kg_include_drafts` trong manifest). Cạnh soạn tay bị từ chối, vì có thể lệch registry, và thiếu
cạnh thì cấu hình Full không khác No-KG. Nội dung truy xuất (`retrieved`) vẫn soạn tay cho tới khi
có RAG của Member 2.

## Bộ dev pilot

`pilot.dev.v1.json` có 33 ca tổng hợp, cố định dev, dùng cho hai việc: thử quy trình gán nhãn (bước 1
của quy trình ở plan §12) và cho công cụ chọn ngưỡng có ca để phân biệt. Bộ này **không phải bộ test**
và không thay cho 160–200 ca của plan.

| Nhóm ca | Mã | Nội dung |
|---|---|---|
| Bài đúng | DP-01 – DP-03 | Đủ bước, cách giải khác, chỉ có đáp án cuối |
| Sai lần đầu | DP-04 – DP-08 | Chỉ có đáp án sai, nghi hiểu sai, lặp hiểu sai, lỗi kéo theo, sai điều kiện |
| Chưa chấm được | DP-09, DP-10 | Input mơ hồ, trả lời bằng lời không xác minh được |
| Lời nhắn của học sinh | DP-11 – DP-15 | Xin đáp án, xin gợi ý khi chưa làm, không hiểu đề, xin tạm dừng, quay lại |
| Sau khi đã hỗ trợ | DP-16, DP-17 | Sửa đúng nhờ gợi ý, kẹt sau hai mức gợi ý |
| Lỗi thao tác theo lịch sử | DP-18 – DP-21 | Cùng một lỗi tính, lịch sử độc lập 4/4, 3/4, 2/4, 1/4 đúng |
| Điều kiện chuyển tiếp | DP-22 – DP-25 | Vừa làm đúng, lịch sử 4/4, 3/4, 2/4 (hai kiểu) đúng |
| Kiến thức nền | DP-26 – DP-28 | Sai tiếp trong nhánh ôn, làm đúng bài nền, kiến thức nền vừa được chứng minh |
| Concept khác | DP-29, DP-30 | Cộng số có dấu, thu gọn hạng tử |
| Về bài gốc sau nhánh ôn | DP-31 – DP-33 | Lặp lỗi phân phối khi bài nền 0/2 và 1/2 đúng độc lập; phân phối đúng nhưng tính sai khi ước lượng nền còn thấp |

Cách soạn:

- **Lịch sử soạn bằng code** (`authoring.Session`), không viết JSON tay. Mỗi lượt đi qua đúng các hàm
  ghi state mà replay dùng, nên bài hiện tại luôn là bài hệ thống đang giữ và quyết định giao bài sai
  luật gate bị từ chối ngay lúc soạn. Mastery, số observation và readiness đều do replay tính từ lịch
  sử; không có giá trị nào soạn tay.
- **Bài pilot** (`problem_version = pilot-0.1.0`) thêm họ mẫu mới cho E02, A02, A03, N01 và một bài
  E05, để một skill có đủ bài khác họ cho các observation độc lập. Đề do AI soạn, cần review nội dung.
  Verifier chưa có đáp án riêng của các bài này, nên generator sẽ dùng fallback khi sinh câu.
- **Nhãn do AI soạn** (`author = ai_draft`) từ tình huống sư phạm, có lý do cho từng ca; **Member 3 đã
  duyệt cả 33 nhãn** (`reviewer = member3`, `human_approved`, bộ `adaptive-pilot-dev-0.2.0`). 22 ca có
  nhãn intent hoặc skill. Các ca "nằm giữa" (DP-19, DP-23, DP-32) cố ý không ràng buộc intent.

Giới hạn cần biết khi đọc kết quả trên bộ này:

- Người soạn nhãn (AI) cũng là công cụ đã viết Rule-policy, và người duyệt (Member 3) là người phát
  triển policy. Rule-policy đạt 33/33 action chấp nhận được và 22/22 nhãn chi tiết; con số đó **không
  phải bằng chứng policy đúng**. Pilot hai người của plan §12 vẫn cần một thành viên khác gán nhãn độc
  lập bằng phiếu không có nhãn (`--sheet ... --blind`), rồi so với nhãn đã duyệt.
- DP-33 từng là ca duy nhất Rule-policy không khớp: học sinh vừa phân phối đúng và chỉ tính sai, nhưng
  policy vẫn hỏi kiểm tra tính phân phối vì ước lượng kiến thức nền còn thấp. Sau khi nhãn được duyệt,
  Rule-policy được sửa (`rule-policy-0.5.0`, [threshold-selection §4.2](threshold-selection.v1.md)).
- Các nhóm ca theo lịch sử (DP-18 – DP-28, DP-31 – DP-33) được thiết kế quanh ranh giới ngưỡng. Chúng thuộc dev;
  bộ test không nên được thiết kế theo ngưỡng.
- Mọi ca dùng chung bài và họ mẫu với nhau và với bộ ví dụ, nên tất cả thuộc một nhóm dev. Các bài
  và họ mẫu này không được xuất hiện trong test.

Xuất phiếu để rà soát hoặc gán nhãn độc lập (ghi vào `data/`, không vào Git):

```powershell
python -m research.scenarios.pilot_dev --sheet data/scenarios/pilot-dev-review.md
python -m research.scenarios.pilot_dev --sheet data/scenarios/pilot-dev-blind.md --blind
python -m research.scenarios.pilot_dev --describe   # state đã replay của từng ca
python -m research.scenarios.pilot_dev              # sinh lại pilot.dev.v1.json sau khi sửa nguồn
```

## Replay

Replay không viết lại logic của graph. Lượt của học sinh đi qua `start_turn` →
`record_student_turn` → `record_observation`, quyết định của tutor đi qua `finish_turn`
(`apply_decision`); đó là các hàm mà node `load`, `analyze`, `observe`, `commit` của
[`graph.py`](../../../backend/app/agent/graph.py) gọi. Vì vậy state dựng lại có cùng mức hỗ trợ,
số lượt chưa tiến bộ, giả thuyết lỗi, câu hỏi prerequisite, return stack, bài đã giao và trạng thái
phiên như hệ thống. Test `test_replay_rebuilds_the_state_the_graph_holds_before_each_decision` chạy
một phiên mười lượt qua engine thật rồi replay lịch sử của phiên đó: state phải trùng ở từng lượt.

Một số hệ quả cần biết khi biên soạn:

- Lượt xin tạm dừng vẫn có `status = active` và `trigger = pause`; quyết định kết thúc mới đổi status.
- Quay lại bài cha thì bài làm và assessment cũ bị xóa, hỗ trợ chỉ còn mức hint của bài cha.
- Action có `counts_as_assistance` là hỗ trợ kể cả ở mức hint 0.
- Làm đúng độc lập thì giả thuyết lỗi của skill đó chuyển sang `ruled_out`.
- Câu hỏi prerequisite được đóng là `unverified` ở lượt kế tiếp, vì chưa có bộ xác minh câu trả lời
  (chờ hợp đồng với Member 1).
- State giữ tối đa 12 lượt gần nhất và 5 observation độc lập gần nhất/skill.

Replay khác graph ở hai nguồn dữ liệu:

1. Assessment lấy từ lịch sử thay cho analyzer.
2. Observation và BKT dùng cùng hàm với graph (`app.agent.observation.observe_submission`, gọi
   `app.knowledge.eligibility` và `app.knowledge.update` của Member 1). Chỉ khác ở tham số: replay
   dùng tham số khai báo cho từng skill trong bộ dữ liệu, graph dùng bộ khởi đầu
   `content/bkt.bootstrap.v1.json` chung cho mọi skill. Mỗi skill có tham số bắt đầu từ prior.
   Observation hợp lệ ghi prediction trước đáp án, mastery trước/sau và phiên bản tham số.
   Readiness tính lại bằng `compute_readiness`.

Đầu vào của luật ghi nhận được dựng như backend của Member 1 (`app/tutor_service.py`), từ sổ ghi
`ObservationLedger` mà graph và replay cùng cập nhật:

- Bài cùng họ mẫu chỉ bị loại (`near_practice`) khi trong phiên đã có bài khác cùng họ nhận trợ giúp.
  Cùng họ mà học sinh tự làm thì vẫn được ghi nhận.
- Chỉ lần nộp chấm được đầu tiên trên một opportunity là lần thử đầu; các lần sau trả `repeat`. Lần
  nộp không đọc được hoặc chưa xác minh không tính.
- Quay lại bài cha (`repeat`) không tạo observation.
- Lỗi thuộc skill khác skill đích của bài không cập nhật skill nào (`not_target_evidence`). Ví dụ
  trên AD-EX-05 (bài E02, lỗi phân phối thuộc A02): mastery của A02 giữ nguyên sau lần sai đó.
- Mastery tính bằng một phiên bản tham số không được cập nhật tiếp bằng phiên bản khác: phải tính lại
  từ lịch sử hoặc chuyển đổi tường minh.

Request trùng hoàn toàn được bỏ qua, request trùng nhưng khác nội dung bị báo lỗi. Tạm dừng và xin
gợi ý không tạo observation. Sửa đúng sau hỗ trợ được đếm riêng.

Phạm vi v1 là lịch sử một học sinh trong một session với thứ tự sự kiện đã biết. Tham số của ví dụ
là giả định kỹ thuật `scenario-demo-0.1.0`, chưa hiệu chỉnh cho người học Việt Nam. Đầu vào không
có trường để ghi thẳng mastery, readiness hay giả thuyết lỗi.

## Chia tập và độ phủ

Nhóm liên thông được tạo theo mọi bài gốc/họ mẫu trong lịch sử, history group, session và
lượt chung ID. Liên kết gián tiếp cũng giữ chung split. Nhóm có hai nhãn split khác nhau làm
build dừng. Có thể cố định `authoring`, `dev`, `test`.

Nhóm chưa gán được chia dev/test theo seed. Mỗi nhóm vào bên đang thiếu ca của các concept trong
nhóm nhiều hơn (mỗi concept cần 2 ca ở mỗi bên, plan §12); khi hai bên thiếu như nhau thì vào bên
có ít ca hơn. Nhóm lớn vẫn giữ nguyên dù tỷ lệ bị lệch. Concept chỉ có một nhóm độc lập thì không
thể có mặt ở cả hai bên: cảnh báo độ phủ sẽ nêu, và cần biên soạn thêm họ mẫu.

Ví dụ đã dùng khi phát triển nên cố định dev. File test của bộ ví dụ rỗng. Khi ít nhóm độc lập,
cần biên soạn thêm họ bài/lịch sử trước khi khóa test. Sau khi khóa, chỉ dùng dev để sửa prompt,
luật và ngưỡng. Context RAG cần được review để loại nguyên ca test, nhãn và lời giải test.
Kiểm tra tương đương ngữ nghĩa giữa RAG và ca test còn cần người rà soát.

Đầu ra có `authoring.json`, `dev.json`, `test.json`, `manifest.json`, `coverage.csv`.
Manifest ghi seed, nhóm, nguồn dữ liệu, trạng thái nhãn, phiên bản replay, SHA-256 đầu vào và
phiên bản/dấu vân tay registry. CSV chứa đủ 40 concept, số ca từng split, số nhóm, loại tình huống,
họ lỗi và mức hỗ trợ. Cảnh báo đối chiếu mục tiêu 160–200 ca dev+test, 80–100 ca test, ít nhất
4 ca/concept trong dev+test và 2 ca test/concept, cùng các loại tình huống còn thiếu.

## Chạy từ thư mục gốc

```powershell
.\.venv\Scripts\python.exe -X utf8 -m research.scenarios.build --input contracts/scenarios/examples.dev.v1.json --out data/scenarios/examples-v3
.\.venv\Scripts\python.exe -X utf8 research/evaluation/run_ablation.py --scenario-set data/scenarios/examples-v3/dev.json --out data/ablation/scenario-tools-fake-v3
.\.venv\Scripts\python.exe -m pytest tests/test_scenarios.py tests/test_ablation.py -q
.\.venv\Scripts\python.exe scripts/exports/export_agent_contracts.py --check
```

Chọn thư mục mới cho lần chạy tiếp. `--scenario-set` chọn file split tường minh, summary ghi
split, phiên bản dữ liệu và SHA-256 của file. Lệnh ablation trên dùng client giả.

Ngân hàng bài công khai được nối vào callback của graph. Đáp án riêng của verifier và công cụ
chấm người hiện vẫn dùng ngân hàng demo. Với ID bài mới cần nối đáp án riêng của Member 1/2
trước khi đánh giá sinh phản hồi thật hoặc tạo phiếu chấm. Khi thiếu đáp án, generator dùng
fallback và ghi lý do theo thiết kế hiện có.

## Việc còn mở

- **Bộ dev pilot:** nhãn đã được Member 3 duyệt. Còn cần một thành viên khác gán nhãn độc lập bằng
  phiếu không có nhãn, viết guideline cho các ca bất đồng (plan §12, bước 1), và review nội dung đề
  của các bài `pilot-0.1.0`.
- **Mở rộng dev** tới khoảng một nửa của 160–200 ca, tối thiểu 2 ca/concept ở mỗi bên. Hiện mới có
  6 trên 40 concept; concept nào chưa có đủ họ mẫu trong problem bank thì chưa soạn được.
- **Bộ test (80–100 ca):** dùng bài gốc và họ mẫu không có trong dev. Nhãn do hai người gán độc lập
  rồi hòa giải (`adjudicated`); hợp đồng đã có chỗ lưu. Người phát triển policy (Member 3 và công cụ
  AI đã viết policy) không soạn nhãn test và không dùng test để chỉnh hệ thống (plan §12, bước 5).
- Chốt quy tắc observation và bộ tham số BKT với Member 1 (bảng ở mục Replay).
- Nối đáp án riêng và RAG thật của Member 1/2 cho ID bài mới.
