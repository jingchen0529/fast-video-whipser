"""
Auth repository — low-level ORM queries for User, Role, Menu entities.

These helpers centralise the most common read-only lookups so that
both the auth service and other call sites share a single, tested
implementation rather than re-implementing the same queries.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.auth import Menu, Role, User, UserRole


class UserRepository:
    """Query helpers for the ``users`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: str) -> User | None:
        return self._session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        return self._session.scalar(
            select(User).where(User.username == username.strip().lower())
        )

    def get_by_email(self, email: str) -> User | None:
        return self._session.scalar(
            select(User).where(User.email == email.strip().lower())
        )

    def get_by_username_or_email(self, login: str) -> User | None:
        normalized = login.strip().lower()
        return self._session.scalar(
            select(User).where(
                (User.username == normalized) | (User.email == normalized)
            )
        )

    def list_all(self) -> list[User]:
        return list(self._session.scalars(select(User).order_by(User.created_at.asc())).all())

    def exists_username(self, username: str) -> bool:
        return self.get_by_username(username) is not None

    def exists_email(self, email: str) -> bool:
        return self.get_by_email(email) is not None


class RoleRepository:
    """Query helpers for the ``roles`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, role_id: str) -> Role | None:
        return self._session.get(Role, role_id)

    def get_by_code(self, code: str) -> Role | None:
        return self._session.scalar(select(Role).where(Role.code == code))

    def list_all(self) -> list[Role]:
        return list(self._session.scalars(select(Role).order_by(Role.created_at.asc())).all())

    def get_roles_for_user(self, user_id: str) -> list[Role]:
        return list(
            self._session.scalars(
                select(Role)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id)
            ).all()
        )


class MenuRepository:
    """Query helpers for the ``menus`` table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, menu_id: str) -> Menu | None:
        return self._session.get(Menu, menu_id)

    def get_by_code(self, code: str) -> Menu | None:
        return self._session.scalar(select(Menu).where(Menu.code == code))

    def list_all(self) -> list[Menu]:
        return list(
            self._session.scalars(
                select(Menu).order_by(Menu.sort_order.asc(), Menu.created_at.asc())
            ).all()
        )

    def list_root_menus(self) -> list[Menu]:
        """Return top-level menus (no parent) with children eager-loaded."""
        return list(
            self._session.scalars(
                select(Menu)
                .where(Menu.parent_id.is_(None))
                .options(selectinload(Menu.children))
                .order_by(Menu.sort_order.asc())
            ).all()
        )

    def get_menus_for_role(self, role_id: str) -> list[Menu]:
        from app.models.auth import RoleMenu
        return list(
            self._session.scalars(
                select(Menu)
                .join(RoleMenu, RoleMenu.menu_id == Menu.id)
                .where(RoleMenu.role_id == role_id)
                .order_by(Menu.sort_order.asc())
            ).all()
        )
