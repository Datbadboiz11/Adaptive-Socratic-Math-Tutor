import { Fragment, createElement as element } from "react";
import { mathLayout, type MathNode } from "../lib/math-layout";

function render(node: MathNode, key = 0): React.ReactNode {
  return element(node.tag, { key }, node.text ?? node.children?.map((child, index) => render(child, index)));
}

export function Formula({ value }: { value: string }) {
  const layout = mathLayout(value);
  if (layout) return element("math", { "aria-label": value, tabIndex: 0 }, render(layout));
  return <code>{value}</code>;
}

export function MathText({ text }: { text: string }) {
  return <span className="math-text">{text.split(/(`[^`\n]+`)/g).map((part, index) =>
    <Fragment key={index}>{part.startsWith("`") && part.endsWith("`")
      ? <Formula value={part.slice(1, -1)} /> : part}</Fragment>)}</span>;
}
