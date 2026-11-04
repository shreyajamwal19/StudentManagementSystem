#!/usr/bin/env python3
"""Result 4: auditability and marks provenance for one sample record, on System B with the real Besu network.
Flow: marks entered -> submitted -> moderated -> approved -> locked -> correction requested -> authorized -> corrected marks
-> moderated -> approved -> locked again. The spec example (72 -> 76) exceeds the dataset's maximum marks (<= 50), so the same
+4 correction is shown on an EndTerm record (max 50): 42.0 -> 46.0.
Outputs: experiments/results/provenance.{json,csv}, experiments/figures/Fig_Provenance.png"""
import csv, datetime, json, pathlib, sys
import httpx
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common import ExperimentEnv
from app.hashing import marks_hash, record_key

ROOT = HERE.parent.parent
ACTION_NAMES = {0: "IMPORT", 1: "CREATE", 2: "UPDATE_MARKS", 3: "SUBMIT", 4: "MODERATE", 5: "APPROVE", 6: "REJECT", 7: "LOCK",
                8: "REQUEST_CORRECTION", 9: "AUTHORIZE_CORRECTION", 10: "APPLY_CORRECTION"}
STATUS_NAMES = {1: "Entered", 2: "Submitted", 3: "Moderated", 4: "Approved", 5: "Locked", 6: "CorrectionRequested", 7: "CorrectionAuthorized"}
LANE = {"fac": 2, "moderator1": 1, "admin1": 0}

