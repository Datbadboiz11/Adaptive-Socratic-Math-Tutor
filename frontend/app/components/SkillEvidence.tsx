import type { SkillReport } from "../lib/api-types";

export function SkillEvidence({ skills }: { skills: SkillReport[] }) {
  return <section aria-label="Bằng chứng theo kỹ năng">{skills.map(skill => <div className="skill-evidence" key={skill.skill_id}>
    <div className="skill-heading"><h3>{skill.title}</h3>{skill.mastery_after !== null && <span className="skill-estimate">Ước lượng: {(skill.mastery_after * 100).toFixed(1)}%</span>}</div>
    {skill.mastery_after !== null && <div className="progress-track" role="meter" aria-label={`Ước lượng ${skill.title}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number((skill.mastery_after * 100).toFixed(1))}><span style={{ width: `${Math.min(100, Math.max(0, skill.mastery_after * 100))}%` }} /></div>}
    <p>{skill.independent_correct} bài tự làm đúng · {skill.assisted_correct} bài đúng sau hỗ trợ · {skill.repeat_or_near_correct} bài lặp hoặc gần đã đúng.</p>
    <p>{skill.incorrect_submissions} lượt chưa đúng · {skill.unverified_submissions} lượt chưa xác minh.</p>
    {skill.mastery_before === null ? <p className="muted">Chưa có bằng chứng đủ điều kiện để ước lượng mức nắm vững kỹ năng này.</p> : <>
      <p>{skill.observation_ids.length} bằng chứng trong phiên; số bằng chứng tích lũy từ {skill.evidence_count_before} đến {skill.evidence_count_after}.</p>
      <p>Ước lượng mức nắm vững từ {((skill.mastery_before ?? 0) * 100).toFixed(1)}% đến {((skill.mastery_after ?? 0) * 100).toFixed(1)}%. Đây là ước lượng từ tham số khởi tạo, không phải điểm số hay kết luận thành thạo.</p>
      {skill.other_session_observations > 0 && <p>Có {skill.other_session_observations} bằng chứng từ phiên khác xen kẽ; thay đổi trên không chỉ thuộc phiên này.</p>}
    </>}
    {skill.parameter_version && <details className="bkt-provenance"><summary>Tham số và thời điểm cập nhật BKT</summary>
      <dl><dt>Phiên bản tham số</dt><dd>{skill.parameter_version}</dd>
        <dt>Nguồn tham số</dt><dd>{skill.parameter_source || "Chưa có dữ liệu nguồn tham số."}</dd>
        <dt>Cập nhật bằng chứng gần nhất trong phiên</dt><dd>{skill.updated_at ? <time dateTime={skill.updated_at}>{new Date(skill.updated_at).toLocaleString("vi-VN", { timeZone: "Asia/Bangkok" })}</time> : "Chưa có thời điểm cập nhật."}</dd></dl>
    </details>}
    <h4>Nhận định từ bài làm</h4>
    <p className="muted">Các nhận định mô tả dấu vết trong bài làm, không kết luận học sinh yếu hay đã thành thạo.</p>
    {!skill.diagnoses?.length && <p>Chưa đủ bằng chứng để gán một mẫu lỗi cụ thể.</p>}
    {skill.diagnoses?.map((diagnosis, index) => <div className="diagnosis" key={index}>
      <p><strong>{({ suspected: "Nghi vấn", supported: "Có bằng chứng lặp lại", rejected: "Đã bác bỏ ở bài làm mới nhất" })[diagnosis.status]}</strong> · {diagnosis.hypothesis}</p>
      <p>{diagnosis.explanation}</p><p>{diagnosis.review_action}</p>
      <ul>{diagnosis.evidence.map((item, i) => <li key={item.turn_id}>
        <a href={`#report-turn-${item.turn_id}`}>Xem bài làm làm căn cứ {i + 1}</a>
        {item.first_error_step ? ` · Bước ${item.first_error_step}` : ""}
        <details><summary>Dữ kiện xác minh</summary>{item.facts.map((fact, j) => <p key={j}><code>{fact}</code></p>)}</details>
      </li>)}</ul>
    </div>)}
    {skill.review_reason && <p className="notice">{skill.review_reason}</p>}
    {!!skill.evidence_turn_ids.length && <p>{skill.evidence_turn_ids.map((id, i) => <span key={id}><a href={`#report-turn-${id}`}>Bài làm cần xem lại {i + 1}</a>{" "}</span>)}</p>}
  </div>)}</section>;
}
