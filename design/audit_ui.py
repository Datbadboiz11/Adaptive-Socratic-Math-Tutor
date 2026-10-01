"""Browser acceptance checks for the local, scripted design prototype.

Run with a Python environment that has Playwright installed and Chromium available.
Start the design server on localhost:8765 first. No external service is contacted
by the test runner; the optional web fonts may load from Google Fonts in the page.
"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'previews'
OUT.mkdir(exist_ok=True)
checks = []
errors = []

def check(label, condition):
    checks.append({'check': label, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(label)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
    page = context.new_page()
    page.on('pageerror', lambda err: errors.append(str(err)))
    page.goto('http://127.0.0.1:8765', wait_until='networkidle')
    page.wait_for_selector('h1')

    def route(name):
        page.goto('http://127.0.0.1:8765/#' + name, wait_until='networkidle')
        page.wait_for_selector('#main')

    def shot(name):
        page.screenshot(path=str(OUT / (name + '.png')), full_page=True)

    def session():
        return page.evaluate("JSON.parse(localStorage.getItem('mo-wireframe-v1')).session")

    def preset(name):
        page.locator('[data-action="scenarios"]').click()
        page.locator('[data-preset="' + name + '"]').click()

    def submit(value):
        page.locator('#answer').fill(value)
        page.locator('#answer-form button[type="submit"]').click()
        page.wait_for_function("!document.querySelector('.typing')")

    shot('01-overview-desktop')
    route('topics')
    check('Six topic cards are available', page.locator('.topic-card').count() == 6)
    page.locator('[data-filter="functions"]').click()
    check('Topic filter shows two function topics', page.locator('.topic-card').count() == 2)
    page.locator('#topic-search').fill('đỉnh')
    check('Vietnamese topic search works', page.locator('.topic-card').count() == 1)
    page.locator('[data-filter="all"]').click()
    page.locator('#topic-search').fill('')
    shot('02-topics-desktop')

    route('learn')
    shot('03-learning-empty-desktop')
    submit('2x - 3 = 10\n2x = 13\nx = 6.5')
    check('First wrong step creates exactly one observation', session()['observations'] == 1)
    check('Wrong step receives diagnostic support', session()['assisted'] and not session()['completedMain'])
    shot('04-learning-hint-desktop')
    page.locator('.tutor-footer [data-action="example"]').click()
    check('Support does not create an extra observation', session()['observations'] == 1)
    submit('2x - 6 = 10\n2x = 16\nx = 8')
    check('Correct after hint is marked assisted', session()['assistedCorrect'] == 1)
    check('Correction does not inflate observation count', session()['observations'] == 1)
    shot('05-learning-assisted-desktop')
    page.locator('[data-action="transfer"]').click()
    check('New problem starts without direct assistance', not session()['assisted'] and not session()['recorded'])
    submit('3x + 6 = 21\n3x = 15\nx = 5')
    check('Independent new answer is counted separately', session()['independentCorrect'] == 1 and session()['observations'] == 2)
    page.locator('[data-action="finish"]').click()
    page.wait_for_url('**/#report')
    check('Report splits assisted and independent outcomes', page.locator('.metric-value').all_text_contents() == ['1bài', '1bài', '2lần'])
    shot('06-report-desktop')

    route('progress')
    shot('07-progress-desktop')
    page.locator('[data-tab="history"]').click()
    check('Finished session appears in history', page.locator('.history-row').count() == 1)
    shot('08-history-desktop')

    preset('empty')
    page.locator('#answer').fill('2x - 6 = 10')
    page.locator('[data-action="pause"]').click()
    page.locator('[data-action="pause-confirm"]').click()
    page.wait_for_url('**/#overview')
    page.reload(wait_until='networkidle')
    page.locator('.resume-foot a').click()
    page.wait_for_url('**/#learn')
    check('Pause and reload preserve the draft', page.locator('#answer').input_value() == '2x - 6 = 10')
    check('Resume does not create an observation', session()['observations'] == 0)

    preset('offline')
    page.locator('[data-action="retry"]').click()
    page.wait_for_function("!document.querySelector('.typing')")
    check('Retry counts one observation only', session()['observations'] == 1)
    submit('2x - 3 = 10\n2x = 13\nx = 6.5')
    check('Repeated wrong answer does not duplicate observation', session()['observations'] == 1)

    preset('empty')
    submit('Em thử biến đổi theo cách khác')
    check('Unverified input is not scored as wrong', session()['observations'] == 0)
    check('Unverified state is visible', 'Chưa xác minh' in page.locator('.feedback').inner_text())
    preset('unclear')
    check('Unclear input has no observation', session()['observations'] == 0)

    route('flow')
    check('Four user-flow lanes are available', page.locator('.flow-section').count() == 4)
    shot('09-user-flow-desktop')
    page.locator('[data-action="wireframe"]').click()
    route('overview')
    check('Wireframe mode is available', page.locator('body.wireframe').count() == 1)
    shot('10-wireframe-desktop')
    page.locator('[data-action="wireframe"]').click()

    route('login')
    shot('11-login-desktop')
    page.locator('#learner-name').fill('An')
    page.locator('#login-form button[type="submit"]').click()
    page.wait_for_url('**/#overview')
    check('New learner has no fabricated history', session() is None)
    shot('12-new-learner-desktop')

    for width in [390, 768, 1024, 1440]:
        page.set_viewport_size({'width': width, 'height': 844 if width == 390 else 1000})
        for screen in ['overview', 'topics', 'learn', 'report', 'progress', 'login', 'flow']:
            route(screen)
            overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
            check(f'{screen} has no horizontal overflow at {width}px', not overflow)
            if width == 390:
                shot(f'mobile-{screen}')

    page.set_viewport_size({'width': 1440, 'height': 1000})
    route('overview')
    check('No uncaught browser runtime errors', not errors)
    browser.close()

(OUT / 'qa-results.json').write_text(json.dumps({'checks': checks, 'browser_errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'passed': len(checks), 'browser_errors': errors, 'previews': str(OUT)}, ensure_ascii=False))
