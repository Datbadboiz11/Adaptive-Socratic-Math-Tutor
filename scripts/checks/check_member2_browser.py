"""Browser acceptance against an isolated demo server backed by PostgreSQL."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(ROOT / 'artifacts/tooling/playwright'))
    bank = json.loads((ROOT / 'content/authoring/batches/member2-original.v2/approved-bank.json').read_bytes())
    out = ROOT / 'artifacts/browser-validation' / ('member2-' + uuid4().hex[:12])
    out.mkdir(parents=True, exist_ok=False)
    errors, checks = [], []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.set_default_timeout(20000)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until='networkidle')
        profile = page.locator('#profile')
        profile.select_option('DEMO-STUDENT-01')
        draft = page.locator('#draft')

        def click_request(label, endpoint):
            with page.expect_response(lambda r: r.url.endswith(endpoint) and r.request.method == 'POST') as pending:
                page.get_by_role('button', name=label, exact=True).click()
            response = pending.value
            assert response.status == 200, response.status
            return response.json()

        def start(concept_id):
            page.locator('#topic').select_option('TOPIC-' + concept_id)
            with page.expect_response(lambda r: r.url.endswith('/api/sessions') and r.request.method == 'POST') as pending:
                page.get_by_role('button', name='Bắt đầu phiên thử').click()
            assert pending.value.status == 201
            problem = pending.value.json()['problem']
            assert problem['concept_id'] == concept_id
            assert set(problem).isdisjoint({'reference_answer', 'reference_steps', 'hint_ladder', 'source_group'})
            expect(draft).to_be_enabled()
            expect(page.locator('#draft-help')).to_contain_text('kiểm tra dòng cuối')
            return problem

        for pack in bank['packs']:
            problem = start(pack['concept_id'])
            draft.fill(pack['problems'][0]['reference_answer'])
            data = click_request('Gửi bài', '/turns')
            assert data['assessment']['assessment_status'] == 'verified_correct'
            expect(page.locator('.tutor-panel')).to_contain_text('Dòng kết quả cuối')
            report = click_request('Kết thúc & xem báo cáo', '/finish')
            assert report['assessment_scope'] == 'final_answer'
            assert (report['independent_correct'], report['valid_observations']) == (1, 0)
            expect(page.get_by_text('Bài lặp hoặc gần đã đúng', exact=True)).to_be_visible()
            checks.append({'concept_id': pack['concept_id'], 'task': problem['task']['kind'], 'result': 'pass'})

        for concept_id, advance_count, help_text in (('F05', 2, 'phương trình trục'), ('F08', 5, 'không phải hàm số mũ')):
            pack = next(pack for pack in bank['packs'] if pack['concept_id'] == concept_id)
            start(concept_id)
            for index in range(advance_count):
                current = click_request(f'Thử bài tiếp ({5 - index})', '/next')
            assert current['problem']['problem_id'] == pack['problems'][advance_count]['case_id']
            expect(page.locator('#draft-help')).to_contain_text(help_text)
            draft.fill(pack['problems'][advance_count]['reference_answer'])
            assert click_request('Gửi bài', '/turns')['assessment']['assessment_status'] == 'verified_correct'

        pack = next(pack for pack in bank['packs'] if pack['concept_id'] == 'A10')
        start('A10')
        expect(page.locator('#draft-help')).to_contain_text('tử|mẫu')
        draft.fill(pack['errors'][0]['response_steps'][0])
        wrong = click_request('Gửi bài', '/turns')
        assert wrong['assessment']['assessment_status'] == 'verified_incorrect'
        assert wrong['message'] == pack['hints'][0]['text']
        expect(page.locator('.tutor-panel')).to_contain_text('Gợi ý từ nội dung đã duyệt')
        for level in (2, 3):
            hint = click_request('Xin gợi ý', '/turns')
            assert hint['session']['hint_level'] == level
        capped = click_request('Xin gợi ý', '/turns')
        assert capped['tutor']['action'] == 'offer_pause' and capped['session']['hint_level'] == 3
        click_request('Tạm dừng', '/pause')
        page.reload(wait_until='networkidle')
        page.locator('.history button').first.click()
        expect(draft).to_have_value(pack['errors'][0]['response_steps'][0])
        click_request('Tiếp tục phiên', '/resume')

        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 950})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(out / f'A10-{width}.png'), full_page=True)
        draft.fill(pack['problems'][0]['reference_answer'])
        with page.expect_response(lambda r: r.url.endswith('/turns') and r.request.method == 'POST') as pending:
            draft.press('Control+Enter')
        assert pending.value.json()['assessment']['assessment_status'] == 'verified_correct'
        report = click_request('Kết thúc & xem báo cáo', '/finish')
        assert report['assisted_correct'] == 1 and report['valid_observations'] == 0
        assert not errors, errors
        browser.close()

    evidence = {'time': datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds'),
                'approved_topics': checks, 'ui_viewports': [1440, 390], 'console_errors': errors,
                'checks': ['approved tasks render', 'task-specific help changes within a topic',
                           'final answer and report', 'wrong answer and hint cap',
                           'pause, reload and resume', 'keyboard submission', 'assisted outcome']}
    (out / 'verification.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'passed', 'topics': len(checks), 'artifact': str(out.relative_to(ROOT))}))


if __name__ == '__main__':
    main()
