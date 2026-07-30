#!/usr/bin/env python3
"""
Phase 1 reproduction runner for "The Effects of Computational Resources on Flaky Tests".
Runs each project's test suite RUNS_PER_CONFIG times under each of Table I's 16
throttling configurations, using the jonbell/raft Docker images.

Usage: python3 phase1_runner.py [--only java|python|js] [--project KEY] [--configs C1,C2,...] [--runs N]
"""
import argparse, csv, json, os, re, subprocess, sys, time, traceback
from pathlib import Path

ROOT = Path(__file__).parent
RESULTS_ROOT = ROOT / "phase1-results"
REGISTRY = json.load(open(ROOT / "phase1_registry.json"))

RUNS_PER_CONFIG_DEFAULT = 10
DOCKER_DEVICE = "/dev/sdd"
RUN_TIMEOUT_SEC = 25 * 60  # per docker invocation

# Table I configs: cpus (cores), mem (docker --memory string), disk (read_kbps,write_kbps), net (down_kbit,up_kbit)
CONFIGS = {
    "Baseline": dict(cpus=4,    mem="14g",  disk=None,       net=None),
    "C":        dict(cpus=0.1,  mem=None,   disk=None,       net=None),
    "M":        dict(cpus=None, mem="512m", disk=None,       net=None),
    "D":        dict(cpus=None, mem=None,   disk=(50, 100),  net=None),
    "N":        dict(cpus=None, mem=None,   disk=None,       net=(1500, 512)),
    "CM":       dict(cpus=0.1,  mem="512m", disk=None,       net=None),
    "CN":       dict(cpus=0.1,  mem=None,   disk=None,       net=(1500, 512)),
    "MN":       dict(cpus=None, mem="512m", disk=None,       net=(1500, 512)),
    "CD":       dict(cpus=0.1,  mem=None,   disk=(50, 100),  net=None),
    "MD":       dict(cpus=None, mem="512m", disk=(50, 100),  net=None),
    "DN":       dict(cpus=None, mem=None,   disk=(50, 100),  net=(1500, 512)),
    "CMN":      dict(cpus=0.1,  mem="512m", disk=None,       net=(1500, 512)),
    "CMD":      dict(cpus=0.1,  mem="512m", disk=(50, 100),  net=None),
    "CDN":      dict(cpus=0.1,  mem=None,   disk=(50, 100),  net=(1500, 512)),
    "MDN":      dict(cpus=None, mem="512m", disk=(50, 100),  net=(1500, 512)),
    "CMDN":     dict(cpus=0.1,  mem="512m", disk=(50, 100),  net=(1500, 512)),
}

TESTCASE_RE = re.compile(
    r'<testcase\b([^>]*?)(?:/>|>(.*?)</testcase>)', re.S)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
MSG_RE = re.compile(r'<(failure|error)[^>]*message="([^"]*)"', re.S)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(cmd, timeout=RUN_TIMEOUT_SEC, input_data=None):
    return subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True,
                           text=True, timeout=timeout, input=input_data)


def docker_flags(cfg):
    flags = []
    if cfg["cpus"] is not None:
        flags += ["--cpus", str(cfg["cpus"])]
    if cfg["mem"] is not None:
        flags += ["--memory", cfg["mem"], "--memory-swap", cfg["mem"]]
    if cfg["disk"] is not None:
        r, w = cfg["disk"]
        flags += ["--device-read-bps", f"{DOCKER_DEVICE}:{r}kb",
                  "--device-write-bps", f"{DOCKER_DEVICE}:{w}kb"]
    return flags


NET_PRELUDE = """
if command -v tc >/dev/null 2>&1; then
  tc qdisc add dev eth0 root tbf rate {up}kbit burst 32kbit latency 400ms 2>/dev/null
  tc qdisc add dev eth0 handle ffff: ingress 2>/dev/null
  tc filter add dev eth0 parent ffff: u32 match u32 0 0 police rate {down}kbit burst 10k drop flowid :1 2>/dev/null
  echo NET_THROTTLE_APPLIED
else
  echo NET_THROTTLE_UNAVAILABLE
fi
"""


