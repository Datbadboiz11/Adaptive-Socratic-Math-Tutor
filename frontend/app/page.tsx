import Workspace from "./workspace";
export const dynamic = "force-dynamic";
export default async function Home() {
  let ready = false;
  try {
    const response = await fetch(`${process.env.BACKEND_URL || "http://127.0.0.1:8000"}/health/ready`, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    ready = response.ok;
  } catch { /* Workspace presents recoverable errors. */ }
  return <Workspace initialReady={ready} />;
}
