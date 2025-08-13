import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

MODEL_DEFAULT_OPENAI  = os.getenv("MODEL_DEFAULT_OPENAI", "gpt-5")
MODEL_DEFAULT_GEMINI  = os.getenv("MODEL_DEFAULT_GEMINI", "gemini-2.0-pro")

# When you move to OAuth, set these and validate JWTs
OAUTH_AUDIENCE = os.getenv("OAUTH_AUDIENCE", "")
OAUTH_ISSUER   = os.getenv("OAUTH_ISSUER", "")
