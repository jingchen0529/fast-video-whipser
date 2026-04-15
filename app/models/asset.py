from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        Index("idx_media_assets_owner_user_id", "owner_user_id"),
        Index("idx_media_assets_asset_type", "asset_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    asset_type: Mapped[str] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(32))
    file_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(1024))
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)


class MotionAsset(Base):
    __tablename__ = "motion_assets"
    __table_args__ = (
        Index("idx_motion_assets_owner_user_id", "owner_user_id"),
        Index("idx_motion_assets_project_id", "project_id"),
        Index("idx_motion_assets_source_video_asset_id", "source_video_asset_id"),
        Index("idx_motion_assets_action_label", "action_label"),
        Index("idx_motion_assets_scene_label", "scene_label"),
        Index("idx_motion_assets_review_status", "review_status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
    )
    source_video_asset_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True,
    )
    clip_asset_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True,
    )
    job_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True,
    )
    owner_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    action_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entrance_style: Mapped[str | None] = mapped_column(String(128), nullable=True)
    emotion_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    temperament_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scene_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    camera_motion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    camera_shot: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    asset_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    review_status: Mapped[str] = mapped_column(String(32), default="draft")
    copyright_risk_level: Mapped[str] = mapped_column(String(32), default="unknown")
    origin: Mapped[str] = mapped_column(String(64), default="ai_generated")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    source_video_asset: Mapped[MediaAsset | None] = relationship(
        foreign_keys=[source_video_asset_id],
    )
    clip_asset: Mapped[MediaAsset | None] = relationship(
        foreign_keys=[clip_asset_id],
    )


class SystemSetting(Base):
    __tablename__ = "system_settings"

    setting_key: Mapped[str] = mapped_column(
        "key", String(128), primary_key=True,
    )
    value_json: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[int] = mapped_column(BigInteger)
    updated_by_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
