# 从内层 fastsam 包导出
from .fastsam import FastSAM, FastSAMPrompt, FastSAMPredictor, FastSAMDecoder

__all__ = ['FastSAM', 'FastSAMPrompt', 'FastSAMPredictor', 'FastSAMDecoder']
