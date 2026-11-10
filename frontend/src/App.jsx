import React, { useEffect, useState } from "react";
import { api, login, setToken } from "./api.js";

const short = (h) => (h ? `${h.slice(0, 10)}…` : "");
const ROLE_ACTIONS = {
  FACULTY: [["update_marks", "Update marks", "marks"], ["submit", "Submit for moderation"], ["request_correction", "Request correction", "reason"], ["apply_correction", "Apply authorized correction", "marks"]],
  MODERATOR: [["moderate", "Moderate"], ["approve", "Approve"], ["reject", "Reject", "reason"]],
  EXAM_ADMIN: [["lock", "Lock"], ["authorize_correction", "Authorize correction"]],
  STUDENT: [],
};

const Card = ({ title, children }) => (
  <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
    {title && <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>}
    {children}
  </section>
);
const Btn = ({ className = "", ...p }) => (
  <button className={`rounded bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 ${className}`} {...p} />
);
const Input = (p) => <input className="rounded border border-slate-300 px-2 py-1.5 text-sm" {...p} />;
const Err = ({ e }) => (e ? <p className="mt-2 rounded bg-red-50 p-2 text-sm text-red-700">{e}</p> : null);

function Login({ onLogin }) {
  const [u, setU] = useState(""), [p, setP] = useState(""), [err, setErr] = useState("");
  const go = async () => { try { setErr(""); const r = await login(u, p); onLogin({ username: u, role: r.role }); } catch (e) { setErr(String(e.message)); } };
  return (
    <div className="mx-auto mt-24 max-w-sm">
      <Card title="Sign in">
        <div className="flex flex-col gap-2">
          <Input placeholder="username (e.g. fac01, moderator1, admin1)" value={u} onChange={(e) => setU(e.target.value)} />
          <Input type="password" placeholder="password" value={p} onChange={(e) => setP(e.target.value)} onKeyDown={(e) => e.key === "Enter" && go()} />
          <Btn onClick={go}>Sign in</Btn>
          <Err e={err} />
          <p className="text-xs text-slate-500">Research prototype. Roles are enforced by the backend and the smart contract, not by this page.</p>
        </div>
      </Card>
    </div>
  );
}

function Dashboard() {
  const [o, setO] = useState(null), [err, setErr] = useState("");
  useEffect(() => { api("/api/overview").then(setO).catch((e) => setErr(String(e.message))); }, []);
  if (err) return <Err e={err} />;
  if (!o) return <p>Loading…</p>;
  const statuses = [...new Set([...Object.keys(o.status_a), ...Object.keys(o.status_b)])];
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title="Blockchain (Hyperledger Besu, QBFT)">
        {o.chain ? (<dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-sm"><dt>Chain ID</dt><dd>{o.chain.chain_id}</dd><dt>Latest block</dt><dd>{o.chain.block_number}</dd>
          <dt>Contract</dt><dd className="break-all font-mono text-xs">{o.chain.contract}</dd><dt>Records anchored</dt><dd>{o.records_anchored}</dd></dl>) : <p className="text-sm text-amber-700">Blockchain not reachable.</p>}
        {o.demo_mode && <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-800">DEMO_MODE is on: the tamper simulation is enabled.</p>}
      </Card>
      <Card title="Records by status (System A vs System B tables)">
        <table className="w-full text-sm"><thead><tr className="text-left text-slate-500"><th>Status</th><th>A</th><th>B</th></tr></thead>
          <tbody>{statuses.map((s) => (<tr key={s} className="border-t"><td>{s}</td><td>{o.status_a[s] ?? 0}</td><td>{o.status_b[s] ?? 0}</td></tr>))}</tbody></table>
      </Card>
    </div>
  );
}

