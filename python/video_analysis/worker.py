"""One supervised model process per slot; IPC carries metadata, never queued frames."""
import asyncio
import multiprocessing as mp
import uuid
from multiprocessing import shared_memory

import numpy as np

from .config import MAX_FRAME_BYTES, MODEL_TIMEOUT_SECONDS, INFERENCE_TIMEOUT_SECONDS


class RecoverableInferenceError(RuntimeError):
    """A camera tracker was reset; the model process remains usable."""


def model_process(connection):
    # Import/load CUDA only in a spawned child, never fork a loaded model.
    from .config import ALGORITHM
    try:
        if ALGORITHM == 'botsort':
            from .botsort_adapter import BoTSortPipeline
            pipeline = BoTSortPipeline()
        else:
            from .detector_adapter import initialize_detector, detect_people
            initialize_detector()
        connection.send({"type": "ready"})
        while True:
            job = connection.recv()
            memory = None
            try:
                memory = shared_memory.SharedMemory(name=job["memory"])
                frame = np.ndarray(job["shape"], dtype=np.uint8, buffer=memory.buf)
                if ALGORITHM == 'botsort':
                    detections, duration = pipeline.infer(frame, job['metadata'])
                else:
                    detections, duration = detect_people(frame)
                del frame
                connection.send({"type": "result", "job_id": job["job_id"],
                                 "detections": detections if job.get('full_results') is True else detections[:500],
                                 "inference_ms": duration})
            except Exception as exc:
                connection.send({"type": "error", "job_id": job["job_id"],
                                 "recoverable": ALGORITHM == 'botsort' and isinstance(exc, np.linalg.LinAlgError),
                                 "error": f"{type(exc).__name__}: {exc}"[:1000]})
            finally:
                if memory is not None:
                    memory.close()
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            connection.send({"type": "error", "error": f"{type(exc).__name__}: {exc}"[:1000]})
        except (EOFError, BrokenPipeError):
            pass
    finally:
        connection.close()


class ModelWorker:
    def __init__(self, slot, target=model_process, model_timeout=MODEL_TIMEOUT_SECONDS,
                 inference_timeout=INFERENCE_TIMEOUT_SECONDS):
        self.slot = slot
        self.target = target
        self.model_timeout = model_timeout
        self.inference_timeout = inference_timeout
        self.process = None
        self.connection = None
        self.ready = False
        self.generation = 0
        self.restarts = 0
        self.initializations = 0
        self.busy = False
        self.last_error = None
        self.assigned_camera = None

    async def _receive(self, timeout):
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if self.connection.poll():
                # poll() may report only a partial IPC payload. Never block the event loop
                # on recv() if the child freezes halfway through sending a result.
                remaining = max(0.001, deadline - asyncio.get_running_loop().time())
                try:
                    return await asyncio.wait_for(asyncio.to_thread(self.connection.recv), remaining)
                except asyncio.TimeoutError as exc:
                    # Python 3.9 uses a distinct asyncio.TimeoutError class.
                    raise TimeoutError("Worker response timed out") from exc
            if not self.process.is_alive():
                raise RuntimeError(f"Worker exited with code {self.process.exitcode}")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Worker response timed out")
            await asyncio.sleep(0.01)

    async def start(self):
        context = mp.get_context("spawn")
        parent, child = context.Pipe(duplex=True)
        self.connection = parent
        self.process = context.Process(target=self.target, args=(child,),
                                       name=f"analysis-model-{self.slot}", daemon=True)
        self.generation += 1
        self.process.start()
        child.close()
        try:
            message = await self._receive(self.model_timeout)
            if message["type"] != "ready":
                raise RuntimeError(message.get("error", "Worker failed to initialize"))
            self.ready = True
            self.last_error = None
            self.initializations += 1
        except BaseException:
            await self.stop()
            raise

    async def infer(self, frame, metadata=None, full_results=False):
        if not self.ready or self.busy:
            raise RuntimeError("Worker is unavailable")
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3 or frame.nbytes > MAX_FRAME_BYTES:
            raise ValueError("Frame exceeds the configured BGR uint8 memory limit")
        self.busy = True
        memory = None
        job_id = uuid.uuid4().hex
        try:
            memory = shared_memory.SharedMemory(create=True, size=frame.nbytes)
            np.ndarray(frame.shape, dtype=np.uint8, buffer=memory.buf)[:] = frame
            job = {"job_id": job_id, "memory": memory.name, "shape": frame.shape,
                   "metadata": metadata}
            if full_results is True:
                job['full_results'] = True
            self.connection.send(job)
            result = await self._receive(self.inference_timeout)
            if (result.get('job_id') == job_id and result.get('type') == 'error'
                    and result.get('recoverable') is True):
                raise RecoverableInferenceError(result.get('error', 'Tracking failed'))
            if result.get("job_id") != job_id or result["type"] != "result":
                raise RuntimeError(result.get("error", "Worker returned an invalid job"))
            return result["detections"], result["inference_ms"]
        except RecoverableInferenceError as exc:
            self.last_error = f'{type(exc).__name__}: {exc}'[:1000]
            raise
        except BaseException as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            self.restarts += 1
            # Kill before releasing memory: an old process must never access the next job.
            await self.stop()
            raise
        finally:
            self.busy = False
            if memory is not None:
                memory.close()
                memory.unlink()

    async def stop(self):
        self.ready = False
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
                deadline = asyncio.get_running_loop().time() + 0.5
                while self.process.is_alive() and asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(0.01)
                if self.process.is_alive():
                    self.process.kill()
                    deadline = asyncio.get_running_loop().time() + 2
                    while self.process.is_alive():
                        if asyncio.get_running_loop().time() >= deadline:
                            raise RuntimeError("OS did not reap the killed model Worker within two seconds")
                        await asyncio.sleep(0.01)
            self.process.join(timeout=0)
            self.process.close()
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def snapshot(self):
        return {"slot": self.slot, "pid": self.process.pid if self.process else None,
                "assigned_camera": self.assigned_camera,
                "state": 'busy' if self.busy else 'ready' if self.ready else 'loading' if self.process else 'dormant',
                "ready": self.ready, "busy": self.busy, "generation": self.generation,
                "restarts": self.restarts, "model_initializations": self.initializations,
                "error": self.last_error}
