"""CLI utility functions."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import click

from ..config import get_config


def parse_tags(tags: Optional[str]) -> Optional[list[str]]:
    """Parse comma-separated tags string."""
    if not tags:
        return None
    return [t.strip() for t in tags.split(",") if t.strip()]


def show_feedback_reminder():
    """Show a reminder to submit feedback after search commands."""
    config = get_config()
    if config.suggest_feedback:
        click.echo()
        click.secho(
            "Tip: Help improve ai-lessons! When done searching, run:",
            dim=True,
        )
        click.secho(
            '  ai-lessons contribute feedback -t "your goal" -q "queries;used" -n <# of searches>',
            dim=True,
        )


def get_git_root(path: Path) -> Optional[Path]:
    """Get the git repository root for a path, if it's in a git repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(path.parent), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def find_common_ancestor(paths: list[Path]) -> Path:
    """Find the highest-level shared directory among paths."""
    if len(paths) == 1:
        return paths[0].parent

    # Get all parts for each path
    all_parts = [p.resolve().parts for p in paths]

    # Find common prefix
    common_parts = []
    for parts in zip(*all_parts):
        if len(set(parts)) == 1:
            common_parts.append(parts[0])
        else:
            break

    if common_parts:
        return Path(*common_parts)
    return Path("/")


def determine_root_dir(paths: list[Path], explicit_root: Optional[str]) -> Path:
    """Determine the root directory for title generation.

    Priority:
    1. Explicit --root if provided
    2. Git repo root (if first file is in a git repo)
    3. Common ancestor directory (multiple files)
    4. Parent directory (single file)
    """
    if explicit_root:
        return Path(explicit_root).resolve()

    # Try git root from first file
    git_root = get_git_root(paths[0])
    if git_root:
        return git_root

    # Fall back to common ancestor or parent
    return find_common_ancestor(paths)


def warn_deprecation(old_cmd: str, new_cmd: str):
    """Show a deprecation warning for old commands."""
    click.secho(
        f"DEPRECATION WARNING: '{old_cmd}' is deprecated. Use '{new_cmd}' instead.",
        fg="yellow",
        err=True,
    )
    click.echo()


def generate_title(path: Path, root_dir: Path) -> str:
    """Generate a title from a path relative to root_dir.

    Title format: root_dir.name / relative_path
    Example: jira-cloud-rest-api/v3/Apis/IssueVotesApi.md
    """
    abs_path = path.resolve()
    try:
        relative = abs_path.relative_to(root_dir)
        return f"{root_dir.name}/{relative}"
    except ValueError:
        # Path is not under root_dir, use filename
        return abs_path.name
