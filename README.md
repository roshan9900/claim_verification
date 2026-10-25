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

The application supports both **Azure Application Insights** and standard **OpenTelemetry OTLP** collectors, with built-in privacy redaction for financial data.

### Azure Application Insights (Live Metrics & Tracing)

When deployed to Azure Container Apps or running locally with an Azure Monitor backend, configure:

```dotenv
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=your-key;IngestionEndpoint=https://your-region.in.applicationinsights.azure.com/;LiveEndpoint=https://your-region.livediagnostics.monitor.azure.com/;ApplicationId=your-app-id
```

When `APPLICATIONINSIGHTS_CONNECTION_STRING` is set:
- **Live Metrics (QuickPulse):** Real-time monitoring of incoming requests, outgoing calls to Foundry/OpenAI, CPU, and memory in the Azure Portal (**crisil-insights -> Live Metrics**).
- **End-to-End Traces:** Distributed tracing for agent turns, tool calls, and LLM completions (**crisil-insights -> Transaction Search**).
- **Application Map:** Visual dependency mapping between `crisil-ui` and the model provider.

### Standard OpenTelemetry OTLP Export

For local debugging with Aspire Dashboard, Jaeger, or an OTel Collector:

```dotenv
OTEL_SERVICE_NAME=crisil-claim-verifier
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
ENABLE_SENSITIVE_DATA=false
```

### Privacy Hardening (`observability.py`)

- Sensitive telemetry is disabled by default (`ENABLE_SENSITIVE_DATA=false`).
- `RedactingSpanProcessor` automatically scrubs financial figures from span descriptions, exception messages, and attributes in-memory before export:
  - Currency amounts (e.g., `₹4,820 crore` -> `[REDACTED_AMOUNT]`)
  - Percentages (e.g., `14%` -> `[REDACTED_PCT]`)
  - Ratios (e.g., `2.4x` -> `[REDACTED_RATIO]`)
  - Formatted numbers (e.g., `73,000` -> `[REDACTED_NUMBER]`)
- `SensitiveLogFilter` intercepts framework log records on ERROR leak paths.

Never commit `.env` or real API keys. The repository's `.gitignore` excludes `.env` files while allowing `.env.example`.

## Deploying to Azure Container Apps

### 1. Build and push image to Azure Container Registry (ACR)

```powershell
az acr build --registry crisilacr16537 --image crisil-ui:v5 . --no-logs
```

### 2. Configure secrets and environment variables

```powershell
# Store secrets
az containerapp secret set --name crisil-ui --resource-group rg-crisil `
  --secrets foundry-key="<YOUR_FOUNDRY_API_KEY>"

# Update container app with image, endpoints, and Application Insights
az containerapp update --name crisil-ui --resource-group rg-crisil `
  --image crisilacr16537.azurecr.io/crisil-ui:v5 `
  --set-env-vars `
    FOUNDRY_OPENAI_BASE_URL="https://crislfoundry.services.ai.azure.com/openai/v1" `
    FOUNDRY_MODEL="gpt-6-luna" `
    FOUNDRY_API_KEY="secretref:foundry-key" `
    APPLICATIONINSIGHTS_CONNECTION_STRING="<YOUR_APPINSIGHTS_CONNECTION_STRING>" `
  --remove-env-vars AZURE_OPENAI_ENDPOINT OPENAI_API_KEY
```

> **Reverse Proxy Note:** The Dockerfile runs Streamlit with `--server.enableCORS=false` and `--server.enableXsrfProtection=false` to support WebSocket handshakes behind Azure Container Apps' Envoy ingress.

## Project layout

| File | Purpose |
| --- | --- |
| `streamlit_app.py` | Streamlit interface, telemetry indicator, and interactive workflow review |
| `main.py` | Console workflow runner and interactive approval CLI |
| `workflow.py` | Provider selection (Foundry / Azure OpenAI / OpenAI), agent wiring, and checkpoints |
| `agents.py` | Draft generator, citation verifier, and Magentic manager agent definitions |
| `tools.py` | Document lookup, demo verdict, and manual-review tools |
| `mock_data.py` | Sample document corpus, draft, and ground-truth verdicts |
| `observability.py` | OpenTelemetry bootstrap, Azure Monitor setup, and financial data redaction |
| `foundry_smoke_test.py` | Connectivity smoke test for Azure AI Foundry endpoint |
| `Dockerfile` | Container configuration for Streamlit behind Azure Container Apps reverse proxy |

The verifier's sample tools use the in-memory corpus and ground-truth verdicts in `mock_data.py`; they do not retrieve external documents or independently establish facts. Replace those tools and demo data before using the workflow with real source material.
