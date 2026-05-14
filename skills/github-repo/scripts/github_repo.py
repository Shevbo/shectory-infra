#!/usr/bin/env python3
"""
GitHub Repo Skill — создание и управление репозиториями через GitHub API.

Токен: ~/.shectory_github_token
SSH ключ: ~/.ssh/id_ed25519_github
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

API_BASE = "https://api.github.com"
TOKEN_FILE = Path.home() / ".shectory_github_token"
SSH_KEY = Path.home() / ".ssh" / "id_ed25519_github"
DEFAULT_ORG = "Shevbo"


def load_token() -> str:
    if not TOKEN_FILE.exists():
        print(f"ERROR: токен не найден в {TOKEN_FILE}", file=sys.stderr)
        print(f"Создай токен на https://github.com/settings/tokens/new (права: repo)", file=sys.stderr)
        print(f"Сохрани: echo 'ghp_...' > {TOKEN_FILE} && chmod 600 {TOKEN_FILE}", file=sys.stderr)
        sys.exit(1)
    token = TOKEN_FILE.read_text().strip()
    if not token:
        print(f"ERROR: токен пустой в {TOKEN_FILE}", file=sys.stderr)
        sys.exit(1)
    return token


def api_request(method: str, path: str, data: dict | None = None) -> dict:
    token = load_token()
    cmd = [
        "curl", "-sf", "-X", method,
        "-H", f"Authorization: token {token}",
        "-H", "Accept: application/vnd.github+json",
        "-H", "X-GitHub-Api-Version: 2022-11-28",
    ]
    if data:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(data)]
    cmd.append(f"{API_BASE}{path}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: API запрос не удался: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    if result.stdout.strip():
        return json.loads(result.stdout)
    return {}


def git_run(args: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if SSH_KEY.exists():
        env["GIT_SSH_COMMAND"] = f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no"
    return subprocess.run(["git"] + args, cwd=cwd, env=env, capture_output=True, text=True, check=check)


def cmd_create(args: argparse.Namespace) -> None:
    org = args.org or DEFAULT_ORG
    payload = {
        "name": args.name,
        "description": args.description or "",
        "private": args.private,
        "auto_init": False,
    }

    print(f"Создаю репозиторий {org}/{args.name}...")
    resp = api_request("POST", f"/orgs/{org}/repos", payload)

    # Если не организация — пробуем как личный аккаунт
    if resp.get("message") and "Not Found" in resp["message"]:
        resp = api_request("POST", "/user/repos", payload)

    if "ssh_url" not in resp:
        print(f"ERROR: не удалось создать репо: {resp}", file=sys.stderr)
        sys.exit(1)

    ssh_url = resp["ssh_url"]
    html_url = resp["html_url"]
    print(f"Репозиторий создан: {html_url}")

    if args.local_path:
        local = args.local_path
        r = git_run(["remote", "get-url", "origin"], cwd=local, check=False)
        if r.returncode == 0:
            git_run(["remote", "set-url", "origin", ssh_url], cwd=local)
            print(f"Remote origin обновлён: {ssh_url}")
        else:
            git_run(["remote", "add", "origin", ssh_url], cwd=local)
            print(f"Remote origin добавлен: {ssh_url}")

        if args.push:
            branch = git_run(["branch", "--show-current"], cwd=local).stdout.strip() or "main"
            print(f"Пушу ветку {branch}...")
            r = git_run(["push", "-u", "origin", branch], cwd=local, check=False)
            if r.returncode != 0:
                print(f"ERROR при push: {r.stderr}", file=sys.stderr)
                sys.exit(1)
            print(f"Запушено успешно.")

    print(json.dumps({"url": html_url, "ssh_url": ssh_url, "name": args.name}, ensure_ascii=False))


def cmd_push(args: argparse.Namespace) -> None:
    local = args.local_path
    r = git_run(["remote", "get-url", "origin"], cwd=local, check=False)
    if r.returncode != 0 or args.url:
        git_run(["remote", "add", "origin", args.url], cwd=local)

    branch = git_run(["branch", "--show-current"], cwd=local).stdout.strip() or "main"
    print(f"Пушу {branch} → {args.url or 'origin'}...")
    r = git_run(["push", "-u", "origin", branch], cwd=local, check=False)
    if r.returncode != 0:
        print(f"ERROR: {r.stderr}", file=sys.stderr)
        sys.exit(1)
    print("Запушено успешно.")


def cmd_list(args: argparse.Namespace) -> None:
    org = args.org or DEFAULT_ORG
    repos = api_request("GET", f"/orgs/{org}/repos?per_page=50&sort=updated")
    if isinstance(repos, list):
        for r in repos:
            vis = "private" if r.get("private") else "public"
            print(f"  {r['name']:40s} [{vis}]  {r['html_url']}")
    else:
        # личный аккаунт
        repos = api_request("GET", "/user/repos?per_page=50&sort=updated")
        for r in repos:
            vis = "private" if r.get("private") else "public"
            print(f"  {r['name']:40s} [{vis}]  {r['html_url']}")


def cmd_delete(args: argparse.Namespace) -> None:
    org = args.org or DEFAULT_ORG
    confirm = input(f"Удалить {org}/{args.name}? Введи имя репо для подтверждения: ").strip()
    if confirm != args.name:
        print("Отменено.")
        return
    api_request("DELETE", f"/repos/{org}/{args.name}")
    print(f"Репозиторий {org}/{args.name} удалён.")


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Repo Skill")
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Создать репозиторий")
    p_create.add_argument("--name", required=True, help="Имя репозитория")
    p_create.add_argument("--description", default="", help="Описание")
    p_create.add_argument("--private", action="store_true", default=True, help="Приватный (по умолчанию)")
    p_create.add_argument("--public", dest="private", action="store_false", help="Публичный")
    p_create.add_argument("--org", default=DEFAULT_ORG, help="Организация или пользователь")
    p_create.add_argument("--local-path", help="Путь к локальному git-репо")
    p_create.add_argument("--push", action="store_true", help="Сразу запушить")

    # push
    p_push = sub.add_parser("push", help="Добавить remote и запушить")
    p_push.add_argument("--url", required=True, help="SSH URL репозитория")
    p_push.add_argument("--local-path", required=True, help="Путь к локальному git-репо")

    # list
    p_list = sub.add_parser("list", help="Список репозиториев")
    p_list.add_argument("--org", default=DEFAULT_ORG, help="Организация")

    # delete
    p_del = sub.add_parser("delete", help="Удалить репозиторий")
    p_del.add_argument("--name", required=True, help="Имя репозитория")
    p_del.add_argument("--org", default=DEFAULT_ORG, help="Организация")

    args = parser.parse_args()

    if args.command == "create":
        cmd_create(args)
    elif args.command == "push":
        cmd_push(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "delete":
        cmd_delete(args)


if __name__ == "__main__":
    main()
