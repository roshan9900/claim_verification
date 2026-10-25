# Credit Assessment Review

A demo credit-assessment workflow built with Microsoft's Agent Framework. It coordinates a draft generator and citation verifier, labels claims as `SUPPORTED`, `MISMATCH`, or `UNSUPPORTED`, and pauses for human review when the workflow needs approval.

> **Demo only:** The included documents and claim-verification data are hard-coded examples in `mock_data.py`. This project does not ingest or verify real credit reports, and its sample outputs are not financial advice.

## Features

- Streamlit interface for submitting a draft and reviewing workflow pauses.
- Generator, citation verifier, and Magentic manager agents.
- Human review for proposed plans and approval requests.
- File-backed workflow checkpoints, configurable with `CHECKPOINT_DIR`.
- Optional OpenTelemetry export with financial-value redaction.
- OpenAI, Azure OpenAI, and Azure AI Foundry endpoint configuration.

## Requirements

- Python 3.13 (the Docker image is based on Python 3.13).
- Credentials for one supported model provider.

## Run locally

In PowerShell, from the project directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and configure **one** model provider, then start the app:

```powershell
streamlit run streamlit_app.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`). The app starts with a sample draft; submit it to run verification, then review any workflow requests shown in the interface.

### Model provider configuration

The workflow selects a provider in this order: Azure AI Foundry, Azure OpenAI, then OpenAI. Configure only the provider you intend to use.

**OpenAI**

```dotenv
OPENAI_API_KEY=your-openai-api-key
LLM_MODEL=gpt-4o-mini
MANAGER_MODEL=gpt-4o
```

**Azure OpenAI**

```dotenv
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_MODEL=gpt-4o
AZURE_OPENAI_MANAGER_MODEL=gpt-4o
```

Azure OpenAI authentication uses `DefaultAzureCredential` from `azure-identity`; sign in or configure an Azure identity supported by that library before running the app.

**Azure AI Foundry (OpenAI-compatible endpoint)**

```dotenv
FOUNDRY_OPENAI_BASE_URL=https://your-resource.services.ai.azure.com/openai/v1
FOUNDRY_API_KEY=your-foundry-api-key
FOUNDRY_MODEL=your-deployment-name
FOUNDRY_MANAGER_MODEL=your-manager-deployment-name
```

The Foundry endpoint and key must both be set. Model values should match deployments available to your endpoint.

## Other ways to run

Run the console workflow, which handles plan and approval requests interactively:

```powershell
python main.py
```

Build and run the Streamlit container:

```powershell
docker build -t credit-assessment-review .
docker run --rm -p 8501:8501 --env-file .env -v "${PWD}\checkpoints:/app/checkpoints" credit-assessment-review
```

Keep the checkpoint volume on durable storage if you need runs to survive container replacement. For multiple replicas, use shared checkpoint storage rather than local files.

## Observability and privacy

The application configures OpenTelemetry export using these optional `.env` values:

```dotenv
OTEL_SERVICE_NAME=crisil-claim-verifier
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
ENABLE_SENSITIVE_DATA=false
```

Sensitive telemetry is disabled by default. Keep `ENABLE_SENSITIVE_DATA=false` for financial or personal information. `observability.py` also redacts common financial amounts, percentages, and ratios from framework span and log data; this is a safeguard, not a substitute for reviewing what data is sent to your telemetry backend.

Never commit `.env` or real API keys. The repository's `.gitignore` excludes `.env` files while allowing `.env.example`.

## Project layout

| File | Purpose |
| --- | --- |
| `streamlit_app.py` | Streamlit interface and interactive workflow review |
| `main.py` | Console workflow runner and observability bootstrap |
| `workflow.py` | Provider selection, agent wiring, and checkpoint storage |
| `agents.py` | Draft generator, citation verifier, and manager |
| `tools.py` | Document lookup, demo verdict, and manual-review tools |
| `mock_data.py` | Sample document corpus, draft, and hard-coded verdicts |
| `observability.py` | Telemetry redaction and framework log filtering |
| `foundry_smoke_test.py` | Optional connectivity smoke test for a Foundry endpoint |

The verifier's sample tools use the in-memory corpus and ground-truth verdicts in `mock_data.py`; they do not retrieve external documents or independently establish facts. Replace those tools and demo data before using the workflow with real source material.
