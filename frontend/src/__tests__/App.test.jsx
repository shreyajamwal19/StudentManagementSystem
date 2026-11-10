import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "../App.jsx";

const REC = { record_id: "REC000001", student_id: "ST0001", course_id: "CS101", assessment_id: "Quiz1", marks_obtained: 15, max_marks: 20, status: "Locked", version_no: 1 };
const routes = {
  "POST /auth/login": () => ({ access_token: "t", role: "EXAM_ADMIN" }),
  "GET /api/overview": () => ({ status_a: { Locked: 3 }, status_b: { Locked: 3 }, records_anchored: 3, demo_mode: true, chain: { block_number: 9, chain_id: 20260, contract: "0xabc" } }),
  "GET /api/b/records": () => [REC],
  "GET /api/b/records/REC000001": () => REC,
  "GET /api/b/records/REC000001/chain-history": () => [{ version_no: 1, action: 0, db_action: "IMPORT", actor: "0x1234567890abcdef", timestamp: 1700000000, block_number: 7, tx_hash: "0xdeadbeefdeadbeef", prev_hash: "0".repeat(64), curr_hash: "a".repeat(64) }],
  "GET /api/b/records/REC000001/verify": () => ({ result: "INTEGRITY_MISMATCH", db_version: 1, chain_versions: 1, history_consistent: true, mismatched_versions: [], db_hash: "1", chain_hash: "2", verify_ms: 5 }),
};
beforeEach(() => {
  global.fetch = vi.fn(async (url, opts = {}) => {
    const key = `${opts.method || "GET"} ${url.split("?")[0]}`;
    const h = routes[key];
    if (!h) return { ok: false, status: 404, json: async () => ({ detail: `no route ${key}` }) };
    return { ok: true, status: 200, json: async () => h() };
  });
});

test("login, search, select, history and mismatch display", async () => {
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/username/i), { target: { value: "admin1" } });
  fireEvent.change(screen.getByPlaceholderText("password"), { target: { value: "x" } });
  fireEvent.click(screen.getByText("Sign in", { selector: "button" }));
  await screen.findByText(/Blockchain \(Hyperledger Besu/);
  expect(screen.getByText("20260")).toBeTruthy();
  fireEvent.click(screen.getByText("Student records"));
  fireEvent.click(screen.getByText("Search"));
  const row = await screen.findByText("REC000001");
  fireEvent.click(row);
  fireEvent.click(screen.getByText("Transaction history"));
  await screen.findByText("IMPORT");
  fireEvent.click(screen.getByText("Integrity verification"));
  fireEvent.click(await screen.findByText("Verify against blockchain"));
  await screen.findByText(/INTEGRITY MISMATCH DETECTED/);
  expect(screen.getByText(/Tamper & verify/)).toBeTruthy();   // demo tamper enabled for admin when DEMO_MODE
});

test("failed login shows an error and keeps the sign-in form", async () => {
  global.fetch = vi.fn(async () => ({ ok: false, status: 401, json: async () => ({ detail: "Invalid credentials" }) }));
  render(<App />);
  fireEvent.change(screen.getByPlaceholderText(/username/i), { target: { value: "x" } });
  fireEvent.change(screen.getByPlaceholderText("password"), { target: { value: "y" } });
  fireEvent.click(screen.getByText("Sign in", { selector: "button" }));
  await waitFor(() => expect(screen.getByText(/401: Invalid credentials/)).toBeTruthy());
});
