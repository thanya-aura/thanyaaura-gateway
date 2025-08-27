# agents.py – extended mapping with GPT, Gemini, Copilot (incl. enterprise SKUs)

AGENT_SKU_TO_AGENT = {
    # ===== Budget =====
    "budget_standard": "budget_standard",
    "budget_plus": "budget_plus",
    "budget_premium": "budget_premium",
    "buds": "budget_standard",
    "budp": "budget_plus",
    "budpr": "budget_premium",
    "module-0-budget-standard": "budget_standard",
    "module-0-budget-plus": "budget_plus",
    "module-0-budget-premium": "budget_premium",

    # ===== Capex =====
    "capex_standard": "capex_standard",
    "capex_plus": "capex_plus",
    "capex_premium": "capex_premium",
    "capexs": "capex_standard",
    "capexp": "capex_plus",
    "capexpr": "capex_premium",
    "module-0-capex-standard": "capex_standard",
    "module-0-capex-plus": "capex_plus",
    "module-0-capex-premium": "capex_premium",

    # ===== Cost =====
    "cost_standard": "cost_standard",
    "cost_plus": "cost_plus",
    "cost_premium": "cost_premium",
    "costs": "cost_standard",
    "costp": "cost_plus",
    "costpr": "cost_premium",
    "module-0-cost-standard": "cost_standard",
    "module-0-cost-plus": "cost_plus",
    "module-0-cost-premium": "cost_premium",

    # ===== Decision =====
    "decision_standard": "decision_standard",
    "decision_plus": "decision_plus",
    "decision_premium": "decision_premium",
    "decs": "decision_standard",
    "decp": "decision_plus",
    "decpr": "decision_premium",
    "module-0-decision-standard": "decision_standard",
    "module-0-decision-plus": "decision_plus",
    "module-0-decision-premium": "decision_premium",

    # ===== Enterprise CF =====
    "enterprise_cf": "enterprise_cf",
    "entcf": "enterprise_cf",
    "module-0-enterprise-cf": "enterprise_cf",

    # ===== Forecast =====
    "forecast_standard": "forecast_standard",
    "forecast_plus": "forecast_plus",
    "forecast_premium": "forecast_premium",
    "fors": "forecast_standard",
    "forp": "forecast_plus",
    "forpr": "forecast_premium",
    "module-0-forecast-standard": "forecast_standard",
    "module-0-forecast-plus": "forecast_plus",
    "module-0-forecast-premium": "forecast_premium",

    # ===== FX =====
    "fx_standard": "fx_standard",
    "fx_plus": "fx_plus",
    "fx_premium": "fx_premium",
    "fxs": "fx_standard",
    "fxp": "fx_plus",
    "fxpr": "fx_premium",
    "module-0-fx-standard": "fx_standard",
    "module-0-fx-plus": "fx_plus",
    "module-0-fx-premium": "fx_premium",

    # ===== Margin =====
    "margin_standard": "margin_standard",
    "margin_plus": "margin_plus",
    "margin_premium": "margin_premium",
    "mars": "margin_standard",
    "marp": "margin_plus",
    "marpr": "margin_premium",
    "module-0-margin-standard": "margin_standard",
    "module-0-margin-plus": "margin_plus",
    "module-0-margin-premium": "margin_premium",

    # ===== Project CF =====
    "project_cf": "project_cf",
    "projcf": "project_cf",
    "module-0-project-cf": "project_cf",

    # ===== Report =====
    "report_standard": "report_standard",
    "report_plus": "report_plus",
    "report_premium": "report_premium",
    "reps": "report_standard",
    "repp": "report_plus",
    "reppr": "report_premium",
    "module-0-report-standard": "report_standard",
    "module-0-report-plus": "report_plus",
    "module-0-report-premium": "report_premium",

    # ===== Revenue =====
    "revenue_standard": "revenue_standard",
    "revenue_intermediate": "revenue_intermediate",
    "revenue_advance": "revenue_advance",
    "revs": "revenue_standard",
    "revp": "revenue_intermediate",
    "revpr": "revenue_advance",
    "module-0-revenue-standard": "revenue_standard",
    "module-0-revenue-intermediate": "revenue_intermediate",
    "module-0-revenue-advance": "revenue_advance",

    # ===== Single CF =====
    "single_cf": "single_cf",
    "scf": "single_cf",
    "module-0-single-cf": "single_cf",

    # ===== Variance =====
    "variance_standard": "variance_standard",
    "variance_plus": "variance_plus",
    "variance_premium": "variance_premium",
    "vars": "variance_standard",
    "varp": "variance_plus",
    "varpr": "variance_premium",
    "module-0-variance-standard": "variance_standard",
    "module-0-variance-plus": "variance_plus",
    "module-0-variance-premium": "variance_premium",

    # ===== Copilot Enterprise SKUs =====
    "en_standard": "ENTERPRISE_LICENSE_STANDARD",
    "en_professional": "ENTERPRISE_LICENSE_PRO",
    "en_unlimited": "ENTERPRISE_LICENSE_UNLIMITED",
}


# --- Extend dynamically with Gemini + Copilot suffixes ---
_extended = {}
for sku, agent in list(AGENT_SKU_TO_AGENT.items()):
    if not sku.startswith("en_"):  # don't suffix enterprise SKUs
        _extended[f"{sku}_gemini"] = agent
        _extended[f"{sku}_ms"] = agent
AGENT_SKU_TO_AGENT.update(_extended)


def get_agent_slug_from_sku(sku: str):
    if not sku:
        return None
    key = sku.strip().lower()
    return AGENT_SKU_TO_AGENT.get(key)
