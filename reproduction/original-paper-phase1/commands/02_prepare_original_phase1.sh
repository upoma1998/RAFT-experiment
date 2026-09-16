#!/usr/bin/env bash
set -euo pipefail
set -x

echo "=== ORIGINAL RAFT PHASE-I PREPARATION ==="

git branch --show-current
git status
git rev-parse HEAD

# Keep the current implementation untouched.
cp phase1_runner.py original_paper_phase1_runner.py

# Create a registry containing the 52 projects reported in Table III.
python3 - <<'PY'
import json
from pathlib import Path

src = json.load(open("phase1_registry.json"))

wanted = {
    "java": [
        "joel-costigliola_assertj-core",
        "wso2.carbon-apimgt-a82213e_analyzer-modules.org.wso2.carbon.apimgt.throttling.siddhi.extension",
        "apache_commons-exec",
        "kagkarlsson.db-scheduler",
        "javadelight.delight-nashorn-sandbox",
        "elasticjob_elastic-job-lite",
        "espertechinc.esper-590fa9c_examples.rfidassetzone",
        "codingchili.excelastic",
        "alibaba.fastjson",
        "fluent.fluent-logger-java",
        "jknack_handlebars.java",
        "hector-client_hector",
        "kevinsawicki_http-request",
        "apache_httpcore",
        "looly.hutool-91565d0_hutool-cron",
        "apache_incubator-dubbo",
        "tootallnate_java-websocket",
        "qos-ch_logback",
        "flaxsearch.luwak-c27ec08_luwak",
        "ninjaframework_ninja",
        "spinn3r.noxy-d53a494_noxy-discovery-zookeeper",
        "orbit_orbit",
        "oryxproject.oryx-72ae4bb_framework.oryx-common",
        "zalando.riptide-8277e11_riptide-failsafe",
        "davidmoten.rxjava2-extras",
        "spring-projects_spring-boot",
        "nationalsecurityagency.timely-3a8cbd3_server",
        "wro4j_wro4j",
        "feroult.yawp-b3bcf9c_yawp-testing.yawp-testing-appengine",
        "zxing_zxing"
    ],

    "js": [
        "apollographql-apollo-client-devtools",
        "icedfrisby-icedfrisby",
        "actions-javascript-action",
        "bubenshchykov-ngrok",
        "babel-preset-modules",
        "arqex-react-datetime",
        "facebook-react-native",
        "badges-shields",
        "atomiks-tippyjs-react",
        "twilio-twilio-video-app-react"
    ],

    "python": [
        "celery-celery",
        "conan-io-conan",
        "spesmilo-electrum",
        "fonttools-fonttools",
        "ipython-ipython",
        "delgan-loguru",
        "mitmproxy-mitmproxy",
        "psf-requests",
        "mwaskom-seaborn",
        "pypa-setuptools",
        "sunpy-sunpy",
        "xonsh-xonsh"
    ]
}

out = {}

for lang, names in wanted.items():
    out[lang] = {}
    for name in names:
        if name not in src.get(lang, {}):
            print(f"MISSING: {lang}: {name}")
        else:
            out[lang][name] = src[lang][name]

Path("original_paper_phase1_registry.json").write_text(
    json.dumps(out, indent=2) + "\n"
)

print()
print("Registry counts:")
total = 0
for lang in ("java", "js", "python"):
    n = len(out[lang])
    total += n
    print(f"{lang}: {n}")
print(f"TOTAL: {total}")
PY

echo "=== PREPARATION COMPLETE ==="
