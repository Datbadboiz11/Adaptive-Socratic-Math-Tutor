import type { SkillMastery, SkillReport } from "../lib/api-types";
import { Icon } from "./Icon";
import { LearningEmptyIllustration } from "./LearningEmptyIllustration";

export function MasteryOverview({ mastery, skills = [], currentSkill }: { mastery: SkillMastery[]; skills?: SkillReport[]; currentSkill?: { id: string; title: string } }) {
  return <section className="panel mastery-panel" aria-labelledby="mastery-heading">
    <div className="section-head"><h2 id="mastery-heading">Mức độ nắm vững</h2><Icon name="target" /></div>
    <p className="section-description">Ước lượng từ bằng chứng học tập, không phải điểm số.</p>
    {!mastery.length ? <div className="empty-state compact"><LearningEmptyIllustration variant="growth" /><h3>Mỗi bài làm là một dấu mốc</h3><p>Khi có đủ bằng chứng, mức nắm vững từng kỹ năng sẽ xuất hiện ở đây.</p><span className="empty-state-caption">Từng chút hiểu thêm, từng bước tiến bộ.</span></div> :
      <div className="mastery-list">{mastery.map((item, index) => {
        const title = skills.find(s => s.skill_id === item.skill_id)?.title || (currentSkill?.id === item.skill_id ? currentSkill.title : `Kỹ năng ${index + 1}`);
        const value = item.mastery === null || item.status === "insufficient_data" ? null : Math.round(Math.min(1, Math.max(0, item.mastery)) * 100);
        return <div className="mastery-item" key={item.skill_id}>
          <div className="mastery-label"><span>{title}</span><strong>{value === null ? "Chưa đủ dữ liệu" : `${value}%`}</strong></div>
          {value !== null && <div className="progress-track" role="meter" aria-label={`Ước lượng ${title}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value}><span style={{ width: `${value}%` }} /></div>}
          <small>{item.evidence_count} lần ghi nhận bằng chứng</small>
        </div>;
      })}</div>}
  </section>;
}
