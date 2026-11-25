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


class MealPlan(str, enum.Enum):
    """Board basis of a tour (form 4.6.2.1, «Тип харчування»; added in feature/catalog-improvements).
    On the tour, not the hotel: the same hotel is sold with different boards."""
    RO = "ro"      # Без харчування (room only)
    BB = "bb"      # Сніданок
    HB = "hb"      # Сніданок і вечеря
    FB = "fb"      # Повний пансіон
    AI = "ai"      # Все включено
    UAI = "uai"    # Ультра все включено


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


class OrderGroup(str, enum.Enum):
    """Filter of «Мої замовлення» (GET /api/orders?group=); a query value, never stored.
    Every group leaves out abandoned bookings: cancelled before «Перейти до оплати»."""
    ALL = "all"                # Усі
    ACTIVE = "active"          # Активні
    COMPLETED = "completed"    # Завершені (also archived after «Завершено»)
    CANCELLED = "cancelled"    # Скасовані (rejected, cancelled, archived without a trip)


class ClientAction(str, enum.Enum):
    """What the client may do with an order now (OrderOut.client_actions). Computed by
    services/order_actions.py from the same checks that enforce each action, so the frontend
    shows exactly the buttons the backend would accept."""
    PAY = "pay"                                # POST /orders/{id}/pay
    CONTINUE_CHECKOUT = "continue_checkout"    # back to the booking wizard (PATCH / confirm)
    CANCEL = "cancel"                          # POST /orders/{id}/cancel (unpaid)
    CANCEL_REQUEST = "cancel_request"          # POST /orders/{id}/cancel-request (paid)
    REVIEW = "review"                          # POST /orders/{id}/review
    VIEW_REVIEW = "view_review"                # the order has a review (GET /orders/{id}/review)
    DOWNLOAD_DOCUMENTS = "download_documents"  # trip documents are shown (may still be empty)


class StaffAction(str, enum.Enum):
    """What a manager may do with an order (ManagerOrderDetailOut.staff_actions, spec 09).
    Computed by services/staff_actions.py from the refusals the action endpoints enforce."""
    TAKE = "take"                              # POST /manager/orders/{id}/take
    ASSIGN = "assign"                          # POST .../assign
    CONFIRM = "confirm"                        # POST .../confirm (PNR, operator deadline)
    REJECT = "reject"                          # POST .../reject (reason)
    UPLOAD_DOCUMENTS = "upload_documents"      # POST .../documents
    DOCUMENTS_READY = "documents_ready"        # POST .../documents-ready
    ARCHIVE = "archive"                        # POST .../archive
    EDIT_COMMENT = "edit_comment"              # PATCH .../ (internal comment)


class UserAdminAction(str, enum.Enum):
    """What the admin may do with a user (AdminUserOut.user_actions, spec 13). Computed by
    services/admin_actions.py from the refusals services/admin_users.py enforces."""
    EDIT = "edit"                              # PATCH /admin/users/{id} (names, e-mail, phone)
    CHANGE_ROLE = "change_role"                # PATCH {role}
    BLOCK = "block"                            # PATCH {is_active: false}
    UNBLOCK = "unblock"                        # PATCH {is_active: true}
    RESET_PASSWORD = "reset_password"          # POST /admin/users/{id}/reset-password


class ReferenceAction(str, enum.Enum):
    """What the admin may do with a reference record (admin_actions on the /admin reference lists,
    spec 13). Computed by services/admin_actions.py from services/reference_admin.py refusals."""
    EDIT = "edit"                              # PATCH
    ARCHIVE = "archive"                        # POST .../archive
    RESTORE = "restore"                        # POST .../restore
    DELETE = "delete"                          # DELETE (nothing refers to it)
    MAKE_DEFAULT = "make_default"              # PATCH {is_default: true} (insurance, transfer)
    ENABLE = "enable"                          # languages: PATCH {is_enabled: true}
    DISABLE = "disable"                        # languages: PATCH {is_enabled: false}


class TourAction(str, enum.Enum):
    """What a manager may do with a tour (ManagerTourOut.tour_actions, spec 10).
    Computed by services/tour_actions.py from the refusals the endpoints enforce. Not stored."""
    EDIT = "edit"                              # PATCH /manager/tours/{id}, photos
    PUBLISH = "publish"                        # POST .../publish
    UNPUBLISH = "unpublish"                    # POST .../unpublish
    ARCHIVE = "archive"                        # POST .../archive (cancels unpaid bookings)
    RESTORE = "restore"                        # POST .../restore (archived -> draft)
    COPY = "copy"                              # POST .../copy (new draft with new dates)


class ManagerTourSort(str, enum.Enum):
    """Sort of the back-office tour list."""
    UPDATED_DESC = "updated_desc"
    DEPARTURE_ASC = "departure_asc"
    TITLE_ASC = "title_asc"


class ManagerQueue(str, enum.Enum):
    """Tabs of «Вхідні заявки»: new (paid, nobody responsible), mine, all (not archived)."""
    NEW = "new"
    MINE = "mine"
    ALL = "all"


class ManagerOrderSort(str, enum.Enum):
    CREATED_DESC = "created_desc"
    CREATED_ASC = "created_asc"
    START_ASC = "start_asc"
    START_DESC = "start_desc"


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


class PaymentOrigin(str, enum.Enum):
    """Where a payment row came from. Finance pages and reports must be able to leave demo money
    out: `demo_seed` rows are written by scripts.seed_demo (dev only), no money ever moved."""
    APP = "app"              # made by the application: Stripe (test mode), mock gateway, bank transfer
    DEMO_SEED = "demo_seed"  # demo data, not a real (or test) payment


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DiscountType(str, enum.Enum):
    PERCENT = "percent"  # Відсоткова
    FIXED = "fixed"      # Фіксована (UAH)


class ReviewStatus(str, enum.Enum):
    """Review moderation (ТЗ 4.5.7 step 6)."""
    PENDING = "pending"        # На модерації
    PUBLISHED = "published"    # Опубліковано
    REJECTED = "rejected"      # Відхилено модератором


class NameDisplay(str, enum.Enum):
    FULL = "full"            # Повне ім'я
    SHORT = "short"          # Скорочене (Іван І.)
    ANONYMOUS = "anonymous"  # Анонімно
