import os

from dotenv import load_dotenv
from agent_framework import FileCheckpointStorage
from agent_framework.openai import OpenAIChatClient
from agent_framework.orchestrations import MagenticBuilder

from agents import build_agents

load_dotenv()

checkpoint_storage = FileCheckpointStorage(
    storage_path=os.getenv("CHECKPOINT_DIR", "./checkpoints")
)


def _create_chat_client(model: str) -> OpenAIChatClient:
    foundry_base_url = os.getenv("FOUNDRY_OPENAI_BASE_URL")
    if foundry_base_url:
        api_key = os.getenv("FOUNDRY_API_KEY")
        if not api_key:
            raise ValueError(
                "FOUNDRY_API_KEY is required when FOUNDRY_OPENAI_BASE_URL is set."
            )
        return OpenAIChatClient(
            model=model,
            base_url=foundry_base_url,
            api_key=api_key,
        )

    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_endpoint:
        from azure.identity import DefaultAzureCredential

        return OpenAIChatClient(
            model=model,
            azure_endpoint=azure_endpoint,
            credential=DefaultAzureCredential(),
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "Configure OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT before starting a run."
        )
    return OpenAIChatClient(model=model, api_key=api_key)


def build_workflow(workflow_name: str):
    foundry_base_url = os.getenv("FOUNDRY_OPENAI_BASE_URL")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if foundry_base_url:
        default_model = os.getenv("FOUNDRY_MODEL", "gpt-6-luna")
        agent_model = default_model
        manager_model = os.getenv("FOUNDRY_MANAGER_MODEL", default_model)
    elif azure_endpoint:
        agent_model = os.getenv("AZURE_OPENAI_MODEL", "gpt-4o")
        manager_model = os.getenv("AZURE_OPENAI_MANAGER_MODEL", agent_model)
    else:
        agent_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        manager_model = os.getenv("MANAGER_MODEL", "gpt-4o")

    generator, verifier, manager = build_agents(
        _create_chat_client(agent_model),
        _create_chat_client(manager_model),
    )
    return MagenticBuilder(
        name=workflow_name,
        participants=[generator, verifier],
        manager_agent=manager,
        max_round_count=10,
        max_stall_count=2,
        enable_plan_review=True,
        checkpoint_storage=checkpoint_storage,
    ).build()
