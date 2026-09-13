from pathlib import Path
import os
import json
import re
import time

from dotenv import load_dotenv
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec


load_dotenv()

# -------------------------
# CONFIG
# -------------------------

NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv(
    "PINECONE_INDEX",
    "rewardpilot-rag-nebius"
)

RAG_DIR = Path(__file__).resolve().parent / "rag_docs"

EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-8B"
DIMENSION = 4096

NAMESPACE = "rewardpilot-policies"


def get_embedding(text: str):
    client = OpenAI(
        base_url="https://api.tokenfactory.nebius.com/v1",
        api_key=NEBIUS_API_KEY, timeout=60, max_retries=1,
    )
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def extract_metadata(text: str):
    """Read the corpus's quoted scalar / inline JSON-list frontmatter format."""
    frontmatter = re.match(r"\A---\s*\n(.*?)\n---(?:\n|$)", text, re.DOTALL)
    if not frontmatter:
        raise ValueError("Policy document is missing YAML frontmatter")
    fields = {}
    for line in frontmatter.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator and key in {
            "title", "program", "source_url", "last_verified",
            "document_type", "policy_type", "tags",
        }:
            fields[key] = json.loads(value.strip())
    return fields


def prepare_vectors(directory):
    """Embed complete files before any deletion; never split policy content."""
    vectors = []
    for file_path in sorted(directory.glob("*.md")):
        if file_path.name.lower() == "readme.md":
            continue
        text = file_path.read_text(encoding="utf-8")
        metadata = {**extract_metadata(text), "text": text,
                    "source_file": file_path.name}
        print(f"Embedding complete document: {file_path.name}", flush=True)
        embedding = get_embedding(text)
        if len(embedding) != DIMENSION:
            raise ValueError(f"Expected dimension {DIMENSION}, got {len(embedding)}")
        vectors.append({"id": file_path.stem, "values": embedding, "metadata": metadata})
    if not vectors:
        raise ValueError("No policy files found; refusing to clear the namespace")
    return vectors


def wait_for_vectors(index, expected_ids, timeout=60):
    """Wait for namespace ID listing and stats to reflect the completed write."""
    deadline = time.monotonic() + timeout
    while True:
        actual_ids = {item.id if hasattr(item, "id") else item
                      for page in index.list(namespace=NAMESPACE) for item in page}
        stats = index.describe_index_stats()
        namespace_stats = stats.namespaces.get(NAMESPACE)
        count = namespace_stats.vector_count if namespace_stats else 0
        if actual_ids == expected_ids and count == len(expected_ids):
            return count
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Namespace not yet consistent: {count} vectors; expected {len(expected_ids)}")
        time.sleep(2)


def replace_policy_vectors(index, vectors):
    if not vectors:
        raise ValueError("Refusing to replace namespace with an empty corpus")
    print(f"Clearing old vectors in namespace: {NAMESPACE}", flush=True)
    index.delete(delete_all=True, namespace=NAMESPACE)
    wait_for_vectors(index, set())
    for start in range(0, len(vectors), 20):
        index.upsert(vectors=vectors[start:start + 20], namespace=NAMESPACE)
    return wait_for_vectors(index, {vector["id"] for vector in vectors})


# -------------------------
# MAIN
# -------------------------

def main():

    if not NEBIUS_API_KEY:
        raise ValueError(
            "NEBIUS_API_KEY is missing from .env"
        )

    if not PINECONE_API_KEY:
        raise ValueError(
            "PINECONE_API_KEY is missing from .env"
        )

    if not RAG_DIR.exists():
        raise ValueError(
            f"RAG directory not found: {RAG_DIR}"
        )

    print("Connecting to Pinecone...")

    pc = Pinecone(
        api_key=PINECONE_API_KEY
    )

    existing_indexes = [
        index.name
        for index in pc.list_indexes()
    ]

    # -------------------------
    # CREATE INDEX
    # -------------------------

    if INDEX_NAME not in existing_indexes:

        print(
            f"Creating Pinecone index: {INDEX_NAME}"
        )

        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )

        print(
            "Waiting for index to become ready..."
        )

        while True:

            description = pc.describe_index(
                INDEX_NAME
            )

            if description.status["ready"]:
                break

            time.sleep(2)

    index = pc.Index(
        INDEX_NAME
    )

    vectors = prepare_vectors(RAG_DIR)
    count = replace_policy_vectors(index, vectors)
    print("Ingestion complete.")
    print(f"Index: {INDEX_NAME}")
    print(f"Embedding model: {EMBEDDING_MODEL}")
    print(f"Dimension: {DIMENSION}")
    print(f"Namespace: {NAMESPACE}")
    print(f"Policy Markdown files: {len(vectors)}")
    print(f"Pinecone vectors verified: {count}")
    print("Stable IDs verified; no stale chunk IDs remain.")


if __name__ == "__main__":
    main()
