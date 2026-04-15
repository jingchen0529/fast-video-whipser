"""
Persistent async task queue backed by the database.

Replaces FastAPI's BackgroundTasks with a durable queue that:
- Persists tasks to the DB (survives restarts)
- Runs tasks via an asyncio background worker
- Supports status polling
- Handles retries and error recording
"""
import asyncio
import json
import logging
import uuid
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from app.auth.security import utcnow_ms
from app.db.session import get_db_session
from app.models.job import TaskQueueItem

logger = logging.getLogger(__name__)

TaskExecutor = Callable[..., Awaitable[Any]]


def _get_session():
    gen = get_db_session()
    return next(gen)


class TaskQueue:
    """
    Persistent async task queue.

    Usage:
        queue = TaskQueue.instance()
        task_id = queue.enqueue(
            task_type="workflow",
            payload={"project_id": 42},
        )
        # The background worker picks up and executes queued tasks.
    """

    _instance: "TaskQueue | None" = None
    _executors: dict[str, TaskExecutor] = {}
    _worker_task: asyncio.Task | None = None
    _running: bool = False
    _poll_interval: float = 2.0
    _wake_event: asyncio.Event | None = None
    _worker_loop_ref: asyncio.AbstractEventLoop | None = None

    @classmethod
    def instance(cls) -> "TaskQueue":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def register_executor(cls, task_type: str, executor: TaskExecutor) -> None:
        """Register an async callable to handle a specific task type."""
        cls._executors[task_type] = executor

    def enqueue(
        self,
        *,
        task_type: str,
        payload: dict[str, Any],
        max_retries: int = 0,
    ) -> str:
        """Add a task to the persistent queue. Returns the task ID."""
        task_id = uuid.uuid4().hex
        now = utcnow_ms()
        session = _get_session()
        try:
            item = TaskQueueItem(
                id=task_id,
                task_type=task_type,
                status="queued",
                payload_json=json.dumps(payload, ensure_ascii=False),
                max_retries=max_retries,
                retry_count=0,
                error_message=None,
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        logger.info("Enqueued task %s (type=%s)", task_id, task_type)
        if self._wake_event is not None and self._worker_loop_ref is not None:
            try:
                self._worker_loop_ref.call_soon_threadsafe(self._wake_event.set)
            except RuntimeError:
                logger.debug("TaskQueue wake signal skipped because the worker loop is unavailable")
        return task_id

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Get the current status of a queued task."""
        session = _get_session()
        try:
            item = session.get(TaskQueueItem, task_id)
            if item is None:
                return None
            result = {
                "id": item.id,
                "task_type": item.task_type,
                "status": item.status,
                "payload_json": item.payload_json,
                "max_retries": item.max_retries,
                "retry_count": item.retry_count,
                "error_message": item.error_message,
                "started_at": item.started_at,
                "finished_at": item.finished_at,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            if item.payload_json:
                result["payload"] = json.loads(item.payload_json)
            return result
        finally:
            session.close()

    async def start_worker(self) -> None:
        """Start the background worker loop."""
        if self._running:
            return
        self._running = True
        self._worker_loop_ref = asyncio.get_running_loop()
        self._wake_event = asyncio.Event()
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("TaskQueue worker started")

    async def stop_worker(self) -> None:
        """Stop the background worker."""
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            except RuntimeError:
                logger.warning(
                    "TaskQueue worker shutdown crossed event loops; forcing cleanup",
                    exc_info=True,
                )
            self._worker_task = None
        self._wake_event = None
        self._worker_loop_ref = None
        logger.info("TaskQueue worker stopped")

    async def _worker_loop(self) -> None:
        """Poll for queued tasks and execute them."""
        while self._running:
            try:
                task = self._claim_next_task()
                if task is not None:
                    await self._execute_task(task)
                else:
                    if self._wake_event is None:
                        await asyncio.sleep(self._poll_interval)
                        continue

                    self._wake_event.clear()
                    try:
                        await asyncio.wait_for(
                            self._wake_event.wait(),
                            timeout=self._poll_interval,
                        )
                    except TimeoutError:
                        pass
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("TaskQueue worker error")
                await asyncio.sleep(self._poll_interval)

    def _claim_next_task(self) -> dict[str, Any] | None:
        """Atomically claim the next queued task.

        Uses SELECT ... FOR UPDATE SKIP LOCKED so that concurrent workers
        (multiple processes or threads) never pick up the same task.  The row
        is locked for the duration of the transaction; other workers will skip
        it and move on to the next available row instead of blocking.

        Note: SKIP LOCKED requires MySQL 8.0+ or PostgreSQL 9.5+.  SQLite does
        not support it, but SQLite is single-writer by nature so the race
        condition cannot occur there.
        """
        now = utcnow_ms()
        session = _get_session()
        try:
            item = session.scalar(
                select(TaskQueueItem)
                .where(TaskQueueItem.status == "queued")
                .order_by(TaskQueueItem.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if item is None:
                session.rollback()
                return None

            task = {
                "id": item.id,
                "task_type": item.task_type,
                "status": item.status,
                "payload_json": item.payload_json,
                "max_retries": item.max_retries,
                "retry_count": item.retry_count,
                "error_message": item.error_message,
                "started_at": item.started_at,
                "finished_at": item.finished_at,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            item.status = "running"
            item.started_at = now
            item.updated_at = now
            session.commit()
            if task.get("payload_json"):
                task["payload"] = json.loads(task["payload_json"])
            return task
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def _execute_task(self, task: dict[str, Any]) -> None:
        """Execute a single task."""
        task_id = task["id"]
        task_type = task["task_type"]
        payload = task.get("payload") or {}

        executor = self._executors.get(task_type)
        if executor is None:
            error_msg = f"No executor registered for task type: {task_type}"
            logger.error(error_msg)
            self._mark_failed(task_id, error_msg)
            return

        try:
            await executor(**payload)
            self._mark_succeeded(task_id)
        except Exception as exc:
            error_msg = str(exc).strip() or "Unknown error"
            retry_count = int(task.get("retry_count") or 0)
            max_retries = int(task.get("max_retries") or 0)

            if retry_count < max_retries:
                self._mark_retry(task_id, retry_count + 1, error_msg)
                logger.warning(
                    "Task %s failed (attempt %d/%d): %s",
                    task_id, retry_count + 1, max_retries, error_msg,
                )
            else:
                self._mark_failed(task_id, error_msg)
                logger.error("Task %s permanently failed: %s", task_id, error_msg)

    def _mark_succeeded(self, task_id: str) -> None:
        now = utcnow_ms()
        session = _get_session()
        try:
            item = session.get(TaskQueueItem, task_id)
            if item is not None:
                item.status = "succeeded"
                item.finished_at = now
                item.updated_at = now
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _mark_failed(self, task_id: str, error_message: str) -> None:
        now = utcnow_ms()
        session = _get_session()
        try:
            item = session.get(TaskQueueItem, task_id)
            if item is not None:
                item.status = "failed"
                item.error_message = error_message
                item.finished_at = now
                item.updated_at = now
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _mark_retry(self, task_id: str, retry_count: int, error_message: str) -> None:
        now = utcnow_ms()
        session = _get_session()
        try:
            item = session.get(TaskQueueItem, task_id)
            if item is not None:
                item.status = "queued"
                item.retry_count = retry_count
                item.error_message = error_message
                item.started_at = None
                item.updated_at = now
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
