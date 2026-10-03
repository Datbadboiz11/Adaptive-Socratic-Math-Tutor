"""Real browser journey against Compose; creates one internal-demo session."""
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parents[2] / 'docs/implementation/mvp/phase2/evidence'
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'http://127.0.0.1:3000'
checks, errors = [], []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    try:
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(BASE, wait_until='networkidle')
        page.locator('#profile').select_option('DEMO-STUDENT-01')
        page.get_by_role('button', name='Bắt đầu phiên thử').click()
        draft = page.locator('#draft')
        expect(draft).to_be_enabled()
        text = '  3x = 15\n\nx = 5  '
        draft.fill(text)
        page.get_by_role('button', name='Tạm dừng', exact=True).click()
        expect(page.get_by_role('button', name='Tiếp tục phiên')).to_be_visible()
        page.reload(wait_until='networkidle')
        page.locator('.history button').first.click()
        expect(draft).to_have_value(text)
        expect(draft).to_be_disabled()
        page.get_by_role('button', name='Tiếp tục phiên').click()
        expect(draft).to_be_enabled()
        checks.append('unsaved draft saved before pause; reload/resume preserves whitespace')

        # Commit at backend, then discard response. UI must retry SAME request ID.
        requests = []
        def lose_first_response(route):
            requests.append(route.request.post_data_json)
            if len(requests) == 1:
                response = route.fetch()
                assert response.status == 200
                route.abort('connectionfailed')
            else:
                route.continue_()
        page.route('**/api/sessions/*/turns', lose_first_response)
        page.get_by_role('button', name='Gửi bài để lưu').click()
        page.get_by_role('button', name='Thử lại yêu cầu').click()
        expect(page.locator('.turn')).to_have_count(1)
        assert len(requests) == 2 and requests[0] == requests[1]
        page.unroute('**/api/sessions/*/turns', lose_first_response)
        checks.append('response lost after commit: UI retries identical payload, one turn')

        # Simulate another tab updating the same version while this tab edits.
        history = page.request.get(BASE + '/api/sessions').json()
        session_id = history[0]['session_id']
        current = page.request.get(BASE + '/api/sessions/' + session_id).json()
        draft.fill('Nháp đang viết ở tab này')
        response = page.request.put(BASE + f'/api/sessions/{session_id}/draft',
            headers={'Origin': BASE}, data={'request_id': str(uuid4()),
            'expected_state_version': current['state_version'], 'draft': 'Nháp từ tab khác'})
        assert response.status == 200
        page.get_by_role('button', name='Lưu nháp', exact=True).click()
        page.get_by_role('button', name='Tải trạng thái mới').click()
        expect(draft).to_have_value('Nháp đang viết ở tab này')
        page.get_by_role('button', name='Lưu nháp', exact=True).click()
        expect(page.get_by_role('button', name='Lưu nháp', exact=True)).to_be_disabled()
        checks.append('version conflict: refresh retains local draft and permits explicit save')

        for width in [1440, 768, 390]:
            page.set_viewport_size({'width': width, 'height': 1000})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(OUT / f'session-{width}.png'), full_page=True)
        checks.append('desktop/tablet/mobile: no horizontal overflow')
        page.get_by_role('button', name='Thử bài tiếp').click()
        expect(draft).to_have_value('')
        page.get_by_role('button', name='Kết thúc & xem báo cáo').click()
        expect(page.locator('.report')).to_be_visible()
        page.reload(wait_until='networkidle')
        page.locator('.history button').first.click()
        expect(page.locator('.report')).to_be_visible()
        report = page.request.get(BASE + f'/api/sessions/{session_id}/report').json()
        assert report['status'] == 'completed' and report['submitted_turns'] == 1
        assert report['problems_viewed'] == 2 and report['valid_observations'] == 0
        assert report['independent_correct'] == report['assisted_correct'] == 0
        page.screenshot(path=str(OUT / 'report-mobile.png'), full_page=True)
        checks.append('next/finish/report/reload use persisted data; no invented correct result')
        cookies = page.context.cookies()
        assert any(c['name'] == 'mo_demo' and c['httpOnly'] and c['sameSite'] == 'Strict' for c in cookies)
        assert 'mo_demo' not in page.evaluate('document.cookie')
        rejected = page.request.post(BASE + '/api/demo/login', headers={'Origin': 'https://other.example'}, data={'demo_profile_id': 'DEMO-STUDENT-01'})
        assert rejected.status == 403
        checks.append('HttpOnly demo cookie and cross-origin mutation rejection')
        assert not errors, errors
    finally:
        browser.close()
(OUT / 'browser-check.json').write_text(json.dumps({'checked_at': datetime.now(timezone.utc).isoformat(),
    'checks': checks, 'browser_errors': errors, 'session_id': session_id,
    'report_counts': {k: report[k] for k in ['submitted_turns','problems_viewed','valid_observations']}},
    ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'PASS: {len(checks)} browser checks, no runtime errors')
