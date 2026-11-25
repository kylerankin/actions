#!/usr/bin/env python3
"""
render_pr_body.py — Generate the promotion PR body for a promotion PR.

The promoted branch pair is a parameter (``--source-branch``/``--target-branch``):
testing → main for the bluefin family, main → stable for finpilot.

Called by reusable-promote-squash.yml. The body contains HTML marker
comments around the gate section so the gate job can do a targeted
replacement without touching the rest of the body.

Usage (squash workflow — describes the actual tree difference of the
promotion branch against the target branch):
    python3 render_pr_body.py \\
        --project-name        "Bluefin" \\
        --primary-image       "bluefin" \\
        --variants-json       '[{"image":"bluefin"},{"image":"bluefin-nvidia"}]' \\
        --repo                "projectbluefin/bluefin" \\
        --run-url             "https://github.com/.../runs/123" \\
        --date                "2026-06-11" \\
        --days-since-stable   12 \\
        --last-release-tag    "stable-20260530-abc1234" \\
        --last-release-url    "https://github.com/.../releases/tag/stable-20260530-abc1234" \\
        --insertions          3 \\
        --deletions           2 \\
        --files-json          '["configs/a.toml","configs/b.toml"]' \\
        --compare-url         "https://github.com/.../compare/main...auto/promote-testing-to-main" \\
        --output              /tmp/pr-body.md

Usage (digest workflow — variants include resolved digests, no git log):
    python3 render_pr_body.py \\
        --project-name        "Dakota" \\
        --primary-image       "dakota" \\
        --variants-json       '[{"image":"dakota","digest":"sha256:abc..."}]' \\
        --repo                "projectbluefin/dakota" \\
        --run-url             "https://github.com/.../runs/456" \\
        --date                "2026-06-11" \\
        --days-since-stable   5 \\
        --last-release-tag    "stable-20260606-def5678" \\
        --last-release-url    "https://github.com/.../releases/tag/stable-20260606-def5678" \\
        --output              /tmp/pr-body.md

The gate section is bounded by HTML markers for targeted replacement:
    <!-- gate-section-start -->
    ...checklist rows...
    <!-- gate-section-end -->
"""
import argparse
import json
import sys
from datetime import datetime, timezone

GATE_START = "<!-- gate-section-start -->"
GATE_END   = "<!-- gate-section-end -->"


# ── Section builders ──────────────────────────────────────────────────────────

