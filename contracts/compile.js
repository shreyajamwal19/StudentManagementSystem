// Compiles AcademicRecords.sol with solc-js (EVM target: shanghai) -> build/AcademicRecords.json {abi, bytecode}
const solc = require("solc"), fs = require("fs"), path = require("path");
const src = fs.readFileSync(path.join(__dirname, "AcademicRecords.sol"), "utf8");
const input = { language: "Solidity", sources: { "AcademicRecords.sol": { content: src } },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "shanghai",
              outputSelection: { "*": { "*": ["abi", "evm.bytecode.object", "evm.deployedBytecode.object"] } } } };
const out = JSON.parse(solc.compile(JSON.stringify(input)));
const errs = (out.errors || []);
errs.forEach(e => console.error(e.formattedMessage));
if (errs.some(e => e.severity === "error")) process.exit(1);
const c = out.contracts["AcademicRecords.sol"].AcademicRecords;
fs.mkdirSync(path.join(__dirname, "build"), { recursive: true });
fs.writeFileSync(path.join(__dirname, "build/AcademicRecords.json"),
  JSON.stringify({ solc: solc.version(), abi: c.abi, bytecode: "0x" + c.evm.bytecode.object }, null, 1));
console.log("solc", solc.version(), "| deployed size bytes:", c.evm.deployedBytecode.object.length / 2, "(limit 24576)");
