from typing import Optional
from app import db

TIER_SKUS = {"standard", "plus", "premium"}
ENTERPRISE_SKUS = {"en_standard", "en_professional", "en_unlimited"}


def _email_domain(email: str) -> Optional[str]:
    try:
        return email.split("@", 1)[1].lower()
    except Exception:
        return None


def _tier_from_slug(agent_slug: str) -> str:
    s = (agent_slug or "").upper()
    # map common suffixes → canonical tier
    if s.endswith("_STANDARD"):
        return "STANDARD"
    if s.endswith("_PLUS") or s.endswith("_INTERMEDIATE"):
        return "PLUS"
    if s.endswith("_PREMIUM") or s.endswith("_ADVANCE"):
        return "PREMIUM"
    # default: safest (won't grant above)
    return "STANDARD"


def _tier_allows(user_tier: str, agent_tier: str) -> bool:
    order = {"STANDARD": 1, "PLUS": 2, "PREMIUM": 3}
    return order.get((user_tier or "").upper(), 0) >= order.get((agent_tier or "").upper(), 0)


def _platform_norm(p: Optional[str]) -> str:
    """
    Normalize platform tags across inputs and storage.
    Examples:
      "MS", "Copilot", "Copilot-Enterprise" -> "Copilot"
      "Gemini", "GEMINI"                   -> "Gemini"
      "GPT", "OpenAI", "ChatGPT"           -> "GPT"
    """
    p = (p or "").strip()
    if not p:
        return ""
    u = p.upper()
    if u in ("MS", "MICROSOFT", "COPILOT") or u.startswith("COPILOT"):
        return "Copilot"
    if u.startswith("GEMINI"):
        return "Gemini"
    if u in ("GPT", "OPENAI", "CHATGPT"):
        return "GPT"
    return p  # unknown tags pass through


def _platform_match(request_platform: str, row_platform: str) -> bool:
    """
    Treat same-family platforms as equal after normalization.
    Empty request matches anything.
    """
    rp = _platform_norm(request_platform)
    sp = _platform_norm(row_platform)
    return (rp == "") or (rp == sp)


def check_entitlement(user_email: str, agent_slug: str, platform: str) -> bool:
    """
    Individual:
      - sku='all' on same platform → allow
      - tier (standard/plus/premium) on same platform → allow by tier ladder
      - specific agent sku (not tier/enterprise/all) on same platform → allow

    Enterprise (domain-based):
      - Copilot family only (Copilot & Copilot-Enterprise & MS)
      - en_standard     → allow only agents whose tier is STANDARD
      - en_professional → allow all tiers
      - en_unlimited    → allow all tiers
    """
    plat_req = _platform_norm(platform)

    rows = [r for r in (db.fetch_subscriptions(user_email) or []) if r.get("status") == "active"]

    # 1) Individual: any-agent on same platform
    for r in rows:
        if (r.get("sku") or "").lower() == "all" and _platform_match(plat_req, r.get("platform")):
            return True

    # 2) Individual: Tiers on same platform
    agent_tier = _tier_from_slug(agent_slug)
    for r in rows:
        sku = (r.get("sku") or "").lower()
        if sku in TIER_SKUS and _platform_match(plat_req, r.get("platform")):
            if _tier_allows(sku.upper(), agent_tier):
                return True

    # 3) Individual: specific agent (not tier/enterprise/all)
    for r in rows:
        sku = (r.get("sku") or "").lower()
        if sku not in (TIER_SKUS | ENTERPRISE_SKUS | {"all"}) and _platform_match(plat_req, r.get("platform")):
            return True

    # 4) Enterprise: Copilot family only
    if _platform_norm(plat_req) != "Copilot":
        return False

    domain = _email_domain(user_email)
    if not domain:
        return False

    ent = db.get_active_enterprise_license_for_domain(domain)
    if not ent:
        return False

    # Enterprise license platform may be saved as "Copilot" or "Copilot-Enterprise" or "MS"
    if not _platform_match("Copilot", ent.get("platform")):
        return False

    lic = (ent.get("sku") or "").lower()
    if lic == "en_standard":
        return agent_tier == "STANDARD"
    if lic in ("en_professional", "en_unlimited"):
        return True

    return False
