"""Retrieve policy evidence only; no chat model is called here."""

from functools import lru_cache
import os

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone

load_dotenv()
NAMESPACE = "rewardpilot-policies"
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"
MIN_SCORE = 0.55


@lru_cache(maxsize=1)
def _clients():
    for name in ("NEBIUS_API_KEY", "PINECONE_API_KEY"):
        if not os.getenv(name):
            raise ValueError(f"{name} is missing.")
    nebius = OpenAI(
        base_url="https://api.tokenfactory.nebius.com/v1",
        api_key=os.environ["NEBIUS_API_KEY"], timeout=60, max_retries=1,
    )
    pinecone = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    index = pinecone.Index(os.getenv("PINECONE_INDEX", "rewardpilot-rag-nebius"))
    return nebius, index


def retrieve_policy_context(question: str, top_k: int = 3,
                            program: str | None = None,
                            policy_type: str | None = None):
    """Return up to top_k distinct sources meeting the existing 0.55 cutoff."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    nebius, index = _clients()
    response = nebius.embeddings.create(model=EMBEDDING_MODEL, input=question)
    filters = {}
    if program is not None:
        filters["program"] = {"$eq": program}
    if policy_type is not None:
        filters["policy_type"] = {"$eq": policy_type}
    results = index.query(
        vector=response.data[0].embedding, top_k=max(8, top_k),
        include_metadata=True, namespace=NAMESPACE,
        **({"filter": filters} if filters else {}),
    )
    evidence = []
    seen_sources = set()
    for match in results.matches:
        if match.score < MIN_SCORE:
            continue
        metadata = match.metadata or {}
        source = metadata.get("source_file", "unknown")
        if source in seen_sources:
            continue
        seen_sources.add(source)
        evidence.append({
            "title": metadata.get("title", "Unknown"),
            "source_file": source,
            "source_url": metadata.get("source_url", "Unknown"),
            "last_verified": metadata.get("last_verified", "Unknown"),
            "program": metadata.get("program", "Unknown"),
            "policy_type": metadata.get("policy_type", "Unknown"),
            "score": float(match.score),
            "text": metadata.get("text", ""),
        })
        if len(evidence) >= top_k:
            break
    return evidence
