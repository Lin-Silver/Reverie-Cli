"""Feedback evolution tool with validated LearningProposal flow."""

from __future__ import annotations

from typing import Any

from .base import BaseTool, ToolResult
from .memory_retrieval import get_memory_os_from_context


class EvolutionFeedbackTool(BaseTool):
    """Record feedback and manage validated learning proposals."""

    name = "evolution_feedback"
    aliases = ("feedback_evolution", "learning_feedback")
    search_hint = "feedback learning proposal evaluate apply workflow memory"
    tool_category = "retrieval"
    tool_tags = ("feedback", "learning", "memory", "evolution")
    read_only = False
    concurrency_safe = False

    description = """Run Reverie's feedback evolution loop.

The pipeline is Observe -> Extract -> Propose -> Evaluate -> Apply. It never directly modifies system prompts or tool strategies. It stores LearningProposal records and only applies validated proposals to workflow memory, tool guidance memory, retrieval ranking memory, or prompt digest memory."""

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["observe", "propose", "evaluate", "apply", "list"],
                "description": "Pipeline action.",
            },
            "feedback": {"type": "string", "description": "Feedback text for observe/propose.", "default": ""},
            "proposal_id": {"type": "string", "description": "LearningProposal id for evaluate/apply.", "default": ""},
            "target": {
                "type": "string",
                "enum": ["workflow_memory", "tool_manifest_guidance", "retrieval_ranking", "prompt_digest"],
                "description": "Validated target memory lane.",
                "default": "workflow_memory",
            },
            "approved": {"type": "boolean", "description": "Whether evaluation approved the proposal.", "default": False},
            "score": {"type": "number", "description": "Replay/eval score from 0 to 1.", "default": 0.0},
            "notes": {"type": "string", "description": "Evaluation notes.", "default": ""},
            "force": {"type": "boolean", "description": "Apply without validation; use only after explicit user confirmation.", "default": False},
        },
        "required": ["action"],
    }

    def execute(self, **kwargs) -> ToolResult:
        action = str(kwargs.get("action") or "").strip().lower()
        memory_os = get_memory_os_from_context(self.context)
        session_id = ""
        agent = self.context.get("agent") if isinstance(self.context, dict) else None
        if agent is not None:
            try:
                session_id = agent._current_session_details("default")[0]
            except Exception:
                session_id = "default"

        if action == "observe":
            feedback = str(kwargs.get("feedback") or "").strip()
            if not feedback:
                return ToolResult.fail("feedback is required for observe")
            proposal = memory_os.evolution.observe_feedback(
                feedback,
                target=str(kwargs.get("target") or "workflow_memory"),
                session_id=session_id,
            )
            return ToolResult.ok(
                "Observed feedback and generated a pending LearningProposal. Evaluate it before apply.\n"
                + self._format_proposal(proposal),
                {"proposal": proposal.to_dict()},
            )
        if action == "propose":
            feedback = str(kwargs.get("feedback") or "").strip()
            if not feedback:
                return ToolResult.fail("feedback is required for propose")
            proposal = memory_os.evolution.propose(
                summary=feedback,
                target=str(kwargs.get("target") or "workflow_memory"),
            )
            return ToolResult.ok(self._format_proposal(proposal), {"proposal": proposal.to_dict()})
        if action == "evaluate":
            proposal_id = str(kwargs.get("proposal_id") or "").strip()
            proposal = memory_os.evolution.evaluate(
                proposal_id,
                approved=self._bool(kwargs.get("approved"), False),
                score=self._float(kwargs.get("score"), 0.0),
                notes=str(kwargs.get("notes") or ""),
            )
            if not proposal:
                return ToolResult.fail(f"LearningProposal not found: {proposal_id}")
            return ToolResult.ok(self._format_proposal(proposal), {"proposal": proposal.to_dict()})
        if action == "apply":
            proposal_id = str(kwargs.get("proposal_id") or "").strip()
            item = memory_os.evolution.apply(
                proposal_id,
                force=self._bool(kwargs.get("force"), False),
            )
            if not item:
                return ToolResult.fail(
                    "LearningProposal was not applied. It must be validated by replay/eval or user confirmation first."
                )
            return ToolResult.ok(f"Applied proposal into MemoryItem {item.id}.", {"memory": item.to_dict()})
        if action == "list":
            proposals = memory_os.evolution.list_proposals(include_applied=True)
            if not proposals:
                return ToolResult.ok("No LearningProposal records found.", {"proposals": []})
            lines = ["# Learning Proposals"]
            lines.extend(self._format_proposal(proposal) for proposal in proposals)
            return ToolResult.ok("\n".join(lines), {"proposals": [proposal.to_dict() for proposal in proposals]})
        return ToolResult.fail("action must be one of observe, propose, evaluate, apply, list")

    @staticmethod
    def _format_proposal(proposal) -> str:
        return (
            f"- {proposal.id} [{proposal.status}] target={proposal.target} "
            f"type={proposal.proposal_type}: {proposal.summary}"
        )

    @staticmethod
    def _bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on", "approved"}

    @staticmethod
    def _float(value: Any, default: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(0.0, min(parsed, 1.0))
