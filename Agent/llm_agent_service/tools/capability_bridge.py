"""Request-scoped discovery and task bridge; uses existing Business service credentials."""
from __future__ import annotations

from dataclasses import dataclass
import os
from time import monotonic, sleep
from typing import Any, Callable
from uuid import uuid4

import httpx
from jsonschema import Draft202012Validator

from .base import ToolResult
from .registry import ToolRegistry

SCHEMA_KEYWORDS = frozenset('type title description default enum const properties required additionalProperties items minItems maxItems uniqueItems minLength maxLength pattern minimum maximum exclusiveMinimum exclusiveMaximum multipleOf minProperties maxProperties allOf anyOf oneOf not'.split())


def check_schema(schema: dict[str, Any]) -> None:
    if not isinstance(schema, dict) or set(schema) - SCHEMA_KEYWORDS:
        raise ValueError('Unsupported capability JSON Schema')
    for child in schema.get('properties', {}).values():
        check_schema(child)
    for key in ('items', 'not', 'additionalProperties'):
        if isinstance(schema.get(key), dict):
            check_schema(schema[key])
    for key in ('allOf', 'anyOf', 'oneOf'):
        for child in schema.get(key, []):
            check_schema(child)
    Draft202012Validator.check_schema(schema)


@dataclass(frozen=True)
class JsonSchemaTool:
    name: str
    description: str
    json_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]
    read_only: bool = True
    capability_managed: bool = True

    def __post_init__(self):
        check_schema(self.json_schema)

    def describe_schema(self):
        return self.json_schema

    def invoke(self, arguments):
        started = monotonic()
        try:
            Draft202012Validator(self.json_schema).validate(arguments)
            result = self.handler(arguments)
            return ToolResult(ok=True, data=result, elapsed_ms=int((monotonic()-started)*1000))
        except Exception:
            return ToolResult(ok=False, error_code='CAPABILITY_CALL_FAILED', error_message='能力调用失败，请检查参数或任务状态', elapsed_ms=int((monotonic()-started)*1000))


class CapabilityDirectoryError(RuntimeError):
    """This request cannot construct its tool snapshot."""


class CapabilityBridge:
    def __init__(self, base_url: str, service_id: str, token: str, *, transport=None, wait_s=10):
        if not base_url or not service_id or not token:
            raise ValueError('Capability Business URL and service identity are required')
        self.base_url = base_url.rstrip('/')
        self.headers = {'X-HXJM-Service-Id': service_id, 'X-HXJM-Service-Token': token}
        self.transport = transport
        self.wait_s = min(10, max(0, wait_s))

    @classmethod
    def from_env(cls):
        enabled = os.getenv('CAPABILITY_BRIDGE_ENABLED', 'false').lower() == 'true'
        if not enabled:
            return None
        return cls(os.getenv('CAPABILITY_BUSINESS_URL', ''), os.getenv('CAPABILITY_SERVICE_ID', ''), os.getenv('CAPABILITY_SERVICE_TOKEN', ''))

    def request(self, method, path, *, deadline=None, **kwargs):
        timeout = 5 if deadline is None else max(0.001, min(5, deadline-monotonic()))
        with httpx.Client(headers=self.headers, timeout=timeout, follow_redirects=False, transport=self.transport) as client:
            response = client.request(method, self.base_url+path, **kwargs)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or 'error' in data:
            raise ValueError('Business capability request failed')
        return data

    def snapshot(self, static: ToolRegistry) -> ToolRegistry:
        # Fetch first: failure never returns a stale/static fallback for this request.
        try:
            catalog = self.request('GET', '/capabilities/tools')
        except Exception as exc:
            raise CapabilityDirectoryError('能力目录暂不可用') from exc
        registry = ToolRegistry()
        for tool in static.list():
            registry.register(tool)
        registry.register(JsonSchemaTool('get_capability_task', '查询此前能力调用返回的 task_id，获取状态及持久化成果。',
            {'type': 'object', 'properties': {'task_id': {'type': 'string', 'minLength': 36, 'maxLength': 36}}, 'required': ['task_id'], 'additionalProperties': False},
            lambda args: self.task(args['task_id'])))
        for item in catalog['items']:
            if item.get('read_only') is not True:
                raise ValueError('Capability catalog includes a writable tool')
            registry.register(JsonSchemaTool(item['tool_name'], item['description'], item['input_schema'],
                lambda arguments, capability=item: self.call(capability, arguments)))
        return registry

    def task(self, task_id, *, deadline=None):
        state = self.request('GET', '/tasks', params={'task_id': task_id}, deadline=deadline)
        return state

    def call(self, capability, arguments):
        deadline = monotonic()+self.wait_s
        submitted = self.request('POST', '/tasks', json={
            'request_id': str(uuid4()), 'task_kind': 'capability.call',
            'capability_code': capability['capability_code'], 'instance_id': capability['instance_id'],
            'task_mode': 'once', 'input': {'kind': 'capability_call', 'payload': arguments},
            'parameters': {}, 'requested_outputs': capability['output_types'],
        })
        task_id = submitted['task_id']
        while monotonic() < deadline:
            try:
                result = self.task(task_id, deadline=deadline)
            except httpx.TimeoutException:
                return {'task_id': task_id, 'state': 'pending', 'message': '等待结束，请用 get_capability_task 查询；后台任务继续运行。'}
            if result['state'] not in ('pending', 'running', 'waiting_input'):
                return result
            sleep(min(0.2, max(0, deadline-monotonic())))
        return {'task_id': task_id, 'state': submitted['state'], 'message': '请用 get_capability_task 查询；后台任务继续运行。'}
