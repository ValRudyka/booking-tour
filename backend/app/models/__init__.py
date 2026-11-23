"""Import every model here so Alembic autogenerate sees the full schema."""
from app.models.base import Base
from app.models.catalog import Tour, TourImage, TourProgramDay
from app.models.finance import AuditLog, Payment, Review, ReviewPhoto
from app.models.orders import (ORDER_NUMBER_SEQ, Order, OrderDocument, OrderStatusHistory,
                               OrderTourist, PromoCode)
from app.models.reference import (City, Country, CurrencyRate, Hotel, InsuranceType, Language,
                                  Resort, Setting, TransferType)
from app.models.users import (Favorite, LoyaltyTransaction, Notification, SavedPassport,
                              SearchHistory, User)

__all__ = [
    "Base", "ORDER_NUMBER_SEQ",
    "AuditLog", "City", "Country", "CurrencyRate", "Favorite", "Hotel", "InsuranceType", "Language",
    "LoyaltyTransaction", "Notification", "Order", "OrderDocument", "OrderStatusHistory",
    "OrderTourist", "Payment", "PromoCode", "Resort", "Review", "ReviewPhoto", "SavedPassport",
    "SearchHistory", "Setting", "Tour", "TourImage", "TourProgramDay", "TransferType", "User",
]
