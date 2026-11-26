"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { SessionView as Session, TopicView as Topic, Report } from "../lib/api-types";
import { api, ApiFailure } from "../lib/api";
type Profile = { student_id: string; display_name: string };
type History = { session_id: string; status: string; created_at: string };
type Pending = { path: string; method: string; body: Record<string, unknown>; apply: "session" | "turn" | "report" };

export function useTutorSession(initialReady: boolean) {
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
  const focusAfterTurn = useRef(false);
  useEffect(() => {
    // Effects run after React commits the response panel. A zero-delay timer
    // can fire before that panel exists, especially on the first keyboard send.
    if (focusAfterTurn.current && feedbackRef.current) {
      focusAfterTurn.current = false;
      feedbackRef.current.focus();
    }
  }, [session]);
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
      else {
        if (request.apply === "turn") focusAfterTurn.current = true;
        next = request.apply === "turn" ? data.session : data; accept(next);
      }
      setNotice(request.apply === "turn" ? "Phản hồi đã được lưu trong nhật ký." : "Đã lưu trên máy chủ.");
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
  const submitTurn = async () => {
    if (!session || locked || session.status !== "active" || !draft.trim()) return;
    const steps = draft.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    if (steps.length > 12 || steps.some(s => s.length > 160)) throw new Error("Tối đa 12 dòng, 160 ký tự mỗi dòng. Bản nháp vẫn được giữ.");
    await mutation(session, "turns", { opportunity_id: session.current_opportunity_id, action: "submit", steps }, "turn");
  };

  const retry = () => act(async () => { if (pending) await execute(pending); });
  const reconcile = (editing: boolean) => act(async () => {
    if (!session) return;
    const fresh = await api<Session>(`sessions/${session.session_id}`);
    const same = fresh.current_opportunity_id === session.current_opportunity_id && fresh.status === "active";
    if (!same && dirty && !window.confirm("Bài đã đổi hoặc phiên đã đóng. Hãy sao chép nháp trước khi tải trạng thái mới. Tiếp tục?")) return;
    setSession(fresh);
    if (!same || !dirty) setDraft(fresh.draft);
    setPending(null); setConflict(false); setError(""); setReady(true);
    if (fresh.status === "completed") setReport(await api<Report>(`sessions/${fresh.session_id}/report`));
    setNotice(same ? editing ? "Đã đối soát với máy chủ. Bạn có thể sửa bài rồi gửi như yêu cầu mới." : "Đã tải trạng thái mới, giữ bản nháp đang viết. Bạn có thể lưu lại." : "Đã tải trạng thái mới.");
  });
  const selectProfile = (id: string) => {
    if (!id || id === profile?.student_id) return;
    return act(async () => {
      await saveCurrentDraft();
      identityEpoch.current += 1;
      const data = await api<{ profile: Profile }>("demo/login", "POST", { demo_profile_id: id });
      setProfile(data.profile); setHistory([]); setSession(null); setDraft(""); setReport(null);
      await Promise.all([refreshHistory(), refreshTopics()]);
    });
  };
  const startSession = () => act(async () => {
    if (!profile) return;
    await saveCurrentDraft();
    await execute({ path: "sessions", method: "POST", body: {
      request_id: crypto.randomUUID(), demo_profile_id: profile.student_id, topic_id: selectedTopic,
    }, apply: "session" });
  });
  return { profiles, topics, selectedTopic, setSelectedTopic, selectedTopicData, profile, history,
    session, draft, setDraft, report, busy, error, notice, conflict, pending, ready, dirty, locked,
    feedbackRef, retry, reconcile, selectProfile, startSession,
    openSession: (id: string) => act(() => openSession(id)),
    submitTurn: () => act(submitTurn),
    saveThen: (action: Parameters<typeof saveThen>[0]) => act(() => saveThen(action)),
    saveDraft: () => act(async () => { if (session) await mutation(session, "draft", { draft }); }),
    resume: () => act(async () => { if (session) await mutation(session, "resume"); }),
  };

}
