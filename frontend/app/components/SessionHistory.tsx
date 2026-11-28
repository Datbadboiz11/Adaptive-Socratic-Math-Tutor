import { Icon } from "./Icon";
import { LearningEmptyIllustration } from "./LearningEmptyIllustration";

type HistoryEntry = { session_id: string; status: string; created_at: string };
export function SessionHistory({ history, limit, currentId, locked, onOpen, onStart }: { history: HistoryEntry[]; limit?: number; currentId?: string; locked: boolean; onOpen: (id: string) => void; onStart?: () => void }) {
  return <div className="history">{!history.length ? <div className="empty-state compact"><LearningEmptyIllustration variant="notebook" /><h3>Hành trình bắt đầu từ một bài toán</h3><p>Các phiên học được lưu sẽ xuất hiện ở đây để em tiếp tục hoặc xem lại.</p>{onStart && <button className="text-button empty-state-action" disabled={locked} onClick={onStart}>Bắt đầu một phiên học<Icon name="arrow" size={16} /></button>}</div> : history.map((entry, index) => <button className={`history-row ${entry.session_id === currentId ? "selected" : ""}`} disabled={locked} key={entry.session_id} onClick={() => onOpen(entry.session_id)}>
    <span className="history-icon"><Icon name={entry.status === "completed" ? "check" : "book"} /></span>
    <span className="history-title"><strong>Phiên học {history.length - index}</strong><time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString("vi-VN", { timeZone: "Asia/Bangkok", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}</time></span>
    <span className={`pill ${entry.status === "completed" ? "success" : "neutral"}`}>{entry.status === "completed" ? "Đã kết thúc" : entry.status === "paused" ? "Tạm dừng" : "Đang học"}</span><Icon name="chevron" size={16} />
  </button>).slice(0, limit)}</div>;
}
