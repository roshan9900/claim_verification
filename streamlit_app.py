import asyncio
import os
from typing import Any
from uuid import uuid4

import streamlit as st
from agent_framework import Content
from agent_framework.orchestrations import (
    AgentRequestInfoResponse,
    MagenticPlanReviewRequest,
)

from mock_data import DRAFT_REPORT
from observability import bootstrap_observability
from workflow import build_workflow, checkpoint_storage

bootstrap_observability()


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value

    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text

    contents = getattr(value, "contents", None)
    if contents:
        return "\n".join(
            part if isinstance(part, str) else getattr(part, "text", str(part))
            for part in contents
        )
    return str(value)


def _is_function_approval_request(request: Any) -> bool:
    return (
        isinstance(request.data, Content)
        and request.data.type == "function_approval_request"
    )


async def _run_workflow(
    workflow_name: str,
    task: str | None = None,
    responses: dict[str, Any] | None = None,
    checkpoint_id: str | None = None,
) -> dict[str, Any]:
    workflow = build_workflow(workflow_name)
    if task is not None:
        stream = workflow.run(task, stream=True)
    else:
        if not responses or checkpoint_id is None:
            raise ValueError("Responses and a checkpoint are required to resume.")
        stream = workflow.run(
            responses=responses,
            checkpoint_id=checkpoint_id,
            stream=True,
        )

    output: str | None = None
    pending_requests = []
    failure_details = None
    try:
        async for event in stream:
            if event.type == "request_info":
                pending_requests.append(event)
            elif event.type == "output":
                output = _message_text(event.data)
            elif event.type == "failed":
                failure_details = event.details
    except Exception as exc:
        if failure_details is None:
            raise
        error_type = getattr(failure_details, "error_type", type(exc).__name__)
        message = getattr(failure_details, "message", "") or str(exc)
        raise RuntimeError(f"Workflow failed ({error_type}): {message}") from exc

    if failure_details is not None:
        error_type = getattr(failure_details, "error_type", "WorkflowError")
        message = getattr(failure_details, "message", "") or "No failure details provided."
        raise RuntimeError(f"Workflow failed ({error_type}): {message}")

    if pending_requests:
        checkpoint = await checkpoint_storage.get_latest(workflow_name=workflow_name)
        if checkpoint is None:
            raise RuntimeError(
                "The workflow paused for review but no checkpoint was saved. "
                "Check that CHECKPOINT_DIR is writable."
            )
        missing_request_ids = [
            request.request_id
            for request in pending_requests
            if request.request_id not in checkpoint.pending_request_info_events
        ]
        if missing_request_ids:
            raise RuntimeError(
                "These review requests were not saved in the workflow checkpoint: "
                f"{', '.join(missing_request_ids)}. Keep consuming the stream until it finishes."
            )
        pending_requests = list(checkpoint.pending_request_info_events.values())
        if not pending_requests:
            raise RuntimeError(
                "The workflow emitted review requests, but the checkpoint contains "
                "no requests to answer."
            )
        return {
            "status": "awaiting_review",
            "requests": pending_requests,
            "checkpoint_id": str(checkpoint.checkpoint_id),
        }

    if output is None:
        final_response = await stream.get_final_response()
        outputs = final_response.get_outputs()
        if not outputs:
            raise RuntimeError("The workflow completed without producing an output.")
        output = _message_text(outputs[-1])
    return {"status": "completed", "output": output}


def _apply_result(result: dict[str, Any]) -> None:
    st.session_state.workflow_status = result["status"]
    if result["status"] == "awaiting_review":
        st.session_state.pending_request = result["requests"]
        st.session_state.checkpoint_id = result["checkpoint_id"]
    else:
        st.session_state.pending_request = None
        st.session_state.checkpoint_id = None
        st.session_state.workflow_output = result["output"]


def _reset_workflow() -> None:
    st.session_state.workflow_status = "idle"
    st.session_state.workflow_name = ""
    st.session_state.workflow_output = None
    st.session_state.pending_request = None
    st.session_state.checkpoint_id = None


def _start_run(task: str) -> None:
    st.session_state.workflow_name = f"claim-review-{uuid4().hex}"
    st.session_state.workflow_output = None
    st.session_state.pending_request = None
    st.session_state.checkpoint_id = None
    st.session_state.workflow_status = "running"
    result = asyncio.run(
        _run_workflow(
            workflow_name=st.session_state.workflow_name,
            task=task,
        )
    )
    _apply_result(result)


def _review_response(request: Any, decision: str, feedback: str) -> Any:
    if isinstance(request.data, MagenticPlanReviewRequest):
        if decision == "Approve":
            return request.data.approve()
        if not feedback.strip():
            raise ValueError("Add revision feedback before submitting.")
        return request.data.revise(feedback.strip())
    if _is_function_approval_request(request):
        return request.data.to_function_approval_response(approved=decision == "Approve")
    elif request.response_type is AgentRequestInfoResponse:
        if decision != "Approve":
            raise ValueError("This workflow request only supports approval.")
        return AgentRequestInfoResponse.approve()
    raise ValueError(
    "This workflow request type is not supported by the review UI: "
    f"{request.response_type!r}"
    )


def _submit_review(
    requests: list[Any],
    decisions: dict[str, tuple[str, str]],
) -> None:
    responses = {
        request.request_id: _review_response(
            request,
            *decisions[request.request_id],
        )
        for request in requests
    }
    st.session_state.workflow_status = "running"
    result = asyncio.run(
        _run_workflow(
            workflow_name=st.session_state.workflow_name,
            responses=responses,
            checkpoint_id=st.session_state.checkpoint_id,
        )
    )
    _apply_result(result)


