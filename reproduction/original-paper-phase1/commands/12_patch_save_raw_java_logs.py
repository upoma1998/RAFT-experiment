from pathlib import Path

p = Path("original_paper_phase1_runner.py")
s = p.read_text()

needle = '''            tests = parse_junit_blob(r.stdout)
'''

insert = '''            # Save the complete raw output of every execution.
            # This preserves evidence even when JUnit parsing succeeds.
            raw_dir = (
                RESULTS_ROOT
                / "java"
                / "raw-logs"
                / project_key
                / cfg_name
            )
            raw_dir.mkdir(parents=True, exist_ok=True)

            (raw_dir / f"run_{run_idx:03d}.stdout.log").write_text(
                r.stdout or "",
                errors="replace"
            )

            (raw_dir / f"run_{run_idx:03d}.stderr.log").write_text(
                r.stderr or "",
                errors="replace"
            )

            tests = parse_junit_blob(r.stdout)
'''

if "raw-logs" in s:
    raise SystemExit("Raw-log patch already appears to be installed.")

if needle not in s:
    raise SystemExit("Could not find JUnit parsing location.")

s = s.replace(needle, insert, 1)
p.write_text(s)

print("Patched runner to preserve stdout/stderr for every Java run.")
