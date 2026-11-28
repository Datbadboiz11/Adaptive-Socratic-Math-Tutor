"use client";
import { useEffect, useRef, useState } from "react";
import type { SessionView, SkillMastery } from "./lib/api-types";
import { useTutorSession } from "./hooks/useTutorSession";
import { LearningReport } from "./components/LearningReport";
import { TeachingFeedback } from "./components/TeachingFeedback";
import { Formula, MathText } from "./components/MathText";
import { ProblemFormula } from "./components/ProblemFormula";
import { Icon, type IconName } from "./components/Icon";
import { MasteryOverview } from "./components/MasteryOverview";
import { SessionHistory } from "./components/SessionHistory";
import { MathIllustration } from "./components/MathIllustration";
import { BrandLogo } from "./components/BrandLogo";
import { SidebarBotanical } from "./components/SidebarBotanical";

type Problem = SessionView["problem"];
type View = "overview" | "learn" | "topics" | "history" | "progress";
const navigation: { id: View; title: string; icon: IconName }[] = [
  { id: "overview", title: "Tổng quan", icon: "overview" },
  { id: "learn", title: "Không gian học", icon: "book" },
  { id: "topics", title: "Khám phá chủ đề", icon: "layers" },
  { id: "history", title: "Lịch sử học tập", icon: "history" },
  { id: "progress", title: "Tiến độ của em", icon: "chart" },
];
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
function sessionMastery(session: SessionView | null): SkillMastery[] {
  return (session?.mastery || []).flatMap(item => {
    if (typeof item.skill_id !== "string" || (item.mastery !== null && (typeof item.mastery !== "number" || !Number.isFinite(item.mastery)))) return [];
    return [{ skill_id: item.skill_id, mastery: item.mastery as number | null,
      evidence_count: typeof item.evidence_count === "number" ? item.evidence_count : 0,
      parameter_version: typeof item.parameter_version === "string" ? item.parameter_version : null,
      status: item.mastery !== null && typeof item.evidence_count === "number" && item.evidence_count >= 3 ? "estimated" as const : "insufficient_data" as const }];
  });
}
export default function Workspace({ initialReady }: { initialReady: boolean }) {
  const { profiles, topics, selectedTopic, setSelectedTopic, selectedTopicData, profile, history,
    session, draft, setDraft, report, busy, error, notice, conflict, pending, ready, dirty, locked,
    feedbackRef, retry, reconcile, selectProfile, startSession, openSession, submitTurn, saveThen, saveDraft, resume,
  } = useTutorSession(initialReady);
  const [view, setView] = useState<View>("overview");
  const [search, setSearch] = useState("");
  const mainRef = useRef<HTMLElement>(null);
  const drawerRef = useRef<HTMLDialogElement>(null);
  const hasNavigated = useRef(false);

  useEffect(() => {
    const sync = () => {
      const next = window.location.hash.slice(1);
      if (navigation.some(item => item.id === next)) setView(next as View);
      else if (!next) setView("overview");
    };
    sync();
    window.addEventListener("hashchange", sync);
    const closeOnResize = () => { if (window.innerWidth > 760) drawerRef.current?.close(); };
    window.addEventListener("resize", closeOnResize);
    return () => { window.removeEventListener("hashchange", sync); window.removeEventListener("resize", closeOnResize); };
  }, []);
  useEffect(() => {
    if (hasNavigated.current) mainRef.current?.focus();
    hasNavigated.current = true;
  }, [view]);
  const navigate = (next: View) => {
    drawerRef.current?.close();
    if (next === view) requestAnimationFrame(() => mainRef.current?.focus());
    setView(next);
    window.location.hash = next;
  };
  const startLearning = async () => { await startSession(); navigate("learn"); };
  const openLearning = async (id: string) => { await openSession(id); navigate("learn"); };
  const approvedExercise = Boolean(session && "task" in session.problem);
  const exerciseTitle = session && ("equation" in session.problem ? "Phương trình bậc nhất" :
    topics.find(topic => topic.topic_id === `TOPIC-${session.problem.concept_id}`)?.title || `Bài luyện ${session.problem.concept_id}`);
  const mastery = report?.mastery || sessionMastery(session);
  const completed = history.filter(item => item.status === "completed").length;
  const active = history.filter(item => item.status !== "completed").length;
  const topicResults = topics.filter(topic => topic.title.toLocaleLowerCase("vi").includes(search.toLocaleLowerCase("vi")));
  const dateLabel = new Date().toLocaleDateString("vi-VN", { timeZone: "Asia/Bangkok", day: "numeric", month: "long" });

  const sidebarContent = (mobile: boolean) => <>
    <div className="sidebar-brand"><a href="#overview" className="brand" onClick={e => { e.preventDefault(); navigate("overview"); }} aria-label="Mở, tổng quan"><BrandLogo /></a>{mobile && <button className="icon-button" aria-label="Đóng điều hướng" onClick={() => drawerRef.current?.close()}><Icon name="close" /></button>}</div>
    <div className="workspace-name"><span className="workspace-logo"><Icon name="book" size={18} /></span><span>Không gian học toán<small>Adaptive Socratic Tutor</small></span></div>
    <nav aria-label="Điều hướng chính"><p className="nav-group-label">Học tập</p>{navigation.map(item => <a key={item.id} href={`#${item.id}`} className={view === item.id ? "nav-link active" : "nav-link"} aria-current={view === item.id ? "page" : undefined} onClick={e => { e.preventDefault(); navigate(item.id); }}><Icon name={item.icon} /><span>{item.title}</span>{item.id === "learn" && session?.status === "active" && <span className="active-dot" />}</a>)}</nav>
    <SidebarBotanical />
    <div className="sidebar-bottom">
      <div className="sidebar-note"><Icon name="leaf" /><p>Hiểu cách nghĩ.<br /><strong>Tự tìm cách giải.</strong></p></div>
      <div className="profile-block"><span className="avatar" aria-hidden="true">{profile?.display_name.slice(0, 1).toLocaleUpperCase("vi") || "M"}</span><div><label htmlFor={mobile ? "profile-mobile" : "profile"}>Hồ sơ học tập <span className="demo-label">Demo</span></label><select id={mobile ? "profile-mobile" : "profile"} value={profile?.student_id || ""} disabled={locked} onChange={e => selectProfile(e.target.value)}><option value="">Chọn hồ sơ</option>{profiles.map(p => <option key={p.student_id} value={p.student_id}>{p.display_name}</option>)}</select></div></div>
    </div>
  </>;
  const topicPicker = <div className="topic-picker">
    <label htmlFor="topic">Em muốn khám phá điều gì?</label>
    <div className="topic-select-row"><select id="topic" value={selectedTopic} disabled={!profile || locked || !topics.length} onChange={e => setSelectedTopic(e.target.value)}>
      {!topics.length && <option value="">{profile ? "Chưa có chủ đề" : "Chọn hồ sơ trước khi bắt đầu"}</option>}
      {topics.map(topic => <option key={topic.topic_id} value={topic.topic_id} disabled={!topic.internal_demo_available}>{topic.title}{!topic.internal_demo_available ? " · Chưa hỗ trợ" : ""}</option>)}
    </select><button className="primary" disabled={!profile || !selectedTopicData?.internal_demo_available || locked} onClick={startLearning}>Bắt đầu phiên thử<Icon name="arrow" size={18} /></button></div>
    {selectedTopicData && <p className="topic-detail">{selectedTopicData.problem_count} bài tập <span aria-hidden="true">/</span> {selectedTopicData.tutoring_ready ? "Nội dung đã duyệt" : selectedTopicData.validator_available ? "Bộ chấm thử nghiệm" : "Chưa có bộ chấm"}</p>}
    {selectedTopicData?.reason && <details className="topic-scope"><summary>Phạm vi chủ đề</summary><p>{selectedTopicData.reason}</p></details>}
    {!profile && <p className="input-help">Chọn hồ sơ demo ở thanh điều hướng để lưu quá trình học của em.</p>}
  </div>;
  const historyPanel = (limit?: number) => <SessionHistory history={history} limit={limit} currentId={session?.session_id} locked={locked} onOpen={openLearning} onStart={() => navigate("learn")} />;
  const introduction = <section className="learning-invitation">
    <div className="invitation-copy"><span className="invitation-label"><span className="small-orbit" aria-hidden="true" />Học từ cách nghĩ</span><h2>Không chỉ tìm đáp án.<br />Hiểu từng bước đi.</h2><p>Một bài toán, nhiều điều để khám phá. Gia sư sẽ gợi mở để em tự tìm ra cách giải.</p>
      {session && session.status !== "completed" && <button className="invitation-resume" onClick={() => navigate("learn")}><Icon name="play" size={16} />Trở lại phiên đang học<Icon name="arrow" size={16} /></button>}
    </div><MathIllustration />
  </section>;

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Đến nội dung chính</a>
    <aside className="app-sidebar">{sidebarContent(false)}</aside>
    <dialog className="mobile-drawer" ref={drawerRef} aria-label="Điều hướng và hồ sơ học tập" onClick={e => { if (e.target === e.currentTarget) drawerRef.current?.close(); }}><div className="drawer-content">{sidebarContent(true)}</div></dialog>
    <div className="app-body">
      <header className="topbar"><div className="topbar-location"><button className="icon-button mobile-menu" aria-label="Mở điều hướng" aria-haspopup="dialog" onClick={() => drawerRef.current?.showModal()}><Icon name="menu" /></button><span className="breadcrumb-root">Không gian học tập</span><Icon name="chevron" size={14} /><span>{navigation.find(item => item.id === view)?.title}</span></div><div className="topbar-meta"><span className="demo-label">Bản thử nội bộ</span><span className={ready ? "connection online" : "connection offline"} role="status"><span aria-hidden="true" />{ready ? "Đã kết nối" : "Chưa kết nối"}</span></div></header>
      <main className="workspace" id="main-content" ref={mainRef} tabIndex={-1}>
        <div className="system-messages">
          {error && <div className="alert" role="alert"><Icon name="info" /><div><strong>Chưa thể hoàn tất thao tác</strong><p>{error}</p><div className="actions">{pending && <button onClick={retry} disabled={busy}>Thử lại yêu cầu</button>}{pending && session && <button onClick={() => reconcile(true)} disabled={busy}>Kiểm tra trạng thái để sửa</button>}{conflict && session && <button onClick={() => reconcile(false)} disabled={busy}>Tải trạng thái mới</button>}</div></div></div>}
          {busy && <div className="busy-note" role="status"><span className="loading-dot" />Đang xử lý yêu cầu…</div>}
          {notice && <div className="notice" role="status"><Icon name="check" size={18} />{notice}</div>}
        </div>

        {view === "overview" && <>
          <div className="page-heading"><div><p className="greeting">{dateLabel}</p><h1>{profile ? `Chào ${profile.display_name}.` : "Chào em, cùng mở bài nhé."}</h1><p>Mỗi bước nhỏ hôm nay, thêm một điều em hiểu.</p></div><span className="heading-mark" aria-hidden="true"><Icon name="leaf" size={28} /></span></div>
          {introduction}
          <section className="panel start-panel overview-start"><div className="start-panel-heading"><span className="start-panel-icon"><Icon name="book" size={22} /></span><div><h2>Buổi học tiếp theo của em</h2><p>Chọn một chủ đề, khám phá bằng cách nghĩ của riêng em.</p></div></div>{topicPicker}</section>
          <div className="dashboard-section-heading"><h2>Hành trình của em</h2><p>Nhìn lại những gì đã học, sẵn sàng cho bước tiếp theo.</p></div>
          <div className="stat-grid" aria-label="Tổng quan học tập">{([
            ["history", history.length, "Phiên học đã lưu", "Hành trình của em"],
            ["check", completed, "Phiên đã hoàn thành", "Từng bước tiến về phía trước"],
            ["book", active, "Phiên có thể tiếp tục", "Trở lại bất cứ lúc nào"],
          ] as const).map(([icon, value, label, detail]) => <div className="stat" key={label}><span className="stat-label">{label}</span><span className="stat-icon"><Icon name={icon} /></span><strong>{value}</strong><small>{detail}</small></div>)}</div>
          <div className="dashboard-columns"><section className="panel recent-panel"><div className="section-head"><h2>Gần đây em đã học</h2><button className="text-button" onClick={() => navigate("history")}>Xem tất cả<Icon name="arrow" size={16} /></button></div><p className="section-description">Bài đang làm và những phiên học đã lưu.</p>{historyPanel(3)}</section><MasteryOverview mastery={mastery} skills={report?.skills} currentSkill={session && exerciseTitle ? { id: session.problem.primary_skill_id, title: exerciseTitle } : undefined} /></div>
          <div className="learning-principle"><Icon name="message" /><p><strong>Một gợi ý đúng lúc, một cách nghĩ mới.</strong> Em có thể xin gợi ý, lưu bài đang làm và tiếp tục khi sẵn sàng.</p></div>
        </>}

        {view === "topics" && <>
          <div className="page-heading"><div><p className="greeting">Học theo nhịp của em</p><h1>Khám phá chủ đề</h1><p>Chọn một chủ đề để bắt đầu từ những điều em muốn hiểu rõ hơn.</p></div></div>
          <div className="catalogue-toolbar"><label className="search-field"><Icon name="search" /><span className="sr-only">Tìm chủ đề</span><input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Tìm tên chủ đề…" /></label><span className="muted" role="status">{topicResults.length} chủ đề</span></div>
          {!topics.length && <section className="panel empty-state"><Icon name="book" size={32} /><h2>{profile ? "Chưa tải được chủ đề" : "Chọn hồ sơ để khám phá"}</h2><p>{profile ? "Kiểm tra kết nối và thử lại sau." : "Chọn hồ sơ demo trong thanh điều hướng để xem các chủ đề hiện có."}</p></section>}
          {!!topics.length && !topicResults.length && <section className="panel empty-state"><Icon name="search" size={32} /><h2>Chưa tìm thấy chủ đề</h2><p>Thử một từ khóa ngắn hơn hoặc xem lại toàn bộ chủ đề.</p><button onClick={() => setSearch("")}>Xóa tìm kiếm</button></section>}
          <div className="topic-grid">{topicResults.map(topic => <article className="panel topic-card" key={topic.topic_id}><div className="section-head"><span className="topic-icon"><Icon name="book" size={23} /></span><span className={topic.internal_demo_available ? "pill success" : "pill neutral"}>{topic.internal_demo_available ? "Có thể luyện tập" : "Chưa hỗ trợ"}</span></div><h2>{topic.title}</h2><p>{topic.problem_count} bài tập trong chủ đề</p><details><summary>{topic.tutoring_ready ? "Nội dung đã duyệt" : "Phạm vi thử nghiệm"}</summary><p>{topic.reason}</p></details><button disabled={locked || !topic.internal_demo_available} onClick={() => { setSelectedTopic(topic.topic_id); navigate("learn"); }}>Chọn chủ đề<Icon name="arrow" size={17} /></button></article>)}</div>
        </>}

        {view === "history" && <>
          <div className="page-heading"><div><p className="greeting">Lưu lại từng bước tiến</p><h1>Lịch sử học tập</h1><p>Tiếp tục bài đang làm hoặc mở lại báo cáo của một phiên đã kết thúc.</p></div><button onClick={() => navigate("learn")}><Icon name="plus" size={18} />Phiên học mới</button></div>
          <section className="panel"><div className="section-head"><h2>Các phiên đã lưu</h2><span className="pill neutral">{history.length} phiên</span></div>{historyPanel()}</section>
        </>}

        {view === "progress" && <>
          <div className="page-heading"><div><p className="greeting">Hiểu hơn về quá trình học</p><h1>Tiến độ của em</h1><p>Xem bằng chứng học tập và những kỹ năng cần tiếp tục khám phá.</p></div><button onClick={() => navigate("learn")}><Icon name="book" size={18} />Trở lại học tập</button></div>
          <MasteryOverview mastery={mastery} skills={report?.skills} currentSkill={session && exerciseTitle ? { id: session.problem.primary_skill_id, title: exerciseTitle } : undefined} />
          {report ? <LearningReport report={report} /> : <section className="panel"><div className="section-head"><h2>Báo cáo phiên học</h2><Icon name="chart" /></div><div className="empty-state compact"><h3>{session ? "Báo cáo sẽ sẵn sàng khi kết thúc phiên" : "Chưa có báo cáo được mở"}</h3><p>{session ? "Tiếp tục làm bài rồi chọn “Kết thúc & xem báo cáo” để nhìn lại từng bước." : "Mở một phiên đã kết thúc từ lịch sử để xem kết quả và bằng chứng theo kỹ năng."}</p><button onClick={() => navigate(session ? "learn" : "history")}>{session ? "Tiếp tục học" : "Xem lịch sử"}<Icon name="arrow" size={17} /></button></div></section>}
        </>}

        {view === "learn" && <>
          <div className="page-heading"><div><p className="greeting">Tự tìm ra cách giải</p><h1>Không gian học</h1><p>{session ? "Cứ thử cách nghĩ của em. Gia sư sẽ đồng hành từng bước." : "Chọn chủ đề và bắt đầu một cuộc trò chuyện với toán học."}</p></div>{session && <span className="pill neutral"><Icon name="clock" size={14} />{session.status === "paused" ? "Đang tạm dừng" : session.status === "completed" ? "Đã kết thúc" : "Phiên đang học"}</span>}</div>
          {(!session || report) && <section className="panel start-panel">{topicPicker}</section>}
          {!session && <>{introduction}<section className="panel"><div className="section-head"><h2>Tiếp tục phiên trước</h2><Icon name="history" /></div>{historyPanel(3)}</section></>}
          {session && !report && <>
            <details className="session-topic-switch"><summary>Chọn chủ đề và mở phiên mới</summary><div className="panel">{topicPicker}</div></details>
            <div className="learning-grid">
              <article className="panel exercise"><div className="section-head"><span className="section-label"><Icon name="book" size={17} />{approvedExercise ? "Bài luyện" : "Phương trình bậc nhất"}</span><span className={session.review_status === "human_approved" ? "pill success" : "pill warning"}>{session.review_status === "human_approved" ? "Nội dung đã duyệt" : "Nội dung thử nghiệm"}</span></div>
                <h2>{exerciseTitle}</h2><div className="problem-prompt"><MathText text={session.problem.prompt} /></div>
                {"equation" in session.problem ? <div className="problem-formula"><Formula value={session.problem.equation} /></div> : <ProblemFormula problem={session.problem} />}
                <div className="editor-heading"><label htmlFor="draft">{approvedExercise ? "Bài làm của em" : "Các bước làm của em"}</label><span className="editor-shortcut">Ctrl + Enter để gửi</span></div>
                <textarea id="draft" rows={7} maxLength={2000} value={draft} disabled={session.status !== "active" || locked} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); submitTurn(); } }} aria-describedby="draft-help" placeholder="Viết mỗi bước trên một dòng…" />
                <p id="draft-help" className="input-help"><MathText text={answerHelp(session.problem)} /></p>
                <div className="draft-meta"><span><Icon name={dirty ? "clock" : "check"} size={14} />{dirty ? "Chưa lưu thay đổi" : "Đã lưu trên máy chủ"}</span><span>{draft.length}/2000 ký tự</span></div>
                {session.status === "paused" ? <button className="primary" disabled={locked} onClick={resume}><Icon name="play" size={17} />Tiếp tục phiên</button> : <div className="editor-actions"><button disabled={locked || !dirty || session.status !== "active"} onClick={saveDraft}><Icon name="save" size={17} />Lưu nháp</button><button className="primary" disabled={locked || !draft.trim() || session.status !== "active"} onClick={submitTurn}>{session.tutoring_enabled ? "Gửi bài" : "Gửi bài để lưu"}<Icon name="send" size={17} /></button></div>}
                <div className="exercise-footer"><span className="muted">Em có thể dừng và quay lại sau.</span><button className="text-button" disabled={locked || session.status !== "active"} onClick={() => saveThen("pause")}><Icon name="pause" size={16} />Tạm dừng</button></div>
              </article>
              <aside className="tutor-column" aria-label="Gia sư đồng hành">
                <section className="panel tutor-card"><div className="tutor-heading"><span className="tutor-avatar"><Icon name="leaf" size={23} /></span><div><h2>Gia sư Mở</h2><span>Gợi mở để em tự khám phá</span></div></div>
                  {session.tutoring_enabled && session.turns.length > 0 ? <div className="tutor-panel" ref={feedbackRef} tabIndex={-1} aria-live="polite" aria-label="Phản hồi mới nhất từ gia sư"><TeachingFeedback response={session.turns[session.turns.length - 1].response} /></div> : <div className="tutor-welcome"><p>{session.tutoring_enabled ? "Em sẽ bắt đầu từ đâu?" : "Phiên này chỉ lưu trữ bài làm."}</p><span>{session.tutoring_enabled ? "Viết bước đầu tiên em nghĩ tới. Nếu cần, hãy xin một gợi ý nhỏ để tìm hướng đi." : "Phản hồi gia sư không khả dụng cho phiên lưu trữ cũ."}</span></div>}
                  {session.tutoring_enabled && <div className="tutor-tools"><button disabled={locked || session.status !== "active"} onClick={() => saveThen("request_hint")}><Icon name="lightbulb" size={18} />Xin gợi ý<span className="hint-count">{session.hint_level}/3</span></button>{approvedExercise && <><button disabled={locked || session.status !== "active"} onClick={() => saveThen("request_explanation")}><Icon name="book" size={18} />Giải thích khái niệm</button><button disabled={locked || session.status !== "active"} onClick={() => saveThen("request_example")}><Icon name="layers" size={18} />Xem ví dụ khác</button></>}</div>}
                </section>
                <div className="study-note"><Icon name="info" size={18} /><p>Gợi ý giúp em tìm hướng đi. Bài tự làm và bài có hỗ trợ được ghi nhận riêng.</p></div>
              </aside>
            </div>
            <section className="panel conversation"><div className="section-head"><h2>Nhật ký phiên</h2><span className="pill neutral">{session.turns.length} lượt trao đổi</span></div>
              {!session.turns.length && <div className="empty-state compact"><Icon name="message" size={26} /><p>Bài làm và phản hồi sẽ được lưu tại đây.<br />Lưu nháp không tạo lượt chấm hay bằng chứng học tập.</p></div>}
              {session.turns.map((turn, index) => <div className="turn" key={turn.turn_id}>
                {turn.action === "submit" && <div className="student-message"><div className="message-heading"><span><Icon name="book" size={16} />Bài làm của em</span><span className={turn.assessment.assessment_status === "verified_correct" ? "pill success" : "pill neutral"}>{assessmentLabel(turn.assessment.assessment_status)}{turn.assessment.first_error_step ? ` · Bước ${turn.assessment.first_error_step}` : ""}</span></div><div className="math-steps">{turn.steps.map((step, i) => <div key={i}><span className="step-index" aria-label={`Bước ${i + 1}`}>{i + 1}</span><Formula value={step} /></div>)}</div></div>}
                <div className="tutor-message"><div className="message-heading"><span><Icon name="leaf" size={17} />Gia sư Mở</span><span className="muted">Lượt {index + 1}</span></div><TeachingFeedback response={turn.response} /></div>
              </div>)}
              <div className="session-actions"><button disabled={locked || session.status !== "active" || session.available_next === 0} onClick={() => saveThen("next")}>Thử bài tiếp ({session.available_next})<Icon name="arrow" size={17} /></button><button disabled={locked} onClick={() => saveThen("finish")}><Icon name="chart" size={17} />Kết thúc & xem báo cáo</button></div>
            </section>
          </>}
          {report && <LearningReport report={report} />}
        </>}
        <footer className="app-footer"><span className="footer-brand"><BrandLogo compact /></span><span>Học từ cách nghĩ, tiến bộ từng bước.</span><details><summary>Về bản thử nghiệm</summary><p>Bản thử nội bộ. Phạm vi chấm và trạng thái duyệt được ghi theo chủ đề. Nguồn phản hồi được ghi ở mỗi lượt trao đổi.</p></details></footer>
      </main>
    </div>
  </div>;
}
