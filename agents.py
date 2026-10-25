from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

from tools import flag_for_manual_review, get_claim_verdict, get_document_span


def build_agents(
    agent_client: OpenAIChatClient,
    manager_client: OpenAIChatClient,
) -> tuple[Agent, Agent, Agent]:
    draft_generator = Agent(
        client=agent_client,
        name="DraftGenerator",
        id="draft-generator-agent",
        instructions=(
            "You produce credit report sections. For every factual claim, attach "
            "a citation placeholder in the format [REF: document_id, page]. If you "
            "cannot find a source, mark the claim as [UNSUPPORTED]."
        ),
    )

    citation_verifier = Agent(
        client=agent_client,
        name="CitationVerifier",
        id="citation-verifier-agent",
        instructions=(
            "Independently verify each citation in a draft report. For each "
            "cited claim, retrieve the cited span, compare it against the claim, "
            "and return a structured verdict of SUPPORTED, MISMATCH, or "
            "UNSUPPORTED. Call flag_for_manual_review for MISMATCH or "
            "UNSUPPORTED claims."
        ),
        tools=[get_document_span, get_claim_verdict, flag_for_manual_review],
    )

    manager = Agent(
        client=manager_client,
        name="MagenticManager",
        id="magentic-manager-agent",
        instructions="Coordinate the participants to complete the user's task.",
    )

    return draft_generator, citation_verifier, manager
