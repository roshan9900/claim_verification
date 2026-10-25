# hosted_main.py
import os
from agent_framework import MagenticBuilder, ChatAgent
from agent_framework.openai import OpenAIChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Import your existing tools
from tools import get_document_span, get_claim_verdict, flag_for_manual_review

load_dotenv()

# Foundry-managed models use DefaultAzureCredential, not API keys
client = OpenAIChatClient(
    model_id=os.getenv("AZURE_OPENAI_MODEL", "gpt-4o"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    credential=DefaultAzureCredential(),
)


def build_workflow():
    """Fresh graph + executors per request; STABLE IDs for checkpoint restore."""
    # Build FRESH agents every time — do not reuse instances
    generator = ChatAgent(
        chat_client=client,
        name="DraftGenerator",
        id="draft-generator-agent",          # STABLE
        instructions=(
            "You produce credit report sections. For every factual claim, attach "
            "a citation placeholder [REF: document_id, page]. Mark unsupported "
            "claims as [UNSUPPORTED]."
        ),
        tools=[],
    )

    verifier = ChatAgent(
        chat_client=client,
        name="CitationVerifier",
        id="citation-verifier-agent",        # STABLE
        instructions=(
            "Independently verify each citation. Retrieve the cited span, compare "
            "it to the claim, and return SUPPORTED, MISMATCH, or UNSUPPORTED. "
            "Flag MISMATCH/UNSUPPORTED claims for manual review."
        ),
        tools=[get_document_span, get_claim_verdict, flag_for_manual_review],
    )

    return (
        MagenticBuilder()
        .participants(generator=generator, verifier=verifier)
        .with_standard_manager(
            chat_client=client,
            max_round_count=10,
            max_stall_count=2,
        )
        .with_plan_review(enable=True)
        .with_human_input_on_stall(enable=True)
        # .with_checkpointing(...)  ← REMOVED. The host owns persistence.
        .build()
    )


# The factory is passed to the host server
server = ResponsesHostServer(agent=build_workflow)