def ensure_tc_image(image):
    """Build (once) and cache a derived image with iproute2 + NET_ADMIN-ready for tc."""
    derived = image.replace(":", "__") + "-tc"
    check = sh(["docker", "image", "inspect", derived], timeout=30)
    if check.returncode == 0:
        return derived
    log(f"  building tc-enabled derived image for {image} ...")
    r = sh(["docker", "run", "--name", f"tcbuild-{os.getpid()}", image,
            "bash", "-c",
            "(apt-get update -qq && apt-get install -y -qq iproute2) "
            "|| (apk add -q iproute2-tc) || true"],
           timeout=300)
    commit = sh(["docker", "commit", f"tcbuild-{os.getpid()}", derived], timeout=120)
    sh(["docker", "rm", "-f", f"tcbuild-{os.getpid()}"], timeout=60)
    if commit.returncode != 0:
        log(f"  WARNING: failed to build tc image for {image}: {commit.stderr[:300]}")
        return image  # fall back, network throttle will be skipped
    return derived


def parse_junit_blob(xml_blob):
    """Parse one or more concatenated JUnit-style XML docs into (classname,name,status,message) tuples."""
    out = []
    for m in TESTCASE_RE.finditer(xml_blob):
        attrs = dict(ATTR_RE.findall(m.group(1)))
        body = m.group(2) or ""
        name = attrs.get("name", "?")
        classname = attrs.get("classname", attrs.get("class", "?"))
        status, message = "pass", ""
        if "<failure" in body:
            status = "failure"
            mm = MSG_RE.search(body)
            message = mm.group(2) if mm else "failure"
        elif "<error" in body:
            status = "error"
            mm = MSG_RE.search(body)
            message = mm.group(2) if mm else "error"
        elif "<skipped" in body:
            status = "skipped"
        out.append((classname, name, status, message))
    return out


class ResultWriter:
    def __init__(self, lang, project_key):
        self.lang = lang
        self.project_key = project_key
        results_dir = RESULTS_ROOT / lang / "results"
        errors_dir = RESULTS_ROOT / lang / "errors"
        results_dir.mkdir(parents=True, exist_ok=True)
        errors_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = results_dir / f"{project_key}.csv"
        self.err_path = errors_dir / f"{project_key}.log"
        new = not self.csv_path.exists()
        self.csv_f = open(self.csv_path, "a", newline="")
        self.writer = csv.writer(self.csv_f)
        if new:
            self.writer.writerow(["project", "config", "run_index", "classname",
                                   "testname", "status", "message"])
        self.err_f = open(self.err_path, "a")

    def write_test(self, config, run_idx, classname, testname, status, message):
        self.writer.writerow([self.project_key, config, run_idx, classname, testname, status, message])

    def write_error(self, config, run_idx, err_type, detail):
        self.err_f.write(f"=== {self.project_key} | config={config} | run={run_idx} | {err_type} "
                          f"| {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n{detail}\n\n")
        self.err_f.flush()

    def flush(self):
        self.csv_f.flush()

    def close(self):
        self.csv_f.close()
        self.err_f.close()


# ---------------- Java ----------------

