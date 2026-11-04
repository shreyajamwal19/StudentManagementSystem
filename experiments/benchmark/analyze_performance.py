#!/usr/bin/env python3
"""Aggregate raw benchmark CSVs -> performance summary CSV and Fig_Performance.png (300 DPI, std-dev error bars).
Usage: analyze_performance.py [--tag benchmark]. Error bars = standard deviation of the per-run mean latency across runs."""
import argparse, pathlib
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
ROOT = pathlib.Path(__file__).resolve().parents[2]
ap = argparse.ArgumentParser(); ap.add_argument("--tag", default="benchmark"); a = ap.parse_args()
RAW = ROOT / "experiments/results/raw"
raw = pd.read_csv(RAW / f"{a.tag}_raw.csv"); runs = pd.read_csv(RAW / f"{a.tag}_runs.csv")
ok = raw[raw.http_status == 200]

rows = []
for (sysx, w), g in runs.groupby(["system", "workload"]):
    r = ok[(ok.system == sysx) & (ok.workload == w)]
    rows.append({"system": sysx, "workload": w, "runs": len(g),
                 "avg_latency_ms": g.mean_e2e_ms.mean(), "std_latency_across_runs_ms": g.mean_e2e_ms.std(ddof=1) if len(g) > 1 else 0.0,
                 "mean_within_run_std_ms": g.std_e2e_ms.mean(), "p95_latency_ms": r.e2e_ms.quantile(0.95),
                 "throughput_tps": g.tps.mean(), "std_tps_across_runs": g.tps.std(ddof=1) if len(g) > 1 else 0.0,
                 "success_rate_pct": 100.0 * g.successes.sum() / g.transactions.sum(),
                 "db_ms": r.db_ms.mean(), "chain_verify_ms": r.verify_ms.mean(), "chain_submit_ms": r.submit_ms.mean(),
                 "chain_confirm_ms": r.confirm_ms.mean(), "server_total_ms": r.server_total_ms.mean()})
summ = pd.DataFrame(rows).sort_values(["system", "workload"]).round(3)
suffix = "" if a.tag == "benchmark" else f"_{a.tag}"
(ROOT / f"experiments/results/performance_summary{suffix}.csv").write_text(summ.to_csv(index=False))
print(summ.to_string(index=False))

fig_dir = ROOT / "experiments/figures"; fig_dir.mkdir(exist_ok=True)
fig, ax = plt.subplots(figsize=(7, 4.6))
for sysx, label, color, marker in (("A", "Conventional System", "#1f77b4", "o"), ("B", "Proposed Blockchain System", "#d62728", "s")):
    s = summ[summ.system == sysx]
    ax.errorbar(s.workload, s.avg_latency_ms, yerr=s.std_latency_across_runs_ms, label=label, color=color, marker=marker, capsize=4, linewidth=1.8)
ax.set_xlabel("Transaction load (number of transactions)"); ax.set_ylabel("Average end-to-end latency (ms)")
ax.set_title("Transaction Load vs Average Latency"); ax.grid(alpha=0.3); ax.legend(); ax.set_yscale("log" if summ.avg_latency_ms.max() / max(summ.avg_latency_ms.min(), 1e-9) > 50 else "linear")
fig.tight_layout(); fig.savefig(fig_dir / f"Fig_Performance{suffix}.png", dpi=300); plt.close(fig)

b = summ[summ.system == "B"]
if len(b):
    fig, ax = plt.subplots(figsize=(7, 4.6)); x = range(len(b)); bottom = [0] * len(b)
    for col, lab in (("db_ms", "Database processing"), ("chain_verify_ms", "Blockchain integrity read"), ("chain_confirm_ms", "Blockchain submit + confirmation")):
        vals = b[col].fillna(0).tolist(); ax.bar(list(x), vals, bottom=bottom, label=lab); bottom = [p + v for p, v in zip(bottom, vals)]
    ax.set_xticks(list(x)); ax.set_xticklabels(b.workload.astype(str)); ax.set_xlabel("Transaction load"); ax.set_ylabel("Mean server-side time per request (ms)")
    ax.set_title("System B latency breakdown"); ax.legend(); fig.tight_layout(); fig.savefig(fig_dir / f"Fig_B_Breakdown{suffix}.png", dpi=300); plt.close(fig)
print("saved figures to", fig_dir)
