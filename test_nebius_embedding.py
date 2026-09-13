import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url="https://api.tokenfactory.nebius.com/v1",
    api_key=os.getenv("NEBIUS_API_KEY")
)

response = client.embeddings.create(
    model="Qwen/Qwen3-Embedding-8B",
    input="RewardPilot embedding dimension test"
)

embedding = response.data[0].embedding

print("Embedding dimension:", len(embedding))
print("First 5 values:", embedding[:5])