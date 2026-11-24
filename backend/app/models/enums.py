"""All fixed value sets of the system. Ukrainian labels are shown by the frontend.

Order and payment statuses follow ТЗ section 4.4.1.
"""
import enum


class UserRole(str, enum.Enum):
    CLIENT = "client"          # Клієнт
    MANAGER = "manager"        # Менеджер (модератор)
    FINANCE = "finance"        # Фінансовий контролер
    ADMIN = "admin"            # Системний адміністратор


class TourStatus(str, enum.Enum):
    DRAFT = "draft"            # Чернетка
    ACTIVE = "active"          # Активний
    ARCHIVED = "archived"      # Архівний


class TransportType(str, enum.Enum):
    AIR = "air"                # Авіа
    BUS = "bus"                # Автобус
    NONE = "none"              # Без транспорту


class Currency(str, enum.Enum):
    UAH = "UAH"
    EUR = "EUR"
    USD = "USD"


class OrderStatus(str, enum.Enum):
    CHECKOUT = "checkout"                  # Оформлення
    AWAITING_PAYMENT = "awaiting_payment"  # Очікує оплати
    PAID = "paid"                          # Оплачено
    IN_PROGRESS = "in_progress"            # В роботі
    CONFIRMED = "confirmed"                # Підтверджено
    DOCUMENTS_READY = "documents_ready"    # Документи готові
    COMPLETED = "completed"                # Завершено
    REJECTED = "rejected"                  # Відхилено
    CANCEL_REQUESTED = "cancel_requested"  # Очікує скасування
    CANCELLED = "cancelled"                # Скасовано
    ARCHIVED = "archived"                  # Архівний


class PaymentStatus(str, enum.Enum):
    AWAITING = "awaiting"                      # Очікує оплати
    PARTIALLY_PAID = "partially_paid"          # Сплачено частково
    PAID = "paid"                              # Сплачено повністю
    PARTIALLY_REFUNDED = "partially_refunded"  # Повернено частково
    REFUNDED = "refunded"                      # Повернено


class OrderDocumentType(str, enum.Enum):
    VOUCHER = "voucher"                    # Ваучер
    AIR_TICKET = "air_ticket"              # Авіаквиток
    INSURANCE_POLICY = "insurance_policy"  # Страховий поліс
    INFO_SHEET = "info_sheet"              # Інфолист
    # Uploaded by the client with a cancellation request (form 4.6.1.3, field 4); staff only.
    CANCEL_EVIDENCE = "cancel_evidence"    # Довідка до клопотання про скасування


# Documents the manager prepares for the trip (form 4.6.2.2, field 5.1); the client downloads them.
TRIP_DOCUMENT_TYPES = frozenset({OrderDocumentType.VOUCHER, OrderDocumentType.AIR_TICKET,
                                 OrderDocumentType.INSURANCE_POLICY, OrderDocumentType.INFO_SHEET})


class CancelReason(str, enum.Enum):
    """Довідник «Причини скасувань» (form 4.6.1.3, field 2)."""
    ILLNESS = "illness"                    # Хвороба
    CHANGE_OF_PLANS = "change_of_plans"    # Зміна планів
    DATA_ERROR = "data_error"              # Помилка в даних
    VISA_REFUSAL = "visa_refusal"          # Відмова у візі
    OTHER = "other"                        # Інше


class PaymentType(str, enum.Enum):
    PAYMENT = "payment"
    REFUND = "refund"


class PaymentMethod(str, enum.Enum):
    CARD = "card"                    # Stripe
    BANK_TRANSFER = "bank_transfer"  # ручний переказ, підтверджує фін. контролер


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DiscountType(str, enum.Enum):
    PERCENT = "percent"  # Відсоткова
    FIXED = "fixed"      # Фіксована (UAH)


class NameDisplay(str, enum.Enum):
    FULL = "full"            # Повне ім'я
    SHORT = "short"          # Скорочене (Іван І.)
    ANONYMOUS = "anonymous"  # Анонімно
