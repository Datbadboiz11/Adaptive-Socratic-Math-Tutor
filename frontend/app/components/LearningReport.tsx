import type { Report } from "../lib/api-types";
import { SkillEvidence } from "./SkillEvidence";
import { Icon } from "./Icon";
import { Formula } from "./MathText";

export function LearningReport({ report }: { report: Report }) {
  const finalAnswer = report.assessment_scope === "final_answer";
  const submissions = report.timeline.filter(turn => turn.action === "submit");
  return <article className="panel report">
    <header className="report-header"><span className="section-label"><Icon name="chart" size={18} />Nhìn lại phiên học</span><h2>Từng bước em đã làm.</h2>
      <p>{finalAnswer ? "Kết quả dựa trên dòng cuối của từng bài. Báo cáo ghi riêng bài tự làm, bài lặp hoặc gần và bài đúng sau gợi ý." : "Kết quả xác minh và mức hỗ trợ được ghi riêng. Bài lặp hoặc sửa sau gợi ý không tự tạo thêm bằng chứng độc lập."}</p>
    </header>
    <div className="metrics">{[["Lượt gửi bài", report.submitted_turns], ["Tự làm đúng", report.independent_correct], ["Đúng sau hỗ trợ", report.assisted_correct], ["Bài đã xem", report.problems_viewed], ["Bài lặp hoặc gần đã đúng", report.repeat_or_near_correct], ["Chưa xác minh", report.unverified_submissions], ["Bằng chứng hợp lệ trong phiên", report.valid_observations], ["Lượt xin gợi ý", report.requested_hints]].map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div>
    <SkillEvidence skills={report.skills} />
    {!!report.limitations.length && <details className="report-limitations"><summary>Cách đọc báo cáo và giới hạn dữ liệu</summary><ul>{report.limitations.map(text => <li key={text}>{text}</li>)}</ul></details>}
    <h3>Bài đã gửi và bằng chứng</h3>
    {!submissions.length && <p className="muted">Phiên này chưa có lượt gửi bài. Các lượt xin gợi ý không được tính là bài tự làm.</p>}
    {submissions.map((turn, index) => <section className="report-turn" id={`report-turn-${turn.turn_id}`} tabIndex={-1} key={turn.turn_id}>
      <h4>Lượt gửi {index + 1}</h4><div className="math-steps">{turn.steps.map((step, i) => <div key={i}><span className="step-index" aria-label={`Bước ${i + 1}`}>{i + 1}</span><Formula value={step} /></div>)}</div>
      <p className="assessment-result">{({ verified_correct: "Đã xác minh đúng", verified_incorrect: "Đã xác minh chưa đúng", unverified: "Chưa xác minh", needs_clarification: "Cần viết rõ hơn" })[turn.assessment.assessment_status]}{turn.assessment.first_error_step ? ` · Bước sai đầu tiên: ${turn.assessment.first_error_step}` : ""}</p>
      <details><summary>Chi tiết bằng chứng của bộ chấm</summary><ul>{turn.assessment.evidence.map((fact, i) => <li key={i}><code>{fact}</code></li>)}</ul></details>
    </section>)}
  </article>;
}
