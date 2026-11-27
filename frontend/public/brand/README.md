# Mở — logo assets

The application currently uses the original open-circle and “mở.” identity, as requested by the user. It is rendered by `BrandLogo.tsx`; `mo-classic-mark.svg` supplies its favicon. The opening-book assets below are retained as an alternate design exploration and are not the active application logo.

The mark depicts two opening pages with an asymmetric lifted right page. The rounded wordmark, Vietnamese horn and hỏi accent are drawn as SVG paths rather than font glyphs. The wordmark reads **mở**, without the old trailing dot.

- `mo-logo.svg`: full logo, teal `#146554` and leaf green `#4F9B80`.
- `mo-logo-mono.svg`: one-color teal version.
- `mo-logo-reverse.svg`: white and mint `#ACD9C4`, for dark teal backgrounds.
- `mo-mark.svg`: symbol for the favicon or compact placements.
- `preview.html`: standalone presentation and SVG downloads, served at `/brand/preview.html`.

Keep the SVG aspect ratio and clear space of at least half the symbol width. Use the full logo at 120px wide or larger and the symbol at 24px or larger where possible. A 16px favicon is a small-size exception. Keep the custom Vietnamese diacritics intact. Do not add shadows, gradients, distortions, or a surrounding frame.

The application uses `BrandLogo.tsx` for both navigation and footer. The alternative exported SVGs are self-contained, have transparent backgrounds, and require no fonts or external resources.
