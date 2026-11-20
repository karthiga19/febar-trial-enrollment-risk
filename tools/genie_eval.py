"""Ask the Genie Agent the benchmark questions via the Conversation API; write question, generated SQL and
real result rows to evidence/genie_conversations.md. Usage: python3 tools/genie_eval.py <space_id>"""
import json, subprocess, sys, time, pathlib

PROFILE = "fevm-current"
def api(method, path, body=None):
    cmd = ["databricks", "api", method.lower(), path, "-p", PROFILE]
    if body is not None: cmd += ["--json", json.dumps(body)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode: raise RuntimeError(out.stderr[:500])
    return json.loads(out.stdout or "{}")

QUESTIONS = [
    "Which studies are Critical or High risk and why?",
    "What is the total projected delay cost by therapeutic area?",
    "Which at-risk studies have no intervention logged yet?",
    "Show actual vs planned enrollment for MRD-CVM-309 over the last 8 weeks",
    "Among public oncology Phase 3 trials, how often do biomarker-selected trials terminate for low accrual vs non-biomarker trials?",
    "How many studies are behind plan, and what is the total addressable savings if we act now?",
]

def ask(space, q):
    m = api("POST", f"/api/2.0/genie/spaces/{space}/start-conversation", {"content": q})
    cid, mid = m["conversation_id"], m["message_id"]
    for _ in range(90):
        msg = api("GET", f"/api/2.0/genie/spaces/{space}/conversations/{cid}/messages/{mid}")
        if msg.get("status") in ("COMPLETED", "FAILED", "CANCELLED"): break
        time.sleep(3)
    res = {"q": q, "status": msg.get("status"), "text": [], "sql": None, "rows": None, "cols": None}
    for a in msg.get("attachments", []) or []:
        if a.get("text"): res["text"].append(a["text"].get("content", ""))
        if a.get("query"):
            res["sql"] = a["query"].get("query"); res["desc"] = a["query"].get("description")
            r = api("GET", f"/api/2.0/genie/spaces/{space}/conversations/{cid}/messages/{mid}/attachments/{a['attachment_id']}/query-result")
            sr = r.get("statement_response", {})
            res["cols"] = [c["name"] for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
            res["rows"] = sr.get("result", {}).get("data_array", [])
    return res

def main(space):
    out = ["# Genie Agent: Conversation API transcripts\n",
           f"Space `{space}` (Meridian Trial Enrollment Risk Agent). Each answer below is the Genie response, the SQL it generated, and the real rows returned.\n"]
    for q in QUESTIONS:
        r = ask(space, q)
        print(r["status"], "|", q, "|", (r["rows"] or [])[:2])
        out.append(f"## Q: {q}\n\n**Status:** {r['status']}\n")
        if r.get("desc"): out.append(f"**Genie's interpretation:** {r['desc']}\n")
        for t in r["text"]: out.append(f"**Answer:** {t}\n")
        if r["sql"]: out.append(f"```sql\n{r['sql']}\n```\n")
        if r["cols"]:
            out.append("| " + " | ".join(r["cols"]) + " |\n|" + "---|" * len(r["cols"]))
            for row in (r["rows"] or [])[:15]: out.append("| " + " | ".join(str(v)[:120] for v in row) + " |")
            out.append("")
    p = pathlib.Path(__file__).resolve().parents[1] / "evidence" / "genie_conversations.md"
    p.write_text("\n".join(out)); print("wrote", p)

if __name__ == "__main__":
    main(sys.argv[1])
