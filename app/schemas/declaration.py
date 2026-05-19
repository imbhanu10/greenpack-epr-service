"""Pydantic schemas for EPR declaration validation."""

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MONTH_REGEX = r"^\d{4}-(0[1-9]|1[0-2])$"
MONTH_PATTERN = re.compile(MONTH_REGEX)


class _DeclarationStoragePayload(BaseModel):
    """Internal storage shape for submitted declaration quantities."""

    declared_quantities_kg: dict[str, Decimal]


class DeclarationSubmitRequest(BaseModel):
    """Request payload for submitting an EPR declaration."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    producer_id: str = Field(..., min_length=1)
    month: str = Field(..., min_length=7, max_length=7, pattern=MONTH_REGEX)
    declared_quantities_kg: dict[str, Decimal] = Field(..., min_length=1)

    @field_validator("producer_id")
    @classmethod
    def validate_producer_id(cls, value: str) -> str:
        """Validate and normalize the producer identifier."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("producer_id must not be empty")
        return normalized

    @field_validator("month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        """Validate month in YYYY-MM format."""
        if not MONTH_PATTERN.fullmatch(value):
            raise ValueError("month must be in YYYY-MM format")
        return value

    @field_validator("declared_quantities_kg")
    @classmethod
    def validate_declared_quantities(
        cls,
        value: dict[str, Decimal],
    ) -> dict[str, Decimal]:
        """Validate declared material quantities."""
        normalized_quantities: dict[str, Decimal] = {}

        for material_type, quantity_kg in value.items():
            normalized_material_type = material_type.strip()
            if not normalized_material_type:
                raise ValueError("material type must not be empty")
            if normalized_material_type in normalized_quantities:
                raise ValueError("material types must be unique")
            if not quantity_kg.is_finite():
                raise ValueError("declared quantities must be finite")
            if quantity_kg < 0:
                raise ValueError("declared quantities must not be negative")

            normalized_quantities[normalized_material_type] = quantity_kg

        return normalized_quantities

    @property
    def declaration_data(self) -> _DeclarationStoragePayload:
        """Return the persistence payload expected by the storage layer."""
        return _DeclarationStoragePayload(
            declared_quantities_kg=self.declared_quantities_kg,
        )


class DeclarationSubmitResponse(BaseModel):
    """Response payload for declaration submission."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    producer_id: str
    month: str
    declared_quantities_kg: dict[str, Decimal]
    created_at: datetime


class ReconciliationItemResponse(BaseModel):
    """Material-level reconciliation response."""

    material_type: str
    declared_quantity_kg: float
    procured_quantity_kg: float
    variance_kg: float
    variance_percent: float | None
    is_mismatch: bool


class ReconciliationResponse(BaseModel):
    """Structured deterministic reconciliation response."""

    producer_id: str
    month: str
    mismatch_threshold_percent: float
    erp_record_count: int
    has_mismatches: bool
    items: list[ReconciliationItemResponse]


class SummaryResponse(BaseModel):
    """Response payload for reconciliation summary results."""

    producer_id: str
    month: str
    reconciliation_results: list[ReconciliationItemResponse]
    llm_summary: str


class AskRequest(BaseModel):
    """Request payload for document-grounded questions."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(..., min_length=1)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        """Validate and normalize the submitted question."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("question must not be empty")
        return normalized


class AskResponse(BaseModel):
    """Response model for compliance question answering."""

    answer: str
    citations: list[str] = Field(default_factory=list)
