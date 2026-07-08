from datetime import datetime
from typing import Any
from schemas.task import AgentStep, OutputFormat
from schemas.agent_state import AgentState

def create_initial_state(
    task_id: str, 
    task: str, 
    output_format: OutputFormat, 
    user_context: str | None = None
) -> AgentState:
    """
    Builds the initial AgentState dictionary to start a LangGraph run.
    """
    return {
        "task_id": task_id,
        "original_task": task,
        "output_format": output_format,
        "user_context": user_context,
        "plan": [],
        "total_subtasks": 0,
        "subtask_results": [],
        "evidence_chunks": [],
        "current_subtask_index": 0,
        "current_subtask": "",
        "steps_taken": 0,
        "errors": [],
        "retrieved_memories": [],
        "agent_steps": [],
        "total_tokens_used": 0,
        "aggregated_content": "",
        "final_output": None,
        "confidence_score": 0.0,
        "is_complete": False,
        "termination_reason": "",
    }

def make_step(state: AgentState, node_name: str, description: str, metadata: dict[str, Any] | None = None) -> AgentStep:
    """
    Creates a new AgentStep object, automatically calculating the step number.
    """
    # Count existing steps to determine the next step number
    # Since agent_steps is Annotated with operator.add, we look at the current list
    steps = state.get("agent_steps", [])
    step_number = len(steps) + 1
    
    return AgentStep(
        step_number=step_number,
        node_name=node_name,
        description=description,
        timestamp=datetime.utcnow(),
        metadata=metadata or {}
    )
