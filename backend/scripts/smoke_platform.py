"""Smoke sem banco para Windows/macOS no CI: importa o app e exercita a lógica pura mais sensível a plataforma."""

from __future__ import annotations

import os
import shlex

os.environ.setdefault("TRACKER_NO_DOTENV", "1")

import tracker.main  # noqa: F401
from tracker.integrations.claude.client import ClaudeCodeClient, find_claude_code
from tracker.modules.jobs.relevance import location_ok
from tracker.modules.resumes.content import category_key

assert location_ok("São Paulo, SP", brazilian_company=False)
assert not location_ok("Remote - USA", brazilian_company=False)
assert category_key("Engenharia de Dados") == "data_engineering"
result, sources = ClaudeCodeClient.parse_stream(
    '{"type":"user","message":{"content":[{"type":"tool_result","content":"Links: [{\\"title\\":\\"A\\",\\"url\\":\\"https://a.com\\"}]"}]}}\n'
    '{"type":"result","is_error":false,"structured_output":{"ok":true}}'
)
assert result and result["structured_output"] == {"ok": True} and sources[0]["url"] == "https://a.com"
cmd = r"C:\Program Files\tectonic\tectonic.exe" if os.name == "nt" else "/usr/local/bin/tectonic"
assert shlex.split(f'"{cmd}"' if os.name == "nt" else cmd, posix=os.name != "nt")[0].strip('"') == cmd
print("smoke ok · claude:", find_claude_code() or "não instalado (ok no CI)")
