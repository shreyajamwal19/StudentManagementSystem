"""Record hardware/software environment for reproducibility -> dict (also usable as a script)."""
import hashlib, json, os, pathlib, platform, subprocess, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]

def _run(cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception: return None

def collect(extra=None):
    mem_kb = None
    try: mem_kb = int([l for l in open("/proc/meminfo") if l.startswith("MemTotal")][0].split()[1])
    except Exception: pass
    cpu = None
    try: cpu = [l.split(":")[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")][0]
    except Exception: cpu = platform.processor() or None
    ds = ROOT / "data/synthetic_student_marks_50000_1.csv"
    env = {"os": platform.platform(), "cpu_model": cpu, "cpu_count": os.cpu_count(), "ram_mb": mem_kb // 1024 if mem_kb else None,
           "python": sys.version.split()[0], "postgres": (_run(["psql", "-Atc", "show server_version"]) or None),
           "java": (_run(["java", "-version"]) or "")[:0] or None,
           "dataset_sha256": hashlib.sha256(ds.read_bytes()).hexdigest() if ds.exists() else None,
           "besu_config": json.loads((ROOT / "besu-network/qbftConfigFile.json").read_text())["genesis"]["config"]}
    for pkg in ("fastapi", "uvicorn", "web3", "psycopg2", "httpx", "pandas", "matplotlib"):
        try:
            import importlib.metadata as m; env.setdefault("packages", {})[pkg] = m.version(pkg.replace("psycopg2", "psycopg2-binary"))
        except Exception: pass
    env.update(extra or {})
    return env

if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
