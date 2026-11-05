from .deep_sort import DeepSort
from .deep_reid import DeepReid


__all__ = ['DeepSort', 'build_tracker', 'DeepReid']


def build_tracker(cfg, sort, use_cuda):
    if sort:
        # 返回DeepSort对象，传入配置参数:
        # REID_CKPT: ReID模型权重路径
        # max_dist: 最大余弦距离阈值
        # min_confidence: 最小检测置信度
        # nms_max_overlap: 非极大值抑制阈值
        # max_iou_distance: 最大IOU距离阈值
        # max_age: 最大追踪帧数
        # n_init: 确认追踪目标所需的连续帧数
        # nn_budget: 特征库容量
        # use_cuda: 是否使用GPU
        return DeepSort(cfg.DEEPSORT.REID_CKPT,
                    max_dist=cfg.DEEPSORT.MAX_DIST, min_confidence=cfg.DEEPSORT.MIN_CONFIDENCE,
                    nms_max_overlap=cfg.DEEPSORT.NMS_MAX_OVERLAP, max_iou_distance=cfg.DEEPSORT.MAX_IOU_DISTANCE,
                    max_age=cfg.DEEPSORT.MAX_AGE, n_init=cfg.DEEPSORT.N_INIT, nn_budget=cfg.DEEPSORT.NN_BUDGET, use_cuda=use_cuda)
    else:
        return DeepReid(cfg.DEEPSORT.REID_CKPT,
                    max_dist=cfg.DEEPSORT.MAX_DIST, min_confidence=cfg.DEEPSORT.MIN_CONFIDENCE,
                    nms_max_overlap=cfg.DEEPSORT.NMS_MAX_OVERLAP, max_iou_distance=cfg.DEEPSORT.MAX_IOU_DISTANCE,
                    max_age=cfg.DEEPSORT.MAX_AGE, n_init=cfg.DEEPSORT.N_INIT, nn_budget=cfg.DEEPSORT.NN_BUDGET, use_cuda=use_cuda)









