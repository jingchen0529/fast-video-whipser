"""
Persistent async task queue backed by SQLite.

Replaces FastAPI's BackgroundTasks with a durable queue that:
- Persists tasks to the DB (survives restarts)
- Runs tasks via an asyncio background worker
- Supports status polling
- Handles retries and error recording
"""
import asyncio
import json
import logging
import traceback
import uuid
from typing import Any, Awaitable, Callable

from app.auth.security import utcnow_iso
from app.db.sqlite import create_connection

logger = logging.getLogger(__name__)

TaskExecutor = Callable[..., Awaitable[Any]]


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
        now = utcnow_iso()
        connection = create_connection()
        try:
            connection.execute(
                """
                INSERT INTO task_queue (
                    id, task_type, status, payload_json,
                    max_retries, retry_count,
                    error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task_type,
                    "queued",
                    json.dumps(payload, ensure_ascii=False),
                    max_retries,
                    0,
                    None,
                    now,
                    now,
                ),
            )
            connection.commit()
        finally:
            connection.close()

        logger.info("Enqueued task %s (type=%s)", task_id, task_type)
        if self._wake_event is not None and self._worker_loop_ref is not None:
            try:
                self._worker_loop_ref.call_soon_threadsafe(self._wake_event.set)
            except RuntimeError:
                logger.debug("TaskQueue wake signal skipped because the worker loop is unavailable")
        return task_id

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:
        """Get the current status of a queued task."""
        connection = create_connection()
        try:
            row = connection.execute(
                "SELECT * FROM task_queue WHERE id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            if item.get("payload_json"):
                item["payload"] = json.loads(item["payload_json"])
            return item
        finally:
            connection.close()

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
        """Atomically claim the next queued task."""
        now = utcnow_iso()
        connection = create_connection()
        try:
            row = connection.execute(
                """
                SELECT * FROM task_queue
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """,
            ).fetchone()
            if row is None:
                return None

            task = dict(row)
            connection.execute(
                """
                UPDATE task_queue
                SET status = 'running', started_at = ?, updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, task["id"]),
            )
            connection.commit()
            if task.get("payload_json"):
                task["payload"] = json.loads(task["payload_json"])
            return task
        finally:
            connection.close()

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
        now = utcnow_iso()
        connection = create_connection()
        try:
            connection.execute(
                """
                UPDATE task_queue
                SET status = 'succeeded', finished_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, task_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _mark_failed(self, task_id: str, error_message: str) -> None:
        now = utcnow_iso()
        connection = create_connection()
        try:
            connection.execute(
                """
                UPDATE task_queue
                SET status = 'failed', error_message = ?, finished_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (error_message, now, now, task_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _mark_retry(self, task_id: str, retry_count: int, error_message: str) -> None:
        now = utcnow_iso()
        connection = create_connection()
        try:
            connection.execute(
                """
                UPDATE task_queue
                SET status = 'queued', retry_count = ?, error_message = ?,
                    started_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (retry_count, error_message, now, task_id),
            )
            connection.commit()
        finally:
            connection.close()
