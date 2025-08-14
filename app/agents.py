# agents.py — generated from Excel (Sheet1) to align SKUs precisely
# Do not edit by hand; regenerate from spreadsheet if SKUs change.

# Canonical mapping (SKU without 'module-0-') and aliases -> agent_slug
AGENT_SKU_TO_AGENT = {
  "budp": "BUDGET_PLUS",
  "budpr": "BUDGET_PREMIUM",
  "buds": "BUDGET_STANDARD",
  "capexp": "CAPEX_PLUS",
  "capexpr": "CAPEX_PREMIUM",
  "capexs": "CAPEX_STANDARD",
  "cfp": "PROJECT_CF_AI_AGENT",
  "cfpr": "ENTERPRISE_CF_AI_AGENT",
  "cfs": "SINGLE_CF_AI_AGENT",
  "costp": "COST_PLUS",
  "costpr": "COST_PREMIUM",
  "costs": "COST_STANDARD",
  "decp": "DECISION_PLUS",
  "decpr": "DECISION_PREMIUM",
  "decs": "DECISION_STANDARD",
  "enterprise_cf": "ENTERPRISE_CF_AI_AGENT",
  "forp": "FORECAST_PLUS",
  "forpr": "FORECAST_PREMIUM",
  "fors": "FORECAST_STANDARD",
  "fxp": "FX_PLUS",
  "fxpr": "FX_PREMIUM",
  "fxs": "FX_STANDARD",
  "marp": "MARGIN_PLUS",
  "marpr": "MARGIN_PREMIUM",
  "mars": "MARGIN_STANDARD",
  "module-0-budp": "BUDGET_PLUS",
  "module-0-budpr": "BUDGET_PREMIUM",
  "module-0-buds": "BUDGET_STANDARD",
  "module-0-capexp": "CAPEX_PLUS",
  "module-0-capexpr": "CAPEX_PREMIUM",
  "module-0-capexs": "CAPEX_STANDARD",
  "module-0-cfp": "PROJECT_CF_AI_AGENT",
  "module-0-cfpr": "ENTERPRISE_CF_AI_AGENT",
  "module-0-cfs": "SINGLE_CF_AI_AGENT",
  "module-0-costp": "COST_PLUS",
  "module-0-costpr": "COST_PREMIUM",
  "module-0-costs": "COST_STANDARD",
  "module-0-decp": "DECISION_PLUS",
  "module-0-decpr": "DECISION_PREMIUM",
  "module-0-decs": "DECISION_STANDARD",
  "module-0-forp": "FORECAST_PLUS",
  "module-0-forpr": "FORECAST_PREMIUM",
  "module-0-fors": "FORECAST_STANDARD",
  "module-0-fxp": "FX_PLUS",
  "module-0-fxpr": "FX_PREMIUM",
  "module-0-fxs": "FX_STANDARD",
  "module-0-marp": "MARGIN_PLUS",
  "module-0-marpr": "MARGIN_PREMIUM",
  "module-0-mars": "MARGIN_STANDARD",
  "module-0-repp": "REPORT_PLUS",
  "module-0-reppr": "REPORT_PREMIUM",
  "module-0-reps": "REPORT_STANDARD",
  "module-0-revp": "REVENUE_INTERMEDIATE",
  "module-0-revpr": "REVENUE_ADVANCE",
  "module-0-revs": "REVENUE_STANDARD",
  "module-0-varp": "VARIANCE_PLUS",
  "module-0-varpr": "VARIANCE_PREMIUM",
  "module-0-vars": "VARIANCE_STANDARD",
  "project_cf": "PROJECT_CF_AI_AGENT",
  "single_cf": "SINGLE_CF_AI_AGENT",
  "module-0-single_cf": "SINGLE_CF_AI_AGENT",
  "repp": "REPORT_PLUS",
  "reppr": "REPORT_PREMIUM",
  "reps": "REPORT_STANDARD",
  "revp": "REVENUE_INTERMEDIATE",
  "revpr": "REVENUE_ADVANCE",
  "revs": "REVENUE_STANDARD",
  "varp": "VARIANCE_PLUS",
  "varpr": "VARIANCE_PREMIUM",
  "vars": "VARIANCE_STANDARD"
}

def get_agent_slug_from_sku(sku: str):
    """
    Normalize SKU (lower/strip). Accepts both 'cfp' and 'module-0-cfp', etc.
    Returns agent_slug (e.g., 'PROJECT_CF_AI_AGENT') or None if unknown.
    """
    if not sku:
        return None
    s = str(sku).strip().lower()
    # Direct lookup (aliases dictionary already contains 'module-0-' variants too)
    return AGENT_SKU_TO_AGENT.get(s) or AGENT_SKU_TO_AGENT.get(s.removeprefix('module-0-'))
