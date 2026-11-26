"use client";
import type { SessionView } from "./lib/api-types";
import { useTutorSession } from "./hooks/useTutorSession";
import { LearningReport } from "./components/LearningReport";
import { TeachingFeedback } from "./components/TeachingFeedback";
import { MathText } from "./components/MathText";
import { ProblemFormula } from "./components/ProblemFormula";

type Problem = SessionView["problem"];
const assessmentLabel = (status: string) => ({ verified_correct: "Đã xác minh đúng", verified_incorrect: "Cần kiểm tra lại", needs_clarification: "Cần viết rõ hơn", unverified: "Chưa xác minh" }[status] || "Chưa xác minh");
const answerFormats: Record<string, string> = {
  numeric: "Nhập một giá trị số.", evaluate: "Nhập giá trị chính xác. Có thể viết phân số bằng dấu /.",
  fraction_compare: "Nhập hai phân số đã quy đồng với dấu <, > hoặc = ở giữa.",
  number_conversion: "Nhập đúng dạng đề yêu cầu. Dùng / cho phân số và % cho phần trăm.",
  polynomial: "Nhập đa thức đã khai triển và thu gọn, chẳng hạn dùng x*x hoặc x^2 cho số mũ hai.",
  factored_polynomial: "Nhập dạng tích, đặt đa thức còn lại trong ngoặc.",
  rational_operation: "Nhập tử|mẫu;{các giá trị bị loại}. Dùng | để ngăn tử với mẫu.",
  word_equation: "Nhập x; đơn vị; nguyên dương; phương trình.",
  quadratic_roots: "Nhập biệt thức;{các nghiệm}. Dùng sqrt(n) cho căn chính xác hoặc {} khi tập nghiệm rỗng.",
  linear_elimination: "Nhập hai hệ số nhân và cặp nghiệm theo mẫu m,n;(x,y).",
  function_domain: "Dùng ký hiệu khoảng, chẳng hạn [a,+∞), hoặc viết R∖{a} khi loại a.",
  quadratic_vertex: "Nhập cặp (hoành độ,tung độ).", quadratic_axis: "Nhập phương trình trục theo mẫu x = số.",
  exponent_numeric: "Nhập cơ số^số mũ = giá trị; tập xác định. Dùng R cho tập số thực.",
};
function answerHelp(problem: Problem) {
  if (!("task" in problem)) return "Viết một phương trình mỗi dòng. Nhấn Ctrl + Enter để gửi bài.";
  const format = problem.task.kind === "exponent_numeric" && problem.task.expression.startsWith("base;")
    ? "Nhập R hoặc ‘không phải hàm số mũ’ theo yêu cầu của đề." : answerFormats[problem.task.kind];
  return `Bộ chấm kiểm tra dòng cuối. ${format || "Nhập theo định dạng trong đề."} Nhấn Ctrl + Enter để gửi bài.`;
}
export default function Workspace({ initialReady }: { initialReady: boolean }) {
  const { profiles, topics, selectedTopic, setSelectedTopic, selectedTopicData, profile, history,
    session, draft, setDraft, report, busy, error, notice, conflict, pending, ready, dirty, locked,
    feedbackRef, retry, reconcile, selectProfile, startSession, openSession, submitTurn, saveThen, saveDraft, resume,
  } = useTutorSession(initialReady);
  const approvedExercise = Boolean(session && "task" in session.problem);
  const exerciseTitle = session && ("equation" in session.problem ? session.problem.equation :
    topics.find(topic => topic.topic_id === `TOPIC-${session.problem.concept_id}`)?.title || `Bài luyện ${session.problem.concept_id}`);

  return <><a className="skip-link" href="#main-content">Đến nội dung chính</a><main className="workspace" id="main-content" tabIndex={-1}>
    <header><a href="/" className="brand" aria-label="Mở, trang chủ">mở<span>.</span></a><span className="tag">KHÔNG GIAN HỌC TOÁN</span><span className="connection" role="status">{ready ? "Đã kết nối" : "Chưa kết nối"}</span></header>
    <div className="demo-note"><strong>Bản thử nội bộ.</strong> Chọn một chủ đề để xem phạm vi bộ chấm và tình trạng duyệt nội dung.</div>
    {error && <div className="alert" role="alert">{error}
      {pending && <button onClick={retry} disabled={busy}>Thử lại yêu cầu</button>}
      {pending && session && <button onClick={() => reconcile(true)} disabled={busy}>Kiểm tra trạng thái để sửa</button>}
      {conflict && session && <button onClick={() => reconcile(false)} disabled={busy}>Tải trạng thái mới</button>}
    </div>}
    {busy && <div className="busy-note" role="status">Đang xử lý yêu cầu…</div>}
    {notice && <div className="notice" role="status">{notice}</div>}
    <div className="learning-grid">
      <aside className="card sidebar"><p className="eyebrow">KHÔNG GIAN CỦA EM</p><h2>Hồ sơ demo</h2><label htmlFor="profile">Chọn hồ sơ để thử</label>
        <select id="profile" value={profile?.student_id || ""} disabled={locked} onChange={e => selectProfile(e.target.value)}><option value="">Chọn một hồ sơ</option>{profiles.map(p => <option key={p.student_id} value={p.student_id}>{p.display_name}</option>)}</select>
        {profile && <div className="topic-picker"><label htmlFor="topic">Chủ đề có thể thử</label>
          <select id="topic" value={selectedTopic} disabled={locked || !topics.length} onChange={e => setSelectedTopic(e.target.value)}>
            {!topics.length && <option value="">Chưa có chủ đề</option>}
            {topics.map(topic => <option key={topic.topic_id} value={topic.topic_id} disabled={!topic.internal_demo_available}>{topic.title}{!topic.internal_demo_available ? " · Chưa hỗ trợ" : ""}</option>)}
          </select>
          {selectedTopicData && <p className="topic-detail">{selectedTopicData.problem_count} bài · {selectedTopicData.tutoring_ready ? "Nội dung đã duyệt" : selectedTopicData.validator_available ? "Có bộ chấm thử nghiệm" : "Chưa có bộ chấm"}<br />{selectedTopicData.reason}</p>}
        </div>}
        <button className="primary" disabled={!profile || !selectedTopicData?.internal_demo_available || locked} onClick={startSession}>Bắt đầu phiên thử <span aria-hidden="true">→</span></button>
        <h3>Các phiên đã lưu</h3>{!history.length && <p className="muted">Chưa có phiên. Bắt đầu một phiên để thử lưu bài.</p>}
        <div className="history">{history.map((h, index) => <button className={session?.session_id === h.session_id ? "selected" : ""} disabled={locked} key={h.session_id} onClick={() => openSession(h.session_id)}><strong>Phiên {history.length - index}</strong><span>{new Date(h.created_at).toLocaleString("vi-VN")}</span><small>{h.status === "completed" ? "Đã kết thúc" : h.status === "paused" ? "Tạm dừng" : "Đang viết"}</small></button>)}</div>
      </aside>
      <section className="learning-main">
        {!session && <div className="hero"><p className="eyebrow">TỰ TÌM RA CÁCH GIẢI</p><h1>Mỗi bước nhỏ.<br />Một điều hiểu thêm.</h1><p className="intro">Chọn hồ sơ và chủ đề để bắt đầu luyện tập. Em có thể lưu bản nháp, xin gợi ý và xem lại kết quả cuối phiên.</p></div>}
        {session && !report && <>
          <article className="card exercise"><div className="section-head"><span className="eyebrow">{approvedExercise ? "BÀI LUYỆN" : "PHƯƠNG TRÌNH BẬC NHẤT"}</span><span className="pill">{session.review_status === "human_approved" ? "Nội dung đã duyệt" : "Nội dung thử nghiệm"}</span></div>
            <h1>{exerciseTitle}</h1><p><MathText text={session.problem.prompt} /></p><ProblemFormula problem={session.problem} /><label htmlFor="draft">{approvedExercise ? "Bài làm của em" : "Các bước làm của em"}</label>
            <textarea id="draft" rows={7} maxLength={2000} value={draft} disabled={session.status !== "active" || locked} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); submitTurn(); } }} aria-describedby="draft-help" placeholder="Viết mỗi bước trên một dòng…" />
            <p id="draft-help" className="input-help"><MathText text={answerHelp(session.problem)} /></p>
            <div className="draft-meta"><span>{dirty ? "Chưa lưu thay đổi" : "Đã lưu trên máy chủ"}</span><span>{draft.length}/2000 ký tự · v{session.state_version}</span></div>
            {session.status === "paused" ? <button className="primary" disabled={locked} onClick={resume}>Tiếp tục phiên</button> : <div className="actions">
              <button disabled={locked || !dirty || session.status !== "active"} onClick={saveDraft}>Lưu nháp</button>
              <button className="primary" disabled={locked || !draft.trim() || session.status !== "active"} onClick={submitTurn}>{session.tutoring_enabled ? "Gửi bài" : "Gửi bài để lưu"}</button>
              {session.tutoring_enabled && <button disabled={locked || session.status !== "active"} onClick={() => saveThen("request_hint")}>Xin gợi ý</button>}
              {session.tutoring_enabled && approvedExercise && <>
                <button disabled={locked || session.status !== "active"} onClick={() => saveThen("request_explanation")}>Giải thích khái niệm</button>
                <button disabled={locked || session.status !== "active"} onClick={() => saveThen("request_example")}>Xem ví dụ khác</button>
              </>}
              <button disabled={locked || session.status !== "active"} onClick={() => saveThen("pause")}>Tạm dừng</button>
            </div>}
          </article>
          {session.tutoring_enabled && session.turns.length > 0 && <div className="tutor-panel" ref={feedbackRef} tabIndex={-1} aria-live="polite">
            <span className="eyebrow">PHẢN HỒI TỪ GIA SƯ</span>
            <TeachingFeedback response={session.turns[session.turns.length - 1].response} />
          </div>}
          <article className="card"><div className="section-head"><h2>Nhật ký phiên</h2><span className="pill">{session.tutoring_enabled ? `Mức hỗ trợ: ${session.hint_level}/3` : "Phiên cũ chỉ lưu trữ"}</span></div>
            {!session.turns.length && <p className="muted">Chưa có bài nộp. Lưu nháp không tạo lượt chấm hoặc observation.</p>}
            {session.turns.map(t => <div className="turn" key={t.turn_id}>{t.action === "submit" && <><span className="pill">{assessmentLabel(t.assessment.assessment_status)}{t.assessment.first_error_step ? ` · Bước ${t.assessment.first_error_step}` : ""}</span><pre>{t.steps.join("\n")}</pre></>}<TeachingFeedback response={t.response} /></div>)}
            <div className="actions"><button disabled={locked || session.status !== "active" || session.available_next === 0} onClick={() => saveThen("next")}>Thử bài tiếp ({session.available_next})</button><button disabled={locked} onClick={() => saveThen("finish")}>Kết thúc & xem báo cáo</button></div>
          </article>
        </>}
        {report && <LearningReport report={report} />}
      </section>
    </div><footer>Demo nội bộ · Kiểm tra Toán trong phạm vi công bố · Nguồn phản hồi được ghi ở từng lượt · API key chỉ ở server</footer>
  </main></>;
}
