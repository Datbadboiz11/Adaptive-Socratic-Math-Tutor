"""Stage 4 end-to-end acceptance on a fresh schema and private local web processes."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
for path in (ROOT / 'backend',ROOT / 'scripts/dev'):
    sys.path.insert(0,str(path))
from validation_runtime import local_environment


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def main():
    environment=local_environment()
    for name in ('OPENAI_API_KEY','GEMINI_API_KEY'):
        environment.pop(name,None)
        os.environ.pop(name,None)
    environment.update(LLM_ENABLED='false',TUTOR_RAG_MODE='full')
    os.environ.update(environment)
    from psycopg import sql
    from app.db import connect
    from app.manage import migrate,seed
    from app.member2_runtime import seed_member2
    from app.kb_projection import load_source,load_example_publications,load_profile,project
    from app.kb_sync import sync_projection
    from app.embeddings import LocalEmbedder
    from app.kb_cli import default_model_dir
    from playwright.sync_api import sync_playwright,expect
    run_id=uuid4().hex[:12]
    schema='stage4_browser_'+run_id
    out=ROOT / 'artifacts/browser-validation' / ('stage4-'+run_id)
    out.mkdir(parents=True,exist_ok=False)
    with connect() as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    previous=os.environ.get('PGOPTIONS')
    environment['PGOPTIONS']='-c search_path='+schema
    os.environ['PGOPTIONS']=environment['PGOPTIONS']
    processes=[]
    try:
        with connect() as connection:
            migrate(connection); seed(connection); seed_member2(connection)
        registry,bank,origin=load_source('member2-v2')
        profile=load_profile()
        projection=project(registry,bank,profile,origin=origin,examples=load_example_publications('member2-v2'))
        synced=sync_projection(projection,LocalEmbedder(profile,default_model_dir(profile)),activate=True)
        backend_port,frontend_port=free_port(),free_port()
        environment['BACKEND_URL']=f'http://127.0.0.1:{backend_port}'
        for name,command,cwd,url in (
            ('backend',[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(backend_port)],ROOT,
             environment['BACKEND_URL']+'/health/ready'),
            ('frontend',['node','node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',str(frontend_port)],ROOT / 'frontend',
             f'http://127.0.0.1:{frontend_port}')):
            with (out / (name+'.log')).open('x',encoding='utf-8') as log:
                process=subprocess.Popen(command,cwd=cwd,env=environment,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            processes.append(process)
            for _ in range(50):
                try:
                    with urlopen(url,timeout=2) as response:
                        if response.status==200: break
                except Exception: time.sleep(.2)
            else: raise RuntimeError(name+' did not become ready; see local artifact log')
        checks=[]
        errors=[]
        with sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True)
            browser_context=browser.new_context(viewport={'width':1440,'height':1000})
            page=browser_context.new_page()
            page.set_default_timeout(20000)
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{frontend_port}',wait_until='networkidle')
            page.keyboard.press('Tab')
            expect(page.locator('.skip-link')).to_be_focused()
            page.keyboard.press('Enter')
            expect(page.locator('#main-content')).to_be_focused()
            page.locator('#profile').select_option('DEMO-STUDENT-01')

            def start(concept):
                page.locator('#topic').select_option('TOPIC-'+concept)
                with page.expect_response(lambda r:r.url.endswith('/api/sessions') and r.request.method=='POST') as pending:
                    page.get_by_role('button',name='Bắt đầu phiên thử').click()
                assert pending.value.status==201
                expect(page.locator('#draft')).to_be_enabled()
                return pending.value.json()

            def click(label,endpoint):
                with page.expect_response(lambda r:r.url.endswith(endpoint) and r.request.method=='POST') as pending:
                    page.get_by_role('button',name=label,exact=True).click()
                response=pending.value
                assert response.status==200,(response.status,label,response.text())
                expect(page.locator('.busy-note')).to_have_count(0)
                return response.json()

            for concept in ('N02','A10','F05'):
                pack=next(p for p in bank.packs if p.concept_id==concept)
                session=start(concept)
                if concept=='A10': expect(page.locator('.problem-formula mfrac')).to_have_count(2)
                page.locator('#draft').fill(pack.errors[0].response_steps[0])
                wrong=click('Gửi bài','/turns')
                assert wrong['response_source']=='reviewed_kb'
                expect(page.locator('.tutor-panel .content-sources')).to_be_visible()
                assert wrong['tutor']['counts_as_assistance']
                page.locator('#draft').fill(pack.problems[0].reference_answer)
                fixed=click('Gửi bài','/turns')
                assert fixed['assessment']['assessment_status']=='verified_correct' and fixed['observation'] is None
                click('Thử bài tiếp (5)','/next')
                click('Thử bài tiếp (4)','/next')
                page.locator('#draft').fill(pack.problems[2].reference_answer)
                independent=click('Gửi bài','/turns')
                assert independent['assessment']['assessment_status']=='verified_correct'
                report=click('Kết thúc & xem báo cáo','/finish')
                assert (report['independent_correct'],report['assisted_correct'],report['valid_observations'])==(1,1,0)
                expect(page.get_by_role('region',name='Bằng chứng theo kỹ năng')).to_be_visible()
                checks.append({'concept':concept,'flow':'wrong → KB hint → assisted correct → independent problem → frozen report','status':'passed'})

            start('E09')
            expect(page.locator('.problem-formula mtable mtr')).to_have_count(2)
            for width in (1440,390):
                page.set_viewport_size({'width':width,'height':950})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(out / f'system-real-{width}.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            click('Kết thúc & xem báo cáo','/finish')
            checks.append({'flow':'approved A10 complex fractions and E09 equation system; 390/1440 viewport','status':'passed'})

            session=start('N02')
            payloads=[]
            def lose_first_response(route):
                payloads.append(route.request.post_data_json)
                if len(payloads)==1:
                    assert route.fetch(timeout=30000).status==200
                    route.abort('connectionfailed')
                else: route.continue_()
            page.route('**/api/sessions/*/turns',lose_first_response)
            page.get_by_role('button',name='Giải thích khái niệm',exact=True).click()
            expect(page.get_by_role('button',name='Thử lại yêu cầu')).to_be_visible()
            page.get_by_role('button',name='Thử lại yêu cầu').click()
            expect(page.locator('.turn')).to_have_count(1)
            assert len(payloads)==2 and payloads[0]==payloads[1]
            page.unroute('**/api/sessions/*/turns',lose_first_response)
            example=click('Xem ví dụ khác','/turns')
            assert len(example['tutor']['content_refs'])==1 and example['tutor']['action']=='different_example'
            expect(page.locator('.tutor-panel')).to_contain_text('Ví dụ hỗ trợ')
            expect(page.locator('.notice[role="status"]')).to_have_text('Phản hồi đã được lưu trong nhật ký.')
            for width in (1440,390):
                page.set_viewport_size({'width':width,'height':950})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(out / f'example-real-{width}.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            # Both tabs retain their request/state versions; stale writes must be rejected.
            second=page.context.new_page()
            second.goto(f'http://127.0.0.1:{frontend_port}',wait_until='networkidle')
            second.locator('.history button').first.click()
            expect(second.locator('#draft')).to_be_enabled()
            second.locator('#draft').fill('Nháp giữ lại khi có xung đột')
            click('Giải thích khái niệm','/turns')
            second.get_by_role('button',name='Lưu nháp',exact=True).click()
            expect(second.get_by_role('button',name='Tải trạng thái mới')).to_be_visible()
            second.get_by_role('button',name='Tải trạng thái mới').click()
            expect(second.locator('#draft')).to_have_value('Nháp giữ lại khi có xung đột')
            second.close()
            checks.append({'flow':'two-tab conflict rejects stale write and preserves the unsaved draft','status':'passed'})
            click('Tạm dừng','/pause')
            page.reload(wait_until='networkidle')
            page.locator('.history button').first.click()
            expect(page.get_by_role('button',name='Tiếp tục phiên')).to_be_visible()
            click('Tiếp tục phiên','/resume')
            checks.append({'flow':'response loss → same-request replay → example citation → pause/reload/resume','status':'passed'})

            # Intercept only a public GET in this browser to test untrusted text rendering.
            # This synthetic UI payload is not attributed to the server/generator.
            def untrusted_text(route):
                response=route.fetch()
                data=response.json()
                if route.request.method=='GET' and isinstance(data,dict) and data.get('turns'):
                    data['turns'][-1]['response']['message']='Dạng hiển thị `1/2`, `x^2`, `sqrt(2)`, `(x+1)/(x-2)`, `2x+y=8;x-y=1`; <img src=x onerror=alert(1)>'
                    route.fulfill(response=response,json=data)
                else: route.fulfill(response=response)
            page.route('**/api/sessions/'+session['session_id'],untrusted_text)
            page.reload(wait_until='networkidle')
            page.locator('.history button').first.click()
            expect(page.locator('.tutor-panel math')).to_have_count(5)
            expect(page.locator('.tutor-panel mfrac')).to_have_count(2)
            expect(page.locator('.tutor-panel mtable mtr')).to_have_count(2)
            expect(page.locator('.tutor-panel img')).to_have_count(0)
            checks.append({'flow':'native MathML fraction/power/root and escaped untrusted text (synthetic browser payload)','status':'passed'})
            for width in (1440,390):
                page.set_viewport_size({'width':width,'height':950})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(out / f'grounded-{width}.png'),full_page=True)
            held_history=[]
            def delayed_old_history(route):
                if route.request.method=='GET' and not held_history:
                    held_history.append((route,route.fetch()))
                else: route.continue_()
            page.route('**/api/sessions',delayed_old_history)
            click('Tạm dừng','/pause')
            # Let the asynchronous, intentionally unawaited history refresh reach its route.
            for _ in range(30):
                if held_history: break
                page.wait_for_timeout(100)
            assert len(held_history)==1
            page.locator('#profile').select_option('DEMO-STUDENT-02')
            expect(page.locator('.history button')).to_have_count(0)
            expect(page.locator('#draft')).to_have_count(0)
            held_route,held_response=held_history[0]
            held_route.fulfill(response=held_response)
            page.wait_for_timeout(100)
            expect(page.locator('.history button')).to_have_count(0)
            checks.append({'flow':'switching profile clears session/report/draft; delayed history from the previous profile is discarded','status':'passed'})

            legacy=start('LINEAR-01')
            legacy_bank=json.loads((ROOT/'content/linear_equations.v1.json').read_text(encoding='utf-8'))['problems']
            problem=next(p for p in legacy_bank if p['problem_id']==legacy['problem']['problem_id'])
            page.locator('#draft').fill('\n'.join(problem['common_errors'][0]['steps']))
            with page.expect_response(lambda r:r.url.endswith('/turns') and r.request.method=='POST') as keyboard_turn:
                page.locator('#draft').press('Control+Enter')
            assert keyboard_turn.value.status==200
            expect(page.locator('.tutor-panel')).to_be_focused()
            page.keyboard.press('Tab')
            assert page.evaluate('document.activeElement !== document.body')
            page.keyboard.press('Shift+Tab')
            page.locator('#draft').fill('\n'.join(problem['reference_methods'][0]['steps']))
            click('Gửi bài','/turns')
            legacy_report=click('Kết thúc & xem báo cáo','/finish')
            assert legacy_report['skills'][0]['parameter_version']
            expect(page.locator('.diagnosis')).to_have_count(2)
            page.locator('.bkt-provenance summary').focus()
            page.keyboard.press('Enter')
            expect(page.locator('.bkt-provenance')).to_contain_text('g2-bootstrap-1.0.0')
            expect(page.locator('.bkt-provenance time')).to_be_visible()
            page.locator('.diagnosis a').first.focus()
            page.keyboard.press('Enter')
            expect(page.locator('.report-turn').first).to_be_focused()
            for width in (1440,390):
                page.set_viewport_size({'width':width,'height':950})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(out / f'report-evidence-{width}.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
            checks.append({'flow':'keyboard skip link, Ctrl+Enter, feedback focus, Tab/Shift+Tab, report evidence anchors and BKT provenance (real legacy report)','status':'passed'})

            # Exercise the production 45s AbortController with Playwright virtual
            # time. The server commits, but its response is deliberately held.
            page.clock.install()
            page.reload(wait_until='networkidle')
            timed_session=start('N02')
            timed_payloads=[]; held_turn=[]
            def hold_first_turn(route):
                timed_payloads.append(route.request.post_data_json)
                if len(timed_payloads)==1:
                    committed=route.fetch(timeout=30000)
                    assert committed.status==200
                    held_turn.append((route,committed))
                else: route.continue_()
            page.route('**/api/sessions/*/turns',hold_first_turn)
            page.locator('#draft').fill('52')
            page.locator('#draft').press('Control+Enter')
            for _ in range(50):
                if held_turn: break
                page.wait_for_timeout(100)
            assert len(held_turn)==1
            expect(page.locator('.busy-note')).to_be_visible()
            expect(page.locator('#draft')).to_be_disabled()
            expect(page.get_by_role('button',name='Gửi bài',exact=True)).to_be_disabled()
            page.clock.fast_forward(45001)
            expect(page.get_by_role('button',name='Thử lại yêu cầu')).to_be_visible()
            expect(page.locator('#draft')).to_have_value('52')
            expect(page.locator('.busy-note')).to_have_count(0)
            held_turn[0][0].fulfill(response=held_turn[0][1])
            page.get_by_role('button',name='Thử lại yêu cầu').focus()
            page.keyboard.press('Enter')
            expect(page.locator('.turn')).to_have_count(1)
            expect(page.locator('.tutor-panel')).to_be_focused()
            assert len(timed_payloads)==2 and timed_payloads[0]==timed_payloads[1]
            committed_state=page.request.get(f'http://127.0.0.1:{frontend_port}/api/sessions/'+timed_session['session_id']).json()
            assert len(committed_state['turns'])==1 and committed_state['state_version']==2
            page.unroute('**/api/sessions/*/turns',hold_first_turn)
            checks.append({'flow':'production 45-second timeout via virtual clock, loading lock, preserved draft, keyboard retry with identical request ID and one committed turn','status':'passed'})
            assert not errors,errors
            browser.close()
        evidence={'checked_at':datetime.now(timezone.utc).isoformat(),'schema_isolated':True,'checks':checks,
                  'browser_errors':errors,'viewports':[1440,390],'snapshot_id':projection.snapshot_id,
                  'chunk_count':synced['chunks'],'model_api_calls':0,'real_local_embeddings':True}
    finally:
        for process in reversed(processes):
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
        with connect() as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        if previous is None: os.environ.pop('PGOPTIONS',None)
        else: os.environ['PGOPTIONS']=previous
    evidence['schema_removed']=True
    (out / 'verification.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'passed','checks':len(checks),'evidence':str((out/'verification.json').relative_to(ROOT))}))


if __name__=='__main__': main()
