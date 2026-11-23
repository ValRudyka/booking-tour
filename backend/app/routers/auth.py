"""Registration, login and the personal account (ТЗ 4.5.1, form 4.6.1.1)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.deps import CurrentUser, DbSession
from app.core.security import create_access_token
from app.schemas.auth import PasswordChange, ProfileUpdate, RegisterRequest, TokenOut, UserOut
from app.services import users as user_service
from app.services.users import UserError

router = APIRouter(prefix="/auth", tags=["auth"])


def _raise(error: UserError):
    raise HTTPException(status_code=error.status_code, detail=error.message)


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
        _raise(error)
    db.commit()
    return user


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT, summary="Змінити пароль")
def change_password(data: PasswordChange, user: CurrentUser, db: DbSession):
    try:
        user_service.change_password(db, user, data.current_password, data.new_password)
    except UserError as error:
        _raise(error)
    db.commit()
