import unittest
from unittest.mock import patch

import torch

from yolox.models.yolo_head import YOLOXHead


def reference_decode(outputs, hw, scales, dtype):
    grids, strides = [], []
    for (height, width), stride in zip(hw, scales):
        yv, xv = torch.meshgrid([torch.arange(height), torch.arange(width)])
        grid = torch.stack((xv, yv), 2).view(1, -1, 2)
        grids.append(grid)
        strides.append(torch.full((*grid.shape[:2], 1), stride))
    grids = torch.cat(grids, dim=1).type(dtype)
    strides = torch.cat(strides, dim=1).type(dtype)
    outputs[..., :2] = (outputs[..., :2] + grids) * strides
    outputs[..., 2:4] = torch.exp(outputs[..., 2:4]) * strides
    return outputs


class DecodeTests(unittest.TestCase):
    def setUp(self):
        self.head = YOLOXHead(num_classes=1, width=0.125, in_channels=(8, 16, 32))
        self.generator = torch.Generator().manual_seed(22)

    def sample(self, hw, dtype=torch.float32, device='cpu'):
        return torch.randn((2, sum(h * w for h, w in hw), 6),
                           generator=self.generator).to(dtype=dtype, device=device)

    def test_exact_original_decode_across_shapes_dtypes_and_strides(self):
        for hw in (((4, 6), (2, 3), (1, 2)), ((3, 5), (2, 2), (1, 1))):
            self.head.hw = hw
            for dtype in (torch.float32, torch.float64):
                for scales in ((8, 16, 32), (4, 8, 16)):
                    with self.subTest(hw=hw, dtype=dtype, scales=scales):
                        self.head.strides = scales
                        for _ in range(2):
                            source = self.sample(hw, dtype)
                            expected = reference_decode(source.clone(), hw, scales, source.type())
                            actual = self.head.decode_outputs(source, source.type())
                            self.assertIs(actual, source)
                            self.assertTrue(torch.equal(actual, expected))

    def test_repeated_decode_reuses_constants_and_preserves_previous_results(self):
        self.head.hw = ((4, 6), (2, 3), (1, 2))
        first = self.sample(self.head.hw)
        self.head.decode_outputs(first, first.type())
        snapshot = first.clone()
        cache = self.head._decode_cache
        grids, strides = cache[1].clone(), cache[2].clone()
        second = self.sample(self.head.hw)
        expected = reference_decode(second.clone(), self.head.hw, self.head.strides, second.type())
        with patch('torch.arange', side_effect=AssertionError('rebuilding cached grids')):
            actual = self.head.decode_outputs(second, second.type())
        self.assertIs(self.head._decode_cache, cache)
        self.assertTrue(torch.equal(actual, expected))
        self.assertTrue(torch.equal(first, snapshot))
        self.assertTrue(torch.equal(cache[1], grids))
        self.assertTrue(torch.equal(cache[2], strides))

    def test_decode_cache_does_not_change_checkpoint_keys(self):
        keys = tuple(self.head.state_dict())
        buffers = tuple(self.head.named_buffers())
        self.head.hw = ((4, 6), (2, 3), (1, 2))
        source = self.sample(self.head.hw)
        self.head.decode_outputs(source, source.type())
        self.assertEqual(tuple(self.head.state_dict()), keys)
        self.assertEqual(tuple(self.head.named_buffers()), buffers)

    @unittest.skipUnless(torch.cuda.is_available(), 'CUDA is required for graph capture')
    def test_warmed_cuda_decode_can_be_captured_and_replayed(self):
        self.head.hw = ((4, 6), (2, 3), (1, 2))
        source = self.sample(self.head.hw, torch.float16, 'cuda')
        expected = reference_decode(source.clone(), self.head.hw, self.head.strides, source.type())
        static = source.clone()
        stream = torch.cuda.Stream()
        stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(stream):
            self.head.decode_outputs(static.clone(), static.type())
        torch.cuda.current_stream().wait_stream(stream)
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            result = self.head.decode_outputs(static.clone(), static.type())
        graph.replay()
        self.assertTrue(torch.equal(result, expected))
        replacement = self.sample(self.head.hw, torch.float16, 'cuda')
        expected = reference_decode(replacement.clone(), self.head.hw, self.head.strides,
                                    replacement.type())
        static.copy_(replacement)
        graph.replay()
        self.assertTrue(torch.equal(result, expected))
