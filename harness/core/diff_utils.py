"""Diff utilities for previewing code changes before applying them.

This module provides functions to generate unified diffs between strings
or files, enabling users to review changes before they are applied.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any


def generate_unified_diff(
    old: str,
    new: str,
    fromfile: str = "original",
    tofile: str = "modified",
    fromfiledate: str = "",
    tofiledate: str = "",
    context_lines: int = 3,
) -> str:
    """Generate a unified diff between two strings.

    Args:
        old: The original content.
        new: The new content.
        fromfile: Label for the original file.
        tofile: Label for the modified file.
        fromfiledate: Optional date string for the original file.
        tofiledate: Optional date string for the modified file.
        context_lines: Number of context lines to show.

    Returns:
        A unified diff string.
    """
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    kwargs: dict[str, Any] = {
        "fromfile": fromfile,
        "tofile": tofile,
        "n": context_lines,
    }
    if fromfiledate:
        kwargs["fromfiledate"] = fromfiledate
    if tofiledate:
        kwargs["tofiledate"] = tofiledate

    diff = difflib.unified_diff(old_lines, new_lines, **kwargs)

    return "".join(diff)


def generate_file_diff(
    file_path: Path,
    new_content: str,
    context_lines: int = 3,
) -> str:
    """Generate a unified diff between a file's current content and new content.

    Args:
        file_path: Path to the file.
        new_content: The new content to compare against.
        context_lines: Number of context lines to show.

    Returns:
        A unified diff string, or empty string if file doesn't exist.
    """
    if not file_path.exists():
        # File is new, show as creation
        return generate_unified_diff(
            "",
            new_content,
            fromfile="/dev/null",
            tofile=str(file_path),
            context_lines=context_lines,
        )

    old_content = file_path.read_text(encoding="utf-8", errors="replace")
    return generate_unified_diff(
        old_content,
        new_content,
        fromfile=str(file_path),
        tofile=str(file_path),
        context_lines=context_lines,
    )


def diff_summary(diff: str) -> dict[str, Any]:
    """Generate a summary of changes from a diff.

    Args:
        diff: A unified diff string.

    Returns:
        A dictionary with summary statistics.
    """
    lines_added = 0
    lines_removed = 0
    lines_changed = 0

    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            lines_added += 1
        elif line.startswith("-") and not line.startswith("---"):
            lines_removed += 1

    # Changed lines are roughly the minimum of added/removed
    lines_changed = min(lines_added, lines_removed)
    lines_added -= lines_changed
    lines_removed -= lines_changed

    return {
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "lines_changed": lines_changed,
        "total_changes": lines_added + lines_removed + lines_changed,
    }


def is_significant_change(diff: str, threshold: int = 10) -> bool:
    """Determine if a diff represents a significant change.

    Args:
        diff: A unified diff string.
        threshold: Minimum number of changed lines to be considered significant.

    Returns:
        True if the change is significant, False otherwise.
    """
    summary = diff_summary(diff)
    return summary["total_changes"] >= threshold


def format_diff_for_display(diff: str) -> str:
    """Format a diff for display in a terminal or UI.

    This adds ANSI color codes for better readability.

    Args:
        diff: A unified diff string.

    Returns:
        A formatted diff string with color codes.
    """
    if not diff:
        return "No changes."

    lines = diff.splitlines()
    formatted = []

    for line in lines:
        if line.startswith("+++"):
            formatted.append(f"\033[32m{line}\033[0m")  # Green for new file
        elif line.startswith("---"):
            formatted.append(f"\033[31m{line}\033[0m")  # Red for old file
        elif line.startswith("+"):
            formatted.append(f"\033[32m{line}\033[0m")  # Green for additions
        elif line.startswith("-"):
            formatted.append(f"\033[31m{line}\033[0m")  # Red for deletions
        elif line.startswith("@@"):
            formatted.append(f"\033[36m{line}\033[0m")  # Cyan for hunk headers
        else:
            formatted.append(line)

    return "\n".join(formatted)


def apply_diff_to_string(original: str, diff: str) -> str:
    """Apply a unified diff to a string.

    Args:
        original: The original string.
        diff: A unified diff string.

    Returns:
        The modified string after applying the diff.

    Raises:
        ValueError: If the diff cannot be applied.
    """
    # This is a simplified implementation
    # For production, consider using a library like patch.py
    original_lines = original.splitlines(keepends=True)
    result_lines = original_lines.copy()

    # Parse the diff and apply changes
    # This is a basic implementation - may not handle all edge cases
    diff_lines = diff.splitlines()
    i = 0
    while i < len(diff_lines):
        line = diff_lines[i]
        if line.startswith("@@"):
            # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
            try:
                parts = line.split()
                old_part = parts[1]
                new_part = parts[2]

                old_start = int(old_part.split(",")[0].lstrip("-"))
                new_start = int(new_part.split(",")[0].lstrip("+"))

                # Skip to the actual diff content
                i += 1
                old_idx = old_start - 1
                new_idx = new_start - 1

                # Process the hunk
                while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
                    diff_line = diff_lines[i]
                    if diff_line.startswith("+"):
                        # Addition
                        result_lines.insert(new_idx, diff_line[1:] + "\n")
                        new_idx += 1
                    elif diff_line.startswith("-"):
                        # Deletion
                        if old_idx < len(result_lines):
                            result_lines.pop(old_idx)
                    elif diff_line.startswith(" "):
                        # Context line - no change
                        old_idx += 1
                        new_idx += 1
                    i += 1
            except (IndexError, ValueError) as e:
                raise ValueError(f"Failed to parse diff hunk: {e}")
        else:
            i += 1

    return "".join(result_lines)
