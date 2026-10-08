""" Instructor Insights Generator (Issue #119)

Accepts data from concepts / error type analytics,
generates instructor insights using an LLM.
"""

import os

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from app.models import InsightStats, InsightsResponse

LOW_DATA_THRESHOLD = 3

SYSTEM_PROMPT = """You are an experienced instructor specialising in teaching foundational programming. 
                    You will be provided with attributes related to error type, total errors, outcomes, and many more.
                    Using this data, you need to provide insights to instructors into what needs to be taught or revised.
                    Provide the insight using exactly three sentences.
                    Rules:
                    - Only cite numbers that appear in the data. Do not make up numbers.
                    - Days with no errors are not included in daily counts, so DO NOT describe trends from a few data points.
                    - If the total number of errors is less than 3, reply in one sentence that the evidence is limited. DO NOT continue generating additional sentences.
                    - If distinct_sessions is null, do not mention session counts.
                    - DO NOT mention individual students or sessions.
                    - related_concepts lists teaching concepts tagged on these errors; use them to suggest what to revise.
                """

_client: OpenAI | None = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ.get("INSTRUCTOR_TOKEN"),
            base_url=os.environ.get("GROQ_API_URL"),
            timeout=20.0,
        )
    return _client



def generate_insights(stats:InsightStats, model:str = "qwen/qwen3.8-27b"):
    """Function to generate insights for instructors, specific to the error type.
       InsightStats accepted as an input, with output being the response from the LLM.
       """

    client = _get_client()

    user_prompt = f""" Supplement the instructions given by the system prompt using the following attributes:
                    Error Type: {stats.error_type},
                    Data Window: {stats.data_window},
                    Statistics: \n{stats.model_dump_json(indent=2, exclude={'error_type', 'data_window'})}
                    """
    messages = [
        {"role":"system", "content":SYSTEM_PROMPT},
        {"role":"user", "content":user_prompt},
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages, 
        max_tokens=200,
        temperature=0,
    )

    response_text = (response.choices[0].message.content or "").strip()
    if not response_text:
        raise ValueError("LLM returned an empty response")

    return InsightsResponse(
        error_type=stats.error_type,
        summary=response_text,
        low_data=stats.total_errors < LOW_DATA_THRESHOLD,
        generated=True,
    )