function Records({ system, selected, onSelect }) {
  const [q, setQ] = useState({ student_id: "", course_id: "", status: "" }), [rows, setRows] = useState([]), [err, setErr] = useState("");
  const search = async () => {
    try { setErr(""); const p = new URLSearchParams({ limit: "50", ...Object.fromEntries(Object.entries(q).filter(([, v]) => v)) });
      setRows(await api(`/api/${system}/records?${p}`)); } catch (e) { setErr(String(e.message)); }
  };
  return (
    <Card title={`Student academic records (System ${system.toUpperCase()})`}>
      <div className="mb-3 flex flex-wrap gap-2">
        <Input placeholder="Student ID (ST0001)" value={q.student_id} onChange={(e) => setQ({ ...q, student_id: e.target.value })} />
        <Input placeholder="Course (CS101)" value={q.course_id} onChange={(e) => setQ({ ...q, course_id: e.target.value })} />
        <Input placeholder="Status (Locked)" value={q.status} onChange={(e) => setQ({ ...q, status: e.target.value })} />
        <Btn onClick={search}>Search</Btn>
      </div>
      <Err e={err} />
      <div className="overflow-x-auto"><table className="w-full text-sm">
        <thead><tr className="text-left text-slate-500"><th>Record</th><th>Student</th><th>Course</th><th>Assessment</th><th>Marks</th><th>Max</th><th>Status</th><th>Ver.</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.record_id} onClick={() => onSelect(r.record_id)} className={`cursor-pointer border-t hover:bg-indigo-50 ${selected === r.record_id ? "bg-indigo-100" : ""}`}>
            <td className="font-mono text-xs">{r.record_id}</td><td>{r.student_id}</td><td>{r.course_id}</td><td>{r.assessment_id}</td><td>{r.marks_obtained}</td><td>{r.max_marks}</td><td>{r.status}</td><td>{r.version_no}</td></tr>))}</tbody>
      </table></div>
      {!rows.length && <p className="text-sm text-slate-500">No results yet. Faculty only see their own courses; students only see their own locked records.</p>}
    </Card>
  );
}

function Workflow({ system, role, rid }) {
  const [marks, setMarks] = useState(""), [reason, setReason] = useState(""), [res, setRes] = useState(null), [err, setErr] = useState(""), [rec, setRec] = useState(null);
  const load = () => rid && api(`/api/${system}/records/${rid}`).then(setRec).catch((e) => setErr(String(e.message)));
  useEffect(() => { setRes(null); setErr(""); setRec(null); load(); }, [rid, system]);
  if (!rid) return <Card title="Marks entry and correction"><p className="text-sm text-slate-500">Select a record in “Records” first.</p></Card>;
  const run = async (action) => {
    try { setErr(""); setRes(await api(`/api/${system}/records/${rid}/actions/${action}`, { method: "POST", body: { marks: marks || undefined, reason: reason || undefined } })); load(); }
    catch (e) { setErr(String(e.message)); setRes(null); }
  };
  return (
    <Card title={`Marks workflow — ${rid} (System ${system.toUpperCase()})`}>
      {rec && <p className="mb-3 text-sm">Student {rec.student_id} · {rec.course_id} {rec.assessment_id} · marks <b>{rec.marks_obtained}</b>/{rec.max_marks} · status <b>{rec.status}</b> · version {rec.version_no}</p>}
      <div className="mb-3 flex flex-wrap gap-2">
        <Input placeholder="marks (0.1 steps)" value={marks} onChange={(e) => setMarks(e.target.value)} />
        <Input placeholder="reason (for reject / correction)" value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      <div className="flex flex-wrap gap-2">{(ROLE_ACTIONS[role] || []).map(([a, label]) => <Btn key={a} onClick={() => run(a)}>{label}</Btn>)}</div>
      <p className="mt-2 text-xs text-slate-500">Buttons only reflect your role; the server and (System B) the smart contract decide what is allowed. Try an action that should be refused.</p>
      <Err e={err} />
      {res && <div className="mt-3 rounded bg-emerald-50 p-3 text-sm"><p>OK — status <b>{res.status}</b>, marks {res.marks_obtained}, version {res.version_no}</p>
        {res.tx_hash && <p className="break-all font-mono text-xs">tx {res.tx_hash} · block {res.block_number}</p>}
        <p className="mt-1 text-xs text-slate-600">Timings (ms): total {res.timings_ms.total_ms} · database {res.timings_ms.db_ms} · chain read {res.timings_ms.verify_ms} · submit {res.timings_ms.submit_ms} · confirm {res.timings_ms.confirm_ms}</p></div>}
    </Card>
  );
}

