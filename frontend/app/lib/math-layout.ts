// Bounded presentation grammar. It never evaluates math or accepts HTML/TeX.
export type MathNode = { tag: string; text?: string; children?: MathNode[] };
const node = (tag: string, ...children: MathNode[]): MathNode => ({ tag, children });
const token = (tag: string, text: string): MathNode => ({ tag, text });

export function mathLayout(input: string): MathNode | null {
  if (!input || input.length > 500) return null;
  const source = input.replace(/−/g, "-").replace(/×|·/g, "*").replace(/÷/g, "/").replace(/²/g, "^2").replace(/³/g, "^3");
  const tokens = source.match(/sqrt|\d+(?:\.\d+)?|[a-zA-Z]|<=|>=|!=|[+\-*/^=<>?();{}]/g) || [];
  if (tokens.join("") !== source.replace(/\s/g, "") || tokens.length > 180) return null;
  let i = 0, depth = 0;
  const peek = () => tokens[i];
  const take = () => tokens[i++];
  const op = (s: string) => token("mo", s === "*" ? "·" : s === "-" ? "−" : s);
  function atom(): MathNode {
    if (++depth > 24) throw Error("depth");
    let value: MathNode;
    const t = take();
    if (t === "sqrt") {
      if (take() !== "(") throw Error("root");
      value = node("msqrt", relation());
      if (take() !== ")") throw Error("root close");
    } else if (t === "(" || t === "{") {
      const inner = relation();
      const end = t === "(" ? ")" : "}";
      if (take() !== end) throw Error("close");
      value = node("mrow", op(t), inner, op(end));
    } else if (t && /^\d/.test(t)) value = token("mn", t);
    else if (t && /^[a-zA-Z]$/.test(t)) value = token("mi", t);
    else throw Error("atom");
    depth--;
    return value;
  }
  function power(): MathNode {
    const left = atom();
    if (peek() === "^") { take(); if (++depth > 24) throw Error("power depth"); const right = unary(); depth--; return node("msup", left, right); }
    return left;
  }
  function unary(): MathNode {
    if (peek() === "+" || peek() === "-") {
      if (++depth > 24) throw Error("unary depth");
      const sign = take(), value = unary(); depth--; return node("mrow", op(sign), value);
    }
    return power();
  }
  function product(): MathNode {
    let left = unary();
    while (peek() === "*" || peek() === "/" || /^(?:\d|[a-zA-Z]|\()/.test(peek() || "")) {
      const explicit = peek() === "*" || peek() === "/", sign = explicit ? take() : "*";
      const right = unary();
      left = sign === "/" ? node("mfrac", left, right) : node("mrow", left, op(sign), right);
    }
    return left;
  }
  function sum(): MathNode {
    let left = product();
    while (peek() === "+" || peek() === "-") { const sign = take(); left = node("mrow", left, op(sign), product()); }
    return left;
  }
  function relation(): MathNode {
    let left = sum();
    while (["=", "<", ">", "<=", ">=", "!=", "?"].includes(peek())) { const sign = take(); left = node("mrow", left, op(sign), sum()); }
    return left;
  }
  try {
    const rows = [relation()];
    while (peek() === ";") { take(); rows.push(relation()); }
    if (i !== tokens.length || rows.length > 8) return null;
    return rows.length === 1 ? rows[0] : node("mrow", op("{"), node("mtable", ...rows.map(row => node("mtr", node("mtd", row)))));
  } catch { return null; }
}
