# encoding: utf-8
"""
@author:  liaoxingyu
@contact: sherlockliao01@gmail.com
"""

import argparse
import glob
import os
import sys

import time
import torch.nn.functional as F
import cv2
import numpy as np
import tqdm
from torch.backends import cudnn

from fastreid.config import get_cfg
from fastreid.utils.logger import setup_logger
from fastreid.utils.file_io import PathManager

from demo.predictor import FeatureExtractionDemo

# import some modules added in project like this below
# sys.path.append("projects/PartialReID")
# from partialreid import *

cudnn.benchmark = True
setup_logger(name="fastreid")


def setup_cfg(args):
    # load config from file and command-line arguments
    cfg = get_cfg()
    # add_partialreid_config(cfg)
    cfg.merge_from_file(args.config_file)
    cfg.merge_from_list(args.opts)
    cfg.freeze()
    return cfg


def get_parser():
    parser = argparse.ArgumentParser(description="使用reid模型进行特征提取")
    parser.add_argument(
        "--config_file",
        default='/home/guest/Documents/hxjm-monitor/mtx/python/reid/models/fast-reid/models/config-test.yaml',
        help="配置文件路径",
    )
    parser.add_argument(
        "--parallel",
        action='store_true',
        help='是否使用多进程进行特征提取。'
    )
    parser.add_argument(
        "--input",
        nargs="+",
        help="空格分隔的输入图像列表；"
             "或单个glob模式，如'directory/*.jpg'",
    )
    parser.add_argument(
        "--output",
        default='demo_output',
        help='保存特征的路径'
    )
    parser.add_argument(
        "--opts",
        help="使用命令行'键 值'对修改配置选项",
        default=['MODEL.WEIGHTS', '/home/guest/Documents/hxjm-monitor/mtx/python/reid/models/fast-reid/models/reid.pth'],
        nargs=argparse.REMAINDER,
    )
    return parser

def reid_feature():
    args = get_parser().parse_args()
    cfg = setup_cfg(args)
    demo = FeatureExtractionDemo(cfg, parallel=args.parallel)
    return demo


class Reid_feature():
    def __init__(self):
        args = get_parser().parse_args()
        cfg = setup_cfg(args)
        self.demo = FeatureExtractionDemo(cfg, parallel=args.parallel)

    def __call__(self, img_list):
        t1 = time.time()
        feat = self.demo.run_on_image(img_list)
        # print('reid time:', time.time() - t1, len(img_list))
        return feat

def postprocess(features):
    # Normalize feature to compute cosine distance
    features = F.normalize(features)
    features = features.cpu().data.numpy()
    return features


if __name__ == '__main__':
    args = get_parser().parse_args()
    cfg = setup_cfg(args)
    demo = FeatureExtractionDemo(cfg, parallel=args.parallel)

    PathManager.mkdirs(args.output)
    if args.input:
        if PathManager.isdir(args.input[0]):
            args.input = glob.glob(os.path.expanduser(args.input[0]))
            assert args.input, "The input path(s) was not found"
        for path in tqdm.tqdm(args.input):
            img = cv2.imread(path)
            feat = demo.run_on_image(img)
            feat = postprocess(feat)
            np.save(os.path.join(args.output, os.path.basename(path).split('.')[0] + '.npy'), feat)
