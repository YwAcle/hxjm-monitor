import unittest

import torch
from torch import nn

from yolox.utils.model_utils import fuse_conv_and_bn


class FusionTests(unittest.TestCase):
    def test_fusion_preserves_predictions_without_retaining_autograd_graph(self):
        torch.manual_seed(7)
        for bias in (False, True):
            conv = nn.Conv2d(3, 4, 3, padding=1, bias=bias).eval()
            bn = nn.BatchNorm2d(4).eval()
            bn.running_mean.copy_(torch.randn(4))
            bn.running_var.copy_(torch.rand(4) + 0.1)
            inputs = torch.randn(2, 3, 8, 8)
            with torch.enable_grad():
                fused = fuse_conv_and_bn(conv, bn)
                torch.testing.assert_close(fused(inputs), bn(conv(inputs)))
                for parameter in fused.half().parameters():
                    self.assertFalse(parameter.requires_grad)
                    self.assertIsNone(parameter.grad_fn)
