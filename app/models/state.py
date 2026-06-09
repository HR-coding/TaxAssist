"""
State tracker models.
Schema source: schemas.jsonc (State Tracking Schema, FY 2025-26)
"""
from __future__ import annotations
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, List
from datetime import datetime


class PrerequisiteItem(BaseModel):
    status: str = "PENDING"               # PENDING | UNVERIFIED UPLOAD | VERIFIED | NOT APPLICABLE
    source_drive_ids: List[str] = Field(default_factory=list)
    description: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ITR1Prerequisites(BaseModel):
    pan_aadhaar_linking_status: PrerequisiteItem = Field(default_factory=PrerequisiteItem)
    bank_account_prevalidation: PrerequisiteItem = Field(default_factory=PrerequisiteItem)
    part_a_general_personal_info: PrerequisiteItem = Field(
        default_factory=lambda: PrerequisiteItem(
            description="Validation of Name, Address, Contact details, and Nature of Employment"
        )
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ITR2Prerequisites(BaseModel):
    pan_aadhaar_linking_status: PrerequisiteItem = Field(default_factory=PrerequisiteItem)
    bank_account_prevalidation: PrerequisiteItem = Field(default_factory=PrerequisiteItem)
    part_a_general_info: PrerequisiteItem = Field(
        default_factory=lambda: PrerequisiteItem(
            description="Identity, contact details, and residential status selection"
        )
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ScheduleChecklistItem(BaseModel):
    status: str = "NOT APPLICABLE"        # NOT APPLICABLE | PENDING | UNVERIFIED UPLOAD | VERIFIED
    source_drive_ids: List[str] = Field(default_factory=list)
    description: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ContextMetadata(BaseModel):
    target_schedule: Optional[str] = None
    filename: Optional[str] = None
    old_value: Optional[float] = None
    new_value: Optional[float] = None
    error_log: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class NotificationBlock(BaseModel):
    type: str = "NONE"                    # ALERT | VERIFY | REQUEST | NONE
    reason_code: Optional[str] = None    # PREREQUISITE_MISSING | UPLOAD_SUCCESS | DOCUMENT_VARIANCE | AUTH_BLOCKED
    context_metadata: ContextMetadata = Field(default_factory=ContextMetadata)

    model_config = ConfigDict(populate_by_name=True, extra="allow")


# Default checklist structures per ITR type
ITR1_CHECKLIST_DEFAULTS: Dict[str, dict] = {
    "income_from_salary": {
        "status": "NOT APPLICABLE", "source_drive_ids": []
    },
    "income_from_one_house_property": {
        "status": "NOT APPLICABLE", "source_drive_ids": []
    },
    "income_from_other_sources": {
        "status": "NOT APPLICABLE",
        "source_drive_ids": [],
        "description": "Savings/FD Interest, Dividend Income, or Family Pension"
    },
    "schedule_via_deductions": {
        "status": "NOT APPLICABLE",
        "source_drive_ids": [],
        "description": "Chapter VI-A allowances: 80C, 80D, 80TTA, 80TTB"
    },
    "schedule_taxes_paid": {
        "status": "NOT APPLICABLE",
        "source_drive_ids": [],
        "description": "TDS on Salary (Form 16), TDS on Other (Form 16A), Advance Tax, Self-Assessment Tax"
    },
}

ITR2_CHECKLIST_DEFAULTS: Dict[str, dict] = {
    "schedule_s_salary": {"status": "NOT APPLICABLE", "source_drive_ids": []},
    "schedule_hp_house_property": {"status": "NOT APPLICABLE", "source_drive_ids": []},
    "schedule_cg_capital_gains": {"status": "NOT APPLICABLE", "source_drive_ids": []},
    "schedule_vda_virtual_digital_assets": {"status": "NOT APPLICABLE", "source_drive_ids": []},
    "schedule_os_other_sources": {"status": "NOT APPLICABLE", "source_drive_ids": []},
    "schedule_cfl_carry_forward_losses": {"status": "NOT APPLICABLE", "source_drive_ids": []},
    "schedule_via_deductions": {"status": "NOT APPLICABLE", "source_drive_ids": []},
    "schedule_fa_foreign_assets": {"status": "NOT APPLICABLE", "source_drive_ids": []},
    "schedule_al_assets_and_liabilities": {"status": "NOT APPLICABLE", "source_drive_ids": []},
    "schedule_tax_credits_26as_ais": {"status": "NOT APPLICABLE", "source_drive_ids": []},
}

ITR1_MILESTONE_DEFAULTS: Dict[str, bool] = {
    "ais_tis_reconciliation_matched": False,
    "gross_total_income_computed": False,
    "part_b_tti_tax_liability_finalized": False,
    "json_utility_file_generated": False,
    "e_verification_completed": False,
}

ITR2_MILESTONE_DEFAULTS: Dict[str, bool] = {
    "ais_tis_reconciliation_matched": False,
    "part_b_ti_total_income_computed": False,
    "part_b_tti_tax_liability_finalized": False,
    "json_utility_file_generated": False,
    "e_verification_completed": False,
}


class StateTracker(BaseModel):
    user_id: str
    tax_year: int = 2025
    assessment_year: str = "2026-27"
    itr_type: str = "ITR1"                # ITR1 | ITR2
    current_portal_stage: str = "PREREQUISITES"
    # PREREQUISITES | VALIDATING_INCOME | VALIDATING_DEDUCTIONS | COMPUTATION | DONE

    notification: NotificationBlock = Field(default_factory=NotificationBlock)

    # Stored as raw dicts in MongoDB for flexibility; initialised from defaults above
    portal_prerequisites: Dict = Field(default_factory=dict)
    schedule_checklist: Dict = Field(default_factory=dict)
    portal_validation_milestones: Dict[str, bool] = Field(default_factory=dict)

    modified_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")
