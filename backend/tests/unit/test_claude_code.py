"""Backend de IA via Claude Code (`claude -p`) com um CLI falso que emite stream-json."""

from __future__ import annotations

import base64
import json
import stat
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from tracker.core.config import get_settings
from tracker.integrations.claude import client as ai
from tracker.modules.platform.models import AiCall

FAKE_CLI = r"""#!{python}
import json, sys, pathlib
args = sys.argv[1:]
prompt = sys.stdin.read()
log = pathlib.Path({log!r})
log.write_text(json.dumps({{"args": args, "prompt": prompt, "files": sorted(p.name for p in pathlib.Path.cwd().iterdir())}}))
def emit(e): print(json.dumps(e))
emit({{"type": "system", "subtype": "init"}})
if "WebSearch" in args[args.index("--tools") + 1]:
    emit({{"type": "assistant", "message": {{"content": [{{"type": "tool_use", "name": "WebSearch", "input": {{"query": "x"}}}}]}}}})
    links = '[{{"title":"Hist\\u00f3ria \\"oficial\\"","url":"https://exemplo.com/sobre"}},{{"title":"B","url":"https://b.com"}}]'
    emit({{"type": "user", "message": {{"content": [{{"type": "tool_result", "content": "Web search results\n\nLinks: " + links}}]}}}})
    emit({{"type": "assistant", "message": {{"content": [{{"type": "tool_use", "name": "WebFetch", "input": {{"url": "https://c.com/x"}}}}]}}}})
if "ERRO" in prompt:
    emit({{"type": "result", "subtype": "error_during_execution", "is_error": True, "result": "boom"}})
else:
    emit({{"type": "result", "subtype": "success", "is_error": False, "structured_output": {{"label": "ok", "n": 3}},
          "usage": {{"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100}}}})
"""


class Out(BaseModel):
    label: str
    n: int


@pytest.fixture
def fake_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    log = tmp_path / "call.json"
    cli = tmp_path / "claude"
    cli.write_text(FAKE_CLI.format(python=sys.executable, log=str(log)))
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(get_settings(), "claude_code_cmd", str(cli))
    return log


async def test_structured_output_and_args(sessionmaker, fake_cli: Path) -> None:
    c = ai.ClaudeCodeClient(sessionmaker)
    res = await c.structured(ai.AIRequest(task="email.classify", system="SYS", user="<email>oi</email>", effort="low"), Out)
    assert res.output == Out(label="ok", n=3) and res.cost_usd == 0.0
    call = json.loads(fake_cli.read_text())
    args = call["args"]
    assert args[args.index("--tools") + 1] == ""  # sem ferramentas por padrão
    assert args[args.index("--effort") + 1] == "low"
    assert json.loads(args[args.index("--json-schema") + 1])["required"] == ["label", "n"]
    assert "--no-session-persistence" in args and call["prompt"] == "<email>oi</email>"
    assert "system.md" in call["files"]
    async with sessionmaker() as s:
        row = await s.scalar(select(AiCall).where(AiCall.task == "email.classify"))
    assert row is not None and row.model.endswith("(claude-code)") and row.cache_read_tokens == 100 and row.error is None


async def test_web_tools_collect_real_sources(sessionmaker, fake_cli: Path) -> None:
    res = await ai.ClaudeCodeClient(sessionmaker).structured(
        ai.AIRequest(task="company.profile", system="S", user="Empresa X", tools=[ai.WEB_SEARCH_TOOL, ai.WEB_FETCH_TOOL]), Out
    )
    args = json.loads(fake_cli.read_text())["args"]
    assert args[args.index("--tools") + 1] == "WebSearch,WebFetch"
    assert {"WebSearch", "WebFetch"} <= set(args[args.index("--allowedTools") + 1 :])
    assert [s["url"] for s in res.sources] == ["https://exemplo.com/sobre", "https://b.com", "https://c.com/x"]
    assert res.sources[0]["title"] == 'História "oficial"'


async def test_pdf_attachment_becomes_file_with_read_tool(sessionmaker, fake_cli: Path) -> None:
    pdf = base64.b64encode(b"%PDF-1.4 x").decode()
    user = [
        {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf}},
        {"type": "text", "text": "Extraia o perfil."},
    ]
    await ai.ClaudeCodeClient(sessionmaker).structured(ai.AIRequest(task="profile.extract", system="S", user=user), Out)
    call = json.loads(fake_cli.read_text())
    assert "anexo_1.pdf" in call["files"] and "./anexo_1.pdf" in call["prompt"]
    assert call["args"][call["args"].index("--tools") + 1] == "Read"


async def test_error_is_recorded(sessionmaker, fake_cli: Path) -> None:
    with pytest.raises(ai.AIError, match="boom"):
        await ai.ClaudeCodeClient(sessionmaker).structured(ai.AIRequest(task="t.err", system="S", user="ERRO"), Out)
    async with sessionmaker() as s:
        row = await s.scalar(select(AiCall).where(AiCall.task == "t.err"))
    assert row is not None and "boom" in (row.error or "")


def test_backend_selection(sessionmaker, fake_cli: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(ai, "_override", None)  # o conftest instala um FakeAIClient global
    monkeypatch.setattr(s, "ai_fake", False)
    monkeypatch.setattr(s, "anthropic_api_key", None)
    assert isinstance(ai.get_ai(sessionmaker), ai.ClaudeCodeClient)  # auto sem chave → Claude Code
    monkeypatch.setattr(s, "anthropic_api_key", "sk-ant-test")
    assert isinstance(ai.get_ai(sessionmaker), ai.ClaudeClient)  # auto com chave → API
    monkeypatch.setattr(s, "ai_backend", "claude_code")
    assert isinstance(ai.get_ai(sessionmaker), ai.ClaudeCodeClient)
