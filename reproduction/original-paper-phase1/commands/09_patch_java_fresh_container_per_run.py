from pathlib import Path

p = Path("original_paper_phase1_runner.py")
s = p.read_text()

start = s.index("def run_java(")
end = s.index("# ---------------- Python (flapy) ----------------", start)

new_function = r'''def run_java(image, project_key, configs, runs, writer, deadline=None, run_offset=0):
    testbody, shell = java_project_info(image)
    log(f"  java cmd ({shell}): {testbody[:160]}...")

    for cfg_name in configs:
        if deadline and time.time() > deadline:
            log(f"  [{project_key}] deadline reached, stopping before config {cfg_name}")
            writer.write_error(
                cfg_name, "*", "DEADLINE_STOP",
                "job wall-clock budget exceeded"
            )
            break

        cfg = CONFIGS[cfg_name]
        flags = docker_flags(cfg)
        run_image = image
        net_prelude = ""

        if cfg["net"] is not None:
            run_image = ensure_tc_image(image)
            flags = flags + ["--cap-add", "NET_ADMIN"]
            down, up = cfg["net"]
            net_prelude = NET_PRELUDE.format(up=up, down=down)

        successful_parses = 0

        for local_idx in range(1, runs + 1):
            run_idx = local_idx + run_offset

            if deadline and time.time() > deadline:
                writer.write_error(
                    cfg_name, run_idx, "DEADLINE_STOP",
                    "job wall-clock budget exceeded"
                )
                break

            # IMPORTANT:
            # Each repetition gets a NEW Docker container.
            # This prevents filesystem/process state from one repetition
            # affecting the next repetition.
            inner = f"""
{net_prelude}
echo "===RUN_START {run_idx}==="
{testbody}
mvn_exit=$?
echo "===MVN_EXIT $mvn_exit==="
find . -path '*/target/surefire-reports/TEST-*.xml' -exec cat {{}} \\; 2>/dev/null
echo "===RUN_END {run_idx}==="
exit 0
"""

            try:
                r = sh(
                    ["docker", "run", "--rm", *flags,
                     run_image, shell, "-c", inner],
                    timeout=RUN_TIMEOUT_SEC,
                )
            except subprocess.TimeoutExpired as e:
                writer.write_error(
                    cfg_name, run_idx, "TIMEOUT", str(e)[:2000]
                )
                log(
                    f"  [{project_key}] config {cfg_name} "
                    f"run {run_idx}: TIMEOUT"
                )
                continue

            tests = parse_junit_blob(r.stdout)

            exit_match = re.search(
                r"===MVN_EXIT\s+(\d+)===", r.stdout
            )
            mvn_exit = (
                exit_match.group(1)
                if exit_match
                else "UNKNOWN"
            )

            if not tests:
                writer.write_error(
                    cfg_name,
                    run_idx,
                    f"NO_TESTS_PARSED_MVN_EXIT_{mvn_exit}",
                    r.stdout[-5000:]
                    + "\n---STDERR---\n"
                    + r.stderr[-3000:]
                )

                log(
                    f"  [{project_key}] config {cfg_name} "
                    f"run {run_idx}: no tests parsed "
                    f"(mvn exit={mvn_exit})"
                )
                continue

            successful_parses += 1

            for classname, name, status, message in tests:
                writer.write_test(
                    cfg_name,
                    run_idx,
                    classname,
                    name,
                    status,
                    message
                )

                if status in ("failure", "error"):
                    writer.write_error(
                        cfg_name,
                        run_idx,
                        status.upper(),
                        f"{classname}.{name}: {message}"
                    )

            writer.flush()

            log(
                f"  [{project_key}] config {cfg_name} "
                f"run {run_idx}: parsed {len(tests)} tests "
                f"(mvn exit={mvn_exit})"
            )

        writer.flush()

        log(
            f"  [{project_key}] config {cfg_name}: "
            f"{successful_parses}/{runs} runs produced "
            f"parseable test results"
        )

'''

s = s[:start] + new_function + s[end:]

p.write_text(s)

print("Patched Java runner to use one fresh Docker container per repetition.")
