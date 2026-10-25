import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

base_url = os.getenv("FOUNDRY_OPENAI_BASE_URL")
api_key = os.getenv("FOUNDRY_API_KEY")
model = os.getenv("FOUNDRY_MODEL", "gpt-6-luna")

if not base_url:
    raise ValueError("Set FOUNDRY_OPENAI_BASE_URL in .env.")
if not api_key:
    raise ValueError("Set FOUNDRY_API_KEY in .env.")

client = OpenAI(base_url=base_url, api_key=api_key)
response = client.responses.create(
    model=model,
    input="What is the capital of France? Answer in one sentence.",
)

print(response.output_text)
