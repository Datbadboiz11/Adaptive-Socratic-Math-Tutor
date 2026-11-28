/** A decorative learning motif, never a representation of student data. */
export function LearningEmptyIllustration({ variant }: { variant: "notebook" | "growth" }) {
  return <svg className="learning-empty-illustration" width="120" height="80" viewBox="0 0 120 80" fill="none" aria-hidden="true" focusable="false">
    {variant === "notebook" ? <>
      <path className="illustration-fill" d="M29 21C41 17 52 19 60 25C68 19 79 17 91 21V65C79 61 69 63 60 68C51 63 41 61 29 65V21Z" />
      <g className="illustration-stroke" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M24 17C38 13 50 16 60 22C70 16 82 13 96 17V59C82 55 70 58 60 64C50 58 38 55 24 59V17ZM60 22V64" />
        <path d="M34 28C40 27 46 29 51 31M34 37C40 36 46 38 51 40M70 31C75 28 80 27 86 28" />
        <path d="M87 49C91 38 99 31 108 30C109 40 102 48 91 49M85 57L102 37" />
      </g>
    </> : <>
      <path className="illustration-fill" d="M57 43C39 45 26 34 27 20C44 19 57 29 57 43ZM63 32C62 16 74 8 90 9C89 23 79 33 63 32Z" />
      <g className="illustration-stroke" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M60 65V32M60 49C47 37 39 31 30 27M60 36C66 25 74 18 83 15" />
        <path d="M57 43C39 45 26 34 27 20C44 19 57 29 57 43ZM63 32C62 16 74 8 90 9C89 23 79 33 63 32Z" />
        <path d="M37 69C48 65 72 65 83 69M46 75H74" />
      </g>
    </>}
  </svg>;
}
