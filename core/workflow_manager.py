"""Workflow manager for orchestrating multi-stage profiling pipelines.

Tracks workflow state through PENDING → RUNNING → SUCCESS/FAILED transitions.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class WorkflowState(str, Enum):
    """Workflow execution states."""
    
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Result from a single pipeline stage."""
    
    stage_name: str
    state: WorkflowState
    start_time: float
    end_time: float | None = None
    duration: float = 0.0
    error: str | None = None
    output: dict[str, Any] = field(default_factory=dict)
    
    def mark_success(self, output: dict[str, Any] | None = None) -> None:
        """Mark stage as successful."""
        self.state = WorkflowState.SUCCESS
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        if output:
            self.output = output
    
    def mark_failed(self, error: str) -> None:
        """Mark stage as failed."""
        self.state = WorkflowState.FAILED
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.error = error
    
    def mark_skipped(self, reason: str = "") -> None:
        """Mark stage as skipped."""
        self.state = WorkflowState.SKIPPED
        self.end_time = time.time()
        self.duration = 0.0
        self.error = reason
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class WorkflowExecution:
    """Complete workflow execution tracking."""
    
    workflow_id: str
    workflow_name: str
    started_at: str
    stages: list[StageResult] = field(default_factory=list)
    completed_at: str | None = None
    total_duration: float = 0.0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_duration": self.total_duration,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "skipped_count": self.skipped_count,
            "stages": [s.to_dict() for s in self.stages],
        }


