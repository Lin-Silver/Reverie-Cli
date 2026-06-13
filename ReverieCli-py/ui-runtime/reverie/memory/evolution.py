"""Feedback evolution pipeline with explicit validation before apply."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_store import EventStore
from .models import LearningProposal, MemoryItem, new_id, utc_now
from .store import MemoryStore


class EvolutionFeedbackPipeline:
    """Observe -> Extract -> Propose -> Evaluate -> Apply."""

    VALID_TARGETS = {
        "workflow_memory",
        "tool_manifest_guidance",
        "retrieval_ranking",
        "prompt_digest",
    }

    def __init__(self, project_data_dir: Path, event_store: EventStore, memory_store: MemoryStore):
        self.project_data_dir = Path(project_data_dir)
        self.memory_dir = self.project_data_dir / "memory"
        self.proposals_path = self.memory_dir / "learning_proposals.json"
        self.event_store = event_store
        self.memory_store = memory_store
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def observe_feedback(
        self,
        feedback: str,
        *,
        target: str = "workflow_memory",
        session_id: str = "",
        implicit: bool = False,
    ) -> LearningProposal:
        event = self.event_store.append(
            "implicit_feedback" if implicit else "explicit_feedback",
            {"feedback": feedback, "target": target},
            actor="user" if not implicit else "runtime",
            session_id=session_id,
            tags=["feedback", target],
        )
        return self.propose(
            summary=str(feedback or "").strip(),
            target=target,
            evidence=[{"event_id": event.id, "event_type": event.event_type}],
        )

    def propose(
        self,
        *,
        summary: str,
        target: str = "workflow_memory",
        proposal_type: str = "workflow_memory",
        evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> LearningProposal:
        normalized_target = str(target or "workflow_memory").strip().lower()
        if normalized_target not in self.VALID_TARGETS:
            normalized_target = "workflow_memory"
        proposal = LearningProposal(
            id=new_id("learn"),
            proposal_type=str(proposal_type or normalized_target),
            summary=str(summary or "").strip(),
            target=normalized_target,
            evidence=list(evidence or []),
            status="pending_validation",
            metadata={
                "pipeline": "Observe -> Extract -> Propose -> Evaluate -> Apply",
                "requires_validation": True,
                "safety": "Does not directly modify system prompts or tool strategies.",
            },
        )
        proposals = self.list_proposals(include_applied=True)
        proposals.append(proposal)
        self._save(proposals)
        return proposal

    def evaluate(
        self,
        proposal_id: str,
        *,
        approved: bool = False,
        score: Optional[float] = None,
        method: str = "user_confirmation",
        notes: str = "",
    ) -> Optional[LearningProposal]:
        proposals = self.list_proposals(include_applied=True)
        for proposal in proposals:
            if proposal.id != str(proposal_id or "").strip():
                continue
            numeric_score = float(score) if score is not None else (1.0 if approved else 0.0)
            proposal.evaluation = {
                "method": str(method or "user_confirmation"),
                "approved": bool(approved),
                "score": numeric_score,
                "notes": str(notes or ""),
                "evaluated_at": utc_now(),
            }
            proposal.status = "validated" if approved or numeric_score >= 0.7 else "rejected"
            proposal.updated_at = utc_now()
            self._save(proposals)
            return proposal
        return None

    def apply(self, proposal_id: str, *, force: bool = False) -> Optional[MemoryItem]:
        proposals = self.list_proposals(include_applied=True)
        for proposal in proposals:
            if proposal.id != str(proposal_id or "").strip():
                continue
            if proposal.status not in {"validated", "applied"} and not force:
                return None
            memory_type = {
                "workflow_memory": "success_workflow",
                "tool_manifest_guidance": "tool_guidance",
                "retrieval_ranking": "retrieval_ranking",
                "prompt_digest": "prompt_digest",
            }.get(proposal.target, "success_workflow")
            item = MemoryItem(
                id=new_id("mem"),
                scope="workflow" if proposal.target != "prompt_digest" else "procedural",
                memory_type=memory_type,
                content=f"Validated learning proposal ({proposal.target}): {proposal.summary}",
                evidence=list(proposal.evidence or []),
                confidence=0.9 if proposal.status == "validated" else 0.72,
                tags=["learning", proposal.target],
                decay=0.01,
                source_event_ids=[
                    str(evidence.get("event_id"))
                    for evidence in proposal.evidence
                    if isinstance(evidence, dict) and evidence.get("event_id")
                ],
                metadata={"learning_proposal_id": proposal.id},
            )
            stored = self.memory_store.upsert(item)
            proposal.status = "applied"
            proposal.applied_memory_id = stored.id
            proposal.updated_at = utc_now()
            self._save(proposals)
            self.event_store.append(
                "learning_proposal_applied",
                {
                    "proposal_id": proposal.id,
                    "memory_id": stored.id,
                    "target": proposal.target,
                },
                actor="memory_os",
                tags=["learning", "applied"],
            )
            return stored
        return None

    def list_proposals(self, *, include_applied: bool = False) -> List[LearningProposal]:
        if not self.proposals_path.exists():
            return []
        try:
            payload = json.loads(self.proposals_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        raw_items = payload.get("proposals") if isinstance(payload, dict) else []
        proposals = [
            LearningProposal.from_dict(item)
            for item in raw_items
            if isinstance(item, dict)
        ]
        if include_applied:
            return proposals
        return [item for item in proposals if item.status != "applied"]

    def _save(self, proposals: List[LearningProposal]) -> None:
        payload = {
            "updated_at": utc_now(),
            "proposals": [proposal.to_dict() for proposal in proposals],
        }
        temp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.memory_dir),
                prefix=f".{self.proposals_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            temp_path.replace(self.proposals_path)
        finally:
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
