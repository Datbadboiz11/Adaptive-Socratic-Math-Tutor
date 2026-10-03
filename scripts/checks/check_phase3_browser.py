"""Browser journey on the running tutor; up to 6 model calls if locally enabled."""
from datetime import datetime,timezone
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'docs/implementation/mvp/phase3/evidence'; OUT.mkdir(parents=True,exist_ok=True)
BASE='http://127.0.0.1:3000'; checks=[]; errors=[]; turns=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    try:
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.set_default_timeout(45000)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(BASE,wait_until='networkidle')
        page.locator('#profile').select_option('DEMO-STUDENT-02')
        page.get_by_role('button',name='Bắt đầu phiên thử').click()
        draft=page.locator('#draft'); expect(draft).to_be_enabled()
        draft.fill('3x = 15')
        page.get_by_role('button',name='Tạm dừng',exact=True).click()
        expect(page.get_by_role('button',name='Tiếp tục phiên')).to_be_visible()
        page.reload(wait_until='networkidle'); page.locator('.history button').first.click()
        expect(draft).to_have_value('3x = 15')
        page.get_by_role('button',name='Tiếp tục phiên').click(); expect(draft).to_be_enabled()
        checks.append('draft, pause, reload and resume preserve state')

        payloads=[]
        def lose_response(route):
            payloads.append(route.request.post_data_json)
            if len(payloads)==1:
                response=route.fetch(timeout=45000); assert response.status==200
                turns.append(response.json()); route.abort('connectionfailed')
            else: route.continue_()
        page.route('**/api/sessions/*/turns',lose_response)
        draft.fill('3x=15\nx=5'); page.get_by_role('button',name='Gửi bài',exact=True).click()
        page.get_by_role('button',name='Thử lại yêu cầu').click()
        expect(page.locator('.turn')).to_have_count(1)
        assert len(payloads)==2 and payloads[0]==payloads[1]
        assert turns[0]['assessment']['assessment_status']=='verified_correct'
        page.unroute('**/api/sessions/*/turns',lose_response)
        checks.append('commit response lost: same request replay, one correct turn')

        def submit(text=None,hint=False):
            if text is not None: draft.fill(text)
            with page.expect_response(lambda r:'/api/sessions/' in r.url and r.url.endswith('/turns') and r.request.method=='POST',timeout=45000) as pending:
                page.get_by_role('button',name='Xin gợi ý' if hint else 'Gửi bài',exact=True).click()
            response=pending.value; assert response.status==200
            result=response.json(); turns.append(result)
            expect(draft).to_be_enabled()
            return result
        page.get_by_role('button',name='Thử bài tiếp').click(); expect(draft).to_have_value('')
        unclear=submit('x=')
        assert unclear['assessment']['assessment_status']=='needs_clarification' and unclear['observation'] is None
        hinted=submit('Nháp trước khi xin gợi ý',hint=True)
        assert hinted['session']['draft']=='Nháp trước khi xin gợi ý'
        assert hinted['session']['hint_level']==1 and hinted['observation'] is None
        corrected=submit('x=-4')
        assert corrected['assessment']['assessment_status']=='verified_correct' and corrected['observation'] is None
        checks.append('unclear input is not wrong; hint preserves draft; assisted correction adds no observation')

        page.get_by_role('button',name='Thử bài tiếp').click(); expect(draft).to_have_value('')
        wrong=submit('2x-3=10\n2x=13\nx=6.5')
        assert wrong['assessment']['first_error_step']==1
        assert 'x = 8' not in wrong['message'] and 'x=8' not in wrong['message']
        for width in [1440,768,390]:
            page.set_viewport_size({'width':width,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            page.screenshot(path=str(OUT/f'tutor-{width}.png'),full_page=True)
        fixed=submit('x-3=5\nx=8')
        assert fixed['assessment']['assessment_status']=='verified_correct' and fixed['observation'] is None
        checks.append('distribution error at step 1; alternative correction accepted; no answer leaked')
        with page.expect_response(lambda r:r.url.endswith('/finish') and r.request.method=='POST') as pending:
            page.get_by_role('button',name='Kết thúc & xem báo cáo').click()
        report=pending.value.json()
        assert report['independent_correct']==1 and report['assisted_correct']==2
        assert report['submitted_turns']==5 and report['unverified_submissions']==1
        assert report['valid_observations']==sum(t['observation'] is not None for t in turns)
        page.reload(wait_until='networkidle'); page.locator('.history button').first.click()
        expect(page.locator('.report')).to_be_visible()
        page.screenshot(path=str(OUT/'report-mobile.png'),full_page=True)
        checks.append('report counters match actual turns and observations after reload')
        checks.append('desktop/tablet/mobile have no horizontal overflow')
        assert not errors,errors
    finally: browser.close()
(OUT/'browser-check.json').write_text(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(),
    'checks':checks,'browser_errors':errors,'turns':turns,'report':report},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'PASS: {len(checks)} browser checks; {len(turns)} tutor turns; no runtime errors')