def java_project_info(image):
    """Extract the real test-invocation command from the image's build history.
    Handles both image generations: newer ones with a per-project mvn-test-command.sh
    (referenced indirectly), and older ones where the full mvn invocation is only
    ever baked into a 'zsh -c ...' build-history layer. Using history works for both,
    since the actual command that pre-cached the image's dependencies is always there.
    """
    r = sh(["docker", "history", "--no-trunc", "--format", "{{.CreatedBy}}", image], timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"docker history failed for {image}: {r.stderr[:300]}")
    line = None
    for l in r.stdout.splitlines():
        if re.search(r"\bmvn\b.*\btest\b", l):
            line = l
            break
    if not line:
        raise RuntimeError(f"no mvn test command found in docker history for {image}")
    cmd = re.sub(r"^/bin/sh -c\s+", "", line).strip()
    m = re.match(r"^zsh -c '(.*)'$", cmd, re.S)
    shell = "zsh"
    if m:
        body = m.group(1)
    else:
        body = cmd  # not zsh-wrapped; run as-is
        shell = "bash"
    # drop any trailing cleanup that would destroy results before we can read them
    body = re.sub(r";\s*rm\s+-rf?\s+\S*surefire-reports\S*\s*;?\s*$", ";", body.strip())
    return body, shell


def run_java(image, project_key, configs, runs, writer, deadline=None):
    testbody, shell = java_project_info(image)
    log(f"  java cmd ({shell}): {testbody[:160]}...")
    for cfg_name in configs:
        if deadline and time.time() > deadline:
            log(f"  [{project_key}] deadline reached, stopping before config {cfg_name}")
            writer.write_error(cfg_name, "*", "DEADLINE_STOP", "job wall-clock budget exceeded")
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
        inner = f"""
{net_prelude}
for i in $(seq 1 {runs}); do
  echo "===RUN_START $i==="
  {testbody}
  echo "===MVN_EXIT $?==="
  find . -path '*/target/surefire-reports/TEST-*.xml' -exec cat {{}} \\; 2>/dev/null
  find . -path '*/target/surefire-reports' -type d -exec rm -rf {{}} + 2>/dev/null
  echo "===RUN_END $i==="
done
"""
        try:
            r = sh(["docker", "run", "--rm", *flags, run_image, shell, "-c", inner],
                   timeout=RUN_TIMEOUT_SEC * runs)
        except subprocess.TimeoutExpired as e:
            writer.write_error(cfg_name, "*", "TIMEOUT", str(e)[:2000])
            log(f"  [{project_key}] config {cfg_name}: TIMEOUT")
            continue
        chunks = r.stdout.split("===RUN_START ")
        for chunk in chunks[1:]:
            idx_str, _, rest = chunk.partition("===")
            run_idx = idx_str.strip()
            tests = parse_junit_blob(rest)
            if not tests:
                writer.write_error(cfg_name, run_idx, "NO_TESTS_PARSED",
                                    rest[:3000] + "\n---STDERR---\n" + r.stderr[-2000:])
            for classname, name, status, message in tests:
                writer.write_test(cfg_name, run_idx, classname, name, status, message)
                if status in ("failure", "error"):
                    writer.write_error(cfg_name, run_idx, status.upper(),
                                        f"{classname}.{name}: {message}")
        if r.returncode != 0 and not chunks[1:]:
            writer.write_error(cfg_name, "*", "CONTAINER_FAILURE",
                                r.stdout[-2000:] + "\n---STDERR---\n" + r.stderr[-2000:])
        writer.flush()
        log(f"  [{project_key}] config {cfg_name}: done ({len(chunks)-1} runs parsed)")


# ---------------- Python (flapy) ----------------

def python_project_info(image):
    r = sh(["docker", "inspect", image, "--format", "{{json .Config.Env}}"])
    env = json.loads(r.stdout)
    d = {}
    for e in env:
        if "=" in e:
            k, v = e.split("=", 1)
            d[k] = v
    return d.get("PROJECT_NAME"), d.get("PROJECT_URL"), d.get("PROJECT_HASH")


