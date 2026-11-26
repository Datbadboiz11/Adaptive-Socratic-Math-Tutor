import type { SessionView } from "../lib/api-types";
import { Formula } from "./MathText";

export function ProblemFormula({ problem }: { problem: SessionView["problem"] }) {
  if (!("task" in problem)) return null;
  const { kind, expression, variable_value } = problem.task;
  // Only display given quantities. Never derive the equation of a word problem,
  // factorization, solution, excluded values or any other requested answer.
  if (["word_equation", "number_conversion", "exponent_numeric", "function_domain"].includes(kind)) return null;
  let value = expression;
  if (kind === "rational_operation") {
    const [operation, ...fractions] = expression.split(";").map(s => s.trim());
    if (!/^[+\-*/]$/.test(operation) || fractions.length !== 2 || fractions.some(f => f.split("|").length !== 2)) return null;
    value = fractions.map(f => `(${f.split("|").map(s => `(${s.trim()})`).join("/")})`).join(` ${operation} `);
  }
  return <div className="problem-formula" aria-label="Biểu thức trong đề"><Formula value={value} />
    {kind === "evaluate" && variable_value && <span> với <Formula value={`x=${variable_value}`} /></span>}
  </div>;
}
