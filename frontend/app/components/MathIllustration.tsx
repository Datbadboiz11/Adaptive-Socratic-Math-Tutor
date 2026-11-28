export function MathIllustration() {
  return <svg className="math-illustration" viewBox="0 0 340 220" fill="none" aria-hidden="true" focusable="false">
    <defs><pattern id="math-grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" stroke="currentColor" strokeOpacity=".12" /></pattern></defs>
    <rect x="15" y="5" width="310" height="210" fill="url(#math-grid)" />
    <path d="M35 165h270M100 205V20m-5 7 5-7 5 7m193 133 7 5-7 5" stroke="currentColor" strokeOpacity=".55" />
    <path d="M40 56Q147 267 284 36" stroke="currentColor" strokeWidth="2.5" />
    <path d="m74 194 188-122" stroke="currentColor" strokeOpacity=".45" strokeDasharray="5 5" />
    <circle cx="182" cy="124" r="6" fill="currentColor" /><circle cx="182" cy="124" r="13" stroke="currentColor" strokeOpacity=".3" />
    <path d="M182 124v41m0-41h-82" stroke="currentColor" strokeOpacity=".4" strokeDasharray="3 5" />
    <text x="205" y="51" fill="currentColor" fontFamily="Cambria Math, Georgia, serif" fontSize="25">y = f(x)</text>
    <text x="308" y="185" fill="currentColor" fontFamily="Cambria Math, Georgia, serif" fontSize="18">x</text>
    <text x="80" y="25" fill="currentColor" fontFamily="Cambria Math, Georgia, serif" fontSize="18">y</text>
  </svg>;
}
