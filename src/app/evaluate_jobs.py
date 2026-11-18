"""In-memory evaluation jobs; MVP requires one worker (CLAUDE.md R8)."""

import logging
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from src.app.constants import CONSTANTS
from src.audio_processing.contracts import AudioRejected, SttUnavailable
from src.audio_processing.pipeline import EvaluationCancelled

logger = logging.getLogger(__name__)


def load_weights(config: dict) -> dict[str, int]:
    weights = dict(config["stage_weights"])
    if (
        set(weights)
        != {"upload", "decode", "vad", "stt", "align", "fluency", "pitch", "semantic", "save"}
        or sum(weights.values()) != 100
    ):
        raise ValueError("Evaluate stage weights must cover nine stages and sum to 100")
    return weights


WEIGHTS = load_weights(CONSTANTS["evaluate_job"])


class RateLimited(Exception):  # noqa: N818
    """The user already has the maximum number of active jobs."""


@dataclass
class EvaluateJob:
    job_id: str
    user_id: str
    workdir: Path
    created_at: float
    status: str = "queued"
    stage: str | None = None
    stages: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"key": key, "state": "done" if key == "upload" else "pending"} for key in WEIGHTS
        ]
    )
    progress: int = field(default_factory=lambda: WEIGHTS["upload"])
    result: dict | None = None
    error_code: str | None = None
    message: str | None = None
    cancel_requested: bool = False
    finished_at: float | None = None


class EvaluateJobStore:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        ttl: float | None = None,
        limit: int | None = None,
    ):
        self.clock = clock
        self.ttl = CONSTANTS["evaluate_job"]["job_ttl_s"] if ttl is None else ttl
        self.limit = CONSTANTS["evaluate_job"]["max_running_per_user"] if limit is None else limit
        self._jobs: dict[str, EvaluateJob] = {}
        self._lock = threading.Lock()

    def _cleanup(self) -> None:
        now = self.clock()
        self._jobs = {
            k: v
            for k, v in self._jobs.items()
            if v.finished_at is None or now - v.finished_at < self.ttl
        }

    def count_active(self, user_id: str) -> int:
        with self._lock:
            return sum(
                j.user_id == user_id and j.status in {"queued", "running"}
                for j in self._jobs.values()
            )

    def create_job(self, user_id: str, workdir: Path) -> EvaluateJob:
        with self._lock:
            self._cleanup()
            if (
                sum(
                    j.user_id == user_id and j.status in {"queued", "running"}
                    for j in self._jobs.values()
                )
                >= self.limit
            ):
                raise RateLimited()
            job = EvaluateJob(str(uuid4()), user_id, workdir, self.clock())
            self._jobs[job.job_id] = job
            return job

    def get(self, job_id: str, user_id: str) -> dict | None:
        with self._lock:
            self._cleanup()
            job = self._jobs.get(job_id)
            return self._snapshot(job) if job and job.user_id == user_id else None

    def cancel(self, job_id: str, user_id: str) -> dict | None:
        with self._lock:
            self._cleanup()
            job = self._jobs.get(job_id)
            if job is None or job.user_id != user_id:
                return None
            if job.status in {"queued", "running"} and job.stage != "save":
                job.cancel_requested = True
            return self._snapshot(job)

    @staticmethod
    def _snapshot(job: EvaluateJob) -> dict:
        return {
            "job_id": job.job_id,
            "status": job.status,
            "stage": job.stage,
            "progress": job.progress,
            "stages": [s.copy() for s in job.stages],
            "result": job.result,
            "error_code": job.error_code,
            "message": job.message,
        }

    def mark_running(self, job: EvaluateJob) -> None:
        with self._lock:
            if job.cancel_requested:
                raise EvaluationCancelled()
            job.status = "running"

    def cancelled(self, job: EvaluateJob) -> bool:
        with self._lock:
            return job.cancel_requested

    def start(self, job: EvaluateJob, key: str) -> None:
        with self._lock:
            if job.cancel_requested:
                raise EvaluationCancelled()
            job.status = "running"
            for stage in job.stages:
                if stage["state"] == "running":
                    stage["state"] = "done"
                if stage["key"] == key:
                    stage["state"] = "running"
            job.stage = key
            job.progress = max(
                job.progress,
                min(
                    100,
                    sum(WEIGHTS[s["key"]] for s in job.stages if s["state"] in {"done", "skipped"}),
                ),
            )

    def begin_save(self, job: EvaluateJob) -> None:
        with self._lock:
            if job.cancel_requested:
                raise EvaluationCancelled()
            for stage in job.stages:
                if stage["state"] == "running":
                    stage["state"] = "done"
                elif stage["state"] == "pending" and stage["key"] != "save":
                    stage["state"] = "skipped"
                if stage["key"] == "save":
                    stage["state"] = "running"
            job.stage = "save"
            job.progress = max(
                job.progress,
                sum(WEIGHTS[s["key"]] for s in job.stages if s["state"] in {"done", "skipped"}),
            )

    def finish(
        self,
        job: EvaluateJob,
        status: str,
        *,
        result: dict | None = None,
        error_code: str | None = None,
        message: str | None = None,
    ) -> None:
        with self._lock:
            job.status, job.result, job.error_code, job.message = (
                status,
                result,
                error_code,
                message,
            )
            job.finished_at = self.clock()
            if status in {"failed", "cancelled"}:
                for stage in job.stages:
                    if stage["state"] == "running":
                        stage["state"] = "pending"
            if status == "done":
                job.stages[-1]["state"] = "done"
                job.progress = 100


def run_evaluate_job(
    store: EvaluateJobStore, job: EvaluateJob, evaluate: Callable, save: Callable
) -> None:
    """Run a job synchronously in a background worker and always remove its upload."""
    try:
        store.mark_running(job)
        result = evaluate(
            on_stage=lambda key: store.start(job, key), should_cancel=lambda: store.cancelled(job)
        )
        store.begin_save(job)
        result = save(result)
        store.finish(job, "done", result=result)
    except EvaluationCancelled:
        store.finish(job, "cancelled")
    except AudioRejected as exc:
        store.finish(job, "failed", error_code=exc.code, message=exc.message)
    except SttUnavailable:
        store.finish(
            job,
            "failed",
            error_code="stt_unavailable",
            message="The speech recognition service is not available right now. "
            "Please try again in a few minutes.",
        )
    except Exception:
        logger.exception("Evaluation job failed")
        store.finish(
            job,
            "failed",
            error_code="evaluation_failed",
            message="Evaluation failed. Please try again.",
        )
    finally:
        shutil.rmtree(job.workdir, ignore_errors=True)