def _section_header(
    project_name: str,
    date: str,
    run_url: str,
    *,
    days_ago: int | None,
    last_tag: str | None,
    last_release_url: str | None,
    source_branch: str = "testing",
    target_branch: str = "stable",
    maintainer_workflow: str = "promote-testing-to-main.yml",
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if days_ago is not None and last_tag and last_release_url:
        noun = "day" if days_ago == 1 else "days"
        days_line = (
            f"> **{days_ago} {noun} since the last stable release**"
            f" · [{last_tag} ↗]({last_release_url})  \n"
        )
    else:
        days_line = ""

    return (
        f"## 🦕 {project_name} {source_branch} → {target_branch} · {date}\n\n"
        f"{days_line}"
        f"> Auto-maintained by `{maintainer_workflow}` · "
        f"Updated `{now}` · [Run ↗]({run_url})\n"
    )


def _section_gate_placeholder() -> str:
    rows = "\n".join(
        f"| {name} | ⏳ checking… | — |"
        for name in ("Digest resolution", "Cosign signatures", "E2E")
    )
    return (
        f"{GATE_START}\n"
        "### Release checklist\n\n"
        "| Check | Status | Details |\n"
        "|---|---|---|\n"
        f"{rows}\n"
        f"{GATE_END}\n"
    )


def _section_variants(variants: list[dict], source_tag: str) -> str:
    has_digests = any("digest" in v for v in variants)

    if has_digests:
        header = "| Variant | Tag | Digest |\n|---|---|---|\n"
        rows = []
        for v in variants:
            image  = v["image"]
            digest = v.get("digest", "")
            if digest.startswith("sha256:"):
                short = f"`sha256:{digest[7:23]}`"
            elif digest:
                short = f"`{digest[:16]}`"
            else:
                short = "—"
            rows.append(f"| `{image}` | `:{source_tag}` | {short} |")
    else:
        header = "| Variant | Tag |\n|---|---|\n"
        rows   = [f"| `{v['image']}` | `:{source_tag}` |" for v in variants]

    return "### Variants being promoted\n\n" + header + "\n".join(rows) + "\n"


def _section_changes(
    files: list[str],
    insertions: int,
    deletions: int,
    compare_url: str | None,
    source_branch: str = "testing",
    target_branch: str = "stable",
) -> str:
    # Empty diff: nothing to promote. The squash branch is only built when the
    # trees differ, so this is the no-op case (e.g. a digest-only caller that
    # supplies no file list).
    if not files and insertions == 0 and deletions == 0:
        return ""

    compare_link = (
        f" · [Compare {target_branch}…{source_branch} ↗]({compare_url})"
        if compare_url
        else ""
    )
    file_noun = "file" if len(files) == 1 else "files"
    intro = (
        f"**{len(files)} {file_noun} changed**, "
        f"+{insertions} −{deletions} ahead of {target_branch}{compare_link}\n"
    )

    if not files:
        return "### Changes since last stable\n\n" + intro

    rows = "\n".join(f"- `{f}`" for f in files)
    details = (
        "<details>\n"
        f"<summary>Changed files (showing last {len(files)})</summary>\n\n"
        f"{rows}\n\n</details>"
    )
    return "### Changes since last stable\n\n" + intro + "\n" + details + "\n"


def _section_footer(repo: str = "") -> str:
    repo_flag = f" --repo {repo}" if repo else ""
    pr_placeholder = "<pr-number>"
    return (
        "---\n\n"
        "_Follow this repository's branch-protection requirements before merging. "
        f"Force: `gh pr merge {pr_placeholder}{repo_flag} --merge --admin`_\n"
    )

def build_title(primary_image: str, date: str,
                source_branch: str = "testing",
                target_branch: str = "stable") -> str:
    """
    Consistent promotion PR title across all image repos:
        ci(promote): <image> <source> → <target> YYYY-MM-DD

    The branch pair is a parameter because not every repository promotes
    testing → stable: finpilot promotes main → stable, and a hardcoded pair
    described someone else's release flow in its PR body.
    """
    return f"ci(promote): {primary_image} {source_branch} → {target_branch} {date}"


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Render promotion PR body (testing → stable)")
    ap.add_argument("--project-name",       required=True,
                    help="Display name, e.g. 'Bluefin LTS'")
    ap.add_argument("--primary-image",      required=True,
                    help="Primary image slug for title, e.g. 'bluefin-lts'")
    ap.add_argument("--variants-json",      required=True,
                    help="JSON array of variant objects: [{\"image\": str, \"digest\"?: str}]")
    ap.add_argument("--repo",               required=True, help="owner/repo")
    ap.add_argument("--run-url",            required=True, help="GitHub Actions run URL")
    ap.add_argument("--date",               required=True, help="Promotion date YYYY-MM-DD")
    ap.add_argument("--days-since-stable",  type=int, default=None,
                    help="Days since last stable release (omit if no prior release)")
    ap.add_argument("--last-release-tag",   default="",
                    help="Tag of last stable release")
    ap.add_argument("--last-release-url",   default="",
                    help="HTML URL of last stable release")
    ap.add_argument("--insertions",       type=int, default=0,
                    help="Insertions in the promotion diff against the target branch")
    ap.add_argument("--deletions",        type=int, default=0,
                    help="Deletions in the promotion diff against the target branch")
    ap.add_argument("--files-json",       default="[]",
                    help="JSON array of changed file paths (relative to repo root)")
    ap.add_argument("--compare-url",        default="",
                    help="GitHub compare URL: .../compare/target...promotion")
    ap.add_argument("--source-tag",         default="testing",
                    help="Source tag being promoted (default: testing)")
    ap.add_argument("--source-branch",      default="testing",
                    help="Branch being promoted (default: testing)")
    ap.add_argument("--target-branch",      default="stable",
                    help="Branch being promoted into (default: stable)")
    ap.add_argument("--maintainer-workflow", default="promote-testing-to-main.yml",
                    help="Workflow file that maintains this PR, for the header line")
    ap.add_argument("--output",             default="pr-body.md")
    args = ap.parse_args()

    variants = json.loads(args.variants_json)
    files    = json.loads(args.files_json)

    sections = [
        _section_header(
            args.project_name, args.date, args.run_url,
            days_ago=args.days_since_stable,
            last_tag=args.last_release_tag or None,
            last_release_url=args.last_release_url or None,
            source_branch=args.source_branch,
            target_branch=args.target_branch,
            maintainer_workflow=args.maintainer_workflow,
        ),
        "",
        _section_gate_placeholder(),
        "",
        _section_variants(variants, args.source_tag),
        "",
        _section_changes(
            files, args.insertions, args.deletions, args.compare_url or None,
            source_branch=args.source_branch,
            target_branch=args.target_branch,
        ),
        "",
        _section_footer(args.repo),
    ]

    body = "\n".join(sections)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(body)

    title = build_title(args.primary_image, args.date,
                        args.source_branch, args.target_branch)
    print(f"PR body written: {args.output} ({len(body):,} chars)")
    print(f"PR title: {title}")


if __name__ == "__main__":
    main()