def run_python(image, project_key, configs, runs, writer, deadline=None):
    pname, purl, phash = python_project_info(image)
    if not pname:
        raise RuntimeError(f"could not read PROJECT_NAME env from {image}")
    repo_dir = f"/workdir/{pname}"
    for cfg_name in configs:
        if deadline and time.time() > deadline:
            log(f"  [{project_key}] deadline reached, stopping before config {cfg_name}")
            writer.write_error(cfg_name, "*", "DEADLINE_STOP", "job wall-clock budget exceeded")
            break
        cfg = CONFIGS[cfg_name]
        flags = docker_flags(cfg)
        run_image = image
        env_flags = ["-e", f"REPOSITORY_DIR={repo_dir}",
                     "-e", "CLOC_DBFILE=/workdir/flapy_cloc.sqlite",
                     "-e", f"REPO_HASH={phash}"]
        if cfg["net"] is not None:
            run_image = ensure_tc_image(image)
            flags = flags + ["--cap-add", "NET_ADMIN"]
        results_host = RESULTS_ROOT / "python" / "_tmp" / project_key / cfg_name
        results_host.mkdir(parents=True, exist_ok=True)
        vol_flags = ["-v", f"{str(results_host)}:/results"]
        entry_override = []
        if cfg["net"] is not None:
            down, up = cfg["net"]
            entry_override = ["--entrypoint", "bash"]
            args = ["-c",
                    NET_PRELUDE.format(up=up, down=down) +
                    f"\n./run_tests_cached_deps.sh '{pname}' '{purl}' '{phash}' '' '' '' {runs} false ''"]
        else:
            args = [pname, purl, phash, "", "", "", str(runs), "false", ""]
        try:
            r = sh(["docker", "run", "--rm", *flags, *env_flags, *vol_flags,
                    *entry_override, run_image, *args],
                   timeout=RUN_TIMEOUT_SEC * runs)
        except subprocess.TimeoutExpired as e:
            writer.write_error(cfg_name, "*", "TIMEOUT", str(e)[:2000])
            log(f"  [{project_key}] config {cfg_name}: TIMEOUT")
            continue
        # extract results.tar.xz -> find junit xmls
        tarpath = results_host / "results.tar.xz"
        found_any = False
        if tarpath.exists():
            extract_dir = results_host / "extracted"
            extract_dir.mkdir(exist_ok=True)
            sh(["tar", "xJf", str(tarpath), "-C", str(extract_dir)], timeout=120)
            for xmlf in extract_dir.rglob("*.xml"):
                blob = xmlf.read_text(errors="ignore")
                tests = parse_junit_blob(blob)
                if tests:
                    found_any = True
                    run_idx_m = re.search(r"output(\d+)", xmlf.name)
                    run_idx = run_idx_m.group(1) if run_idx_m else "?"
                    for classname, name, status, message in tests:
                        writer.write_test(cfg_name, run_idx, classname, name, status, message)
                        if status in ("failure", "error"):
                            writer.write_error(cfg_name, run_idx, status.upper(),
                                                f"{classname}.{name}: {message}")
        if not found_any:
            writer.write_error(cfg_name, "*", "NO_TESTS_PARSED",
                                r.stdout[-3000:] + "\n---STDERR---\n" + r.stderr[-2000:])
        writer.flush()
        log(f"  [{project_key}] config {cfg_name}: done (parsed={found_any})")


# ---------------- JS (npm-filter) ----------------

