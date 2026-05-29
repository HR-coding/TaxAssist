from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# ==============================================================================
# GENERAL ENUMS & BASIC MODELS
# ==============================================================================

class FilingSection(str, Enum):
    ON_OR_BEFORE_DUE_DATE = "139_1"
    BELATED = "139_4"
    REVISED = "139_5"
    AFTER_CONDONATION_OF_DELAY = "119_2_b"

class ResidentialStatus(str, Enum):
    RESIDENT = "RES"
    NON_RESIDENT = "NRI"
    RESIDENT_BUT_NOT_ORDINARILY_RESIDENT = "RNOR"

class HousePropertyType(str, Enum):
    SELF_OCCUPIED = "SELF_OCCUPIED"
    LET_OUT = "LET_OUT"
    DEEMED_LET_OUT = "DEEMED_LET_OUT"

class AssetType(str, Enum):
    LISTED_SHARES = "LISTED_SHARES"
    UNLISTED_SHARES = "UNLISTED_SHARES"
    REAL_ESTATE = "REAL_ESTATE"
    DEBT_MUTUAL_FUNDS = "DEBT_MUTUAL_FUNDS"
    GOLD_JEWELLERY = "GOLD_JEWELLERY"
    OTHERS = "OTHERS"

class PersonalInfo(BaseModel):
    pan: str = Field(..., pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", description="Permanent Account Number")
    aadhaar_number: Optional[str] = Field(None, pattern=r"^[0-9]{12}$")
    first_name: str
    middle_name: Optional[str] = None
    last_name: str
    date_of_birth: date
    email: str = Field(..., description="Email address of the filer")
    mobile_number: str
    residential_status: ResidentialStatus = ResidentialStatus.RESIDENT
    filing_section: FilingSection = FilingSection.ON_OR_BEFORE_DUE_DATE

class TaxesPaidSummary(BaseModel):
    advance_tax: float = Field(default=0.0)
    self_assessment_tax: float = Field(default=0.0)
    tds_on_salary: float = Field(default=0.0)
    tds_other_than_salary: float = Field(default=0.0)
    tcs: float = Field(default=0.0)
    total_taxes_paid: float = Field(default=0.0)

# ==============================================================================
# ITR-1 (SAHAJ) SCHEMA REPRESENTATION
# ==============================================================================

class ITR1Salary(BaseModel):
    gross_salary: float = Field(..., description="Salary as per section 17(1) + perquisites + profits in lieu of salary")
    exempt_allowances: float = Field(default=0.0, description="Exempt allowances u/s 10 (e.g. HRA, LTA)")
    standard_deduction: float = Field(default=50000.0, description="Standard deduction u/s 16(ia)")
    entertainment_allowance: float = Field(default=0.0, description="Deduction u/s 16(ii)")
    professional_tax: float = Field(default=0.0, description="Deduction u/s 16(iii)")
    net_salary_income: float = Field(default=0.0)

class ITR1HouseProperty(BaseModel):
    property_type: HousePropertyType = HousePropertyType.SELF_OCCUPIED
    gross_rent_received: float = Field(default=0.0)
    municipal_taxes_paid: float = Field(default=0.0)
    annual_value: float = Field(default=0.0)
    standard_deduction_30: float = Field(default=0.0, description="30% of Annual Value")
    interest_on_borrowed_capital: float = Field(default=0.0, description="Interest on housing loan")
    net_house_property_income: float = Field(default=0.0)

class ITR1OtherSources(BaseModel):
    savings_interest: float = Field(default=0.0)
    deposit_interest: float = Field(default=0.0)
    family_pension: float = Field(default=0.0)
    dividend_income: float = Field(default=0.0)
    others: float = Field(default=0.0)
    deductions_u_s_57_iia: float = Field(default=0.0, description="Family pension deduction u/s 57")
    net_other_sources_income: float = Field(default=0.0)

class ITR1ChapterVIA(BaseModel):
    sec_80c: float = Field(default=0.0, le=150000.0)
    sec_80ccc: float = Field(default=0.0, le=150000.0)
    sec_80ccd1: float = Field(default=0.0, le=150000.0)
    sec_80ccd1b: float = Field(default=0.0, le=50000.0, description="NPS self contribution")
    sec_80ccd2: float = Field(default=0.0, description="NPS employer contribution")
    sec_80d: float = Field(default=0.0, description="Health insurance premium")
    sec_80dd: float = Field(default=0.0, description="Disabled dependent maintenance")
    sec_80ddb: float = Field(default=0.0, description="Medical treatment for specified diseases")
    sec_80e: float = Field(default=0.0, description="Interest on education loan")
    sec_80ee: float = Field(default=0.0, description="Interest on home loan")
    sec_80eea: float = Field(default=0.0, description="Affordable housing loan interest")
    sec_80eeb: float = Field(default=0.0, description="Electric vehicle loan interest")
    sec_80g: float = Field(default=0.0, description="Donations to charitable funds")
    sec_80gg: float = Field(default=0.0, description="Rent paid (no HRA received)")
    sec_80gga: float = Field(default=0.0)
    sec_80ggc: float = Field(default=0.0, description="Contribution to political parties")
    sec_80tta: float = Field(default=0.0, le=10000.0, description="Savings account interest deduction")
    sec_80ttb: float = Field(default=0.0, le=50000.0, description="Senior citizen interest deduction")
    sec_80u: float = Field(default=0.0, description="Person with disability deduction")
    total_chapter_via_deductions: float = Field(default=0.0)

class ITR1ExemptIncome(BaseModel):
    agricultural_income: float = Field(default=0.0, le=5000.0, description="Exempt agricultural income (Max Rs. 5,000 for ITR-1)")
    others_exempt: float = Field(default=0.0)

class ITR1Profile(BaseModel):
    """
    ITR-1 (Sahaj) Schema.
    Designed for Residents having Income from Salary, One House Property,
    Other Sources, and Agricultural Income up to Rs. 5,000.
    """
    user_id: str
    tax_year: int
    personal_info: PersonalInfo
    salary_income: ITR1Salary
    house_property: Optional[ITR1HouseProperty] = None
    other_sources: ITR1OtherSources
    deductions: ITR1ChapterVIA
    exempt_income: ITR1ExemptIncome
    taxes_paid: TaxesPaidSummary
    modified_at: datetime = Field(default_factory=datetime.utcnow)

# ==============================================================================
# ITR-2 SCHEMA REPRESENTATION (COMPLEX MULTI-SCHEDULE)
# ==============================================================================

class ITR2SalaryEmployer(BaseModel):
    employer_name: str
    employer_ein: str
    employer_address: str
    salary_u_s_17_1: float
    perquisites_u_s_17_2: float
    profits_in_lieu_u_s_17_3: float
    exempt_allowances_total: float
    deductions_u_s_16_total: float = Field(default=50000.0)
    net_employer_income: float

class ITR2HousePropertyDetail(BaseModel):
    property_address: str
    co_owned: bool = False
    owner_percentage: float = 100.0
    property_type: HousePropertyType = HousePropertyType.LET_OUT
    annual_letting_value: float = Field(default=0.0, description="Rent received or receivable")
    municipal_taxes_paid: float = Field(default=0.0)
    net_annual_value: float = Field(default=0.0)
    standard_deduction_30: float = Field(default=0.0)
    interest_on_borrowed_capital: float = Field(default=0.0)
    unrealized_rent_recovered_u_s_25a: float = Field(default=0.0)
    net_property_income: float

class CapitalGainTransaction(BaseModel):
    asset_type: AssetType
    shares_111a_compliant: bool = False
    shares_112a_compliant: bool = False
    date_of_acquisition: date
    date_of_transfer: date
    full_value_of_consideration: float = Field(..., description="Sale value")
    cost_of_acquisition: float
    cost_of_improvement: float = Field(default=0.0)
    indexed_cost_of_acquisition: float = Field(default=0.0)
    indexed_cost_of_improvement: float = Field(default=0.0)
    expenditure_on_transfer: float = Field(default=0.0)
    capital_gains_amount: float = Field(default=0.0)

class ITR2CapitalGainsSchedule(BaseModel):
    short_term_gains: List[CapitalGainTransaction] = Field(default_factory=list)
    long_term_gains: List[CapitalGainTransaction] = Field(default_factory=list)
    total_short_term_cg: float = Field(default=0.0)
    total_long_term_cg: float = Field(default=0.0)

class ITR2OtherSourcesDetail(BaseModel):
    savings_interest: float = Field(default=0.0)
    fd_interest: float = Field(default=0.0)
    dividend_income_domestic: float = Field(default=0.0)
    dividend_income_foreign: float = Field(default=0.0)
    family_pension: float = Field(default=0.0)
    rental_from_machinery_plant: float = Field(default=0.0)
    deductions_u_s_57: float = Field(default=0.0, description="Deductions directly linked to earning other income")
    net_other_sources_income: float = Field(default=0.0)

class ITR2ForeignAssets(BaseModel):
    foreign_bank_accounts: List[Dict[str, Any]] = Field(default_factory=list, description="Schedule FA - Bank Accounts details")
    foreign_equity_holdings: List[Dict[str, Any]] = Field(default_factory=list, description="Schedule FA - Shares holdings")
    foreign_immovable_properties: List[Dict[str, Any]] = Field(default_factory=list)
    other_foreign_assets: List[Dict[str, Any]] = Field(default_factory=list)

class ITR2AssetsLiabilities(BaseModel):
    """
    Schedule AL - Mandatory to fill if total income exceeds Rs. 50 Lakhs.
    """
    immovable_assets_cost: float = Field(default=0.0, description="Cost of Land & Building")
    movable_assets_cost: float = Field(default=0.0, description="Cost of shares, cash in hand, vehicles, jewellery")
    liabilities_outstanding: float = Field(default=0.0)

class ITR2Profile(BaseModel):
    """
    ITR-2 Schema.
    Designed for Individuals having income from Salaries, multiple House Properties,
    Capital Gains, Foreign Assets, and exceeding limits of ITR-1.
    """
    user_id: str
    tax_year: int
    personal_info: PersonalInfo
    schedule_salary: List[ITR2SalaryEmployer] = Field(default_factory=list)
    schedule_house_property: List[ITR2HousePropertyDetail] = Field(default_factory=list)
    schedule_capital_gains: ITR2CapitalGainsSchedule = Field(default_factory=ITR2CapitalGainsSchedule)
    schedule_other_sources: ITR2OtherSourcesDetail = Field(default_factory=ITR2OtherSourcesDetail)
    schedule_foreign_assets: Optional[ITR2ForeignAssets] = None
    schedule_via_deductions: ITR1ChapterVIA = Field(default_factory=ITR1ChapterVIA)
    schedule_al_assets_liabilities: Optional[ITR2AssetsLiabilities] = None
    taxes_paid: TaxesPaidSummary = Field(default_factory=TaxesPaidSummary)
    modified_at: datetime = Field(default_factory=datetime.utcnow)
