"""Registry of jonbell/raft images -> (language, project_key) built from the live tag list."""
import json, re, urllib.request

def fetch_tags():
    url = "https://hub.docker.com/v2/repositories/jonbell/raft/tags?page_size=100"
    with urllib.request.urlopen(url) as r:
        d = json.load(r)
    return [t["name"] for t in d["results"]]

def build_registry():
    tags = fetch_tags()
    java, python, js = {}, {}, {}
    for t in tags:
        if t.startswith("flapy-"):
            # flapy-<owner>-<repo>-<full sha>
            body = t[len("flapy-"):]
            m = re.match(r"^(.*)-([0-9a-f]{16,40})$", body)
            if not m:
                continue
            key = m.group(1)
            python[key] = t
        elif t.startswith("npm-filter-"):
            body = t[len("npm-filter-"):]
            m = re.match(r"^(.*)-([0-9a-f]{16,40})$", body)
            if not m:
                continue
            key = m.group(1)
            js[key] = t
        elif t.endswith("_dot-latest"):
            # java: <owner>.<repo>-<shortsha>_dot-latest  OR <owner>_<repo>-<shortsha>_dot-latest
            key = t[: -len("_dot-latest")]
            key = re.sub(r"-[0-9a-f]{6,}$", "", key)
            java[key] = t
        elif t.endswith("-latest"):
            # java sub-module images: <owner>.<repo>-<sha>_<module.path>-latest
            # (sha sits mid-string next to the module path, not at the end, so
            # unlike the _dot-latest case there's nothing safe to strip further)
            key = t[: -len("-latest")]
            if key not in java:
                java[key] = t
    return {"java": java, "python": python, "js": js}

if __name__ == "__main__":
    reg = build_registry()
    for lang, d in reg.items():
        print(f"== {lang}: {len(d)} projects ==")
        for k, v in sorted(d.items()):
            print(f"  {k:50s} -> {v}")
    with open("phase1_registry.json", "w") as f:
        json.dump(reg, f, indent=2)
