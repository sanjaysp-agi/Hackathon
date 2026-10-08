"""Phase 0 connectivity check: verify a 'hello Claude' round-trip on Bedrock.

Walks the candidate model IDs and reports which (if any) succeed, so we lock in
the right inference-profile string before building on it.

Run:  py backend/scripts/check_bedrock.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, llm  # noqa: E402


def main() -> int:
    print("=== Bedrock connectivity check ===")
    print(f"Region        : {config.AWS_REGION}")
    print(f"Token present : {config.have_bedrock_token()}")
    if not config.have_bedrock_token():
        print("!! AWS_BEARER_TOKEN_BEDROCK is empty. Check .env.")
        return 2

    working: list[str] = []
    for model_id in config.MODEL_CANDIDATES:
        ok, detail = llm.probe(model_id)
        status = "OK  " if ok else "FAIL"
        print(f"[{status}] {model_id}  ->  {detail}")
        if ok:
            working.append(model_id)

    print("-" * 60)
    if working:
        print(f"Usable model IDs: {working}")
        print(f"Set BEDROCK_MODEL_PRIMARY to one of the Opus/Sonnet entries above.")
        return 0
    print("No candidate model succeeded. Likely causes:")
    print("  - Model access not enabled for this account/region in Bedrock console")
    print("  - Wrong region (try AWS_REGION=us-west-2 in .env)")
    print("  - Token lacks bedrock:InvokeModel permission")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
