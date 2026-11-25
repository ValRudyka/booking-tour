"""Registration, login and the personal account (ТЗ 4.5.1, form 4.6.1.1)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.deps import CurrentUser, DbSession
from app.core.security import create_access_token
from app.schemas.auth import PasswordChange, ProfileUpdate, RegisterRequest, TokenOut, UserOut
from app.models.enums import UserRole
from app.services import maintenance
from app.services import users as user_service
from app.services.users import UserError

router = APIRouter(prefix="/auth", tags=["auth"])


def _raise(error: UserError):
    raise HTTPException(status_code=error.status_code, detail=error.message)


def _raise_field(error: UserError):
    """Personal account: a rule about one field answers like FastAPI's own 422 (with the rule's
    status), so the form puts the message under that field. "profile_rule" says msg is a
    Ukrainian text meant for the client (like "checkout_rule" in the orders router)."""
    if error.field is None:
        _raise(error)
    raise HTTPException(status_code=error.status_code, detail=[
        {"loc": ["body", error.field], "msg": error.message, "type": "profile_rule"}])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             summary="Реєстрація клієнта")
def register(data: RegisterRequest, db: DbSession):
    try:
        user = user_service.create_user(db, **data.model_dump())
    except UserError as error:
        _raise(error)
    db.commit()
    return user


@router.post("/login", response_model=TokenOut, summary="Вхід (телефон або e-mail + пароль)")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    """OAuth2 password flow: the `username` field takes a phone number or an e-mail."""
    user = user_service.authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невірний логін або пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Maintenance blocks everyone except admins (only they can switch it off). The password is
    # checked first, so a wrong one is still 401; a manager or finance token would be refused by
    # every other endpoint anyway, so they get the 503 here, on the login page.
    if user.role != UserRole.ADMIN and maintenance.is_on(db):
        raise maintenance.unavailable(db)
    token = create_access_token(user.id, user.role.value)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut, summary="Мій профіль")
def me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut, summary="Редагувати профіль")
def update_me(data: ProfileUpdate, user: CurrentUser, db: DbSession):
    try:
        user_service.update_profile(db, user, data.model_dump(exclude_unset=True))
    except UserError as error:
        _raise_field(error)
    db.commit()
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT, summary="Змінити пароль",
             description="Завершує всі сеанси, зокрема поточний: після зміни потрібно увійти знову.")
def change_password(data: PasswordChange, user: CurrentUser, db: DbSession):
    try:
        user_service.change_password(db, user, data.current_password, data.new_password)
    except UserError as error:
        _raise_field(error)
    db.commit()
