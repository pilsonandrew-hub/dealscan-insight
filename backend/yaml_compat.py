"""Minimal YAML compatibility layer for simple project config files."""

from __future__ import annotations

from typing import Any


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    try:
        if any(token in value for token in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value


def _clean_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        lines.append((indent, raw_line.strip()))
    return lines


def _parse_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index

    current_indent, current_text = lines[index]
    if current_indent != indent:
        raise ValueError(f"Unexpected indentation at line: {current_text}")

    if current_text.startswith("- "):
        items: list[Any] = []
        while index < len(lines):
            line_indent, text = lines[index]
            if line_indent < indent:
                break
            if line_indent != indent or not text.startswith("- "):
                break

            item_text = text[2:].strip()
            index += 1

            if not item_text:
                if index < len(lines) and lines[index][0] > indent:
                    value, index = _parse_block(lines, index, lines[index][0])
                    items.append(value)
                else:
                    items.append(None)
                continue

            if ":" in item_text:
                key, raw_value = item_text.split(":", 1)
                item: dict[str, Any] = {}
                raw_value = raw_value.strip()
                if raw_value:
                    item[key.strip()] = _parse_scalar(raw_value)
                elif index < len(lines) and lines[index][0] > indent:
                    value, index = _parse_block(lines, index, lines[index][0])
                    item[key.strip()] = value
                else:
                    item[key.strip()] = {}

                if index < len(lines) and lines[index][0] > indent and not lines[index][1].startswith("- "):
                    extra, index = _parse_block(lines, index, lines[index][0])
                    if isinstance(extra, dict):
                        item.update(extra)
                items.append(item)
                continue

            items.append(_parse_scalar(item_text))

        return items, index

    mapping: dict[str, Any] = {}
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent < indent:
            break
        if line_indent != indent or text.startswith("- "):
            break

        key, raw_value = text.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        index += 1

        if raw_value:
            mapping[key] = _parse_scalar(raw_value)
            continue

        if index < len(lines) and lines[index][0] > indent:
            value, index = _parse_block(lines, index, lines[index][0])
            mapping[key] = value
        else:
            mapping[key] = {}

    return mapping, index


def safe_load(stream: Any) -> Any:
    text = stream.read() if hasattr(stream, "read") else str(stream)
    lines = _clean_lines(text)
    if not lines:
        return {}
    result, _ = _parse_block(lines, 0, lines[0][0])
    return result
