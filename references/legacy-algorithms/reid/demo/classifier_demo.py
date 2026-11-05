from calendar import c
from utils.logger import setup_logger
from datasets.make_dataloader_clipreid import make_dataloader
from model.make_model_clipreid import make_model
from solver.make_optimizer_prompt import make_optimizer_1stage, make_optimizer_2stage
from solver.scheduler_factory import create_scheduler
from solver.lr_scheduler import WarmupMultiStepLR
from loss.make_loss import make_loss
from processor.processor_clipreid_stage1 import do_train_stage1
from processor.processor_clipreid_stage2 import do_train_stage2
import random
import torch
import numpy as np
import os
import argparse
from config import cfg
import torchvision.transforms as T
from PIL import Image, ImageFile
import os.path as osp




def set_seed(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = True

def read_image(img_path):
    """Keep reading image until succeed.
    This can avoid IOError incurred by heavy IO process."""
    got_img = False
    if not osp.exists(img_path):
        raise IOError("{} does not exist".format(img_path))
    while not got_img:
        try:
            img = Image.open(img_path).convert('RGB')
            got_img = True
        except IOError:
            print("IOError incurred when reading '{}'. Will redo. Don't worry. Just chill.".format(img_path))
            pass
    return img

val_transforms = T.Compose([
        T.Resize([256, 128]),
        T.ToTensor(),
        T.Normalize(mean=cfg.INPUT.PIXEL_MEAN, std=cfg.INPUT.PIXEL_STD)
    ])

@torch.no_grad()
def classify_one_image(img_path, cam_label=None, view_label=None):
    # 1. 读图
    img = read_image(img_path)
    img = val_transforms(img).unsqueeze(0).to(device)  # [1, C, H, W]

    # 2. forward
    feat, cls_score, cls_score_proj = model(
        img,
        cam_label=cam_label,
        view_label=view_label
    )

    # 3. 预测 ID
    # print(cls_score)
    pred_id = cls_score.argmax(dim=1).item()

    # 4. 置信度（可选）
    prob = torch.softmax(cls_score, dim=1)
    conf = prob.max(dim=1)[0].item()
    # print(prob.sum(dim=1))

    return pred_id, conf, cls_score.squeeze(0)


from collections import Counter

def evaluate_sequences_from_txt(label_txt, thresholds=(0.90, 0.95, 0.99), verbose=True):
    """
    label_txt 每行格式:
    <sequence_dir> <gt_name> <manual_date>

    thresholds: e.g. (0.90, 0.95, 0.99)
    """

    total_seq = 0
    hit_cnt = {t: 0 for t in thresholds}

    print("\n================ Sequence Evaluation ================")

    with open(label_txt, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            seq_dir = parts[0]
            gt_name = parts[1]

            if not os.path.isdir(seq_dir):
                print(f"[WARN] Missing directory: {seq_dir}")
                continue

            preds = []

            for img_name in sorted(os.listdir(seq_dir)):
                if not img_name.lower().endswith((".jpg", ".png", ".jpeg")):
                    continue

                img_path = os.path.join(seq_dir, img_name)
                pred_id, _, _ = classify_one_image(img_path)
                pred_name = finalpid2name.get(pred_id, "Unknown")
                preds.append(pred_name)

            if len(preds) == 0:
                continue

            total_seq += 1

            counter = Counter(preds)
            correct = counter.get(gt_name, 0)
            total = len(preds)
            ratio = correct / total
            top1 = counter.most_common(1)[0][0]

            for t in thresholds:
                if ratio >= t:
                    hit_cnt[t] += 1

            if verbose:
                print(
                    f"[SEQ] {os.path.basename(seq_dir):35s} "
                    f"GT={gt_name:<6s} "
                    f"Top1={top1:<6s} "
                    f"Acc={ratio:.3f} "
                    f"({correct}/{total})"
                )

    print("\n================ Summary ================")
    print(f"Total sequences evaluated: {total_seq}")
    for t in thresholds:
        acc = hit_cnt[t] / total_seq if total_seq > 0 else 0
        print(f"Seq@{int(t*100):02d}: {hit_cnt[t]:4d}/{total_seq} = {acc:.4f}")

    print("========================================\n")

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="ReID Baseline Training")
    parser.add_argument(
        "--config_file", default="configs/person/cnn_clipreid.yml", help="path to config file", type=str
    )

    parser.add_argument("opts", help="Modify config options using the command-line", default=None,
                        nargs=argparse.REMAINDER)
    parser.add_argument("--local_rank", default=0, type=int)
    args = parser.parse_args()

    if args.config_file != "":
        cfg.merge_from_file(args.config_file)
    cfg.merge_from_list(args.opts)
    cfg.freeze()

    set_seed(cfg.SOLVER.SEED)

    if cfg.MODEL.DIST_TRAIN:
        torch.cuda.set_device(args.local_rank)

    output_dir = cfg.OUTPUT_DIR
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    logger = setup_logger("transreid", output_dir, if_train=True)
    logger.info("Saving model in the path :{}".format(cfg.OUTPUT_DIR))
    logger.info(args)

    if args.config_file != "":
        logger.info("Loaded configuration file {}".format(args.config_file))
        with open(args.config_file, 'r') as cf:
            config_str = "\n" + cf.read()
            logger.info(config_str)
    logger.info("Running with config:\n{}".format(cfg))

    if cfg.MODEL.DIST_TRAIN:
        torch.distributed.init_process_group(backend='nccl', init_method='env://')

    # train_loader_stage2, train_loader_stage1, val_loader, num_query, num_classes, camera_num, view_num = make_dataloader(cfg)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = make_model(cfg, num_class=21, camera_num=None, view_num = None, device=device)
    model.load_param('/mnt/share/ubuntu/code/other/CLIP-ReID/RN50_120.pth')
    model.eval()
    model.to(device)
    
    # 你给的原始映射
    name2rawpid = {
    "倪偲淳": 1,
    "况长江": 2,
    "冷佳旭": 3,
    "吴占杰": 4,
    "张嘉豪": 5,
    "张雨朦": 6,
    "李昆鸿": 7,
    "李爽": 8,
    "王政杰": 9,
    "苟英宏": 10,
    "莫梦竞成": 11,
    "郑健康": 12,
    "陈雪": 13,
    "黄周杰": 14,
    "秦陈": 15,
    "高振峰": 16,
    "屈云进": 17,
    "陈纪帆": 18,
    "杨社丹": 19,
    "童新阳": 20,
    "王苗青": 21
    }

    # final pid (0~13) -> name
    finalpid2name = {
        raw_pid - 1: name
        for name, raw_pid in name2rawpid.items()
    }
    # img_path = "/mnt/share/ubuntu/code/project/save/live_camera_2_savereid_track_7/000005.jpg"

    # pred_id, conf, logits = classify_one_image(img_path)

    # print("Pred ID:", pred_id)
    # print("Confidence:", conf)
    # print("Logits:", logits)
    # seq_dir = "/mnt/share/ubuntu/code/project/save/live_camera_1_savereid_track_116"

    results = []

    # for img_name in sorted(os.listdir(seq_dir)):
    #     if not img_name.lower().endswith((".jpg", ".png", ".jpeg")):
    #         continue

    img_path = os.path.join(seq_dir, img_name)

    pred_id, conf, _ = classify_one_image(img_path)

    results.append(pred_id)

    pred_name = finalpid2name.get(pred_id, "Unknown")


    print(
        f"{img_name:>10s}  ->  "
        f"Pred ID: {pred_id:2d}  "
        f"Name: {pred_name:<6s}  "
        f"Conf: {conf:.3f}"
    )

    # label_txt = "/mnt/share/ubuntu/code/other/CLIP-ReID/txt/manual_labels_20260108_fullpath.txt"

    # evaluate_sequences_from_txt(
    #     label_txt,
    #     thresholds=(0.90, 0.95, 0.99),
    #     verbose=True   # 第一次建议 True
    # )