st.set_page_config(page_title="Credit Assessment Review", page_icon="📄", layout="wide")

st.title("Credit Assessment Review")
st.caption(
    "Draft a credit assessment, verify its citations, and review workflow pauses."
)

with st.sidebar:
    st.subheader("Configuration")
    if os.getenv("FOUNDRY_OPENAI_BASE_URL") and os.getenv("FOUNDRY_API_KEY"):
        st.success("Azure AI Foundry endpoint and API key configured")
    elif os.getenv("AZURE_OPENAI_ENDPOINT"):
        st.success("Azure OpenAI endpoint configured")
    elif os.getenv("OPENAI_API_KEY"):
        st.success("OpenAI API key configured")
    else:
        st.warning(
            "Configure Foundry endpoint/key, Azure OpenAI identity, or OPENAI_API_KEY in .env."
        )

    if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        st.success("Application Insights telemetry active")
    st.caption(
        "Workflow checkpoints use local storage. For Azure, mount durable storage "
        "or switch to a shared checkpoint backend before scaling replicas."
    )

if "workflow_status" not in st.session_state:
    st.session_state.workflow_status = "idle"
    st.session_state.workflow_name = ""
    st.session_state.workflow_output = None
    st.session_state.pending_request = None
    st.session_state.checkpoint_id = None
elif "pending_request" not in st.session_state:
    st.session_state.pending_request = None

if st.session_state.workflow_status == "idle":
    with st.form("draft-form"):
        draft = st.text_area("Draft report", value=DRAFT_REPORT, height=300)
        submitted = st.form_submit_button("Verify draft", type="primary")
    if submitted:
        if not draft.strip():
            st.error("Enter a draft report before starting verification.")
        else:
            task = (
                "Generate and verify a credit assessment summary. For every claim, "
                "return an explicit verdict: SUPPORTED, MISMATCH, or UNSUPPORTED. "
                "Flag every MISMATCH or UNSUPPORTED claim for manual review.\n\n"
                f"DRAFT:\n{draft.strip()}"
            )
            with st.spinner("Running the verification workflow..."):
                _start_run(task)

if st.session_state.workflow_status == "running":
    st.info("The workflow is running.")
    if st.button("Restart workflow"):
        _reset_workflow()
        st.rerun()

if st.session_state.workflow_status == "awaiting_review":
    stored_requests = st.session_state.pending_request
    requests = stored_requests if isinstance(stored_requests, list) else [stored_requests]
    requests = [request for request in requests if request is not None]
    st.subheader("Review required")
    if len(requests) > 1:
        st.info(f"{len(requests)} requests are waiting for review.")

    with st.form(f"workflow-review-{st.session_state.workflow_name}"):
        decisions: dict[str, tuple[str, str]] = {}
        for index, request in enumerate(requests, start=1):
            st.markdown(f"#### Request {index} of {len(requests)}")
            is_plan_review = isinstance(request.data, MagenticPlanReviewRequest)
            is_function_approval = _is_function_approval_request(request)

            if is_plan_review:
                st.markdown("**Proposed plan**")
                st.write(_message_text(request.data.plan))
                if request.data.current_progress:
                    with st.expander(f"Progress so far — request {index}"):
                        st.write(request.data.current_progress)
                if request.data.is_stalled:
                    st.warning(
                        "The workflow reports that it is stalled. Review the revised plan carefully."
                    )
                choices = ["Approve", "Revise"]
                default_decision = "Revise" if request.data.is_stalled else "Approve"
            elif is_function_approval:
                function_call = request.data.function_call
                st.markdown("**Tool call approval**")
                st.write(f"Tool: `{function_call.name or 'unknown'}`")
                arguments = function_call.parse_arguments()
                if arguments:
                    st.json(arguments)
                else:
                    st.caption("This tool call has no arguments.")
                choices = ["Approve", "Reject"]
                default_decision = "Approve"
            elif request.response_type is AgentRequestInfoResponse:
                st.write("The workflow is requesting approval to continue.")
                st.write(request.data)
                choices = ["Approve"]
                default_decision = "Approve"
            else:
                st.error(
                    "Unsupported workflow request type: "
                    f"{request.response_type!r}"
                )
                continue

            selected_decision = st.radio(
                "Decision",
                choices,
                index=choices.index(default_decision),
                horizontal=True,
                key=f"review-decision-{request.request_id}",
            )
            feedback = ""
            if is_plan_review:
                feedback = st.text_area(
                    "Revision feedback",
                    disabled=selected_decision != "Revise",
                    key=f"review-feedback-{request.request_id}",
                )
            decisions[request.request_id] = (selected_decision, feedback)

        review_submitted = st.form_submit_button("Submit reviews", type="primary")
    if review_submitted:
        try:
            with st.spinner("Resuming the workflow..."):
                _submit_review(requests, decisions)
        except (RuntimeError, ValueError) as exc:
            st.session_state.workflow_status = "awaiting_review"
            st.error(f"Could not resume the workflow: {exc}")
            st.warning(
                "If this review was paused before the checkpoint fix, discard it "
                "and start a new verification run."
            )
    if st.button("Discard this review and start over"):
        _reset_workflow()
        st.rerun()

if st.session_state.workflow_status == "completed":
    st.subheader("Verification result")
    st.markdown(st.session_state.workflow_output or "_The workflow returned no text output._")
    if st.button("Start a new review"):
        _reset_workflow()
        st.rerun()
