"""
ITR-1 and ITR-2 Pydantic ledger models.
Schema source: schemas.jsonc (Grand Master Schema for ITR Filing, FY 2025-26)
"""
from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime


# ─────────────────────────────────────────────
# Shared primitives
# ─────────────────────────────────────────────

class NumericField(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class PersonalInfo(BaseModel):
    pan: str = ""
    aadhaar_number: str = ""
    first_name: str = ""
    middle_name: str = ""
    last_name: str = ""
    date_of_birth: Optional[str] = None          # YYYY-MM-DD
    email: str = ""
    mobile_number: str = ""
    residential_status: str = "RES"               # RES | NRI | RNOR
    filing_section: str = "139_1"                 # 139_1 | 139_4 | 139_5 | 119_2_b

    model_config = ConfigDict(populate_by_name=True, extra="allow")


# ─────────────────────────────────────────────
# ITR-1 field models
# ─────────────────────────────────────────────

class ITR1SalaryIncome(BaseModel):
    gross_salary: NumericField = Field(default_factory=NumericField)
    exempt_allowances: NumericField = Field(default_factory=NumericField)
    standard_deduction: NumericField = Field(
        default_factory=lambda: NumericField(value=50000.0, source_doc_id="SYSTEM_DEFAULT")
    )
    entertainment_allowance: NumericField = Field(default_factory=NumericField)
    professional_tax: NumericField = Field(default_factory=NumericField)
    net_salary_income: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ITR1HouseProperty(BaseModel):
    property_type: str = "SELF_OCCUPIED"          # SELF_OCCUPIED | LET_OUT | DEEMED_LET_OUT
    gross_rent_received: NumericField = Field(default_factory=NumericField)
    municipal_taxes_paid: NumericField = Field(default_factory=NumericField)
    annual_value: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )
    standard_deduction_30: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )
    interest_on_borrowed_capital: NumericField = Field(default_factory=NumericField)
    net_house_property_income: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class OtherSourceItem(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None
    description: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ITR1OtherSources(BaseModel):
    savings_interest: List[OtherSourceItem] = Field(default_factory=list)
    deposit_interest: List[OtherSourceItem] = Field(default_factory=list)
    family_pension: NumericField = Field(default_factory=NumericField)
    dividend_income: List[OtherSourceItem] = Field(default_factory=list)
    others: List[OtherSourceItem] = Field(default_factory=list)
    deductions_u_s_57_iia: NumericField = Field(default_factory=NumericField)
    net_other_sources_income: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Deduction80CItem(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None
    category: str = ""                            # PPF | ELSS | EPF | LIC

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Deduction80DItem(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None
    category: str = ""                            # SELF | PARENTS_SENIOR

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Deduction80GItem(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None
    donee_name: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class DeductionItem(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class Deductions(BaseModel):
    sec_80c: List[Deduction80CItem] = Field(default_factory=list)
    sec_80ccc: List[DeductionItem] = Field(default_factory=list)
    sec_80ccd1: List[DeductionItem] = Field(default_factory=list)
    sec_80ccd1b: List[DeductionItem] = Field(default_factory=list)
    sec_80ccd2: List[DeductionItem] = Field(default_factory=list)
    sec_80d: List[Deduction80DItem] = Field(default_factory=list)
    sec_80dd: List[DeductionItem] = Field(default_factory=list)
    sec_80ddb: List[DeductionItem] = Field(default_factory=list)
    sec_80e: List[DeductionItem] = Field(default_factory=list)
    sec_80ee: List[DeductionItem] = Field(default_factory=list)
    sec_80eea: List[DeductionItem] = Field(default_factory=list)
    sec_80eeb: List[DeductionItem] = Field(default_factory=list)
    sec_80g: List[Deduction80GItem] = Field(default_factory=list)
    sec_80gg: List[DeductionItem] = Field(default_factory=list)
    sec_80gga: List[DeductionItem] = Field(default_factory=list)
    sec_80ggc: List[DeductionItem] = Field(default_factory=list)
    sec_80tta: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )
    sec_80ttb: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )
    sec_80u: List[DeductionItem] = Field(default_factory=list)
    total_chapter_via_deductions: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ExemptIncome(BaseModel):
    agricultural_income: NumericField = Field(default_factory=NumericField)
    others_exempt: List[dict] = Field(default_factory=list)  # {value, source_doc_id, section}

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class AdvanceTaxItem(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None
    bsr_code: str = ""
    challan_no: str = ""
    date: Optional[str] = None                   # YYYY-MM-DD

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class TDSSalaryItem(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None
    deductor_tan: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class TCSItem(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None
    collector_tan: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class TaxesPaid(BaseModel):
    advance_tax: List[AdvanceTaxItem] = Field(default_factory=list)
    self_assessment_tax: List[AdvanceTaxItem] = Field(default_factory=list)
    tds_on_salary: List[TDSSalaryItem] = Field(default_factory=list)
    tds_other_than_salary: List[TDSSalaryItem] = Field(default_factory=list)
    tcs: List[TCSItem] = Field(default_factory=list)
    total_taxes_paid: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ITR1Ledger(BaseModel):
    user_id: str = ""
    itr_type: str = "ITR1"
    tax_year: int = 2025
    assessment_year: str = "2026-27"
    filing_status: str = "DRAFT"
    tax_regime: str = "NEW"                       # NEW | OLD — used by calculator
    modified_at: Optional[datetime] = None

    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    salary_income: ITR1SalaryIncome = Field(default_factory=ITR1SalaryIncome)
    house_property: ITR1HouseProperty = Field(default_factory=ITR1HouseProperty)
    other_sources: ITR1OtherSources = Field(default_factory=ITR1OtherSources)
    deductions: Deductions = Field(default_factory=Deductions)
    exempt_income: ExemptIncome = Field(default_factory=ExemptIncome)
    taxes_paid: TaxesPaid = Field(default_factory=TaxesPaid)

    model_config = ConfigDict(populate_by_name=True, extra="allow")


# ─────────────────────────────────────────────
# ITR-2 field models
# ─────────────────────────────────────────────

class ScheduleSalaryItem(BaseModel):
    source_doc_id: Optional[str] = None
    employer_name: str = ""
    employer_ein: str = ""
    employer_address: str = ""
    salary_u_s_17_1: float = 0.0
    perquisites_u_s_17_2: float = 0.0
    profits_in_lieu_u_s_17_3: float = 0.0
    exempt_allowances_total: float = 0.0
    deductions_u_s_16_total: float = 50000.0
    net_employer_income: float = 0.0              # CALCULATED_FIELD

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ScheduleHousePropertyItem(BaseModel):
    source_doc_id: Optional[str] = None
    property_address: str = ""
    co_owned: bool = False
    owner_percentage: float = 100.0
    property_type: str = "SELF_OCCUPIED"          # SELF_OCCUPIED | LET_OUT | DEEMED_LET_OUT
    annual_letting_value: float = 0.0
    municipal_taxes_paid: float = 0.0
    net_annual_value: float = 0.0                 # CALCULATED_FIELD
    standard_deduction_30: float = 0.0            # CALCULATED_FIELD
    interest_on_borrowed_capital: float = 0.0
    unrealized_rent_recovered_u_s_25a: float = 0.0
    net_property_income: float = 0.0              # CALCULATED_FIELD

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class CapitalGainItem(BaseModel):
    source_doc_id: Optional[str] = None
    asset_type: str = "OTHERS"
    # LISTED_SHARES | UNLISTED_SHARES | REAL_ESTATE | DEBT_MUTUAL_FUNDS | GOLD_JEWELLERY | OTHERS
    shares_111a_compliant: bool = False
    shares_112a_compliant: bool = False
    date_of_acquisition: Optional[str] = None    # YYYY-MM-DD
    date_of_transfer: Optional[str] = None       # YYYY-MM-DD
    full_value_of_consideration: float = 0.0
    cost_of_acquisition: float = 0.0
    cost_of_improvement: float = 0.0
    indexed_cost_of_acquisition: float = 0.0
    indexed_cost_of_improvement: float = 0.0
    expenditure_on_transfer: float = 0.0
    capital_gains_amount: float = 0.0             # CALCULATED_FIELD

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ScheduleCapitalGains(BaseModel):
    short_term_gains: List[CapitalGainItem] = Field(default_factory=list)
    long_term_gains: List[CapitalGainItem] = Field(default_factory=list)
    total_short_term_cg: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )
    total_long_term_cg: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ITR2OtherSources(BaseModel):
    savings_interest: List[NumericField] = Field(default_factory=list)
    fd_interest: List[NumericField] = Field(default_factory=list)
    dividend_income_domestic: List[NumericField] = Field(default_factory=list)
    dividend_income_foreign: List[NumericField] = Field(default_factory=list)
    family_pension: NumericField = Field(default_factory=NumericField)
    rental_from_machinery_plant: NumericField = Field(default_factory=NumericField)
    deductions_u_s_57: NumericField = Field(default_factory=NumericField)
    net_other_sources_income: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ForeignBankAccountItem(BaseModel):
    source_doc_id: Optional[str] = None
    institution_name: str = ""
    account_number_masked: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ForeignEquityItem(BaseModel):
    source_doc_id: Optional[str] = None
    company_name: str = ""
    investment_amount: float = 0.0

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ForeignImmovablePropertyItem(BaseModel):
    source_doc_id: Optional[str] = None
    property_details: str = ""
    cost_of_acquisition: float = 0.0

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ForeignOtherAssetItem(BaseModel):
    source_doc_id: Optional[str] = None
    asset_description: str = ""
    value: float = 0.0

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ScheduleForeignAssets(BaseModel):
    foreign_bank_accounts: List[ForeignBankAccountItem] = Field(default_factory=list)
    foreign_equity_holdings: List[ForeignEquityItem] = Field(default_factory=list)
    foreign_immovable_properties: List[ForeignImmovablePropertyItem] = Field(default_factory=list)
    other_foreign_assets: List[ForeignOtherAssetItem] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class VDATransactionItem(BaseModel):
    source_doc_id: Optional[str] = None
    asset_name: str = ""
    date_of_acquisition: Optional[str] = None
    date_of_transfer: Optional[str] = None
    cost_of_acquisition: float = 0.0
    consideration_received: float = 0.0
    vda_income: float = 0.0                       # CALCULATED_FIELD: consideration - cost

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ScheduleVDA(BaseModel):
    transactions: List[VDATransactionItem] = Field(default_factory=list)
    total_vda_income: NumericField = Field(
        default_factory=lambda: NumericField(source_doc_id="CALCULATED_FIELD")
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class CFLEntry(BaseModel):
    assessment_year: str = ""
    source: str = ""                              # HOUSE_PROPERTY | SHORT_TERM_CG | LONG_TERM_CG | OTHER_SOURCES
    amount: float = 0.0

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ScheduleCFL(BaseModel):
    brought_forward_losses: List[CFLEntry] = Field(default_factory=list)
    current_year_losses_to_carry_forward: List[CFLEntry] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ALItem(BaseModel):
    value: float = 0.0
    source_doc_id: Optional[str] = None
    description: str = ""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ScheduleAL(BaseModel):
    immovable_assets_cost: List[ALItem] = Field(default_factory=list)
    movable_assets_cost: List[ALItem] = Field(default_factory=list)
    liabilities_outstanding: List[ALItem] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ITR2Ledger(BaseModel):
    user_id: str = ""
    itr_type: str = "ITR2"
    tax_year: int = 2025
    assessment_year: str = "2026-27"
    filing_status: str = "DRAFT"
    tax_regime: str = "NEW"
    modified_at: Optional[datetime] = None

    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    schedule_salary: List[ScheduleSalaryItem] = Field(default_factory=list)
    schedule_house_property: List[ScheduleHousePropertyItem] = Field(default_factory=list)
    schedule_capital_gains: ScheduleCapitalGains = Field(default_factory=ScheduleCapitalGains)
    schedule_other_sources: ITR2OtherSources = Field(default_factory=ITR2OtherSources)
    schedule_foreign_assets: ScheduleForeignAssets = Field(default_factory=ScheduleForeignAssets)
    schedule_via_deductions: Deductions = Field(default_factory=Deductions)
    schedule_vda: ScheduleVDA = Field(default_factory=ScheduleVDA)
    schedule_cfl: ScheduleCFL = Field(default_factory=ScheduleCFL)
    schedule_al_assets_liabilities: ScheduleAL = Field(default_factory=ScheduleAL)
    taxes_paid: TaxesPaid = Field(default_factory=TaxesPaid)

    model_config = ConfigDict(populate_by_name=True, extra="allow")
