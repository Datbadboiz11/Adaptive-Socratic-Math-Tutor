import type { Report } from "../lib/api-types";
import { SkillEvidence } from "./SkillEvidence";

export function LearningReport({ report }: { report: Report }) {
  const finalAnswer = report.assessment_scope === "final_answer";
  return <article className="card report"><p className="eyebrow">NHÌN LẠI PHIÊN THỬ</p><h1>Từng bước em đã làm.</h1>
    <p>{finalAnswer ? "Kết quả dựa trên dòng cuối của từng bài. Báo cáo ghi riêng bài tự làm, bài lặp hoặc gần và bài đúng sau gợi ý." : "Kết quả xác minh và mức hỗ trợ được ghi riêng. Bài lặp hoặc sửa sau gợi ý không tự tạo thêm bằng chứng độc lập."}</p>
    <div className="metrics">{[["Lượt gửi bài", report.submitted_turns], ["Chưa xác minh", report.unverified_submissions], ["Bài đã xem", report.problems_viewed], ["Tự làm đúng", report.independent_correct], ["Đúng sau hỗ trợ", report.assisted_correct], ["Bài lặp hoặc gần đã đúng", report.repeat_or_near_correct], ["Observation trong phiên", report.valid_observations]].map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div>
    <SkillEvidence skills={report.skills} />
    <ul>{report.limitations.map(text => <li key={text}>{text}</li>)}</ul>
    <h2>Bài đã gửi và bằng chứng</h2>{report.timeline.filter(t => t.action === "submit").map((t, index) =>
      <section className="report-turn" id={`report-turn-${t.turn_id}`} tabIndex={-1} key={t.turn_id}>
        <h3>Lượt gửi {index + 1}</h3><pre>{t.steps.join("\n")}</pre>
        <p>{({ verified_correct: "Đã xác minh đúng", verified_incorrect: "Đã xác minh chưa đúng", unverified: "Chưa xác minh", needs_clarification: "Cần viết rõ hơn" })[t.assessment.assessment_status]}{t.assessment.first_error_step ? ` · Bước sai đầu tiên: ${t.assessment.first_error_step}` : ""}</p>
        <details><summary>Chi tiết bằng chứng của bộ chấm</summary><ul>{t.assessment.evidence.map((fact, i) => <li key={i}><code>{fact}</code></li>)}</ul></details>
      </section>)}
  </article>;
}
