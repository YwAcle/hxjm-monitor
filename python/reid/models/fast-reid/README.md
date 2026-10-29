<img src=".github/FastReID-Logo.png" width="300" >

[![Gitter](https://badges.gitter.im/fast-reid/community.svg)](https://gitter.im/fast-reid/community?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge)

Gitter: [fast-reid/community](https://gitter.im/fast-reid/community?utm_source=share-link&utm_medium=link&utm_campaign=share-link)

微信: 

<img src=".github/wechat_group.png" width="150" >


FastReID 是一个实现了最先进的重识别算法的研究平台。它是对之前版本 [reid strong baseline](https://github.com/michuanhaohao/reid-strong-baseline) 的全面重写。

## 最新动态

- [2021年9月] [DG-ReID](https://github.com/xiaomingzhid/sskd) 已更新，您可以查看[论文](https://arxiv.org/pdf/2108.05045.pdf)。
- [2021年6月] 支持[连续参数](https://github.com/PhilJd/contiguous_pytorch_params)，现在可以加速约20%。
- [2021年5月] 支持Vision Transformer骨干网络，请参见 `configs/Market1501/bagtricks_vit.yml`。
- [2021年4月] [FastFace](projects/FastFace) 中支持Partial FC！
- [2021年1月] [FastRT](projects/FastRT) 中的TRT网络定义API已发布！感谢[Darren](https://github.com/TCHeish)的贡献。
- [2021年1月] 基于fastreid的NAIC20(reid赛道)[第一名解决方案](projects/NAIC20)已发布！
- [2021年1月] FastReID V1.0已发布！🎉
  支持超越reid的许多任务，如图像检索和人脸识别。查看[发布说明](https://github.com/JDAI-CV/fast-reid/releases/tag/v1.0.0)。
- [2020年10月] 基于fastreid添加了[超参数优化](projects/FastTune)。请参见 `projects/FastTune`。
- [2020年9月] 基于fastreid添加了[人物属性识别](projects/FastAttr)。请参见 `projects/FastAttr`。
- [2020年9月] 支持使用 `apex` 进行自动混合精度训练。设置 `cfg.SOLVER.FP16_ENABLED=True` 开启此功能。
- [2020年8月] 支持[模型蒸馏](projects/FastDistill)，感谢[王冠安](https://github.com/wangguanan)的贡献。
- [2020年8月] 支持ONNX/TensorRT转换器。
- [2020年7月] 支持多GPU分布式训练，训练速度大幅提升。
- 包含更多功能，如圆形损失函数、丰富的可视化方法和评估指标、在传统、跨域、部分和车辆重识别上的最先进结果、同时在多个数据集上测试等。
- 可以作为库使用，支持在其基础上开发[不同项目](projects)。我们将以这种方式开源更多研究项目。
- 移除了对[ignite](https://github.com/pytorch/ignite)（一个高级库）的依赖，由[PyTorch](https://pytorch.org/)提供支持。

我们撰写了关于这个工具箱的[fastreid介绍](https://l1aoxingyu.github.io/blogpages/reid/fastreid/2020/05/29/fastreid.html)
和[fastreid v1.0](https://l1aoxingyu.github.io/blogpages/reid/fastreid/2021/04/28/fastreid-v1.html)。

## 更新日志

详细信息和发布历史请参考[changelog.md](CHANGELOG.md)。

## 安装

请参见[INSTALL.md](INSTALL.md)。

## 快速开始

设计的架构遵循这个指南[PyTorch-Project-Template](https://github.com/L1aoXingyu/PyTorch-Project-Template)，您可以自行查看每个文件夹的用途。

请参见[GETTING_STARTED.md](GETTING_STARTED.md)。

在我们的[文档](https://fast-reid.readthedocs.io/)中了解更多信息。查看[projects/](projects)获取基于fastreid构建的一些项目。

## 模型库和基线

我们提供了大量的基线结果和可供下载的训练模型，详见[Fastreid模型库](MODEL_ZOO.md)。

## 部署

我们在[Fastreid部署](tools/deploy)中提供了一些示例和脚本，用于将fastreid模型转换为Caffe、ONNX和TensorRT格式。

## 许可证

Fastreid在[Apache 2.0许可证](LICENSE)下发布。

## 引用FastReID

如果您在研究中使用FastReID或希望引用模型库中发布的基线结果，请使用以下BibTeX条目。
