from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    user_roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )
    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    user_roles: Mapped[list[UserRole]] = relationship(
        back_populates="role", cascade="all, delete-orphan",
    )
    role_menus: Mapped[list[RoleMenu]] = relationship(
        back_populates="role", cascade="all, delete-orphan",
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index("idx_user_roles_user_id", "user_id"),
        Index("idx_user_roles_role_id", "role_id"),
    )

    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True,
    )
    role_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True,
    )
    created_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    user: Mapped[User] = relationship(back_populates="user_roles")
    role: Mapped[Role] = relationship(back_populates="user_roles")


class Menu(Base):
    __tablename__ = "menus"
    __table_args__ = (
        Index("idx_menus_parent_id", "parent_id"),
        Index("idx_menus_sort_order", "sort_order"),
        Index("idx_menus_visible_enabled", "is_visible", "is_enabled"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("menus.id", ondelete="RESTRICT"), nullable=True,
    )
    code: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    menu_type: Mapped[str] = mapped_column(String(32), default="menu")
    route_path: Mapped[str] = mapped_column(String(512), default="")
    route_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    redirect_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(128), nullable=True)
    component_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)
    open_mode: Mapped[str] = mapped_column(String(16), default="self")
    is_cacheable: Mapped[bool] = mapped_column(Boolean, default=False)
    is_affix: Mapped[bool] = mapped_column(Boolean, default=False)
    active_menu_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    badge_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    badge_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    parent: Mapped[Menu | None] = relationship(
        back_populates="children", remote_side=[id],
    )
    children: Mapped[list[Menu]] = relationship(back_populates="parent")
    role_menus: Mapped[list[RoleMenu]] = relationship(
        back_populates="menu", cascade="all, delete-orphan",
    )


class RoleMenu(Base):
    __tablename__ = "role_menus"
    __table_args__ = (
        Index("idx_role_menus_role_id", "role_id"),
        Index("idx_role_menus_menu_id", "menu_id"),
    )

    role_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True,
    )
    menu_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("menus.id", ondelete="CASCADE"), primary_key=True,
    )
    created_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    role: Mapped[Role] = relationship(back_populates="role_menus")
    menu: Mapped[Menu] = relationship(back_populates="role_menus")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("idx_refresh_tokens_user_id", "user_id"),
        Index("idx_refresh_tokens_token_jti", "token_jti"),
        Index("idx_refresh_tokens_session_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"),
    )
    session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    token_jti: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[int] = mapped_column(BigInteger)
    revoked_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # -- relationships --
    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("idx_auth_sessions_user_id", "user_id"),
        Index("idx_auth_sessions_revoked_at", "revoked_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"),
    )
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    csrf_token: Mapped[str] = mapped_column(String(128))
    remember: Mapped[bool] = mapped_column(Boolean, default=False)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    last_seen_at: Mapped[int] = mapped_column(BigInteger)
    revoked_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # -- relationships --
    user: Mapped[User] = relationship(back_populates="sessions")


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        Index("idx_auth_rate_limits_blocked_until", "blocked_until"),
    )

    scope_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    blocked_until: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_attempt_at: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)
