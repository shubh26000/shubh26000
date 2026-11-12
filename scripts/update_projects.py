#!/usr/bin/env python3
"""Refresh profile README project cards from the owner's public repositories."""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

START_MARKER = "<!-- PROJECTS:START -->"
END_MARKER = "<!-- PROJECTS:END -->"
README = Path("README.md")
MAX_PROJECTS = 4
API_BASE = "https://api.github.com"


def fetch_repositories(owner: str) -> list[dict[str, object]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-readme-project-refresh",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repos: list[dict[str, object]] = []
    page = 1
    while True:
        query = urlencode(
            {"type": "owner", "sort": "updated", "direction": "desc", "per_page": 100, "page": page}
        )
        request = Request(f"{API_BASE}/users/{quote(owner, safe='')}/repos?{query}", headers=headers)
        try:
            with urlopen(request, timeout=20) as response:
                batch = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Could not fetch GitHub repositories: {exc}") from exc
        if not isinstance(batch, list):
            raise RuntimeError("GitHub returned an unexpected repository response")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def eligible_repositories(owner: str, repos: list[dict[str, object]]) -> list[dict[str, object]]:
    profile_repo = f"{owner}/{owner}".casefold()
    selected = []
    for repo in repos:
        repo_owner = repo.get("owner") or {}
        full_name = str(repo.get("full_name", ""))
        if not isinstance(repo_owner, dict):
            continue
        if str(repo_owner.get("login", "")).casefold() != owner.casefold():
            continue
        if full_name.casefold() == profile_repo:
            continue
        # Fail closed: only repos the API explicitly identifies as public can appear.
        if repo.get("private") is not False or repo.get("visibility") != "public":
            continue
        if repo.get("fork") is True or repo.get("archived") is True:
            continue
        if repo.get("disabled") is True:
            continue
        selected.append(repo)

    selected.sort(key=lambda repo: str(repo.get("updated_at", "")), reverse=True)
    return selected[:MAX_PROJECTS]


def safe_text(value: object, default: str = "") -> str:
    text = " ".join(str(value or "").split())
    return html.escape(text or default, quote=True)


def project_cards(owner: str, repos: list[dict[str, object]]) -> str:
    if not repos:
        return '<p align="center"><sub>No public projects to feature yet.</sub></p>'

    cells = []
    for repo in repos:
        name = str(repo.get("name", "Repository"))
        href = f"https://github.com/{quote(owner, safe='')}/{quote(name, safe='')}"
        display_name = safe_text(name, "Repository")
        description = safe_text(repo.get("description"), "Repository and source code.")
        language = safe_text(repo.get("language"))
        topics = repo.get("topics")
        tags = [safe_text(topic) for topic in topics if isinstance(topic, str)] if isinstance(topics, list) else []
        if language:
            tags.insert(0, language)
        tags = list(dict.fromkeys(tag for tag in tags if tag))[:4]
        stack = " · ".join(f"<code>{tag}</code>" for tag in tags)
        stack_line = f"<br><br>{stack}" if stack else ""
        safe_href = html.escape(href, quote=True)
        cells.append(
            f'<td width="50%" valign="top"><strong><a href="{safe_href}">{display_name}</a></strong>'
            f"<br><sub>{description}</sub>{stack_line}<br>"
            f'<a href="{safe_href}">Open repository ↗</a></td>'
        )

    rows = []
    for index in range(0, len(cells), 2):
        row = cells[index : index + 2]
        if len(row) == 1:
            row[0] = row[0].replace('<td width="50%"', '<td width="100%" colspan="2"', 1)
        rows.append("<tr>" + "".join(row) + "</tr>")
    return '<table align="center" width="100%">\n' + "\n".join(rows) + "\n</table>"


def main() -> None:
    owner = os.environ.get("GITHUB_USERNAME", "shubh26000").strip()
    if not owner:
        raise RuntimeError("GITHUB_USERNAME is empty")

    readme = README.read_text(encoding="utf-8")
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise RuntimeError("README must contain exactly one PROJECTS:START and PROJECTS:END marker")
    start = readme.index(START_MARKER) + len(START_MARKER)
    end = readme.index(END_MARKER)
    if end < start:
        raise RuntimeError("Project markers are out of order")

    repos = eligible_repositories(owner, fetch_repositories(owner))
    updated = readme[:start] + "\n" + project_cards(owner, repos) + "\n" + readme[end:]
    if updated != readme:
        README.write_text(updated, encoding="utf-8", newline="\n")
        print(f"Updated featured projects with {len(repos)} public repositories.")
    else:
        print("Featured projects are already up to date.")


if __name__ == "__main__":
    main()
