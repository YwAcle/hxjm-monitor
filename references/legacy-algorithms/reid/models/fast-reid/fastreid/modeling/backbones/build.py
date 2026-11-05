# encoding: utf-8
"""
@author:  liaoxingyu
@contact: sherlockliao01@gmail.com
"""

from ...utils.registry import Registry

BACKBONE_REGISTRY = Registry("META_ARCH")
BACKBONE_REGISTRY.__doc__ = """
Registry for backbones, which extract feature maps from images
The registered object must be a callable that accepts two arguments:
1. A :class:`fastreid.config.CfgNode`
It must returns an instance of :class:`Backbone`.

骨干网络注册表，用于从图像中提取特征图
注册的对象必须是接受两个参数的可调用对象：
1. 一个 :class:`fastreid.config.CfgNode` 配置节点
它必须返回一个 :class:`Backbone` 的实例。
"""


def build_backbone(cfg):
    """
    Build a backbone from `cfg.MODEL.BACKBONE.NAME`.
    Returns:
        an instance of :class:`Backbone`
        
    根据 `cfg.MODEL.BACKBONE.NAME` 构建骨干网络。
    返回：
        一个 :class:`Backbone` 的实例
    """

    backbone_name = cfg.MODEL.BACKBONE.NAME
    backbone = BACKBONE_REGISTRY.get(backbone_name)(cfg)
    return backbone
