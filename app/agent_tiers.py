# app/agent_tiers.py
"""
จำแนก agent ออกเป็น 3 ระดับ: STANDARD / PLUS / PREMIUM
- รองรับทั้ง slug canonical (budget_standard) และ alias SKU (buds, capexs, revp ...)
- normalize ค่าที่เข้ามาให้เป็นรูปแบบเทียบได้ (ตัด prefix/suffix module-0-*, *_gemini, *_ms, *_ai_agent)
"""
from typing import Literal

TierCode = Literal["STANDARD", "PLUS", "PREMIUM"]

# --- ชุดมาตรฐานตาม family (รวม alias SKU สำคัญเพื่อให้ครอบคลุม) ---
STANDARD_SET = {
    # CF family
    "single_cf", "project_cf", "enterprise_cf",
    "scf", "pcf", "entcf",  # alias ยอดนิยม
    # Revenue (standard)
    "revenue_standard", "revs",
    # Budget
    "budget_standard", "buds",
    # Capex
    "capex_standard", "capexs",
    # FX
    "fx_standard", "fxs",
    # Cost
    "cost_standard", "costs",
    # Report
    "report_standard", "reps",
    # Variance
    "variance_standard", "vars",
    # Margin
    "margin_standard", "mars",
    # Forecast
    "forecast_standard", "fors",
    # Decision
    "decision_standard", "decs",
}

PLUS_SET = {
    # Revenue (intermediate)
    "revenue_intermediate", "revp",
    # Budget
    "budget_plus", "budp",
    # Capex
    "capex_plus", "capexp",
    # FX
    "fx_plus", "fxp",
    # Cost
    "cost_plus", "costp",
    # Report
    "report_plus", "repp",
    # Variance
    "variance_plus", "varp",
    # Margin
    "margin_plus", "marp",
    # Forecast
    "forecast_plus", "forp",
    # Decision
    "decision_plus", "decp",
}

PREMIUM_SET = {
    # Revenue (advance/premium)
    "revenue_advance", "revpr",
    # Budget
    "budget_premium", "budpr",
    # Capex
    "capex_premium", "capexpr",
    # FX
    "fx_premium", "fxpr",
    # Cost
    "cost_premium", "costpr",
    # Report
    "report_premium", "reppr",
    # Variance
    "variance_premium", "varpr",
    # Margin
    "margin_premium", "marpr",
    # Forecast
    "forecast_premium", "forpr",
    # Decision
    "decision_premium", "decpr",
}

def _canon(s: str) -> str:
    """
    - ทำให้เป็นตัวพิมพ์เล็ก
    - ตัด prefix 'module-0-'
    - ตัด suffix '_gemini' / '_ms'
    - ตัด suffix พิเศษ '_ai_agent' ที่มาจาก slug เดิม (เช่น SINGLE_CF_AI_AGENT)
    """
    s = (s or "").strip().lower()
    if s.startswith("module-0-"):
        s = s[9:]
    if s.endswith("_gemini"):
        s = s[:-7]
    if s.endswith("_ms"):
        s = s[:-3]
    if s.endswith("_ai_agent"):
        s = s[:-9]
    return s

def classify_agent_tier(agent_slug_or_sku: str) -> TierCode:
    s = _canon(agent_slug_or_sku)
    if s in PREMIUM_SET:
        return "PREMIUM"
    if s in PLUS_SET:
        return "PLUS"
    return "STANDARD"
