"""Export executed job-task notebooks (code + real outputs) as readable Markdown into evidence/.

Databricks `jobs export-run` returns an HTML page that embeds the executed notebook model
(base64 + URL-encoded JSON). We decode it and render each command with its text/table output.
Usage: python3 tools/export_run_evidence.py <job_run_id>
"""
import base64, json, pathlib, re, subprocess, sys, urllib.parse, html

PROFILE = "fevm-current"
OUT = pathlib.Path(__file__).resolve().parents[1] / "evidence"

def cli(*args):
    return subprocess.run(["databricks", *args, "-p", PROFILE, "-o", "json"], capture_output=True, text=True, check=True).stdout

def render_result(r):
    if not r: return ""
    t = r.get("type")
    if t == "listResults":
        parts = [render_result(x) for x in r.get("data", [])]
        return "\n\n".join(p for p in parts if p)
    if t == "ansi":
        txt = re.sub(r"\x1b\[[0-9;]*m", "", str(r.get("data", "")))
        keep = [l for l in txt.splitlines() if not re.search(r"Warning|warnings.warn|MLflow Tracing|you may need to restart|^\s*$", l)]
        return "\n".join(keep).strip()[:8000]
    if t in ("html",) and r.get("data"):
        txt = re.sub(r"<[^>]+>", "", str(r["data"]))
        return html.unescape(txt).strip()[:6000]
    if t == "table":
        cols = [c["name"] for c in r.get("schema", [])]
        rows = r.get("data", [])[:40]
        md = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
        for row in rows:
            md += "| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ")[:160] for v in row) + " |\n"
        if len(r.get("data", [])) > 40: md += f"\n_(showing 40 of {len(r['data'])} rows)_\n"
        return md
    if t == "error" or r.get("cause"):
        return "ERROR: " + re.sub(r"\x1b\[[0-9;]*m", "", str(r.get("summary") or r.get("cause") or r.get("data")))[:3000]
    data = r.get("data")
    if isinstance(data, str): return re.sub(r"\x1b\[[0-9;]*m", "", data).strip()[:8000]
    if isinstance(data, list): return "\n".join(map(str, data))[:8000]
    return ""

def main(run_id):
    run = json.loads(cli("jobs", "get-run", str(run_id)))
    OUT.mkdir(exist_ok=True)
    index = [f"# Execution evidence: job run {run_id}\n", f"Job: `{run.get('run_name')}`, result **{run['state'].get('result_state')}**\n",
             f"Run page: {run.get('run_page_url')}\n", "| task | attempt | result | duration (s) | evidence |", "|---|---|---|---|---|"]
    latest = {}
    for t in run["tasks"]:
        k = t["task_key"]
        if k not in latest or t.get("attempt_number", 0) >= latest[k].get("attempt_number", 0): latest[k] = t
    for k, t in sorted(latest.items(), key=lambda kv: kv[1].get("start_time", 0)):
        dur = round((t.get("end_time", 0) - t.get("start_time", 0)) / 1000)
        res = t["state"].get("result_state")
        ev = ""
        if "notebook_task" in t and res:
            try:
                h = json.loads(cli("jobs", "export-run", str(t["run_id"])))
                content = h["views"][0]["content"]
                m = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", content)
                model = json.loads(urllib.parse.unquote(base64.b64decode(m.group(1)).decode()))
                nb = t["notebook_task"]["notebook_path"].split("/")[-1]
                md = [f"# {nb} (executed, with outputs)\n", f"Job run `{run_id}` · task `{k}` · task run `{t['run_id']}` · result **{res}**\n"]
                for c in model["commands"]:
                    code = c.get("command", "")
                    if code.strip().startswith("%md"):
                        md.append(re.sub(r"^%md\s?", "", code.strip()) + "\n"); continue
                    lang = "sql" if code.strip().startswith("%sql") else "python"
                    md.append(f"```{lang}\n{code.strip()}\n```")
                    out = render_result(c.get("results"))
                    if out: md.append("**Output:**\n\n" + (out if out.startswith("|") else f"```text\n{out}\n```") + "\n")
                name = f"{k}.md"
                (OUT / name).write_text("\n".join(md))
                ev = f"[{name}]({name})"
            except Exception as e:  # keep going; record the failure
                ev = f"export failed: {e}"
        elif "pipeline_task" in t:
            ev = "[pipeline_run.md](pipeline_run.md)"
        elif "sql_task" in t:
            ev = "SQL file `src/sql/05_governance_semantic_layer.sql`"
        index.append(f"| {k} | {t.get('attempt_number', 0)} | {res} | {dur} | {ev} |")
    (OUT / "JOB_RUN.md").write_text("\n".join(index) + "\n")
    print("\n".join(index))

if __name__ == "__main__":
    main(sys.argv[1])
