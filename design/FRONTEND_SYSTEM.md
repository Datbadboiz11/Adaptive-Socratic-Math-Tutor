# Mở — Frontend design system

## Audit and direction

The live frontend previously put profile selection, exercise composition, feedback, history, and reporting in one continuous view. Global element selectors conflicted with workspace styling. Large rounded containers gave every section equal emphasis; there was no overview, topic catalogue, or visual mastery summary. Technical metadata competed with the student's next action, and session steps were rendered as plain code.

Keep the original Mở identity and Vietnamese voice: an open-circle symbol and the “mở.” wordmark, restored at the user's request. Combine Linear's quiet navigation and density, Notion's readable content hierarchy, and Khan Academy's emphasis on learning and encouragement. These are references for principles, not copied layouts. The learning invitation uses a mathematical coordinate drawing. Sparse sage foliage decorates the sidebar's free space, separated from navigation and profile controls; it is hidden from assistive technology and omitted on short screens. The alternate opening-book logo files remain available in `frontend/public/brand/` as an unused exploration. No stock illustration, artificial achievement, decorative gradients, or emoji icons.

UI/UX Pro Max searches were reviewed before implementation. The education result suggested claymorphism and playful fonts; the narrower SaaS result suggested glass. Both conflict with this brief, so their visual prescriptions are rejected. Apply the verified accessibility, responsive, semantic color, and font-loading guidance, with the deliberate tokens below.

## Tokens

| Role | Value | Purpose |
| --- | --- | --- |
| Canvas | `#F7F9FA` | Main workspace |
| Surface | `#FFFFFF` | Reading and composition |
| Sidebar | `#EDF6F0` | Pale mint-sage navigation background |
| Sidebar selection | `#D6EADD` | Active navigation, distinct from the sidebar surface |
| Ink | `#182B30` | Main text |
| Muted | `#56676D` | Secondary text, minimum AA contrast on light surfaces |
| Primary | `#146554` | Navigation, links, primary actions |
| Soft primary | `#E9F3EF` | Selection and helpful feedback |

Other semantic tokens: border `#DFE7E5`, input border `#8B9C99`, warning text `#865015`, warning surface `#FFF6E8`, error text `#A22D34`, error surface `#FFF0F0`, focus `#167568`. All are CSS custom properties in `frontend/app/globals.css`; components consume roles rather than selecting new colors. Borders separating content are subtle; interactive control outlines have stronger contrast.

Dashboard: use a single three-column statistics strip in `--dashboard-tint` (`#F0F6F2`) with dividers instead of three isolated cards. Recent sessions use a white reading surface; the adjacent knowledge panel uses `--dashboard-mint` (`#EAF3EE`). The topic starter has a quiet header and a separated form. Empty states use decorative notebook/sprout SVGs, with no invented graphs or activity. The history empty state offers navigation to the existing learning view. Keep all three totals readable on mobile; hide secondary descriptions there, never the labels or values.

Dashboard refresh validation: production build passed; `check_frontend_design.py --start-server` passed all 11 acceptance groups and 12 automated accessibility audits. Screenshots and results: `artifacts/browser-validation/frontend-design-ccfdb66f36/`. Tests use isolated API fixtures and do not modify backend or database.

Typography: locally hosted Be Vietnam Pro (400/500/600/700), including Vietnamese characters. UI 14px, reading 16px/1.75, page title 28–32px, invitation title 34–40px. Data uses tabular numerals. Native MathML uses the browser's mathematical font with Cambria/STIX fallback. Long formulas scroll within their own container rather than widening the page.

Spacing: 4, 8, 12, 16, 24, 32, 40, 48px. Radius: 6px controls, 10px panels, 14px featured invitation. No card shadows; a single shadow is reserved for the mobile navigation overlay. Icons share a 24px viewBox and 1.7px stroke.

## Layout

Left-aligned application shell, 232px desktop sidebar, 72px header, content capped at 1240px. Reading/composition column remains shrinkable. At 1100px, learning support moves below the exercise. At 760px, the sidebar becomes an accessible disclosure with a backdrop, Escape dismissal, focus return, and no hidden focus targets. Content becomes one column; metrics retain two columns where readable.

```text
Desktop
┌────────────┬────────────────────────────────────────┐
│ Mở         │ Current view               Connection  │
│ Navigation ├────────────────────────────────────────┤
│            │ Heading + next action                  │
│ Profile    │ Learning invitation / exercise         │
│            │ Progress + topics / conversation       │
└────────────┴────────────────────────────────────────┘

Mobile
┌────────────────────────┐
│ Menu  Mở  Current view │
├────────────────────────┤
│ Heading                │
│ Main action / exercise │
│ Supporting information │
└────────────────────────┘
```

## Views and reusable components

- Overview: current profile, real session counts, a topic picker, recent sessions, and knowledge estimates when supplied by the current session/report.
- Learn: problem context, existing draft editor and actions, latest tutor response, and the complete conversation with source disclosures. Never reveal a worked solution as decorative content.
- Topics: searchable existing topic catalogue, availability and review status, selection that uses the existing topic state.
- History: saved session buttons use the existing open/resume/report actions.
- Progress: BKT estimates labeled as estimates (not grades), independent/assisted/repeated results kept separate, existing evidence and provenance retained.

Shared elements: `Icon`, `SessionHistory`, `MasteryOverview`, `LearningReport`, `TeachingFeedback`, `MathText`, `ProblemFormula`. Preserve the existing session hook, generated API contracts, proxy, and backend. Hash navigation allows back/forward navigation while keeping the draft mounted in state.

## Interaction and accessibility

44px minimum action targets; visible labels and keyboard focus; skip link; landmarks; one page-level heading per view. Decorative icons are hidden from assistive technology. Status is conveyed by text as well as color. New view navigation focuses the content; feedback retains the existing hook's focus behavior. Loading and error feedback remain reachable, including retry/reconciliation.

Motion answers actions: 160ms color/opacity and 220ms drawer transitions. No continuous decorative motion. Disable transitions and animation under `prefers-reduced-motion`. Test mobile navigation, 320/390/768/1024/1440px viewports, long math, empty/offline states, tutoring, pause/resume, report, and retained drafts.

## Validation — 2026-11-27

- `npm run build`, `npm run typecheck`, and `npm test` in `frontend`: passed; all four existing mathematical-layout tests passed. No lint script is configured in this project.
- `.venv/Scripts/python.exe scripts/checks/check_frontend_design.py --start-server`: passed 11 acceptance groups, including all five views at 320/390/768/1024/1440px without page overflow.
- Axe 4.10.3: 12 audited states, no reported violations for the selected WCAG A/AA tags. This is an automated check, not a complete accessibility certification.
- Verified keyboard skip link, hash navigation and browser history, retained drafts, hint feedback focus, submission retry with the same request ID, pause/resume, topic filtering/availability, native modal navigation, structured fractions, and report evidence.
- 17 screenshots and machine-readable results: `artifacts/browser-validation/frontend-design-c348c3c4e0/`. Desktop, mobile, and report screenshots were reviewed visually during implementation.

The browser test runs the production frontend against isolated API fixtures. Backend/PostgreSQL were not running; live persistence and real tutor responses were not retested. No backend, API proxy, generated contracts, session hook, or database files were changed. The fixture data exists only in the browser acceptance script.

The browser script uses the workspace Python environment with Playwright, installed Chrome, and `artifacts/tooling/axe-4.10.3.min.js`. Build the frontend first. `--start-server` launches a temporary production server on port 3117 and stops it after the test; omit the flag and use `--url` to test an already running frontend.
