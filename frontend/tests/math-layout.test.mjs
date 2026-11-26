import { test } from "node:test";
import assert from "node:assert/strict";
import { mathLayout } from "../app/lib/math-layout.ts";

test("nested fractions preserve numerator and denominator structure", () => {
  const layout = mathLayout("(x+1)/(x-2)");
  assert.equal(layout.tag, "mfrac");
  assert.equal(layout.children.length, 2);
  assert.match(JSON.stringify(layout.children[0]), /\+/);
  assert.match(JSON.stringify(layout.children[1]), /−/);
  assert.equal(mathLayout("(1/2)/(3/4)").tag, "mfrac");
});
test("powers, signed exponent and square roots preserve precedence", () => {
  assert.equal(mathLayout("-x^2").children[1].tag, "msup");
  assert.equal(mathLayout("x^-2").tag, "msup");
  assert.equal(mathLayout("sqrt((x+1)/2)").children[0].tag, "mfrac");
  assert.equal(mathLayout("x²").tag, "msup");
});
test("system of equations has two MathML rows and implicit multiplication", () => {
  const layout = mathLayout("2x+y=8;x-y=1");
  assert.equal(layout.children[1].tag, "mtable");
  assert.equal(layout.children[1].children.length, 2);
});
test("unsupported and excessive inputs fail safely to escaped text", () => {
  for (const input of ["<img src=x onerror=alert(1)>", "\\frac{1}{2}", "x=", "sqrt(x", "(".repeat(30)+"1"+")".repeat(30), "-".repeat(30)+"1", "x^".repeat(30)+"2", "x".repeat(501)]) {
    assert.equal(mathLayout(input), null, input);
  }
});
