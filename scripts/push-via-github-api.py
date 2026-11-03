"""用 GitHub Git Data API 推送提交（git 端点 443 不可用时的备用通道）。

关键设计：**精确复现**每个提交的 tree / message / author / committer，
使远程生成的 commit SHA 与本地完全一致 —— 这样推送后本地与远程不会分叉。

适用场景：网络策略允许 api.github.com:443、但阻断 github.com:443 时，
普通 `git push` 会一直 "Failed to connect to github.com:443"。

用法：
    python scripts/push-via-github-api.py <branch> <sha1> [<sha2> ...]

安全设计（任一校验不通过即中止，绝不写坏远程）：
    1) 本地提交的 parent 必须等于远程当前 ref，否则拒绝（防止覆盖他人提交）
    2) API 返回的 tree SHA 必须等于本地 `git rev-parse <sha>^{tree}`
    3) API 返回的 commit SHA 必须等于本地提交 SHA
    4) ref 更新使用 force=False，只允许快进
因为 SHA 被精确复现，推送后**本地与远程不会分叉**，后续可正常使用 git fetch/pull。
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

REPO = os.environ.get("GITHUB_REPO", "ggg333219/2026FWW-provin")
API = f"https://api.github.com/repos/{REPO}"
TOKEN = (
    subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True,
        text=True,
    ).stdout
)
TOKEN = next(
    (l.split("=", 1)[1] for l in TOKEN.splitlines() if l.startswith("password=")), ""
)


def api(method, path, payload=None):
    url = path if path.startswith("http") else API + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"API {method} {path} 失败 HTTP {e.code}\n{detail[:1500]}")
    return json.loads(body) if body else None


def git(*args):
    # core.quotepath=false：否则中文路径会被转义成八进制，cat-file 取不到内容
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout


REPO_ROOT = os.environ.get("REPO_ROOT") or subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
).stdout.strip()


def local_tree(sha):
    return git("rev-parse", f"{sha}^{{tree}}").strip()


def local_commit_meta(sha):
    """取本地提交的 author/committer/message。

    message 必须**原样**保留末尾换行 —— git commit 对象里的 message 末尾自带 "\\n"，
    去掉它会让 API 生成的 commit SHA 与本地不一致。
    """
    raw = subprocess.run(
        ["git", "-c", "core.quotepath=false", "cat-file", "commit", sha],
        capture_output=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout
    # header 与 body 之间是空行；body 之后还有一个结尾换行
    header, _, body = raw.partition(b"\n\n")
    ident_re = re.compile(rb"^(author|committer) (.*) <(.*)> (\d+) ([+-]\d{4})$")
    meta = {"author": None, "committer": None}
    for line in header.split(b"\n"):
        m = ident_re.match(line)
        if not m:
            continue
        role, name, email, ts, tz = m.groups()
        ts = int(ts)
        tz_s = tz.decode()
        sign = 1 if tz_s[0] == "+" else -1
        hh, mm = int(tz_s[1:3]), int(tz_s[3:5])
        offset = sign * (hh * 3600 + mm * 60)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(
            timezone(timedelta(seconds=offset))
        )
        # GitHub 要求 ISO8601 且带冒号的时区：+08:00（不是 +0800）
        iso_tz = f"{tz_s[:3]}:{tz_s[3:]}"
        meta[role.decode()] = {
            "name": name.decode("utf-8"),
            "email": email.decode("utf-8"),
            "date": dt.strftime("%Y-%m-%dT%H:%M:%S") + iso_tz,
        }
    return {
        "author": meta["author"],
        "committer": meta["committer"],
        "message": body.decode("utf-8"),
    }


def changed_paths(sha):
    """该提交相对其第一父提交的全部变更（含增/改/删）。"""
    out = git("diff-tree", "-r", "--no-commit-id", "--name-status", "-M", sha)
    entries = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]
        entries.append((status, path))
    return entries


def create_blob(content_bytes):
    b64 = base64.b64encode(content_bytes).decode("ascii")
    r = api(
        "POST",
        "/git/blobs",
        {"content": b64, "encoding": "base64"},
    )
    return r["sha"]


def push_commit(sha, parent_sha):
    tree_sha = local_tree(sha)
    entries = []
    for status, path in changed_paths(sha):
        if status.startswith("D"):
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            continue
        blob_sha = git("rev-parse", f"{sha}:{path}").strip()
        mode = git("ls-tree", sha, "--", path).split()[0]
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": blob_sha})
        # 预创建 blob，确保 tree 引用得到
        content = subprocess.run(
            ["git", "cat-file", "blob", blob_sha],
            capture_output=True,
            cwd=REPO_ROOT,
            check=True,
        ).stdout
        created = create_blob(content)
        if created != blob_sha:
            raise SystemExit(
                f"blob SHA 不一致：本地 {blob_sha} vs API {created} ({path})"
            )

    parent_tree = local_tree(parent_sha)
    tree = api(
        "POST",
        "/git/trees",
        {"base_tree": parent_tree, "tree": entries},
    )
    if tree["sha"] != tree_sha:
        raise SystemExit(
            f"tree SHA 不一致：本地 {tree_sha} vs API {tree['sha']}\n"
            f"entries={json.dumps(entries, ensure_ascii=False)[:800]}"
        )
    print(f"    tree 校验通过 {tree_sha[:10]}")

    meta = local_commit_meta(sha)
    parents = git("rev-list", "--parents", "-n", "1", sha).split()[1:]
    commit = api(
        "POST",
        "/git/commits",
        {
            "message": meta["message"],
            "tree": tree["sha"],
            "parents": parents,
            "author": meta["author"],
            "committer": meta["committer"],
        },
    )
    if commit["sha"] != git("rev-parse", sha).strip():
        raise SystemExit(
            f"commit SHA 不一致：本地 {sha} vs API {commit['sha']}\n"
            f"author={meta['author']}\ncommitter={meta['committer']}\n"
            f"message前80字={meta['message'][:80]!r}"
        )
    print(f"    commit 校验通过 {sha[:10]}")
    return commit["sha"]


def main():
    branch = sys.argv[1]
    shas = sys.argv[2:]
    if not shas:
        raise SystemExit("用法: python tmp/push_via_api.py <branch> <sha1> [...]")

    ref_path = f"/git/ref/heads/{branch}"
    remote_ref = api("GET", ref_path)
    current = remote_ref["object"]["sha"]
    print(f"远程 {branch} 当前 = {current[:10]}")

    for sha in shas:
        parents = git("rev-list", "--parents", "-n", "1", sha).split()[1:]
        parent = parents[0]
        print(f"\n推送提交 {sha[:10]} (parent {parent[:10]})")
        if parent != current:
            raise SystemExit(
                f"父提交不匹配：本地父 {parent} vs 远程当前 {current}，请先确认历史一致"
            )
        new_sha = push_commit(sha, parent)
        # 更新 ref（快进）
        api("PATCH", ref_path.replace("/git/ref/", "/git/refs/"), {"sha": new_sha, "force": False})
        current = new_sha
        print(f"    ref 已更新 → {new_sha[:10]}")

    print(f"\n完成：远程 {branch} = {current}")
    final = api("GET", ref_path)
    print(f"复核：远程 ref = {final['object']['sha']}")
    print(f"本地 HEAD    = {git('rev-parse', 'HEAD').strip()}")


if __name__ == "__main__":
    main()
