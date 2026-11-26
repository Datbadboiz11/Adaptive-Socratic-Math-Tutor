"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { SessionView, TopicView, Report } from "./lib/api-types";
import { api, ApiFailure } from "./lib/api";
import { TeachingFeedback } from "./components/TeachingFeedback";
import { SkillEvidence } from "./components/SkillEvidence";
import { MathText } from "./components/MathText";

type Profile = { student_id: string; display_name: string };
type Topic = TopicView;
type Session = SessionView;
type Problem = SessionView["problem"];
type History = { session_id: string; status: string; created_at: string };
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
type Pending = { path: string; method: string; body: Record<string, unknown>; apply: "session" | "turn" | "report" };

export default function Workspace({ initialReady }: { initialReady: boolean }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedTopic, setSelectedTopic] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [history, setHistory] = useState<History[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [draft, setDraft] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [ready, setReady] = useState(initialReady);
  const busyRef = useRef(false);
  const identityEpoch = useRef(0);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const refreshHistory = useCallback(async () => {
    const epoch = identityEpoch.current;
    const rows = await api<History[]>("sessions");
    if (epoch === identityEpoch.current) setHistory(rows);
  }, []);
  const refreshTopics = useCallback(async () => {
    const available = await api<Topic[]>("topics");
    setTopics(available);
    setSelectedTopic(current => available.some(topic => topic.topic_id === current && topic.internal_demo_available)
      ? current : available.find(topic => topic.internal_demo_available)?.topic_id || "");
  }, []);
  useEffect(() => {
    api<Profile[]>("demo/profiles").then(setProfiles).catch(e => setError(e.message));
    const epoch = identityEpoch.current;
    api<Profile>("me").then(p => {
      if (epoch !== identityEpoch.current) return;
      setProfile(p); return Promise.all([refreshHistory(), refreshTopics()]);
    }).catch(() => {});
  }, [refreshHistory, refreshTopics]);
  const dirty = Boolean(session && draft !== session.draft);
  useEffect(() => {
    if (!dirty && !pending) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, pending]);
  const accept = (value: Session) => {
    setSession(value); setDraft(value.draft); setReport(null); setReady(true);
    const topic = "equation" in value.problem ? "TOPIC-LINEAR-01" : `TOPIC-${value.problem.concept_id}`;
    setSelectedTopic(topic);
  };
  const act = async (fn: () => Promise<void>) => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setError(""); setNotice("");
    try { await fn(); }
    catch (e) { const failure = e as ApiFailure; setError(failure.message); if (failure.code === "network_unavailable") setReady(false); if (["state_conflict", "opportunity_conflict"].includes(failure.code)) setConflict(true); }
    finally { busyRef.current = false; setBusy(false); }
  };
  const execute = async (request: Pending): Promise<Session | null> => {
    try {
      const data = await api<Session & Report & { session: Session; message: string }>(request.path, request.method, request.body);
      setPending(null); setConflict(false);
      setReady(true);
      let next: Session | null = null;
      if (request.apply === "report") { setReport(data); setSession(s => s ? { ...s, status: "completed" } : s); }
      else { next = request.apply === "turn" ? data.session : data; accept(next); }
      setNotice(request.apply === "turn" ? data.message : "Đã lưu vào PostgreSQL.");
      if (request.apply === "turn") window.setTimeout(() => feedbackRef.current?.focus(), 0);
      refreshHistory().catch(() => {});
      return next;
    } catch (e) { if ((e as ApiFailure).retryable) setPending(request); else setPending(null); throw e; }
  };
  const mutation = (s: Session, action: string, extra: Record<string, unknown> = {}, apply: Pending["apply"] = "session") => execute({
    path: `sessions/${s.session_id}/${action}`, method: action === "draft" ? "PUT" : "POST",
    body: { request_id: crypto.randomUUID(), expected_state_version: s.state_version, ...extra }, apply,
  });
  const saveCurrentDraft = async () => {
    if (session && dirty && session.status === "active") await mutation(session, "draft", { draft });
  };
  const saveThen = async (action: "pause" | "next" | "finish" | "request_hint" | "request_explanation" | "request_example") => {
    if (!session) return;
    let current = session;
    if (dirty) current = (await mutation(current, "draft", { draft }))!;
    if (action.startsWith("request_")) await mutation(current,"turns",{ opportunity_id: current.current_opportunity_id, action, steps: [] },"turn");
    else await mutation(current, action, {}, action === "finish" ? "report" : "session");
  };
  const openSession = async (id: string) => {
    if (session?.session_id === id) return;
    await saveCurrentDraft();
    const value = await api<Session>(`sessions/${id}`);
    accept(value); setConflict(false); setPending(null);
    if (value.status === "completed") setReport(await api<Report>(`sessions/${id}/report`));
  };
  const locked = busy || Boolean(pending) || conflict;
  const selectedTopicData = topics.find(topic => topic.topic_id === selectedTopic);
  const approvedExercise = Boolean(session && "task" in session.problem);
  const exerciseTitle = session && ("equation" in session.problem ? session.problem.equation :
    topics.find(topic => topic.topic_id === `TOPIC-${session.problem.concept_id}`)?.title || `Bài luyện ${session.problem.concept_id}`);
  const finalAnswerReport = report?.assessment_scope === "final_answer";
  const submitTurn = async () => {
    if (!session || locked || session.status !== "active" || !draft.trim()) return;
    const steps = draft.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    if (steps.length > 12 || steps.some(s => s.length > 160)) throw new Error("Tối đa 12 dòng, 160 ký tự mỗi dòng. Bản nháp vẫn được giữ.");
    await mutation(session, "turns", { opportunity_id: session.current_opportunity_id, action: "submit", steps }, "turn");
  };

  return <><a className="skip-link" href="#main-content">Đến nội dung chính</a><main className="workspace" id="main-content">
    <header><a href="/" className="brand" aria-label="Mở, trang chủ">mở<span>.</span></a><span className="tag">KHÔNG GIAN HỌC TOÁN</span><span className="connection" role="status">{ready ? "Đã kết nối" : "Chưa kết nối"}</span></header>
    <div className="demo-note"><strong>Bản thử nội bộ.</strong> Chọn một chủ đề để xem phạm vi bộ chấm và tình trạng duyệt nội dung.</div>
    {error && <div className="alert" role="alert">{error}
      {pending && <button onClick={() => act(async () => { await execute(pending); })} disabled={busy}>Thử lại yêu cầu</button>}
      {pending && session && <button onClick={() => act(async () => {
        const fresh = await api<Session>(`sessions/${session.session_id}`);
        const same = fresh.current_opportunity_id === session.current_opportunity_id && fresh.status === "active";
        if (!same && dirty && !window.confirm("Bài đã đổi hoặc phiên đã đóng. Hãy sao chép nháp trước khi tải trạng thái mới. Tiếp tục?")) return;
        setSession(fresh); setDraft(same ? draft : fresh.draft); setPending(null); setConflict(false);
        setNotice(same ? "Đã đối soát với máy chủ. Bạn có thể sửa bài rồi gửi như yêu cầu mới." : "Đã tải bài hiện tại từ máy chủ.");
      })} disabled={busy}>Kiểm tra trạng thái để sửa</button>}
      {conflict && session && <button onClick={() => act(async () => {
        const fresh = await api<Session>(`sessions/${session.session_id}`);
        const same = fresh.current_opportunity_id === session.current_opportunity_id && fresh.status === "active";
        if (!same && dirty && !window.confirm("Bài đã đổi hoặc phiên đã đóng. Hãy sao chép nháp trước khi tải trạng thái mới. Tiếp tục?")) return;
        setSession(fresh); if (!same || !dirty) setDraft(fresh.draft); setConflict(false); setError(""); setNotice(same ? "Đã tải trạng thái mới, giữ bản nháp đang viết. Bạn có thể lưu lại." : "Đã tải trạng thái mới.");
      })} disabled={busy}>Tải trạng thái mới</button>}
    </div>}
    {busy && <div className="busy-note" role="status">Đang xử lý yêu cầu…</div>}
    {notice && <div className="notice" role="status">{notice}</div>}
    <div className="learning-grid">
      <aside className="card sidebar"><p className="eyebrow">KHÔNG GIAN CỦA EM</p><h2>Hồ sơ demo</h2><label htmlFor="profile">Chọn hồ sơ để thử</label>
        <select id="profile" value={profile?.student_id || ""} disabled={locked} onChange={e => { const id = e.target.value; if (!id || id === profile?.student_id) return; act(async () => {
          await saveCurrentDraft();
          identityEpoch.current += 1;
          const data = await api<{ profile: Profile }>("demo/login", "POST", { demo_profile_id: id }); setProfile(data.profile); setHistory([]); setSession(null); setDraft(""); setReport(null); await Promise.all([refreshHistory(), refreshTopics()]);
        }); }}><option value="">Chọn một hồ sơ</option>{profiles.map(p => <option key={p.student_id} value={p.student_id}>{p.display_name}</option>)}</select>
        {profile && <div className="topic-picker"><label htmlFor="topic">Chủ đề có thể thử</label>
          <select id="topic" value={selectedTopic} disabled={locked || !topics.length} onChange={e => setSelectedTopic(e.target.value)}>
            {!topics.length && <option value="">Chưa có chủ đề</option>}
            {topics.map(topic => <option key={topic.topic_id} value={topic.topic_id} disabled={!topic.internal_demo_available}>{topic.title}{!topic.internal_demo_available ? " · Chưa hỗ trợ" : ""}</option>)}
          </select>
          {selectedTopicData && <p className="topic-detail">{selectedTopicData.problem_count} bài · {selectedTopicData.tutoring_ready ? "Nội dung đã duyệt" : selectedTopicData.validator_available ? "Có bộ chấm thử nghiệm" : "Chưa có bộ chấm"}<br />{selectedTopicData.reason}</p>}
        </div>}
        <button className="primary" disabled={!profile || !selectedTopicData?.internal_demo_available || locked} onClick={() => act(async () => {
          await saveCurrentDraft();
          await execute({ path: "sessions", method: "POST", body: { request_id: crypto.randomUUID(), demo_profile_id: profile!.student_id, topic_id: selectedTopic }, apply: "session" });
        })}>Bắt đầu phiên thử <span aria-hidden="true">→</span></button>
        <h3>Các phiên đã lưu</h3>{!history.length && <p className="muted">Chưa có phiên. Bắt đầu một phiên để thử lưu bài.</p>}
        <div className="history">{history.map((h, index) => <button className={session?.session_id === h.session_id ? "selected" : ""} disabled={locked} key={h.session_id} onClick={() => act(() => openSession(h.session_id))}><strong>Phiên {history.length - index}</strong><span>{new Date(h.created_at).toLocaleString("vi-VN")}</span><small>{h.status === "completed" ? "Đã kết thúc" : h.status === "paused" ? "Tạm dừng" : "Đang viết"}</small></button>)}</div>
      </aside>
      <section className="learning-main">
        {!session && <div className="hero"><p className="eyebrow">TỰ TÌM RA CÁCH GIẢI</p><h1>Mỗi bước nhỏ.<br />Một điều hiểu thêm.</h1><p className="intro">Chọn hồ sơ và chủ đề để bắt đầu luyện tập. Em có thể lưu bản nháp, xin gợi ý và xem lại kết quả cuối phiên.</p></div>}
        {session && !report && <>
          <article className="card exercise"><div className="section-head"><span className="eyebrow">{approvedExercise ? "BÀI LUYỆN" : "PHƯƠNG TRÌNH BẬC NHẤT"}</span><span className="pill">{session.review_status === "human_approved" ? "Nội dung đã duyệt" : "Nội dung thử nghiệm"}</span></div>
            <h1>{exerciseTitle}</h1><p><MathText text={session.problem.prompt} /></p><label htmlFor="draft">{approvedExercise ? "Bài làm của em" : "Các bước làm của em"}</label>
            <textarea id="draft" rows={7} maxLength={2000} value={draft} disabled={session.status !== "active" || locked} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); act(submitTurn); } }} aria-describedby="draft-help" placeholder="Viết mỗi bước trên một dòng…" />
            <p id="draft-help" className="input-help"><MathText text={answerHelp(session.problem)} /></p>
            <div className="draft-meta"><span>{dirty ? "Chưa lưu thay đổi" : "Đã lưu trên máy chủ"}</span><span>{draft.length}/2000 ký tự · v{session.state_version}</span></div>
            {session.status === "paused" ? <button className="primary" disabled={locked} onClick={() => act(async () => { await mutation(session, "resume"); })}>Tiếp tục phiên</button> : <div className="actions">
              <button disabled={locked || !dirty || session.status !== "active"} onClick={() => act(async () => { await mutation(session, "draft", { draft }); })}>Lưu nháp</button>
              <button className="primary" disabled={locked || !draft.trim() || session.status !== "active"} onClick={() => act(submitTurn)}>{session.tutoring_enabled ? "Gửi bài" : "Gửi bài để lưu"}</button>
              {session.tutoring_enabled && <button disabled={locked || session.status !== "active"} onClick={() => act(() => saveThen("request_hint"))}>Xin gợi ý</button>}
              {session.tutoring_enabled && approvedExercise && <>
                <button disabled={locked || session.status !== "active"} onClick={() => act(() => saveThen("request_explanation"))}>Giải thích khái niệm</button>
                <button disabled={locked || session.status !== "active"} onClick={() => act(() => saveThen("request_example"))}>Xem ví dụ khác</button>
              </>}
              <button disabled={locked || session.status !== "active"} onClick={() => act(() => saveThen("pause"))}>Tạm dừng</button>
            </div>}
          </article>
          {session.tutoring_enabled && session.turns.length > 0 && <div className="tutor-panel" ref={feedbackRef} tabIndex={-1} aria-live="polite">
            <span className="eyebrow">PHẢN HỒI TỪ GIA SƯ</span>
            <TeachingFeedback response={session.turns[session.turns.length - 1].response} />
          </div>}
          <article className="card"><div className="section-head"><h2>Nhật ký phiên</h2><span className="pill">{session.tutoring_enabled ? `Mức hỗ trợ: ${session.hint_level}/3` : "Phiên cũ chỉ lưu trữ"}</span></div>
            {!session.turns.length && <p className="muted">Chưa có bài nộp. Lưu nháp không tạo lượt chấm hoặc observation.</p>}
            {session.turns.map(t => <div className="turn" key={t.turn_id}>{t.action === "submit" && <><span className="pill">{assessmentLabel(t.assessment.assessment_status)}{t.assessment.first_error_step ? ` · Bước ${t.assessment.first_error_step}` : ""}</span><pre>{t.steps.join("\n")}</pre></>}<TeachingFeedback response={t.response} /></div>)}
            <div className="actions"><button disabled={locked || session.status !== "active" || session.available_next === 0} onClick={() => act(() => saveThen("next"))}>Thử bài tiếp ({session.available_next})</button><button disabled={locked} onClick={() => act(() => saveThen("finish"))}>Kết thúc & xem báo cáo</button></div>
          </article>
        </>}
        {report && <article className="card report"><p className="eyebrow">NHÌN LẠI PHIÊN THỬ</p><h1>Từng bước em đã làm.</h1><p>{finalAnswerReport ? "Kết quả dựa trên dòng cuối của từng bài. Báo cáo ghi riêng bài tự làm, bài lặp hoặc gần và bài đúng sau gợi ý." : report.tutoring_enabled ? "Kết quả xác minh và mức hỗ trợ được ghi riêng. Bài lặp hoặc sửa sau gợi ý không tự tạo thêm bằng chứng độc lập." : "Đây là phiên cũ chỉ lưu trữ. Bắt đầu phiên mới để thử bộ chấm."}</p>
          <div className="metrics">{[["Lượt gửi bài", report.submitted_turns], ["Chưa xác minh", report.unverified_submissions], ["Bài đã xem", report.problems_viewed], ["Tự làm đúng", report.independent_correct], ["Đúng sau hỗ trợ", report.assisted_correct], ["Bài lặp hoặc gần đã đúng", report.repeat_or_near_correct], ["Observation trong phiên", report.valid_observations]].map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div>
          <SkillEvidence skills={report.skills} />
          {!finalAnswerReport && !report.mastery.length && <p className="muted">Phiên này chưa tạo bằng chứng BKT đủ điều kiện. Bài lặp và bài có hỗ trợ vẫn được lưu trong kết quả.</p>}
          <ul>{report.limitations.map(text => <li key={text}>{text}</li>)}</ul><h2>Bài đã gửi</h2>{session?.turns.filter(t => t.action === "submit").map(t => <pre key={t.turn_id}>{t.steps.join("\n")}</pre>)}
        </article>}
      </section>
    </div><footer>Demo nội bộ · Kiểm tra Toán trong phạm vi công bố · Nguồn phản hồi được ghi ở từng lượt · API key chỉ ở server</footer>
  </main></>;
}
