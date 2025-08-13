# agents.py
# Mappings for 33 agents (SKU <-> CODE <-> agent_slug)
# NOTE:
# - Keep 'CFP' (NOT 'CFR') for PROJECT_CF_AI_AGENT as requested.

AGENT_SPECS = {
    "CFS":   {"name": "CFS",   "providers": ["openai", "gemini"], "endpoint": "https://ai-finance-api-3.onrender.com", "github": "https://github.com/thanya-aura/ai-finance-api"},
    "CFP":   {"name": "CFP",   "providers": ["openai", "gemini"], "endpoint": "https://ai-finance-api-3.onrender.com", "github": "https://github.com/thanya-aura/ai-finance-api"},
    "CFPR":  {"name": "CFPR",  "providers": ["openai", "gemini"], "endpoint": "https://ai-finance-api-3.onrender.com", "github": "https://github.com/thanya-aura/ai-finance-api"},

    "REVS":  {"name": "REVS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-revenue-api.onrender.com",   "github": "https://github.com/thanya-aura/ai_revenue_api"},
    "REVP":  {"name": "REVP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-revenue-api.onrender.com",   "github": "https://github.com/thanya-aura/ai_revenue_api"},
    "REVPR": {"name": "REVPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-revenue-api.onrender.com",   "github": "https://github.com/thanya-aura/ai_revenue_api"},

    "CAPEXS":  {"name": "CAPEXS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-capex-api.onrender.com", "github": "https://github.com/thanya-aura/ai-capex-api.git"},
    "CAPEXP":  {"name": "CAPEXP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-capex-api.onrender.com", "github": "https://github.com/thanya-aura/ai-capex-api.git"},
    "CAPEXPR": {"name": "CAPEXPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-capex-api.onrender.com", "github": "https://github.com/thanya-aura/ai-capex-api.git"},

    "FXS":  {"name": "FXS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-fx-api.onrender.com", "github": "https://github.com/thanya-aura/ai-fx-api.git"},
    "FXP":  {"name": "FXP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-fx-api.onrender.com", "github": "https://github.com/thanya-aura/ai-fx-api.git"},
    "FXPR": {"name": "FXPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-fx-api.onrender.com", "github": "https://github.com/thanya-aura/ai-fx-api.git"},

    "COSTS":  {"name": "COSTS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-cost-api.onrender.com", "github": "https://github.com/thanya-aura/ai-cost-api.git"},
    "COSTP":  {"name": "COSTP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-cost-api.onrender.com", "github": "https://github.com/thanya-aura/ai-cost-api.git"},
    "COSTPR": {"name": "COSTPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-cost-api.onrender.com", "github": "https://github.com/thanya-aura/ai-cost-api.git"},

    "BUDS":  {"name": "BUDS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-budget-api.onrender.com", "github": "https://github.com/thanya-aura/ai-budget-api.git"},
    "BUDP":  {"name": "BUDP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-budget-api.onrender.com", "github": "https://github.com/thanya-aura/ai-budget-api.git"},
    "BUDPR": {"name": "BUDPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-budget-api.onrender.com", "github": "https://github.com/thanya-aura/ai-budget-api.git"},

    "REPS":  {"name": "REPS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-report-api.onrender.com", "github": "https://github.com/thanya-aura/ai-report-api.git"},
    "REPP":  {"name": "REPP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-report-api.onrender.com", "github": "https://github.com/thanya-aura/ai-report-api.git"},
    "REPPR": {"name": "REPPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-report-api.onrender.com", "github": "https://github.com/thanya-aura/ai-report-api.git"},

    "VARS":  {"name": "VARS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-variance-api.onrender.com", "github": "https://github.com/thanya-aura/ai-variance-api.git"},
    "VARP":  {"name": "VARP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-variance-api.onrender.com", "github": "https://github.com/thanya-aura/ai-variance-api.git"},
    "VARPR": {"name": "VARPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-variance-api.onrender.com", "github": "https://github.com/thanya-aura/ai-variance-api.git"},

    "MARS":  {"name": "MARS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-margin-api.onrender.com", "github": "https://github.com/thanya-aura/ai-margin-api.git"},
    "MARP":  {"name": "MARP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-margin-api.onrender.com", "github": "https://github.com/thanya-aura/ai-margin-api.git"},
    "MARPR": {"name": "MARPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-margin-api.onrender.com", "github": "https://github.com/thanya-aura/ai-margin-api.git"},

    "FORS":  {"name": "FORS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-forecast-api.onrender.com", "github": "https://github.com/thanya-aura/ai-forecast-api.git"},
    "FORP":  {"name": "FORP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-forecast-api.onrender.com", "github": "https://github.com/thanya-aura/ai-forecast-api.git"},
    "FORPR": {"name": "FORPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-forecast-api.onrender.com", "github": "https://github.com/thanya-aura/ai-forecast-api.git"},

    "DECS":  {"name": "DECS",  "providers": ["openai", "gemini"], "endpoint": "https://ai-decision-api.onrender.com", "github": "https://github.com/thanya-aura/ai-decision-api.git"},
    "DECP":  {"name": "DECP",  "providers": ["openai", "gemini"], "endpoint": "https://ai-decision-api.onrender.com", "github": "https://github.com/thanya-aura/ai-decision-api.git"},
    "DECPR": {"name": "DECPR", "providers": ["openai", "gemini"], "endpoint": "https://ai-decision-api.onrender.com", "github": "https://github.com/thanya-aura/ai-decision-api.git"},
}

