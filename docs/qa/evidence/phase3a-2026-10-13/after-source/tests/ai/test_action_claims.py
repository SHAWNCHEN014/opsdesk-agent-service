"""QA-AI-ACTION-01: reviewed narrative must agree with real queue effects."""
import asyncio

import pytest
from sqlalchemy import select

from opsdesk import service as service_module
from opsdesk.contracts import AnswerReview, SupportInput
from opsdesk.orchestration import heuristic_intake, impact_priority
from opsdesk.queueing import ActionWorker
from opsdesk.storage import WorkOrder


@pytest.mark.parametrize("message,draft,replaced", [
    ("My laptop cannot power on. Only I am affected.", "No work order is created for this question. If the issue persists, a work order will be queued.", True),
    ("我的笔记本无法开机。", "此问题无需创建工单。", True),
    ("Please install approved software for me", "A work order has been created.", True),
    ("How do I request system access?", "A work order will be queued.", True),
    ("My laptop cannot power on.", "A work order will be queued. Please record the error.", False),
    ("My laptop cannot power on.", "No work order has been created yet; it will be queued.", False),
    ("How do I request system access?", "No work order is created for this question.", False),
    ("How do I request system access?", "If a real incident occurs, a work order will be queued.", False),
])
def test_action_narrative_and_persisted_side_effects_agree(runtime, monkeypatch, message, draft, replaced):
    config, db, _, service, owner, _ = runtime
    config.model_mode = "ollama"
    class ApprovedModel:
        def __init__(self, config): self.config, self.calls = config, []
        async def ask(self, purpose, instructions, payload, schema=None):
            self.calls.append({"purpose": purpose})
            if purpose == "intake": return heuristic_intake(message)
            if purpose == "priority": return impact_priority(heuristic_intake(message))
            if purpose == "draft": return draft
            return AnswerReview(approved=True, reason="Controlled reviewer approves the inconsistent draft")
    monkeypatch.setattr(service_module, "InferenceGateway", ApprovedModel)
    async def run():
        ids = await service.submit(owner, SupportInput(message=message, request_id="action-contract"))
        await service.tasks[ids["operation_id"]]
        state = service.status(ids["operation_id"], owner)
        worker = ActionWorker(db, config)
        while await worker.step(): pass
        return state
    state = asyncio.run(run());outcome = state["outcome"]
    assert outcome["review"]["replacement_used"] is replaced
    expected = 0 if heuristic_intake(message).intent == "FAQ" else 1
    with db.session() as session:
        assert len(list(session.scalars(select(WorkOrder)))) == expected
    if replaced:
        assert outcome["answer"] != draft and "action policy" in outcome["review"]["reason"]
        assert ("will be queued" in outcome["answer"]) if expected else ("No work order" in outcome["answer"])
    else: assert outcome["answer"] == draft
