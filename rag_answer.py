import os

from dotenv import load_dotenv
from openai import OpenAI

from rag_retriever import retrieve_policy_context

load_dotenv()
CHAT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"


def search_policy(question: str):
    return retrieve_policy_context(question)


# -------------------------
# BUILD RAG CONTEXT
# -------------------------

def build_context(matches):

    context_parts = []

    for number, match in enumerate(
        matches,
        start=1
    ):

        metadata = match

        source = metadata.get(
            "source_file",
            "Unknown"
        )

        title = metadata.get(
            "title",
            "Unknown"
        )

        program = metadata.get(
            "program",
            "Unknown"
        )

        verified = metadata.get(
            "last_verified",
            "Unknown"
        )

        source_url = metadata.get(
            "source_url",
            "Unknown"
        )

        text = metadata.get(
            "text",
            ""
        )

        context_part = f"""
SOURCE {number}

Title: {title}
Program: {program}
Source file: {source}
Last verified: {verified}
Source URL: {source_url}

Policy content:
{text}
"""

        context_parts.append(
            context_part
        )

    return "\n".join(
        context_parts
    )


# -------------------------
# LLM ANSWER
# -------------------------

def generate_answer(
    question: str,
    context: str
):

    system_prompt = """
You are RewardPilot, a credit card and travel rewards assistant.

Answer the user's question using ONLY facts explicitly stated
in the provided policy context.

STRICT RULES:

1. Never use your own knowledge about credit cards,
   loyalty programs, point values, transfer ratios,
   annual fees, benefits, or policies.

2. Never infer a numeric value that is not explicitly
   present in the retrieved context.

3. If the context refers to another rule or value
   but does not provide that value, say:
   "The retrieved policy does not provide that value."

4. Do not invent or assume:
   - point valuations
   - earn rates
   - transfer ratios
   - award prices
   - eligibility
   - booking availability

5. If retrieved sources disagree, explain the conflict.

6. Use only sources that actually support your answer.

7. Be concise and practical.

8. End with:
   Sources:
   - Source title (Last verified: date)
"""

    user_prompt = f"""
USER QUESTION:

{question}


RETRIEVED POLICY CONTEXT:

{context}


Answer the user's question using only the policy context above.
"""

    nebius_client = OpenAI(
        base_url="https://api.tokenfactory.nebius.com/v1",
        api_key=os.getenv("NEBIUS_API_KEY"),
    )
    response = nebius_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        temperature=0.1
    )

    return response.choices[0].message.content


# -------------------------
# MAIN
# -------------------------

def main():

    if not os.getenv("NEBIUS_API_KEY"):
        raise ValueError(
            "NEBIUS_API_KEY is missing."
        )

    if not os.getenv("PINECONE_API_KEY"):
        raise ValueError(
            "PINECONE_API_KEY is missing."
        )

    question = input(
        "Ask RewardPilot: "
    )

    matches = search_policy(
        question
    )

    if not matches:
        print()
        print(
            "I could not find sufficiently relevant "
            "policy information for that question."
        )
        return

    context = build_context(
        matches
    )

    answer = generate_answer(
        question,
        context
    )

    print()
    print("=" * 70)
    print("REWARDPILOT ANSWER")
    print("=" * 70)
    print()
    print(answer)


if __name__ == "__main__":
    main()