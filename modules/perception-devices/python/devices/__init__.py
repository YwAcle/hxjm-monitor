"""Device adapters translate protocols; Capability remains the task coordinator."""
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class DeviceDescription:
    device_id: str
    display_name: str
    capability_codes: tuple[str, ...]
    implementation_code: str
    implementation_version: str


@dataclass(frozen=True)
class DeviceTask:
    # IDs are allocated by the existing Capability task/run lifecycle.
    device_id: str
    task_id: str
    run_id: str
    capability_code: str
    input: dict[str, Any]
    parameters: dict[str, Any]


@dataclass(frozen=True)
class DeviceStatus:
    device_id: str
    state: str  # offline / idle / busy / error
    task_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class DeviceFeedback:
    task_id: str
    run_id: str
    state: str  # running / succeeded / failed
    outputs: tuple[dict[str, Any], ...] = ()
    error_code: str | None = None

    def completion(self, *, expected_revision: int, execution_token: str):
        """Existing /tasks/complete or /tasks/fail body, not a new result store.

        The coordinator owns revision/token and calls this only for terminal feedback.
        Running feedback is handled by the existing /tasks/heartbeat lifecycle.
        """
        if self.state not in ('succeeded', 'failed'):
            raise ValueError('Completion requires terminal device feedback')
        if self.state == 'succeeded' and (not self.outputs or self.error_code):
            raise ValueError('Successful feedback requires outputs and no error')
        if self.state == 'failed' and (not self.error_code or self.outputs):
            raise ValueError('Failed feedback requires error_code and no outputs')
        body = dict(task_id=self.task_id, run_id=self.run_id,
                    expected_revision=expected_revision, execution_token=execution_token)
        if self.state == 'succeeded':
            body['outputs'] = list(self.outputs)
        else:
            body['error_code'] = self.error_code
        return body


class DeviceAdapter(Protocol):
    """No SDK, discovery service, hardware access or automatic retries here.

    submit must retain task_id/run_id as the external idempotency reference.
    A callback or polling integration supplies feedback for that same run.
    """
    def describe(self) -> DeviceDescription: ...
    def submit(self, task: DeviceTask) -> DeviceStatus: ...
    def status(self, device_id: str) -> DeviceStatus: ...
    def feedback(self, task_id: str, run_id: str) -> DeviceFeedback: ...