function History({ system, rid }) {
  const [rows, setRows] = useState(null), [err, setErr] = useState("");
  useEffect(() => { setRows(null); setErr(""); if (!rid) return;
    api(system === "b" ? `/api/b/records/${rid}/chain-history` : `/api/a/records/${rid}/history`).then(setRows).catch((e) => setErr(String(e.message))); }, [rid, system]);
  if (!rid) return <Card title="History"><p className="text-sm text-slate-500">Select a record first.</p></Card>;
  return (
    <Card title={system === "b" ? `Blockchain transaction history — ${rid}` : `Database version history (System A, no hashes) — ${rid}`}>
      <Err e={err} />
      <div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr className="text-left text-slate-500">
        <th>v</th><th>Action</th>{system === "b" ? <><th>Actor (address)</th><th>Block time</th><th>Block</th><th>Tx hash</th><th>Prev hash</th><th>Current hash</th></> : <><th>Marks</th><th>Status</th><th>Actor</th><th>Time</th></>}</tr></thead>
        <tbody>{(rows || []).map((r) => system === "b" ? (
          <tr key={r.version_no} className="border-t"><td>{r.version_no}</td><td>{r.db_action ?? r.action}</td><td className="font-mono">{short(r.actor)}</td>
            <td>{new Date(r.timestamp * 1000).toISOString().replace("T", " ").slice(0, 19)}</td><td>{r.block_number}</td><td className="font-mono" title={r.tx_hash}>{short(r.tx_hash)}</td>
            <td className="font-mono" title={r.prev_hash}>{short(r.prev_hash)}</td><td className="font-mono" title={r.curr_hash}>{short(r.curr_hash)}</td></tr>
        ) : (<tr key={r.version_no} className="border-t"><td>{r.version_no}</td><td>{r.action}</td><td>{r.marks_obtained}</td><td>{r.status}</td><td>{r.actor}</td><td>{String(r.created_at).slice(0, 19)}</td></tr>))}</tbody></table></div>
    </Card>
  );
}

function Verify({ rid, role, demo }) {
  const [v, setV] = useState(null), [err, setErr] = useState(""), [t, setT] = useState(""), [msg, setMsg] = useState("");
  useEffect(() => { setV(null); setErr(""); setMsg(""); }, [rid]);
  if (!rid) return <Card title="Integrity verification"><p className="text-sm text-slate-500">Select a record first.</p></Card>;
  const check = async () => { try { setErr(""); setV(await api(`/api/b/records/${rid}/verify`)); } catch (e) { setErr(String(e.message)); } };
  const tamper = async () => { try { setErr(""); const r = await api("/api/b/demo/tamper", { method: "POST", body: { record_id: rid, marks: t } }); setMsg(`${r.marks_before} → ${r.marks_after}. ${r.note}`); await check(); } catch (e) { setErr(String(e.message)); } };
  const ok = v?.result === "MATCH";
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card title={`Integrity verification — ${rid}`}>
        <Btn onClick={check}>Verify against blockchain</Btn><Err e={err} />
        {v && <div className={`mt-3 rounded p-3 text-sm ${ok ? "bg-emerald-50 text-emerald-900" : "bg-red-50 text-red-900"}`}>
          <p className="text-base font-bold">{ok ? "MATCH — record equals the anchored version" : "INTEGRITY MISMATCH DETECTED"}</p>
          <p>DB version {v.db_version} · chain versions {v.chain_versions} · history consistent: {String(v.history_consistent)}{v.mismatched_versions.length ? ` (bad versions: ${v.mismatched_versions.join(", ")})` : ""}</p>
          <p className="break-all font-mono text-xs">DB hash {v.db_hash}</p><p className="break-all font-mono text-xs">Chain hash {v.chain_hash}</p><p className="text-xs">verification took {v.verify_ms} ms</p></div>}
        <p className="mt-3 text-xs text-slate-500">Verification detects alteration; it does not prevent someone with database access from editing the data.</p>
      </Card>
      <Card title="Demonstrate database tampering (demo only)">
        {demo && role === "EXAM_ADMIN" ? (<>
          <p className="mb-2 text-sm">Simulates an insider editing the database directly: no audit entry, no version row, no blockchain transaction. Then verification runs.</p>
          <div className="flex gap-2"><Input placeholder="new marks (within max)" value={t} onChange={(e) => setT(e.target.value)} /><Btn className="bg-red-600 hover:bg-red-700" onClick={tamper}>Tamper &amp; verify</Btn></div>
          {msg && <p className="mt-2 text-xs text-slate-600">{msg}</p>}</>) :
          <p className="text-sm text-slate-500">Disabled. Start the backend with DEMO_MODE=1 and sign in as admin1 to enable the tamper simulation.</p>}
      </Card>
    </div>
  );
}

