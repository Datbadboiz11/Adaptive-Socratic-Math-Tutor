import { Fragment, createElement as element } from "react";

function Formula({ value }: { value: string }) {
  const fraction = value.match(/^(-?\d+|[a-z])\s*\/\s*(-?\d+|[a-z])$/i);
  const power = value.match(/^([a-z]|\d+)\^(-?\d+)$/i);
  const root = value.match(/^sqrt\((\d+|[a-z])\)$/i);
  const token = (text: string) => element(/^-?\d+$/.test(text) ? "mn" : "mi", null, text);
  if (fraction) return element("math", { "aria-label": value }, element("mfrac", null, token(fraction[1]), token(fraction[2])));
  if (power) return element("math", { "aria-label": value }, element("msup", null, token(power[1]), token(power[2])));
  if (root) return element("math", { "aria-label": value }, element("msqrt", null, token(root[1])));
  // Unsupported grammar remains readable escaped text; no HTML/TeX evaluation.
  return <code>{value}</code>;
}

export function MathText({ text }: { text: string }) {
  return <span className="math-text">{text.split(/(`[^`\n]+`)/g).map((part, index) =>
    <Fragment key={index}>{part.startsWith("`") && part.endsWith("`")
      ? <Formula value={part.slice(1, -1)} /> : part}</Fragment>)}</span>;
}
