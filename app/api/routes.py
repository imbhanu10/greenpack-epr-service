"""API routes for EPR declaration, summary, and question workflows."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.db.crud import (
    DeclarationRecord,
    create_declaration_record,
    get_latest_declaration_record,
)
from app.db.database import get_session
from app.schemas.declaration import (
    AskRequest,
    AskResponse,
    DeclarationSubmitRequest,
    DeclarationSubmitResponse,
    MONTH_REGEX,
    ReconciliationItemResponse,
    ReconciliationResponse,
    SummaryResponse,
)
from app.services.rag_service import answer_question
from app.services.llm_service import (
    LLMConfigurationError,
    LLMServiceError,
    generate_reconciliation_summary,
)
from app.services.reconciliation_service import (
    ReconciliationResult,
    reconcile_declaration_against_erp,
)

router = APIRouter()

ProducerIdPath = Annotated[str, Path(min_length=1)]
MonthPath = Annotated[str, Path(pattern=MONTH_REGEX)]
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.post(
    "/submit",
    response_model=DeclarationSubmitResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit(
    payload: DeclarationSubmitRequest,
    session: DatabaseSession,
) -> DeclarationSubmitResponse:
    """Persist a validated EPR declaration."""
    record = create_declaration_record(
        session=session,
        payload=payload,
    )

    return _build_submit_response(record)


def _build_submit_response(
    record: DeclarationRecord,
) -> DeclarationSubmitResponse:
    """Convert persisted declaration into API response."""
    return DeclarationSubmitResponse(
        record_id=record.record_id,
        producer_id=record.producer_id,
        month=record.month,
        declared_quantities_kg=record.declaration_data[
            "declared_quantities_kg"
        ],
        created_at=record.created_at,
    )


@router.get(
    "/summary/{producer_id}/{month}",
    response_model=SummaryResponse,
)
def get_summary(
    producer_id: ProducerIdPath,
    month: MonthPath,
    session: DatabaseSession,
) -> SummaryResponse:
    """Return reconciliation results with LLM summary."""
    declaration = get_latest_declaration_record(
        session=session,
        producer_id=producer_id,
        month=month,
    )

    if declaration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Declaration not found for producer and month."
            ),
        )

    result = reconcile_declaration_against_erp(
        producer_id=producer_id,
        month=month,
        declared_quantities_kg=declaration.declaration_data[
            "declared_quantities_kg"
        ],
    )

    reconciliation_json = (
        _build_reconciliation_response(result)
        .model_dump(mode="json")
    )

    llm_summary = _generate_llm_summary(
        reconciliation_json
    )

    return SummaryResponse(
        producer_id=producer_id,
        month=month,
        reconciliation_results=reconciliation_json[
            "items"
        ],
        llm_summary=llm_summary,
    )


def _build_reconciliation_response(
    result: ReconciliationResult,
) -> ReconciliationResponse:
    """Convert reconciliation result into response schema."""
    return ReconciliationResponse(
        producer_id=result.producer_id,
        month=result.month,
        mismatch_threshold_percent=(
            result.mismatch_threshold_percent
        ),
        erp_record_count=result.erp_record_count,
        has_mismatches=result.has_mismatches,
        items=[
            ReconciliationItemResponse(
                material_type=item.material_type,
                declared_quantity_kg=(
                    item.declared_quantity_kg
                ),
                procured_quantity_kg=(
                    item.procured_quantity_kg
                ),
                variance_kg=item.variance_kg,
                variance_percent=item.variance_percent,
                is_mismatch=item.is_mismatch,
            )
            for item in result.items
        ],
    )


def _generate_llm_summary(
    reconciliation_json: dict[str, Any],
) -> str:
    """Generate Gemini summary safely."""
    try:
        return generate_reconciliation_summary(
            reconciliation_json
        )

    except LLMConfigurationError as exc:
        return f"LLM summary unavailable: {exc}"

    except LLMServiceError as exc:
        return f"LLM summary unavailable: {exc}"


@router.post(
    "/ask",
    response_model=AskResponse,
)
def ask(
    payload: AskRequest,
) -> AskResponse:
    """Answer EPR compliance questions using RAG."""
    result = answer_question(payload.question)

    return AskResponse(
        answer=result["answer"],
        citations=result["citations"],
    )
