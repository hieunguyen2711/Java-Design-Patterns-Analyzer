import os
from google import genai
from google.genai import types

PROJECT = os.environ["GOOGLE_CLOUD_PROJECT"]   # your Project ID
LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

for model in ["gemini-2.5-flash", "gemini-2.5-pro"]:
    print(f"\n=== {model} ===")
    try:
        resp = client.models.generate_content(
            model=model,
            contents="Write a one-line Java comment.",
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=64,
                response_logprobs=True,   # ask for chosen-token logprobs
                logprobs=5,               # also return top-5 alternatives per step (1..20)
            ),
        )
        cand = resp.candidates[0]
        lp = getattr(cand, "logprobs_result", None)
        print("text:", (resp.text or "").strip()[:80])
        if lp is not None:
            chosen = getattr(lp, "chosen_candidates", None) or getattr(lp, "chosen", None)
            n = len(chosen) if chosen else 0
            print(f"LOGPROBS OK — {n} chosen-token logprobs returned")
        else:
            print("WARNING: no logprobs_result on the response — inspect resp before running volume")
    except Exception as e:
        print(f"ERROR for {model}: {e}")