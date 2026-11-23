"""Public read-only reference lists for catalog filters and the tour form."""
from fastapi import APIRouter

from app.core.deps import DbSession
from app.schemas.reference import CityOut, CountryOut, HotelOut, ResortOut, ServiceOptionOut
from app.services import reference as reference_service

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/countries", response_model=list[CountryOut], summary="Країни")
def countries(db: DbSession):
    return reference_service.countries(db)


@router.get("/resorts", response_model=list[ResortOut], summary="Курорти (за країною)")
def resorts(db: DbSession, country_id: int | None = None):
    return reference_service.resorts(db, country_id)


@router.get("/hotels", response_model=list[HotelOut], summary="Готелі (за курортом або країною)")
def hotels(db: DbSession, resort_id: int | None = None, country_id: int | None = None):
    return reference_service.hotels(db, resort_id, country_id)


@router.get("/cities", response_model=list[CityOut], summary="Міста відправлення")
def cities(db: DbSession):
    return reference_service.cities(db)


@router.get("/insurance-types", response_model=list[ServiceOptionOut],
            summary="Типи медичного страхування (ціна за туриста)")
def insurance_types(db: DbSession):
    return reference_service.insurance_types(db)


@router.get("/transfer-types", response_model=list[ServiceOptionOut],
            summary="Типи трансферу (ціна за замовлення)")
def transfer_types(db: DbSession):
    return reference_service.transfer_types(db)