# 1) SKU -> CODE (33)
AGENT_SKU_TO_CODE = {
    "module-0-cfs":    "CFS",
    "module-0-cfr":    "CFP",   # keep CFP (not CFR)
    "module-0-cfpr":   "CFPR",

    "module-0-revs":   "REVS",
    "module-0-revp":   "REVP",
    "module-0-revpr":  "REVPR",

    "module-0-capexs": "CAPEXS",
    "module-0-capexp": "CAPEXP",
    "module-0-capexpr":"CAPEXPR",

    "module-0-fxs":    "FXS",
    "module-0-fxp":    "FXP",
    "module-0-fxpr":   "FXPR",

    "module-0-costs":  "COSTS",
    "module-0-costp":  "COSTP",
    "module-0-costpr": "COSTPR",

    "module-0-buds":   "BUDS",
    "module-0-budp":   "BUDP",
    "module-0-budpr":  "BUDPR",

    "module-0-reps":   "REPS",
    "module-0-repp":   "REPP",
    "module-0-reppr":  "REPPR",

    "module-0-vars":   "VARS",
    "module-0-varp":   "VARP",
    "module-0-varpr":  "VARPR",

    "module-0-mars":   "MARS",
    "module-0-marp":   "MARP",
    "module-0-marpr":  "MARPR",

    "module-0-fors":   "FORS",
    "module-0-forp":   "FORP",
    "module-0-forpr":  "FORPR",

    "module-0-decs":   "DECS",
    "module-0-decp":   "DECP",
    "module-0-decpr":  "DECPR",
}

# 2) agent_slug -> CODE
AGENT_SLUG_TO_CODE = {
    "SINGLE_CF_AI_AGENT":       "CFS",
    "PROJECT_CF_AI_AGENT":      "CFP",     # CFP
    "ENTERPRISE_CF_AI_AGENT":   "CFPR",

    "REVENUE_STANDARD":         "REVS",
    "REVENUE_INTERMEDIATE":     "REVP",
    "REVENUE_ADVANCE":          "REVPR",

    "CAPEX_STANDARD":           "CAPEXS",
    "CAPEX_PLUS":               "CAPEXP",
    "CAPEX_PREMIUM":            "CAPEXPR",

    "FX_STANDARD":              "FXS",
    "FX_PLUS":                  "FXP",
    "FX_PREMIUM":               "FXPR",

    "COST_STANDARD":            "COSTS",
    "COST_PLUS":                "COSTP",
    "COST_PREMIUM":             "COSTPR",

    "BUDGET_STANDARD":          "BUDS",
    "BUDGET_PLUS":              "BUDP",
    "BUDGET_PREMIUM":           "BUDPR",

    "REPORT_STANDARD":          "REPS",
    "REPORT_PLUS":             "REPP",
    "REPORT_PREMIUM":          "REPPR",

    "VARIANCE_STANDARD":        "VARS",
    "VARIANCE_PLUS":            "VARP",
    "VARIANCE_PREMIUM":         "VARPR",

    "MARGIN_STANDARD":          "MARS",
    "MARGIN_PLUS":              "MARP",
    "MARGIN_PREMIUM":           "MARPR",

    "FORECAST_STANDARD":        "FORS",
    "FORECAST_PLUS":            "FORP",
    "FORECAST_PREMIUM":         "FORPR",

    "DECISION_STANDARD":        "DECS",
    "DECISION_PLUS":            "DECP",
    "DECISION_PREMIUM":         "DECPR",
}

# 3) CODE -> agent_slug
AGENT_CODE_TO_SLUG = {
    "CFS":   "SINGLE_CF_AI_AGENT",
    "CFP":   "PROJECT_CF_AI_AGENT",   # CFP
    "CFPR":  "ENTERPRISE_CF_AI_AGENT",

    "REVS":  "REVENUE_STANDARD",
    "REVP":  "REVENUE_INTERMEDIATE",
    "REVPR": "REVENUE_ADVANCE",

    "CAPEXS":  "CAPEX_STANDARD",
    "CAPEXP":  "CAPEX_PLUS",
    "CAPEXPR": "CAPEX_PREMIUM",

    "FXS":   "FX_STANDARD",
    "FXP":   "FX_PLUS",
    "FXPR":  "FX_PREMIUM",

    "COSTS":  "COST_STANDARD",
    "COSTP":  "COST_PLUS",
    "COSTPR": "COST_PREMIUM",

    "BUDS":  "BUDGET_STANDARD",
    "BUDP":  "BUDGET_PLUS",
    "BUDPR": "BUDGET_PREMIUM",

    "REPS":  "REPORT_STANDARD",
    "REPP":  "REPORT_PLUS",
    "REPPR": "REPORT_PREMIUM",

    "VARS":  "VARIANCE_STANDARD",
    "VARP":  "VARIANCE_PLUS",
    "VARPR": "VARIANCE_PREMIUM",

    "MARS":  "MARGIN_STANDARD",
    "MARP":  "MARGIN_PLUS",
    "MARPR": "MARGIN_PREMIUM",

    "FORS":  "FORECAST_STANDARD",
    "FORP":  "FORECAST_PLUS",
    "FORPR": "FORECAST_PREMIUM",

    "DECS":  "DECISION_STANDARD",
    "DECP":  "DECISION_PLUS",
    "DECPR": "DECISION_PREMIUM",
}

__all__ = [
    "AGENT_SPECS",
    "AGENT_SKU_TO_CODE",
    "AGENT_SLUG_TO_CODE",
    "AGENT_CODE_TO_SLUG",
]
