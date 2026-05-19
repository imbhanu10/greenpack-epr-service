"""Deterministic reconciliation workflow services."""

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping


MISMATCH_THRESHOLD_PERCENT = Decimal("5")
DEFAULT_ERP_CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "mock_erp_feed.csv"


@dataclass(frozen=True, slots=True)
class SubmissionResult:
    """Result of accepting a declaration for later processing."""

    status: str
    message: str


@dataclass(frozen=True, slots=True)
class MaterialQuantity:
    """Material quantity used as reconciliation input."""

    material_type: str
    quantity_kg: Decimal


@dataclass(frozen=True, slots=True)
class ERPProcurementRecord:
    """Procurement record loaded from the ERP feed."""

    producer_id: str
    month: str
    material_type: str
    quantity_kg: Decimal
    procurement_date: str
    supplier_name: str
    invoice_number: str


@dataclass(frozen=True, slots=True)
class ReconciliationItem:
    """Material-level reconciliation result."""

    material_type: str
    declared_quantity_kg: Decimal
    procured_quantity_kg: Decimal
    variance_kg: Decimal
    variance_percent: Decimal | None
    is_mismatch: bool


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Complete deterministic reconciliation result."""

    items: list[ReconciliationItem]
    has_mismatches: bool
    producer_id: str = ""
    month: str = ""
    mismatch_threshold_percent: Decimal = MISMATCH_THRESHOLD_PERCENT
    erp_record_count: int = 0


def submit_declaration(*, producer_id: str, month: str) -> SubmissionResult:
    """Accept a declaration payload for future reconciliation logic."""
    return SubmissionResult(
        status="accepted",
        message=f"Declaration received for producer {producer_id} for {month}.",
    )


def reconcile_declaration_against_erp(
    *,
    producer_id: str,
    month: str,
    declared_quantities_kg: Mapping[str, Any],
    erp_csv_path: Path | str = DEFAULT_ERP_CSV_PATH,
    mismatch_threshold_percent: Decimal = MISMATCH_THRESHOLD_PERCENT,
) -> ReconciliationResult:
    """Compare submitted declaration quantities against ERP procurement data."""
    declared_materials = [
        MaterialQuantity(
            material_type=material_type,
            quantity_kg=_parse_quantity(quantity_kg, "declared quantity"),
        )
        for material_type, quantity_kg in declared_quantities_kg.items()
    ]
    erp_records = load_erp_procurement_records(erp_csv_path)
    matching_records = filter_erp_records(
        erp_records=erp_records,
        producer_id=producer_id,
        month=month,
    )
    procured_materials = [
        MaterialQuantity(
            material_type=record.material_type,
            quantity_kg=record.quantity_kg,
        )
        for record in matching_records
    ]

    return reconcile_declared_vs_procured(
        declared_materials=declared_materials,
        procured_materials=procured_materials,
        mismatch_threshold_percent=mismatch_threshold_percent,
        producer_id=producer_id,
        month=month,
        erp_record_count=len(matching_records),
    )


def load_erp_procurement_records(
    csv_path: Path | str = DEFAULT_ERP_CSV_PATH,
) -> list[ERPProcurementRecord]:
    """Load procurement records from an ERP CSV export."""
    path = Path(csv_path)
    with path.open(mode="r", encoding="utf-8", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        _validate_erp_columns(reader.fieldnames)
        return [
            _parse_erp_row(row=row, row_number=row_number)
            for row_number, row in enumerate(reader, start=2)
        ]


def filter_erp_records(
    *,
    erp_records: list[ERPProcurementRecord],
    producer_id: str,
    month: str,
) -> list[ERPProcurementRecord]:
    """Return ERP records for a producer and reporting month."""
    normalized_producer_id = _normalize_producer_id(producer_id)
    return [
        record
        for record in erp_records
        if _normalize_producer_id(record.producer_id) == normalized_producer_id
        and record.month == month
    ]


def reconcile_declared_vs_procured(
    declared_materials: list[MaterialQuantity],
    procured_materials: list[MaterialQuantity],
    mismatch_threshold_percent: Decimal = MISMATCH_THRESHOLD_PERCENT,
    producer_id: str = "",
    month: str = "",
    erp_record_count: int = 0,
) -> ReconciliationResult:
    """Compare declared and procured quantities and flag material mismatches."""
    if not mismatch_threshold_percent.is_finite():
        raise ValueError("mismatch_threshold_percent must be finite")
    if mismatch_threshold_percent < 0:
        raise ValueError("mismatch_threshold_percent must not be negative")

    declared_totals = _aggregate_materials(declared_materials)
    procured_totals = _aggregate_materials(procured_materials)
    material_types = sorted(declared_totals.keys() | procured_totals.keys())

    items = [
        _build_reconciliation_item(
            material_type=material_type,
            declared_quantity_kg=declared_totals.get(material_type, Decimal("0")),
            procured_quantity_kg=procured_totals.get(material_type, Decimal("0")),
            mismatch_threshold_percent=mismatch_threshold_percent,
        )
        for material_type in material_types
    ]

    return ReconciliationResult(
        items=items,
        has_mismatches=any(item.is_mismatch for item in items),
        producer_id=producer_id,
        month=month,
        mismatch_threshold_percent=mismatch_threshold_percent,
        erp_record_count=erp_record_count,
    )


def _aggregate_materials(materials: list[MaterialQuantity]) -> dict[str, Decimal]:
    """Aggregate quantities by normalized material type."""
    totals: dict[str, Decimal] = {}

    for material in materials:
        material_type = _normalize_material_type(material.material_type)
        quantity = _validate_quantity(material.quantity_kg)
        totals[material_type] = totals.get(material_type, Decimal("0")) + quantity

    return totals


def _build_reconciliation_item(
    *,
    material_type: str,
    declared_quantity_kg: Decimal,
    procured_quantity_kg: Decimal,
    mismatch_threshold_percent: Decimal,
) -> ReconciliationItem:
    """Build a material-level reconciliation result."""
    variance_kg = declared_quantity_kg - procured_quantity_kg
    variance_percent = _calculate_variance_percent(
        variance_kg=variance_kg,
        procured_quantity_kg=procured_quantity_kg,
    )
    is_mismatch = _is_mismatch(
        variance_kg=variance_kg,
        variance_percent=variance_percent,
        mismatch_threshold_percent=mismatch_threshold_percent,
    )

    return ReconciliationItem(
        material_type=material_type,
        declared_quantity_kg=declared_quantity_kg,
        procured_quantity_kg=procured_quantity_kg,
        variance_kg=variance_kg,
        variance_percent=variance_percent,
        is_mismatch=is_mismatch,
    )


def _calculate_variance_percent(
    *,
    variance_kg: Decimal,
    procured_quantity_kg: Decimal,
) -> Decimal | None:
    """Calculate variance percentage against procured quantity."""
    if procured_quantity_kg == 0:
        return None

    return (abs(variance_kg) / procured_quantity_kg) * Decimal("100")


def _is_mismatch(
    *,
    variance_kg: Decimal,
    variance_percent: Decimal | None,
    mismatch_threshold_percent: Decimal,
) -> bool:
    """Return whether a variance should be flagged as a mismatch."""
    if variance_percent is None:
        return variance_kg != 0

    return variance_percent > mismatch_threshold_percent


def _normalize_material_type(material_type: str) -> str:
    """Normalize material labels for deterministic comparison."""
    normalized = material_type.strip().lower()
    if not normalized:
        raise ValueError("material_type must not be empty")
    return normalized


def _normalize_producer_id(producer_id: str) -> str:
    """Normalize producer identifiers for deterministic matching."""
    normalized = producer_id.strip().upper()
    if not normalized:
        raise ValueError("producer_id must not be empty")
    return normalized


def _validate_quantity(quantity_kg: Decimal) -> Decimal:
    """Reject invalid quantities before reconciliation."""
    if not quantity_kg.is_finite():
        raise ValueError("quantity_kg must be finite")
    if quantity_kg < 0:
        raise ValueError("quantity_kg must not be negative")
    return quantity_kg


def _parse_quantity(value: Any, field_name: str) -> Decimal:
    """Parse and validate a quantity from declared or ERP input."""
    try:
        quantity = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal") from exc

    return _validate_quantity(quantity)


def _validate_erp_columns(fieldnames: list[str] | None) -> None:
    """Validate required ERP CSV columns are present."""
    required_columns = {
        "producer_id",
        "month",
        "procurement_date",
        "supplier_name",
        "invoice_number",
        "material_type",
        "quantity_kg",
    }
    if fieldnames is None:
        raise ValueError("ERP CSV is missing a header row")

    missing_columns = required_columns - set(fieldnames)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"ERP CSV is missing required columns: {missing}")


def _parse_erp_row(
    *,
    row: dict[str, str],
    row_number: int,
) -> ERPProcurementRecord:
    """Parse a single ERP CSV row into a procurement record."""
    try:
        producer_id = row["producer_id"].strip()
        month = row["month"].strip()
        material_type = row["material_type"].strip()
        quantity_kg = _parse_quantity(row["quantity_kg"], "ERP quantity")
        procurement_date = row["procurement_date"].strip()
        supplier_name = row["supplier_name"].strip()
        invoice_number = row["invoice_number"].strip()
    except KeyError as exc:
        raise ValueError(f"ERP CSV row {row_number} is malformed") from exc

    if not producer_id:
        raise ValueError(f"ERP CSV row {row_number} has an empty producer_id")
    if not month:
        raise ValueError(f"ERP CSV row {row_number} has an empty month")
    if not material_type:
        raise ValueError(f"ERP CSV row {row_number} has an empty material_type")

    return ERPProcurementRecord(
        producer_id=producer_id,
        month=month,
        material_type=material_type,
        quantity_kg=quantity_kg,
        procurement_date=procurement_date,
        supplier_name=supplier_name,
        invoice_number=invoice_number,
    )
