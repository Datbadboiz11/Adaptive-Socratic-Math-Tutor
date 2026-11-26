import type { TutorResponseView } from "../lib/api-types";
import { MathText } from "./MathText";

export const sourceLabel = (source: string) => ({
  reviewed_kb: "Nội dung từ kho kiến thức đã duyệt", reviewed_hint: "Gợi ý từ nội dung đã duyệt",
  assessment_feedback: "Phản hồi từ bộ chấm", gemini: "Gemini · câu trả lời thuộc danh sách cho phép",
  openai: "OpenAI · cách diễn đạt đã được kiểm tra", draft_template: "Mẫu gợi mở thử nghiệm · chưa duyệt chuyên môn",
}[source] || "Thông báo lưu trữ");

export function TeachingFeedback({ response }: { response: TutorResponseView }) {
  return <>
    {response.action === "different_example" && <h3>Ví dụ hỗ trợ · khác bài đang làm</h3>}
    {response.action === "explanation" && <h3>Giải thích khái niệm</h3>}
    <p><MathText text={response.message} /></p>
    <small>{sourceLabel(response.response_source)}</small>
    {response.content_refs.length > 0 && <ul className="content-sources" aria-label="Nguồn nội dung đã dùng">
      {response.content_refs.map(ref => <li key={`${ref.content_id}:${ref.content_version}`}>
        <details><summary>{ref.title}</summary><span>Phiên bản {ref.content_version}</span></details>
      </li>)}
    </ul>}
    {response.counts_as_assistance && <p className="support-note">Nội dung này được ghi nhận là hỗ trợ cho bài hiện tại.</p>}
  </>;
}
