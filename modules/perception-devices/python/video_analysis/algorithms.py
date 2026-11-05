"""Video runtime extension point. Import factories only inside model workers."""
from dataclasses import dataclass
from importlib import import_module
from typing import Protocol


class Algorithm(Protocol):
    last_removed_tracks: list

    def infer(self, frame, metadata):
        """BGR uint8 frame + capture metadata -> (normalized detections, duration_ms)."""


@dataclass(frozen=True)
class AlgorithmSpec:
    capability_code: str
    factory: str
    tracking: bool
    default_interval: str
    result_type: str = 'detection.frame'
    schema_version: str = '1'

    def describe(self, implementation_code):
        return dict(capability_code=self.capability_code, implementation_code=implementation_code,
                    implementation_version='1', execution_mode='continuous',
                    input_kinds=['live_video'], output_types=[self.result_type],
                    schema_version=self.schema_version, tracking=self.tracking)

    def create(self) -> Algorithm:
        module, name = self.factory.split(':')
        return getattr(import_module(module), name)()


# Same-mode additions only change this registry and their own adapter module.
ALGORITHMS = {
    'garbage': AlgorithmSpec('garbage.detection', 'video_analysis.garbage_adapter:GarbageDetector', False, '5', 'garbage.detection'),
    'botsort': AlgorithmSpec('person.tracking', 'video_analysis.botsort_adapter:BoTSortPipeline', True, '0.05'),
    # Historical name: this implementation detects people; it does not run DeepSORT.
    'deepsort': AlgorithmSpec('person.detection', 'video_analysis.detector_adapter:PersonDetector', False, '1'),
}


def algorithm_spec(name):
    try:
        return ALGORITHMS[name]
    except KeyError as exc:
        raise ValueError(f'Unknown video algorithm: {name}') from exc
