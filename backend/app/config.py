"""Central configuration for the Intelligent Workflow Manager backend.

Loads .env from the project root, exposes Bedrock settings, and chooses the
Claude model (inference profile) to use. Numbers come from the engine; this
module only governs the AI/transport layer.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root is the parent of the backend/ directory.
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# --- AWS Bedrock ----------------------------------------------------------
# The token lives in .env as AWS_BEARER_TOKEN_BEDROCK (Bedrock API key).
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_BEARER_TOKEN = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")

# On Bedrock, model IDs take an `anthropic.` prefix, and current-gen models are
# reached via a regional inference profile (e.g. `us.anthropic.claude-opus-4-8`).
# Override with env if the account needs a different profile/region prefix.
# Verified working on this account (us-east-1) via the connectivity probe:
#   us.anthropic.claude-opus-4-8                   -> OK
#   us.anthropic.claude-sonnet-4-5-20250929-v1:0   -> OK
MODEL_PRIMARY = os.getenv("BEDROCK_MODEL_PRIMARY", "us.anthropic.claude-opus-4-8")
MODEL_FAST = os.getenv(
    "BEDROCK_MODEL_FAST", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)

# Candidate model IDs to probe, in priority order. The connectivity check walks
# these until one succeeds, so we don't hard-fail on a profile naming mismatch.
MODEL_CANDIDATES = [
    "us.anthropic.claude-opus-4-8",
    "anthropic.claude-opus-4-8",
    "us.anthropic.claude-sonnet-4-5",
    "anthropic.claude-sonnet-4-5",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
]

# --- Engine / data --------------------------------------------------------
DB_PATH = os.getenv("LSMV_DB_PATH", str(ROOT / "backend" / "lsmv.db"))
WEIGHTS_PATH = os.getenv("WEIGHTS_PATH", str(ROOT / "backend" / "app" / "weights.yaml"))


def have_bedrock_token() -> bool:
    return bool(BEDROCK_BEARER_TOKEN)
