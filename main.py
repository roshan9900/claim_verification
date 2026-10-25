# main.py
"""
LAYER 4 - application control plane + observability bootstrap.

Magentic workflows are EVENT-DRIVEN. You do not call the workflow once and get
an answer. You drive a loop:

    run  ->  collect RequestInfoEvent(s)  ->  decide  ->  run(responses=[...])

The current API resumes a paused run via
`workflow.run(responses={request_id: response}, checkpoint_id=..., stream=True)`.

Human review surfaces are delivered as `request_info` workflow events:
  1. Plan review   -> APPROVE / REVISE
  2. Tool approval -> approve the flagged call
"""

import asyncio
import os
from typing import Any

from dotenv import load_dotenv

from agent_framework.orchestrations import (
    AgentRequestInfoResponse,
    MagenticPlanReviewRequest,
)
from agent_framework.observability import configure_otel_providers

from mock_data import DRAFT_REPORT
from observability import RedactingSpanProcessor, install_log_filter
from workflow import build_workflow, checkpoint_storage

load_dotenv()


# ---------------------------------------------------------------------------
# Observability bootstrap
# ---------------------------------------------------------------------------
def bootstrap_observability() -> None:
    """
    1. Install the log redaction filter (covers the ERROR-log leak path).
    2. Enable MAF instrumentation with sensitive data OFF.
    3. Attach the redacting span processor (covers the span leak path).

    Both layers are needed: the flag alone does not stop exception text.
    """
    install_log_filter(("agent_framework", "agent_framework.observability"))

    configure_otel_providers(
        enable_sensitive_data=os.getenv("ENABLE_SENSITIVE_DATA", "false").lower() == "true"
    )

    try:
        from opentelemetry import trace
        provider = trace.get_tracer_provider()
        if hasattr(provider, "add_span_processor"):
            provider.add_span_processor(RedactingSpanProcessor())
    except Exception as exc:  # pragma: no cover
        print(f"[observability] span processor not attached: {exc}")


# ---------------------------------------------------------------------------
# Event helpers (tolerate both typed events and the newer .type field)
# ---------------------------------------------------------------------------
def is_request_info(event: Any) -> bool:
    return getattr(event, "type", None) == "request_info"


def is_output(event: Any) -> bool:
    return getattr(event, "type", None) == "output" or type(event).__name__ == "WorkflowOutputEvent"


def request_payload(event: Any) -> Any:
    return getattr(event, "data", None)


def request_id(event: Any) -> str:
    return getattr(event, "request_id", "")


# ---------------------------------------------------------------------------
# HITL handlers
# ---------------------------------------------------------------------------
async def handle_intervention(request: Any, response_type: type[Any]) -> Any:
    if isinstance(request, MagenticPlanReviewRequest):
        print("\n" + "=" * 68)
        print("PLAN REVIEW")
        print("=" * 68)
        print(request.plan)
        if request.current_progress:
            print(f"\nProgress: {request.current_progress}")
        choice = input("\nDecision [APPROVE/REVISE]: ").strip().upper()
        if choice == "REVISE":
            comments = input("Revision comments: ").strip()
            if not comments:
                raise ValueError("Revision comments cannot be empty.")
            return request.revise(comments)
        return request.approve()

    if response_type is AgentRequestInfoResponse:
        print("\nThe workflow is requesting approval to continue.")
        choice = input("Approve? [Y/N]: ").strip().upper()
        if choice == "Y":
            return AgentRequestInfoResponse.approve()
        return AgentRequestInfoResponse.from_strings(
            ["The requested action was not approved."]
        )

    raise TypeError(f"Unsupported workflow request type: {type(request).__name__}")


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------
async def main() -> None:
    bootstrap_observability()

    thread_id = "crisil-claim-verification-thread-001"
    workflow = build_workflow(thread_id)
    print("Crisil Claim-Verification Orchestrator (MAF Magentic)")
    print(f"thread_id: {thread_id}")

    task = (
        "Generate and verify a credit assessment summary. The draft is below. "
        "Orchestrate the generator and verifier so that every claim receives an "
        "explicit verdict: SUPPORTED, MISMATCH, or UNSUPPORTED. Flag every "
        "MISMATCH or UNSUPPORTED claim for manual review.\n\n"
        f"DRAFT:\n{DRAFT_REPORT}"
    )

    pending_responses: dict[str, Any] | None = None
    pending_checkpoint: str | None = None
    final_output: Any = None

    while final_output is None:
        # First pass: start the workflow. Later passes: resume it.
        if pending_responses:
            stream = workflow.run(
                responses=pending_responses,
                checkpoint_id=pending_checkpoint,
                stream=True,
            )
        else:
            stream = workflow.run(task, thread_id=thread_id, stream=True)

        pending_responses = None
        pending_request = None
        failure_details = None

        async for event in stream:
            if is_output(event):
                final_output = event
            elif is_request_info(event) and pending_request is None:
                pending_request = event
            elif getattr(event, "type", None) == "failed":
                failure_details = getattr(event, "details", None)
            else:
                data = getattr(event, "data", None)
                if data:
                    print(f"[event] {data}")

        if failure_details is not None:
            error_type = getattr(failure_details, "error_type", "WorkflowError")
            message = getattr(failure_details, "message", "") or "No failure details provided."
            raise RuntimeError(f"Workflow failed ({error_type}): {message}")

        if pending_request is not None:
            reply = await handle_intervention(
                request_payload(pending_request),
                pending_request.response_type,
            )
            pending_responses = {pending_request.request_id: reply}
            checkpoint = await checkpoint_storage.get_latest(workflow_name=thread_id)
            if checkpoint is None:
                raise RuntimeError(
                    "The workflow paused for review but no checkpoint was saved."
                )
            pending_checkpoint = str(checkpoint.checkpoint_id)

    print("\n" + "=" * 68)
    print("FINAL OUTPUT")
    print("=" * 68)
    print(getattr(final_output, "data", final_output))


if __name__ == "__main__":
    asyncio.run(main())