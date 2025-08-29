# app/plans.py
from dataclasses import dataclass
from typing import Literal, Set

TierCode = Literal["STANDARD", "PLUS", "PREMIUM"]

@dataclass(frozen=True)
class PlanSpec:
    code: str
    monthly_quota: int
    allowed_tiers: Set[TierCode]
    addon_block: int            # ขนาดบล็อก add-on (หน่วย = calls)
    addon_price: float          # ราคาบล็อก add-on (เพื่อโชว์/บันทึก ไม่ใช้คิดเงินจริง)

ENTERPRISE_STANDARD = PlanSpec(
    code="ENT_STANDARD", monthly_quota=10_000,
    allowed_tiers={"STANDARD"},
    addon_block=1_000, addon_price=9.90
)
ENTERPRISE_PLUS = PlanSpec(
    code="ENT_PLUS", monthly_quota=30_000,
    allowed_tiers={"STANDARD","PLUS"},
    addon_block=1_000, addon_price=12.00  # หรือ 5k = 55 ตามโปรโมชัน
)
ENTERPRISE_PRO = PlanSpec(
    code="ENT_PRO", monthly_quota=100_000,
    allowed_tiers={"STANDARD","PLUS","PREMIUM"},
    addon_block=10_000, addon_price=59.00
)

PLAN_BY_CODE = {
    ENTERPRISE_STANDARD.code: ENTERPRISE_STANDARD,
    ENTERPRISE_PLUS.code: ENTERPRISE_PLUS,
    ENTERPRISE_PRO.code: ENTERPRISE_PRO,
}