function Results() {
  const [sec, setSec] = useState(null), [perf, setPerf] = useState(null), [err, setErr] = useState("");
  useEffect(() => { api("/api/experiments/security").then(setSec).catch((e) => setErr(String(e.message))); api("/api/experiments/performance").then(setPerf).catch(() => {}); }, []);
  const tests = sec ? [...new Set(sec.results.map((r) => r.test))].sort() : [];
  const get = (t, s) => sec.results.find((r) => r.test === t && r.system === s);
  return (
    <div className="flex flex-col gap-4">
      <Err e={err} />
      {sec && <Card title="Security and integrity experiments (T1–T6)"><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-slate-500"><th>Test</th><th>Description</th><th>System A</th><th>System B</th></tr></thead>
        <tbody>{tests.map((t) => (<tr key={t} className="border-t align-top"><td className="font-semibold">{t}</td><td>{get(t, "A").description}</td>
          <td title={get(t, "A").evidence}>{get(t, "A").outcome}</td><td title={get(t, "B").evidence}>{get(t, "B").outcome}</td></tr>))}</tbody></table></div>
        <p className="mt-2 text-xs text-slate-500">Hover an outcome for the supporting evidence. Run at {sec.run_at_utc}.</p></Card>}
      {perf && <Card title="Performance summary"><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-slate-500"><th>System</th><th>Load</th><th>Avg latency (ms)</th><th>Std (ms)</th><th>TPS</th><th>Success %</th></tr></thead>
        <tbody>{perf.rows.map((r, i) => (<tr key={i} className="border-t"><td>{r.system}</td><td>{r.workload}</td><td>{Number(r.avg_latency_ms).toFixed(1)}</td><td>{Number(r.std_latency_across_runs_ms).toFixed(1)}</td><td>{Number(r.throughput_tps).toFixed(1)}</td><td>{Number(r.success_rate_pct).toFixed(1)}</td></tr>))}</tbody></table></div>
        {perf.smoke_test_only && <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-800">Smoke test only (tiny run on a development machine). Not final results.</p>}</Card>}
    </div>
  );
}

const TABS = [["dash", "Dashboard"], ["records", "Student records"], ["work", "Marks entry & correction"], ["hist", "Transaction history"], ["verify", "Integrity verification"], ["results", "Experiment results"]];

export default function App() {
  const [user, setUser] = useState(null), [tab, setTab] = useState("dash"), [system, setSystem] = useState("b"), [rid, setRid] = useState(null), [demo, setDemo] = useState(false);
  useEffect(() => { if (user && user.role !== "STUDENT") api("/api/overview").then((o) => setDemo(o.demo_mode)).catch(() => {}); }, [user]);
  if (!user) return <Login onLogin={setUser} />;
  const tabs = user.role === "STUDENT" ? TABS.filter(([k]) => ["records", "hist"].includes(k)) : TABS;
  const t = tabs.some(([k]) => k === tab) ? tab : tabs[0][0];
  return (
    <div className="mx-auto max-w-6xl p-4">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-bold">Blockchain-Based Academic Records — Research Prototype</h1>
        <div className="flex items-center gap-3 text-sm">
          <label>System <select className="rounded border px-1 py-0.5" value={system} onChange={(e) => setSystem(e.target.value)}><option value="a">A (conventional)</option><option value="b">B (blockchain)</option></select></label>
          <span>{user.username} · {user.role}</span><button className="underline" onClick={() => { setToken(null); setUser(null); }}>Sign out</button>
        </div>
      </header>
      <nav className="mb-4 flex flex-wrap gap-1">{tabs.map(([k, l]) => (<button key={k} onClick={() => setTab(k)} className={`rounded px-3 py-1.5 text-sm ${t === k ? "bg-indigo-600 text-white" : "bg-white hover:bg-slate-100"}`}>{l}</button>))}</nav>
      {rid && <p className="mb-3 text-sm">Selected record: <span className="font-mono">{rid}</span></p>}
      {t === "dash" && <Dashboard />}
      {t === "records" && <Records system={system} selected={rid} onSelect={setRid} />}
      {t === "work" && <Workflow system={system} role={user.role} rid={rid} />}
      {t === "hist" && <History system={system} rid={rid} />}
      {t === "verify" && (system === "b" ? <Verify rid={rid} role={user.role} demo={demo} /> : <Card title="Integrity verification"><p className="text-sm">System A has no integrity verification mechanism. Switch to System B.</p></Card>)}
      {t === "results" && <Results />}
    </div>
  );
}
