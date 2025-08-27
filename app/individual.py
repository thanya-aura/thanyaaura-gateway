# app/individual.py
import os
from typing import Optional, Dict, Any, Iterable

import psycopg
from psycopg.rows import dict_row

# Feature sets per individual tier (customize if needed)
INDIVIDUAL_FEATURES: Dict[str, Dict[str, Any]] = {
    "Standard": {"platforms": ["GPT"], "api_limit": "2k/day",  "export": False},
    "Plus":     {"platforms": ["GPT", "Gemini"], "api_limit": "10k/day", "export": True},
    "Premium":  {"platforms": ["GPT", "Gemini", "Copilot"], "api_limit": "50k/day", "export": True},
}

RANK = {"Standard": 10, "Plus": 20, "Premium": 30}

TIER_ALIASES = {
    "standard": "Standard", "tier_standard": "Standard",
    "plus": "Plus",         "tier_plus": "Plus",
    "premium": "Premium",   "tier_premium": "Premium",
}

def _connect():
    url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL")
    if not url:
        raise RuntimeError("DATABASE_URL/DB_URL is not set")
    return psycopg.connect(url, row_factory=dict_row)

def _tier_from_sku(sku: str) -> Optional[str]:
    s = (sku or "").strip().lower()
    return TIER_ALIASES.get(s)

def _pick_highest(plans: Iterable[str]) -> Optional[str]:
    best = None
    best_rank = -1
    for p in plans:
        r = RANK.get(p, -1)
        if r > best_rank:
            best, best_rank = p, r
    return best

def entitlements_for_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Individual entitlement is determined by any active tier purchase for the email.
    If no tier purchase exists but agent SKUs exist, we still return scope=individual
    with minimal features inferred from platforms present.
    """
    email = (email or "").strip().lower()
    if not email:
        return None

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT sku, platform
              FROM subscriptions
             WHERE user_email = %s
               AND status = 'active'
            """,
            (email,),
        )
        rows = cur.fetchall()

    if not rows:
        return None

    # If any enterprise SKU exists, we shouldn't be here; the resolver will prefer enterprise.
    # We still proceed as individual otherwise.
    tiers = []
    platforms = set()
    agent_skus = []

    for r in rows:
        sku = (r.get("sku") or "").lower()
        plat = r.get("platform") or ""
        if sku.startswith("en_"):
            continue
        t = _tier_from_sku(sku)
        if t:
            tiers.append(t)
        if plat:
            platforms.add(plat)
        # Agent SKUs: anything that isn't a tier/all/trial/en_
        if not t and sku not in {"all", "trial"} and not sku.startswith("en_"):
            agent_skus.append(sku)

    plan = _pick_highest(tiers) or "Standard"
    feats = dict(INDIVIDUAL_FEATURES.get(plan, {}))

    # If we observed actual platforms in active subs, reflect them (superset to avoid accidental drops)
    if platforms:
        feats["platforms"] = sorted({*feats.get("platforms", []), *platforms})

    return {
        "scope": "individual",
        "email": email,
        "plan": plan,
        "features": feats,
        "expires_at": None,
        "source": "db",
        "agents": sorted(set(agent_skus)) if agent_skus else [],
    }
