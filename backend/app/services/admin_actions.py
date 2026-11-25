"""What the administrator may do with a user or a reference record right now (spec 13 §0: the
interface shows the safety rules before a request, not only an error after it).

The counterpart of staff_actions.py for the admin pages. Each action is listed where it makes
sense (block only for an active user, restore only for an archived record, …); the same refusal
function the endpoint raises decides whether it is allowed, and its text is the reason. The
frontend shows an allowed action as a button and a refused one as a disabled button with the
reason, and never mirrors these rules.

Users (services/admin_users.py):

| action         | listed                | refused by                                  |
|----------------|-----------------------|---------------------------------------------|
| edit           | always                | edit_refusal (a client edits own data)      |
| change_role    | always                | role_refusal (client, yourself, last admin) |
| block          | active users          | block_refusal (yourself, last admin)        |
| unblock        | blocked users         | —                                           |
| reset_password | always                | reset_refusal (yourself)                    |

Reference records (services/reference_admin.py): see reference_actions().
"""
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.models.enums import ReferenceAction as R
from app.models.enums import UserAdminAction as U
from app.services import admin_users as users
from app.services import reference_admin as refs


def _action(action, reason: str | None) -> dict[str, Any]:
    return dict(action=action, allowed=reason is None, reason=reason)


def user_actions(admin: User, target: User, admin_ids: set[int]) -> list[dict[str, Any]]:
    """`admin_ids`: the active admins (users.active_admin_ids), read once per list."""
    actions = [_action(U.EDIT, users.edit_refusal(target)),
               _action(U.CHANGE_ROLE, users.role_refusal(admin, target, admin_ids))]
    if target.is_active:
        actions.append(_action(U.BLOCK, users.block_refusal(admin, target, admin_ids)))
    else:
        actions.append(_action(U.UNBLOCK, None))
    actions.append(_action(U.RESET_PASSWORD, users.reset_refusal(admin, target)))
    return actions


def with_user_actions(db: Session, admin: User, targets: list[User]) -> list[dict[str, Any]]:
    """AdminUserOut dicts with user_actions."""
    from app.schemas.admin import AdminUserOut

    admin_ids = users.active_admin_ids(db)
    return [{**AdminUserOut.model_validate(t).model_dump(), "user_actions": user_actions(admin, t, admin_ids)}
            for t in targets]


def reference_actions(db: Session, kind: str, items: list[Any]) -> dict[Any, list[dict[str, Any]]]:
    """{item id: admin_actions} for one list of a reference kind (one batch of counts)."""
    context = refs.refusal_context(db, kind, items)
    out: dict[Any, list[dict[str, Any]]] = {}
    for item in items:
        actions = [_action(R.EDIT, None)]
        if item.is_archived:
            actions.append(_action(R.RESTORE, refs.restore_refusal(kind, item, context)))
        else:
            actions.append(_action(R.ARCHIVE, refs.archive_refusal(kind, item, context)))
        if kind in refs.DEFAULT_KINDS and not item.is_default:
            actions.append(_action(R.MAKE_DEFAULT, refs.default_refusal(item)))
        actions.append(_action(R.DELETE, refs.delete_refusal(kind, item, context)))
        out[item.id] = actions
    return out


def language_actions(language) -> list[dict[str, Any]]:
    toggle = R.DISABLE if language.is_enabled else R.ENABLE
    reason = refs.language_disable_refusal(language) if toggle == R.DISABLE else None
    return [_action(R.EDIT, None), _action(toggle, reason),
            _action(R.DELETE, refs.language_delete_refusal(language))]