def main():
    import psycopg2
    p = psycopg2.connect(); c = p.cursor()
    c.execute("SELECT m.record_id, c.faculty_id FROM marks_a m JOIN courses c USING(course_id) WHERE m.assessment_id='EndTerm' AND m.status='Entered' "
              "AND c.faculty_id='FAC01' ORDER BY m.record_id LIMIT 1")
    rid, fac = c.fetchone(); p.close()
    with ExperimentEnv(anchor_records=[rid]) as env:
        f = env.token(fac.lower()); m = env.token("moderator1"); a = env.token("admin1")
        act = lambda h, action, **b: httpx.post(f"{env.base}/api/b/records/{rid}/actions/{action}", json=b, headers=h, timeout=120)
        steps = [(f, "update_marks", {"marks": "42.0"}), (f, "submit", {}), (m, "moderate", {}), (m, "approve", {}), (a, "lock", {}),
                 (f, "request_correction", {"reason": "re-evaluation of answer sheet"}), (a, "authorize_correction", {}),
                 (f, "apply_correction", {"marks": "46.0"}), (m, "moderate", {}), (m, "approve", {}), (a, "lock", {})]
        for h, action, body in steps:
            r = act(h, action, **body); assert r.status_code == 200, (action, r.text)
        ver = httpx.get(f"{env.base}/api/b/records/{rid}/verify", headers=m, timeout=60).json()
        chist = httpx.get(f"{env.base}/api/b/records/{rid}/chain-history", headers=m, timeout=60).json()
        cur = env.db.cursor()
        cur.execute("SELECT version_no, action, marks_obtained, status, actor FROM record_versions_b WHERE record_id=%s ORDER BY version_no", (rid,))
        dbv = {r[0]: r for r in cur.fetchall()}
        cur.execute("SELECT version_no, tx_hash, block_number FROM chain_anchor WHERE record_id=%s", (rid,)); anch = {r[0]: r for r in cur.fetchall()}
        pepper = env.env["PSEUDONYM_PEPPER"]
        addr_name = {a_.address.lower(): n for n, a_ in env.accts.items()}
        rows = []
        for e in chist:
            v = e["version_no"]; d = dbv[v]
            # on-chain data only holds hashes: recompute the marks hash from the DB marks and compare with the chain
            marks_ok = marks_hash(pepper, rid, d[2]) == e["marks_hash"]
            rows.append({"version": v, "action": ACTION_NAMES[e["action"]], "status": STATUS_NAMES[e["status"]], "marks": float(d[2]),
                         "marks_hash_matches_chain": marks_ok, "prev_hash": e["prev_hash"], "current_hash": e["curr_hash"],
                         "actor_signer": addr_name.get(e["actor"].lower(), e["actor"]), "actor_address": e["actor"], "app_user": d[4],
                         "block_timestamp_utc": datetime.datetime.fromtimestamp(e["timestamp"], datetime.timezone.utc).isoformat(timespec="seconds"),
                         "tx_hash": anch[v][1], "block_number": anch[v][2]})
    # checks
    assert ver["result"] == "MATCH" and len(rows) == 12
    assert all(r["marks_hash_matches_chain"] for r in rows)
    assert rows[0]["prev_hash"] == "0" * 64 and all(rows[i]["prev_hash"] == rows[i - 1]["current_hash"] for i in range(1, 12))
    assert len({r["tx_hash"] for r in rows}) == 12 and rows[-1]["status"] == "Locked"
    summary = {"record_id": rid, "imported_marks": rows[0]["marks"], "original_marks_before_correction": rows[5]["marks"], "corrected_marks": rows[-1]["marks"], "final_status": rows[-1]["status"], "events_on_chain": len(rows),
               "verification": ver["result"], "note": "Spec example 72->76 exceeds dataset max marks (<=50); same +4 correction shown with 42->46.", "events": rows}
    out = ROOT / "experiments/results"
    (out / "provenance.json").write_text(json.dumps(summary, indent=2) + "\n")
    with open(out / "provenance.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    draw(rows, rid)
    print(json.dumps({k: v for k, v in summary.items() if k != "events"}, indent=2))

def draw(rows, rid):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
    n = len(rows)
    fig = plt.figure(figsize=(22, 8.5))
    ax = fig.add_axes([0.04, 0.46, 0.94, 0.48]); ax.set_xlim(-0.6, n - 0.4); ax.set_ylim(-0.7, 2.7); ax.axis("off")
    for lane, name in ((2, "Faculty"), (1, "Moderator"), (0, "Exam Admin")):
        ax.axhline(lane, color="#cccccc", lw=0.8, zorder=0); ax.text(-0.58, lane + 0.33, name, fontsize=11, fontweight="bold", color="#555")
    pos = []
    for i, r in enumerate(rows):
        lane = 2 if r["actor_signer"].startswith("fac") else 1 if r["actor_signer"].startswith("moderator") else 0
        pos.append((i, lane))
        col = "#f8d7da" if "CORRECTION" in r["action"] or r["status"].startswith("Correction") else "#d4edda" if r["status"] == "Locked" else "#dbe9f6"
        ax.add_patch(FancyBboxPatch((i - 0.40, lane - 0.26), 0.80, 0.52, boxstyle="round,pad=0.02", fc=col, ec="#333", lw=1, zorder=2))
        ax.text(i, lane + 0.06, f"v{r['version']} {r['action'].replace('_', ' ').title()}", ha="center", va="center", fontsize=7.6, zorder=3)
        ax.text(i, lane - 0.12, f"marks {r['marks']:.1f}", ha="center", va="center", fontsize=8, color="#222", zorder=3)
    for i in range(1, n):
        ax.annotate("", xy=(pos[i][0] - 0.40, pos[i][1]), xytext=(pos[i - 1][0] + 0.40, pos[i - 1][1]),
                    arrowprops=dict(arrowstyle="-|>", color="#444", lw=1.1, shrinkA=0, shrinkB=0), zorder=1)
    ax.text(n / 2 - 0.5, 2.62, f"Marks provenance of record {rid}: imported {rows[0]['marks']:.1f}, entered 42.0 → locked → correction requested → 46.0 → moderated → approved → locked again "
            f"(arrow = prevHash link to the previous version of the SAME record)", ha="center", fontsize=12, fontweight="bold")
    cols = [f"v{r['version']}" for r in rows]
    cell = [["Action"] + [r["action"].replace("_", " ").title() for r in rows], ["Status"] + [r["status"] for r in rows],
            ["Marks"] + [f"{r['marks']:.1f}" for r in rows], ["Previous hash"] + [r["prev_hash"][:8] + "…" for r in rows],
            ["Current hash"] + [r["current_hash"][:8] + "…" for r in rows], ["Actor (signer)"] + [r["actor_signer"] for r in rows],
            ["Block time (UTC)"] + [r["block_timestamp_utc"][11:19] for r in rows], ["Besu tx id"] + [r["tx_hash"][:10] + "…" for r in rows]]
    tax = fig.add_axes([0.01, 0.02, 0.98, 0.40]); tax.axis("off")
    t = tax.table(cellText=cell, colLabels=["Field"] + cols, loc="center", cellLoc="center"); t.auto_set_font_size(False); t.set_fontsize(7.5); t.scale(1, 1.9)
    for (ri, ci), c_ in t.get_celld().items():
        if ri == 0: c_.set_facecolor("#e8e8e8"); c_.set_text_props(fontweight="bold")
        if ci == 0: c_.set_text_props(fontweight="bold"); c_.set_width(0.085)
    fig.savefig(ROOT / "experiments/figures/Fig_Provenance.png", dpi=300, bbox_inches="tight"); plt.close(fig)

if __name__ == "__main__":
    main()