def run_js(image, project_key, configs, runs, writer, deadline=None):
    for cfg_name in configs:
        if deadline and time.time() > deadline:
            log(f"  [{project_key}] deadline reached, stopping before config {cfg_name}")
            writer.write_error(cfg_name, "*", "DEADLINE_STOP", "job wall-clock budget exceeded")
            break
        cfg = CONFIGS[cfg_name]
        flags = docker_flags(cfg)
        run_image = image
        entry_override = []
        if cfg["net"] is not None:
            run_image = ensure_tc_image(image)
            flags = flags + ["--cap-add", "NET_ADMIN"]
            down, up = cfg["net"]
            entry_override = ["--entrypoint", "bash"]
        for run_idx in range(1, runs + 1):
            results_host = RESULTS_ROOT / "js" / "_tmp" / project_key / cfg_name / str(run_idx)
            results_host.mkdir(parents=True, exist_ok=True)
            vol_flags = ["-v", f"{str(results_host)}:/home/npm-filter/results"]
            args = []
            if cfg["net"] is not None:
                args = ["-c", NET_PRELUDE.format(up=up, down=down) +
                        "\n. /envfile; ./run_verbose_for_repo_and_config.sh $ENV_REPO_LINK $ENV_REPO_COMMIT"]
            try:
                r = sh(["docker", "run", "--rm", *flags, *vol_flags, *entry_override,
                        run_image, *args], timeout=RUN_TIMEOUT_SEC)
            except subprocess.TimeoutExpired as e:
                writer.write_error(cfg_name, run_idx, "TIMEOUT", str(e)[:2000])
                continue
            found_any = False
            for jf in results_host.glob("*verbose_test_report.json"):
                try:
                    data = json.loads(jf.read_text(errors="ignore"))
                except Exception:
                    continue
                for tr in data.get("testResults", []):
                    fname = tr.get("name", "?")
                    for ar in tr.get("assertionResults", []):
                        status = ar.get("status", "unknown")
                        status = {"passed": "pass", "failed": "failure", "pending": "skipped"}.get(status, status)
                        msg = "; ".join(ar.get("failureMessages", []))[:500]
                        writer.write_test(cfg_name, run_idx, fname, ar.get("fullName", ar.get("title", "?")), status, msg)
                        found_any = True
                        if status == "failure":
                            writer.write_error(cfg_name, run_idx, "FAILURE", f"{fname} :: {ar.get('fullName')}: {msg}")
            if not found_any:
                writer.write_error(cfg_name, run_idx, "NO_TESTS_PARSED",
                                    r.stdout[-3000:] + "\n---STDERR---\n" + r.stderr[-2000:])
        writer.flush()
        log(f"  [{project_key}] config {cfg_name}: done ({runs} runs)")


LANG_RUNNERS = {"java": run_java, "python": run_python, "js": run_js}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["java", "python", "js"])
    ap.add_argument("--project")
    ap.add_argument("--configs", default=",".join(CONFIGS.keys()))
    ap.add_argument("--runs", type=int, default=RUNS_PER_CONFIG_DEFAULT)
    ap.add_argument("--max-minutes", type=float, default=None,
                     help="wall-clock budget for the whole invocation; stop gracefully before it elapses")
    args = ap.parse_args()
    configs = args.configs.split(",")
    for c in configs:
        assert c in CONFIGS, f"unknown config {c}"
    deadline = time.time() + args.max_minutes * 60 if args.max_minutes else None

    langs = [args.only] if args.only else ["java", "python", "js"]
    for lang in langs:
        projects = REGISTRY[lang]
        keys = args.project.split(",") if args.project else sorted(projects.keys())
        for key in keys:
            if deadline and time.time() > deadline:
                log(f"GLOBAL DEADLINE reached, stopping before {lang}/{key}")
                break
            if key not in projects:
                log(f"SKIP unknown project {key} for {lang}")
                continue
            image = f"jonbell/raft:{projects[key]}"
            log(f"=== {lang}/{key} ({image}) ===")
            writer = ResultWriter(lang, key)
            try:
                r = sh(["docker", "pull", image], timeout=1200)
                if r.returncode != 0:
                    writer.write_error("*", "*", "PULL_FAILED", r.stderr[-2000:])
                    log(f"  PULL FAILED: {r.stderr[-300:]}")
                    writer.close()
                    continue
                LANG_RUNNERS[lang](image, key, configs, args.runs, writer, deadline=deadline)
            except Exception as e:
                writer.write_error("*", "*", "FATAL", traceback.format_exc())
                log(f"  FATAL: {e}")
            finally:
                writer.close()
    log("ALL DONE")


if __name__ == "__main__":
    main()
