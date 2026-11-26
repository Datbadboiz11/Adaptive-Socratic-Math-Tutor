"""Workspace-local PostgreSQL and web helpers. Never removes data or exposes credentials."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "artifacts/runtime-validation"
PG_BIN = ROOT / "artifacts/tooling/pg16/Library/bin"
PG_DATA = RUNTIME / "postgres-data"
STAGE4_TESTS = ["tests/test_stage4_teaching.py", "tests/test_stage4_reports.py", "tests/test_release_inputs.py", "tests/test_member2_runtime.py", "tests/test_phase3_db.py",
                "tests/test_phase3_math.py", "tests/test_phase2.py", "tests/test_phase1.py", "tests/test_stage3_completion.py"]


def local_environment():
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    env = {**os.environ, **{k: v for k, v in values.items() if v},
           "PGHOST": "127.0.0.1", "PGPORT": values.get("POSTGRES_PORT", "5433"),
           "PGDATABASE": values.get("POSTGRES_DB", "mo_tutor_dev"),
           "PGUSER": values.get("POSTGRES_USER", "mo_dev"), "PGPASSWORD": values["POSTGRES_PASSWORD"],
           "DEMO_MODE": "true", "TUTOR_ENABLED": "true", "LLM_ENABLED": "false",
           "PYTHONPATH": str(ROOT / "backend"), "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1",
           "NEXT_TELEMETRY_DISABLED": "1", "PLAYWRIGHT_BROWSERS_PATH": str(ROOT / "artifacts/tooling/playwright"),
           "PATH": str(PG_BIN) + os.pathsep + os.environ["PATH"]}
    env.pop("DATABASE_URL", None)
    env.pop("PGOPTIONS", None)
    return env


def run(command, env, cwd=ROOT):
    # A service spawned by pg_ctl can inherit pipe handles and keep communicate() waiting.
    # File-backed output lets us wait only for the helper itself, retaining every log.
    RUNTIME.mkdir(parents=True, exist_ok=True)
    log_path = RUNTIME / ("command-" + str(time.time_ns()) + ".log")
    with log_path.open("x", encoding="utf-8") as log:
        result = subprocess.run([str(a) for a in command], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    output = log_path.read_text(encoding="utf-8", errors="replace")
    if result.returncode:
        # Commands never contain secrets. Keep full local diagnostic logs out of published evidence.
        raise RuntimeError("Local helper failed: " + Path(command[0]).name + "; inspect artifacts/runtime-validation logs")
    return output


def port_open(port):
    with socket.socket() as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", int(port))) == 0


def database(env):
    import psycopg
    from psycopg import sql
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not PG_DATA.exists():
        password_file = RUNTIME / "initdb-password.local"
        with password_file.open("x", encoding="utf-8") as stream:
            stream.write(env["PGPASSWORD"] + "\n")
        run([PG_BIN / "initdb.exe", "-D", PG_DATA, "-U", env["PGUSER"], "--encoding=UTF8", "--locale=C",
             "--auth=scram-sha-256", "--pwfile", password_file], env)
    if (PG_DATA / "PG_VERSION").read_text().strip() != "16":
        raise ValueError("Unexpected PostgreSQL data directory version")
    if not port_open(env["PGPORT"]):
        run([PG_BIN / "pg_ctl.exe", "-D", PG_DATA, "-l", RUNTIME / "postgres.log", "-o",
             "-h 127.0.0.1 -p " + env["PGPORT"], "-w", "start"], env)
    with psycopg.connect(host="127.0.0.1", port=int(env["PGPORT"]), user=env["PGUSER"],
                         password=env["PGPASSWORD"], dbname="postgres", autocommit=True) as connection:
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (env["PGDATABASE"],)).fetchone():
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(env["PGDATABASE"])))
    with psycopg.connect(host="127.0.0.1", port=int(env["PGPORT"]), user=env["PGUSER"],
                         password=env["PGPASSWORD"], dbname=env["PGDATABASE"]) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        version = connection.execute("SELECT version()").fetchone()[0]
        vector = connection.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0]
    run([sys.executable, "-m", "app.manage", "bootstrap"], env)
    return {"postgres": version, "pgvector": vector, "host": "127.0.0.1", "port": int(env["PGPORT"])}


def spawn(command, env, name, cwd=ROOT):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    prefix = RUNTIME / (name + "-" + str(time.time_ns()))
    with Path(str(prefix) + ".stdout.log").open("x", encoding="utf-8") as stdout, \
         Path(str(prefix) + ".stderr.log").open("x", encoding="utf-8") as stderr:
        process = subprocess.Popen([str(a) for a in command], cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return process.pid


def serve(env):
    backend_port = int(env.get("BACKEND_PORT", "8000"))
    frontend_port = int(env.get("FRONTEND_PORT", "3000"))
    env["BACKEND_URL"] = f"http://127.0.0.1:{backend_port}"
    processes = {}
    for port, name, command, cwd in [
        (backend_port, "backend", [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(backend_port)], ROOT),
        (frontend_port, "frontend", ["node", "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(frontend_port)], ROOT / "frontend"),
    ]:
        if port_open(port):
            raise ValueError(f"Port {port} is occupied; inspect before starting another helper")
        processes[name] = spawn(command, env, name, cwd)
    for url in (env["BACKEND_URL"] + "/health/ready", f"http://127.0.0.1:{frontend_port}"):
        for _ in range(40):
            try:
                with urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("Local service did not become ready; inspect runtime logs")
    return {"processes": processes, "backend": env["BACKEND_URL"], "frontend": f"http://127.0.0.1:{frontend_port}"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["database", "serve", "tests"])
    parser.add_argument("--enable-model", action="store_true", help="Enable the configured provider for serve only")
    parser.add_argument("--suite", choices=["full", "stage4"], default="full", help="Select the current Stage 4/runtime suite or all historical tests")
    args = parser.parse_args()
    env = local_environment()
    if args.enable_model:
        prefix = {"gemini": "GEMINI", "openai": "OPENAI"}.get(env.get("LLM_PROVIDER", "openai"))
        if args.command != "serve" or not prefix or not env.get(prefix + "_API_KEY") or not env.get(prefix + "_MODEL"):
            parser.error("--enable-model requires serve and a configured provider key/model")
        env["LLM_ENABLED"] = "true"
    if args.command == "database":
        result = database(env)
    elif args.command == "serve":
        result = serve(env)
    else:
        env["RUN_DB_TESTS"] = "1"
        # The user's .env may now contain a live key. Tests set their own synthetic credentials.
        for name in ("OPENAI_API_KEY", "GEMINI_API_KEY"):
            env.pop(name, None)
        env.update(LLM_PROVIDER="openai", LLM_ENABLED="false", AUTHORING_LLM_ENABLED="false")
        paths = STAGE4_TESTS if args.suite == "stage4" else ["tests"]
        report_path = "artifacts/stage4-current-tests.xml" if args.suite == "stage4" else "artifacts/validation-db-tests.xml"
        command = [sys.executable, "-m", "pytest", *paths, "-q", "--disable-warnings",
                   "-o", "cache_dir=artifacts/validation-pytest-cache", "--junitxml=" + report_path]
        print(run(command, env))
        return
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
