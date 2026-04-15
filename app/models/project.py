from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("idx_projects_user_id", "user_id"),
        Index("idx_projects_status", "status"),
        Index("idx_projects_updated_at", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"),
    )
    title: Mapped[str] = mapped_column(String(512), default="")
    source_url: Mapped[str] = mapped_column(Text)
    source_platform: Mapped[str] = mapped_column(String(64), default="local")
    workflow_type: Mapped[str] = mapped_column(String(64), default="analysis")
    source_type: Mapped[str] = mapped_column(String(32), default="upload")
    source_name: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_media_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    source_asset_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True,
    )
    script_overview_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ecommerce_analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline_segments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_generation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    task_steps: Mapped[list[ProjectTaskStep]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
    )
    shot_segments: Mapped[list[ShotSegment]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
    )
    storyboards: Mapped[list[Storyboard]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
    )
    messages: Mapped[list[ProjectMessage]] = relationship(
        back_populates="project", cascade="all, delete-orphan",
    )


class ProjectMessage(Base):
    __tablename__ = "project_messages"
    __table_args__ = (
        Index("idx_project_messages_project_id", "project_id"),
        Index("idx_project_messages_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
    )
    role: Mapped[str] = mapped_column(String(32))
    message_type: Mapped[str] = mapped_column(String(64), default="text")
    content: Mapped[str] = mapped_column(Text)
    content_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_to_message_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("project_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    project: Mapped[Project] = relationship(back_populates="messages")
    reply_to: Mapped[ProjectMessage | None] = relationship(
        remote_side=[id],
    )


class ProjectTaskStep(Base):
    __tablename__ = "project_task_steps"
    __table_args__ = (
        Index("idx_project_task_steps_project_id", "project_id"),
        Index("idx_project_task_steps_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
    )
    step_key: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    project: Mapped[Project] = relationship(back_populates="task_steps")


class ShotSegment(Base):
    __tablename__ = "shot_segments"
    __table_args__ = (
        UniqueConstraint("project_id", "segment_index", name="uq_shot_segments_project_segment"),
        Index("idx_shot_segments_project_id", "project_id"),
        Index("idx_shot_segments_source_video_asset_id", "source_video_asset_id"),
        Index("idx_shot_segments_job_id", "job_id"),
        Index("idx_shot_segments_start_ms", "project_id", "start_ms"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
    )
    source_video_asset_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("media_assets.id", ondelete="CASCADE"),
    )
    job_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True,
    )
    owner_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    segment_index: Mapped[int] = mapped_column(Integer, default=0)
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    start_frame: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_frame: Mapped[int | None] = mapped_column(Integer, nullable=True)
    boundary_in_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    boundary_out_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detector_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detector_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detector_config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    keyframe_asset_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    shot_type_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    camera_angle_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    camera_motion_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scene_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    lighting_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dominant_color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    people_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    face_regions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    project: Mapped[Project] = relationship(back_populates="shot_segments")
    storyboard_item_links: Mapped[list[StoryboardItemSegment]] = relationship(
        back_populates="shot_segment",
    )


class Storyboard(Base):
    __tablename__ = "storyboards"
    __table_args__ = (
        UniqueConstraint("project_id", "version_no", name="uq_storyboards_project_version"),
        Index("idx_storyboards_project_id", "project_id"),
        Index("idx_storyboards_source_video_asset_id", "source_video_asset_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
    )
    job_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True,
    )
    source_video_asset_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("media_assets.id", ondelete="CASCADE"),
    )
    owner_user_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="generated")
    generator_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generator_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    project: Mapped[Project] = relationship(back_populates="storyboards")
    items: Mapped[list[StoryboardItem]] = relationship(
        back_populates="storyboard", cascade="all, delete-orphan",
    )


class StoryboardItem(Base):
    __tablename__ = "storyboard_items"
    __table_args__ = (
        UniqueConstraint(
            "storyboard_id", "item_index", name="uq_storyboard_items_storyboard_index",
        ),
        Index("idx_storyboard_items_storyboard_id", "storyboard_id"),
        Index("idx_storyboard_items_start_ms", "storyboard_id", "start_ms"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    storyboard_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("storyboards.id", ondelete="CASCADE"),
    )
    item_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(255))
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    shot_type_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    camera_angle_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    camera_motion_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    visual_description: Mapped[str] = mapped_column(Text)
    transcript_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="auto_generated")
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)

    # -- relationships --
    storyboard: Mapped[Storyboard] = relationship(back_populates="items")
    segment_links: Mapped[list[StoryboardItemSegment]] = relationship(
        back_populates="storyboard_item", cascade="all, delete-orphan",
    )


class StoryboardItemSegment(Base):
    __tablename__ = "storyboard_item_segments"
    __table_args__ = (
        Index("idx_storyboard_item_segments_shot_segment_id", "shot_segment_id"),
    )

    storyboard_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("storyboard_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    shot_segment_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("shot_segments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_order: Mapped[int] = mapped_column(Integer, default=1)

    # -- relationships --
    storyboard_item: Mapped[StoryboardItem] = relationship(
        back_populates="segment_links",
    )
    shot_segment: Mapped[ShotSegment] = relationship(
        back_populates="storyboard_item_links",
    )