class WorkflowManager:
    """Manages multi-stage workflow execution with state tracking."""
    
    # Standard pipeline stages
    STANDARD_PIPELINE = [
        "intake",
        "format",
        "standardization",
        "profile",
        "quality",
        "pk",
        "relationship",
        "enrichment",
        "lcil",
        "er",
        "dbml",
        "charts",
        "tree",
        "ui_refresh",
    ]
    
    def __init__(self, workflow_dir: Path | None = None):
        """Initialize workflow manager.
        
        Args:
            workflow_dir: Directory for workflow state (default: output/workflows/)
        """
        self.workflow_dir = workflow_dir or Path("output/workflows")
        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        self.current_execution: WorkflowExecution | None = None
    
    def start_workflow(self, workflow_name: str = "full_pipeline") -> str:
        """Start a new workflow execution.
        
        Args:
            workflow_name: Name of the workflow
            
        Returns:
            Workflow ID
        """
        import uuid
        
        workflow_id = str(uuid.uuid4())[:8]
        self.current_execution = WorkflowExecution(
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            started_at=datetime.now().isoformat(),
        )
        
        return workflow_id
    
    def start_stage(self, stage_name: str) -> StageResult:
        """Start a pipeline stage.
        
        Args:
            stage_name: Name of the stage
            
        Returns:
            StageResult object
        """
        if self.current_execution is None:
            self.start_workflow()
        
        stage = StageResult(
            stage_name=stage_name,
            state=WorkflowState.RUNNING,
            start_time=time.time(),
        )
        
        self.current_execution.stages.append(stage)
        self._save_state()
        
        return stage
    
    def complete_stage(
        self,
        stage: StageResult,
        success: bool = True,
        output: dict[str, Any] | None = None,
        error: str | None = None
    ) -> None:
        """Complete a pipeline stage.
        
        Args:
            stage: StageResult to update
            success: Whether stage succeeded
            output: Optional output data
            error: Optional error message
        """
        if success:
            stage.mark_success(output or {})
            self.current_execution.success_count += 1
        else:
            stage.mark_failed(error or "Unknown error")
            self.current_execution.failed_count += 1
        
        self._save_state()
    
    def skip_stage(self, stage_name: str, reason: str = "") -> None:
        """Skip a pipeline stage.
        
        Args:
            stage_name: Name of the stage
            reason: Reason for skipping
        """
        if self.current_execution is None:
            self.start_workflow()
        
        stage = StageResult(
            stage_name=stage_name,
            state=WorkflowState.SKIPPED,
            start_time=time.time(),
        )
        stage.mark_skipped(reason)
        
        self.current_execution.stages.append(stage)
        self.current_execution.skipped_count += 1
        
        self._save_state()
    
    def complete_workflow(self) -> WorkflowExecution:
        """Complete the current workflow.
        
        Returns:
            Completed WorkflowExecution
        """
        if self.current_execution is None:
            raise RuntimeError("No active workflow")
        
        self.current_execution.completed_at = datetime.now().isoformat()
        
        # Calculate total duration
        if self.current_execution.stages:
            start_times = [s.start_time for s in self.current_execution.stages]
            end_times = [s.end_time for s in self.current_execution.stages if s.end_time]
            
            if start_times and end_times:
                self.current_execution.total_duration = max(end_times) - min(start_times)
        
        self._save_state()
        
        return self.current_execution
    
    def get_current_state(self) -> dict[str, Any]:
        """Get current workflow state.
        
        Returns:
            Dictionary with workflow state
        """
        if self.current_execution is None:
            return {"status": "no_active_workflow"}
        
        return self.current_execution.to_dict()
    
    def execute_full_pipeline(
        self,
        stages: list[tuple[str, Callable[[], dict[str, Any]]]] | None = None
    ) -> WorkflowExecution:
        """Execute a full pipeline with automatic stage tracking.
        
        Args:
            stages: List of (stage_name, stage_function) tuples
            
        Returns:
            Completed WorkflowExecution
        """
        workflow_id = self.start_workflow("full_pipeline")
        
        if stages is None:
            raise ValueError("No stages provided")
        
        for stage_name, stage_func in stages:
            stage = self.start_stage(stage_name)
            
            try:
                output = stage_func()
                self.complete_stage(stage, success=True, output=output)
            except Exception as e:
                self.complete_stage(stage, success=False, error=str(e))
                # Continue with remaining stages even if one fails
        
        return self.complete_workflow()
    
    def _save_state(self) -> None:
        """Save current workflow state to disk."""
        if self.current_execution is None:
            return
        
        state_file = self.workflow_dir / f"{self.current_execution.workflow_id}.json"
        state_file.write_text(
            json.dumps(self.current_execution.to_dict(), indent=2),
            encoding="utf-8"
        )
    
    def load_workflow(self, workflow_id: str) -> WorkflowExecution | None:
        """Load a workflow by ID.
        
        Args:
            workflow_id: Workflow ID
            
        Returns:
            WorkflowExecution or None if not found
        """
        state_file = self.workflow_dir / f"{workflow_id}.json"
        
        if not state_file.exists():
            return None
        
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            
            # Reconstruct WorkflowExecution
            stages = [
                StageResult(
                    stage_name=s["stage_name"],
                    state=WorkflowState(s["state"]),
                    start_time=s["start_time"],
                    end_time=s.get("end_time"),
                    duration=s.get("duration", 0.0),
                    error=s.get("error"),
                    output=s.get("output", {}),
                )
                for s in data.get("stages", [])
            ]
            
            execution = WorkflowExecution(
                workflow_id=data["workflow_id"],
                workflow_name=data["workflow_name"],
                started_at=data["started_at"],
                completed_at=data.get("completed_at"),
                total_duration=data.get("total_duration", 0.0),
                success_count=data.get("success_count", 0),
                failed_count=data.get("failed_count", 0),
                skipped_count=data.get("skipped_count", 0),
                stages=stages,
            )
            
            return execution
            
        except Exception:
            return None
    
    def list_workflows(self) -> list[dict[str, Any]]:
        """List all workflows.
        
        Returns:
            List of workflow summaries
        """
        workflows = []
        
        for state_file in self.workflow_dir.glob("*.json"):
            try:
                data = json.loads(state_file.read_text(encoding="utf-8"))
                workflows.append({
                    "workflow_id": data["workflow_id"],
                    "workflow_name": data["workflow_name"],
                    "started_at": data["started_at"],
                    "completed_at": data.get("completed_at"),
                    "success_count": data.get("success_count", 0),
                    "failed_count": data.get("failed_count", 0),
                })
            except Exception:
                continue
        
        # Sort by start time descending
        workflows.sort(key=lambda w: w["started_at"], reverse=True)
        
        return workflows
