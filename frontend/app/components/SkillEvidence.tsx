import type { SkillReport } from "../lib/api-types";

export function SkillEvidence({ skills }: { skills: SkillReport[] }) {
  return <section aria-label="Bằng chứng theo kỹ năng">{skills.map(skill => <div className="skill-evidence" key={skill.skill_id}>
    <h2>{skill.title}</h2>
    <p>{skill.independent_correct} bài tự làm đúng · {skill.assisted_correct} bài đúng sau hỗ trợ · {skill.repeat_or_near_correct} bài lặp hoặc gần đã đúng.</p>
    <p>{skill.incorrect_submissions} lượt chưa đúng · {skill.unverified_submissions} lượt chưa xác minh.</p>
    {skill.mastery_before === null ? <p className="muted">Chưa có observation đủ điều kiện để ước lượng BKT cho kỹ năng này.</p> : <>
      <p>{skill.observation_ids.length} observation trong phiên; count tích lũy từ {skill.evidence_count_before} đến {skill.evidence_count_after}.</p>
      <p>Ước lượng BKT từ {((skill.mastery_before ?? 0) * 100).toFixed(1)}% đến {((skill.mastery_after ?? 0) * 100).toFixed(1)}%. Đây là ước lượng từ tham số khởi tạo, không phải điểm số hay kết luận thành thạo.</p>
      {skill.other_session_observations > 0 && <p>Có {skill.other_session_observations} observation từ phiên khác xen kẽ; thay đổi trên không chỉ thuộc phiên này.</p>}
    </>}
    {skill.review_reason && <p className="notice">{skill.review_reason}</p>}
  </div>)}</section>;
}
