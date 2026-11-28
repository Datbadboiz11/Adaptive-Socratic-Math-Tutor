"""UI acceptance using isolated API fixtures; never touches backend or database.

Run with .venv/Scripts/python.exe scripts/checks/check_frontend_design.py
against a running frontend (default http://127.0.0.1:3000).
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    out = ROOT / "artifacts/browser-validation" / ("frontend-design-" + uuid4().hex[:10])
    out.mkdir(parents=True, exist_ok=False)
    now = datetime.now(timezone.utc)
    profile = {"student_id": "UI-FIXTURE-01", "display_name": "Minh Anh"}
    topics = [
        {"topic_id": "TOPIC-LINEAR-01", "title": "Phương trình bậc nhất", "problem_count": 6, "tutoring_ready": True, "internal_demo_available": True, "validator_available": True, "validator_task_kinds": ["linear_equation"], "reason": "Kiểm tra các phép biến đổi phương trình trong phạm vi hỗ trợ."},
        {"topic_id": "TOPIC-A10", "title": "Phép toán phân thức đại số", "problem_count": 6, "tutoring_ready": True, "internal_demo_available": True, "validator_available": True, "validator_task_kinds": ["rational_operation"], "reason": "Kiểm tra dòng kết quả cuối và điều kiện xác định."},
        {"topic_id": "TOPIC-G01", "title": "Hình học không gian", "problem_count": 0, "tutoring_ready": False, "internal_demo_available": False, "validator_available": False, "validator_task_kinds": [], "reason": "Nội dung chưa được hỗ trợ trong bản thử."},
    ]
    old_ids = [str(uuid4()) for _ in range(4)]
    history = [{"session_id": sid, "status": "completed" if i < 3 else "paused", "created_at": (now - timedelta(days=i + 1)).isoformat()} for i, sid in enumerate(old_ids)]
    state = {"logged_in": False, "session": None, "fail_next": False, "retry_ids": []}
    mastery = [{"skill_id": "SK-LINEAR-01", "mastery": .72, "evidence_count": 4, "parameter_version": "fixture-v1"}]
    skills = [{"concept_id": "CON-LINEAR-01", "skill_id": "SK-LINEAR-01", "title": "Biến đổi phương trình tương đương", "problems_viewed": 2, "independent_correct": 1, "assisted_correct": 1, "repeat_or_near_correct": 0, "unverified_submissions": 0, "incorrect_submissions": 0, "observation_ids": ["fixture-observation"], "mastery_before": .4, "mastery_after": .72, "evidence_count_before": 3, "evidence_count_after": 4, "other_session_observations": 0, "parameter_version": "fixture-v1", "parameter_source": "Tham số khởi tạo dùng cho kiểm tra giao diện", "updated_at": now.isoformat(), "review_reason": None, "evidence_turn_ids": [], "diagnoses": []}]

    def new_session(topic):
        problem = {"problem_id": "UI-PROBLEM", "content_version": "fixture-v1", "concept_id": "CON-LINEAR-01", "primary_skill_id": "SK-LINEAR-01", "family_id": "UI-FAMILY", "prompt": "Giải phương trình và trình bày các bước biến đổi của em.", "equation": "3(x+2)=21", "domain": "real_numbers", "difficulty": "introductory"}
        if topic == "TOPIC-A10":
            problem.pop("equation")
            problem.update({"contract_version": "member2-proposal-0.3.0", "concept_id": "A10", "prompt": "Thực hiện phép cộng hai phân thức và nêu điều kiện xác định.", "task": {"kind": "rational_operation", "expression": "+;(x+1)|(x-2);(2*x+3)|(x-2)", "variable_value": None}})
        return {"session_id": str(uuid4()), "student_id": profile["student_id"], "status": "active", "state_version": 1, "current_opportunity_id": str(uuid4()), "problem": problem, "draft": "", "hint_level": 0, "created_at": now.isoformat(), "mode": "internal_demo", "review_status": "human_approved", "tutoring_enabled": True, "mastery": deepcopy(mastery), "relation": "new", "turns": [], "eligible_observations": 1, "available_next": 5, "assistance_received": False, "rag_mode": "full"}

    def report_for(session):
        return {"tutoring_enabled": True, "mastery": [{**mastery[0], "status": "estimated"}], "session_id": session["session_id"], "status": "completed", "independent_correct": 1, "assisted_correct": 1, "repeat_or_near_correct": 0, "assessment_scope": "solution_steps", "valid_observations": 1, "unverified_submissions": 0, "submitted_turns": sum(t["action"] == "submit" for t in session["turns"]), "problems_viewed": 2, "requested_hints": 1, "completed_at": now.isoformat(), "timeline": session["turns"], "limitations": ["Ước lượng từ tham số khởi tạo, không phải điểm số hay kết luận thành thạo."], "report_version": "learning-report-2.1.0", "skills": deepcopy(skills)}

    def handle(route):
        path = urlparse(route.request.url).path.removeprefix("/api/")
        body = route.request.post_data_json or {}
        status = 200
        if path == "demo/profiles": data = [profile]
        elif path == "me":
            status = 200 if state["logged_in"] else 401
            data = profile if state["logged_in"] else {"message": "Chưa chọn hồ sơ"}
        elif path == "demo/login":
            state["logged_in"] = True
            data = {"profile": profile}
        elif path == "topics": data = topics
        elif path == "sessions" and route.request.method == "GET": data = history
        elif path == "sessions":
            state["session"] = new_session(body["topic_id"])
            s = state["session"]
            history.insert(0, {"session_id": s["session_id"], "status": s["status"], "created_at": s["created_at"]})
            data, status = s, 201
        elif path.startswith("sessions/"):
            s = state["session"]
            suffix = path.split("/")[-1]
            if suffix == "turns":
                state["retry_ids"].append(body["request_id"])
                if state["fail_next"]:
                    state["fail_next"] = False
                    route.fulfill(status=503, json={"code": "network_unavailable", "retryable": True, "message": "Kết nối thử nghiệm bị gián đoạn. Giữ bài làm và thử lại."})
                    return
                action = body["action"]
                assessment = {"assessment_id": str(uuid4()), "assessment_status": "verified_correct", "first_error_step": None, "primary_skill_id": "SK-LINEAR-01", "error_family": None, "misconception_candidate": None, "diagnosis_status": "unknown", "reason_code": "valid_solution", "evidence": ["Phép biến đổi được xác minh."], "verification_method": "symbolic_and_rule", "validator_version": "fixture-v1"}
                response = {"message": "Em thử phân phối hệ số vào trong ngoặc. Hai vế còn tương đương chứ?" if action != "submit" else "Các bước biến đổi của em tương đương. Em có thể thử một bài mới để củng cố cách làm.", "response_source": "reviewed_hint" if action != "submit" else "assessment_feedback", "action": "hint" if action != "submit" else "feedback", "hint_level": 1, "content_review_status": "human_approved", "counts_as_assistance": action != "submit", "content_refs": [{"content_id": "UI-HINT", "content_version": "1", "title": "Phép biến đổi tương đương", "kind": "hint"}], "next_actions": [], "fallback_reason": None, "policy_version": None, "prompt_version": None, "model": None, "model_response_id": None, "usage": None}
                s["turns"].append({"turn_id": str(uuid4()), "opportunity_id": s["current_opportunity_id"], "request_id": body["request_id"], "action": action, "steps": body["steps"], "assessment": assessment, "response": response, "created_at": now.isoformat()})
                s["hint_level"] = 1
                s["draft"] = "\n".join(body["steps"]) if action == "submit" else s["draft"]
                data = {"session": s, "assessment": assessment, "message": response["message"], "tutor": response, "observation": None, "eligibility": {"eligible": False, "reason": "assisted"}, "response_source": response["response_source"]}
            elif suffix == "draft": s["draft"] = body["draft"]; data = s
            elif suffix in ("pause", "resume", "finish"):
                s["status"] = {"pause": "paused", "resume": "active", "finish": "completed"}[suffix]
                history[0]["status"] = s["status"]
                data = report_for(s) if suffix == "finish" else s
            elif suffix == "next":
                s["current_opportunity_id"] = str(uuid4())
                s["draft"] = ""
                s["available_next"] -= 1
                data = s
            elif suffix == "report": data = report_for(s)
            else: data = s
            s["state_version"] += 1
        else: raise AssertionError("Unexpected API route " + path)
        route.fulfill(status=status, json=data)

    errors, checks, accessibility = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="C:/Program Files/Google/Chrome/Application/chrome.exe", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/**", handle)
        page.goto(args.url, wait_until="networkidle")
        assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(247, 249, 250)", "Design tokens must load"
        page.add_script_tag(path=str(ROOT / "artifacts/tooling/axe-4.10.3.min.js"))

        def capture(**options):
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(**options)

        def audit(label):
            result = page.evaluate("""async () => (await axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa','wcag22aa']}})).violations.map(v => ({id:v.id, impact:v.impact, nodes:v.nodes.map(n => ({target:n.target,summary:n.failureSummary}))}))""")
            accessibility.append({"view": label, "violations": result})
            (out / "accessibility.json").write_text(json.dumps(accessibility, ensure_ascii=False, indent=2), encoding="utf-8")
            assert not result, (label, result)
        page.keyboard.press("Tab")
        expect(page.locator(".skip-link")).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator("#main-content")).to_be_focused()
        capture(path=str(out / "overview-empty-1440.png"), full_page=True)
        audit("empty-overview")
        checks.append("Empty state and keyboard skip link")
        page.locator("#profile").select_option(profile["student_id"])
        expect(page.locator("#topic option")).to_have_count(3)
        capture(path=str(out / "overview-1440.png"), full_page=True)
        page.get_by_role("button", name="Bắt đầu phiên thử").click()
        draft = page.locator("#draft")
        expect(draft).to_be_enabled()
        draft.fill("3x+6=21\n3x=15\nx=5")
        page.locator(".app-sidebar a.nav-link[href='#overview']").click()
        expect(page.locator("#main-content")).to_be_focused()
        expect(page.get_by_role("meter")).to_have_attribute("aria-valuenow", "72")
        page.locator(".app-sidebar a.nav-link[href='#learn']").click()
        expect(draft).to_have_value("3x+6=21\n3x=15\nx=5")
        page.go_back()
        expect(page).to_have_url(args.url + "/#overview")
        page.go_forward()
        expect(draft).to_have_value("3x+6=21\n3x=15\nx=5")
        checks.append("Navigation, browser back/forward, actual session mastery and draft retention")
        page.get_by_role("button", name="Lưu nháp", exact=True).click()
        expect(page.get_by_text("Đã lưu trên máy chủ", exact=True).last).to_be_visible()
        page.get_by_role("button", name="Xin gợi ý").click()
        expect(page.locator(".tutor-panel")).to_be_focused()
        state["fail_next"] = True
        draft.press("Control+Enter")
        expect(page.locator(".alert[role='alert']")).to_be_visible()
        expect(draft).to_have_value("3x+6=21\n3x=15\nx=5")
        page.get_by_role("button", name="Thử lại yêu cầu", exact=True).click()
        expect(page.locator(".tutor-panel")).to_be_focused()
        assert state["retry_ids"][-1] == state["retry_ids"][-2]
        expect(page.locator(".student-message math")).to_have_count(3)
        page.get_by_role("button", name="Tạm dừng", exact=True).click()
        expect(page.get_by_role("button", name="Tiếp tục phiên")).to_be_visible()
        page.get_by_role("button", name="Tiếp tục phiên", exact=True).click()
        expect(draft).to_be_enabled()
        checks.append("Save, hint, keyboard submit, error/retry preserving request identity, pause/resume, MathML transcript")

        def view(name):
            page.evaluate("name => { window.location.hash = name; }", name)
            expect(page.locator(".app-sidebar a.nav-link[href='#" + name + "']")).to_have_attribute("aria-current", "page")

        for width in (1440, 1024, 768, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            for name in ("overview", "learn", "topics", "history", "progress"):
                view(name)
                page.evaluate("document.fonts.ready")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (width, name, "overflow")
                assert page.locator("main h1").count() == 1
                if width in (1440, 390) or (width == 768 and name == "learn"):
                    capture(path=str(out / f"{name}-{width}.png"), full_page=True)
                if width in (1440, 390): audit(f"{name}-{width}")
            checks.append(f"All five views: {width}px, one h1, no page overflow")

        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("button", name="Mở điều hướng").click()
        expect(page.locator("dialog")).to_be_visible()
        page.evaluate("document.querySelector('main').focus()")
        assert page.evaluate("document.querySelector('dialog').contains(document.activeElement)")
        capture(path=str(out / "mobile-navigation-390.png"), full_page=True)
        page.keyboard.press("Escape")
        expect(page.locator("dialog")).not_to_be_visible()
        expect(page.get_by_role("button", name="Mở điều hướng")).to_be_focused()
        page.get_by_role("button", name="Mở điều hướng").click()
        page.locator("dialog a[href='#learn']").click()
        expect(page.locator("dialog")).not_to_be_visible()
        expect(page.locator("#main-content")).to_be_focused()
        checks.append("Mobile modal navigation: focus containment, Escape, focus return and link navigation")
        page.get_by_role("button", name="Kết thúc & xem báo cáo", exact=True).click()
        expect(page.locator(".report")).to_be_visible()
        expect(page.locator(".report .metrics > div")).to_have_count(8)
        expect(page.locator(".report-turn")).to_have_count(1)
        expect(page.locator(".skill-evidence")).to_contain_text("không phải điểm số")
        capture(path=str(out / "report-390.png"), full_page=True)
        audit("report-390")
        page.set_viewport_size({"width": 1440, "height": 1000})
        capture(path=str(out / "report-1440.png"), full_page=True)
        checks.append("Report: independent/assisted/repeated results, estimates, evidence timeline, mobile layout")
        view("topics")
        page.get_by_role("searchbox", name="Tìm chủ đề").fill("phân thức")
        expect(page.locator(".topic-card")).to_have_count(1)
        page.get_by_role("searchbox").fill("no-match-fixture")
        expect(page.get_by_role("heading", name="Chưa tìm thấy chủ đề")).to_be_visible()
        page.get_by_role("button", name="Xóa tìm kiếm").click()
        expect(page.locator(".topic-card")).to_have_count(3)
        expect(page.locator(".topic-card").last.get_by_role("button")).to_be_disabled()
        page.locator(".topic-card").nth(1).get_by_role("button").click()
        if page.locator(".session-topic-switch > summary").count():
            page.locator(".session-topic-switch > summary").click()
        expect(page.locator("#topic")).to_have_value("TOPIC-A10")
        page.get_by_role("button", name="Bắt đầu phiên thử").click()
        expect(page.locator(".problem-formula math mfrac")).to_have_count(2)
        for width in (1440, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            if width != 320: capture(path=str(out / f"fractions-{width}.png"), full_page=True)
        checks.append("Topic search, unavailable actions, selection and structured fraction formula")
        assert not errors, errors
        browser.close()
    result = {"fixture_mode": True, "backend_or_database_modified": False, "checks": checks, "accessibility_checks": len(accessibility), "browser_errors": errors, "screenshots": len(list(out.glob("*.png"))), "evidence": str(out)}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    if "--start-server" in sys.argv:
        sys.argv.remove("--start-server")
        sys.argv.extend(["--url", "http://127.0.0.1:3117"])
        log_path = ROOT / "artifacts" / ("frontend-design-server-" + uuid4().hex[:8] + ".log")
        with log_path.open("x", encoding="utf-8") as log:
            server = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "3117"], cwd=ROOT / "frontend", stdout=log, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                for _ in range(30):
                    try:
                        with urlopen("http://127.0.0.1:3117", timeout=2) as response:
                            if response.status == 200: break
                    except Exception: time.sleep(.3)
                else: raise RuntimeError("Frontend did not start; inspect " + str(log_path))
                main()
            finally:
                server.terminate()
                server.wait(timeout=10)
    else:
        main()
