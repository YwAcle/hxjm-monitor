"""Grounded litter candidates with bounded resolution and optional tiled inspection."""
import json
import math
import time
from pathlib import Path

REGIONS = ["左上", "中上", "右上", "左中", "中央", "右中", "左下", "中下", "右下"]


def validate_result(text):
    try:
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except (ValueError, TypeError):
        raise ValueError("模型未返回有效的垃圾判断，请重新检测。") from None
    if not isinstance(data, dict) or type(data.get("has_garbage")) is not bool:
        raise ValueError("模型未返回有效的垃圾判断，请重新检测。")
    targets = data.get("targets", [])
    if not isinstance(targets, list) or len(targets) > 100:
        raise ValueError("模型返回的目标列表无效。")
    normalized = []
    for target in targets:
        if isinstance(target, str):
            target = {"label": target}
        if not isinstance(target, dict):
            raise ValueError("模型返回的目标格式无效。")
        box, score = target.get("bbox"), target.get("confidence")
        numeric = lambda value: type(value) in (int, float) and math.isfinite(value)
        if not isinstance(target.get("label"), str) or not target["label"].strip():
            raise ValueError("模型返回的垃圾类别无效。")
        if score is not None and (not numeric(score) or not 0 <= score <= 1):
            raise ValueError("模型返回的垃圾评分无效。")
        if box is None:
            normalized.append({"label": target["label"][:80], "confidence": score,
                               "bbox": None, "region_id": None, "region_name": "未定位"})
            continue
        if (not isinstance(box, list) or len(box) != 4
                or not all(numeric(v) and 0 <= v <= 1000 for v in box)
                or box[0] >= box[2] or box[1] >= box[3]):
            raise ValueError("模型返回的垃圾位置或评分无效，请重新检测。")
        col = min(2, int((box[0] + box[2]) / 2 * 3 / 1000))
        row = min(2, int((box[1] + box[3]) / 2 * 3 / 1000))
        normalized.append({"label": target["label"][:80], "confidence": score,
                           "bbox": box, "region_id": f"r{row + 1}c{col + 1}",
                           "region_name": REGIONS[row * 3 + col]})
    if normalized and not data["has_garbage"]:
        raise ValueError("模型的垃圾判断与目标列表矛盾，请重新检测。")
    return {"has_garbage": data["has_garbage"], "targets": normalized,
            "scene_description": str(data.get("scene_description", ""))[:1000],
            "reason": str(data.get("reason", ""))[:1000],
            "unlocalized": data["has_garbage"] and (not normalized or any(t["bbox"] is None for t in normalized))}


CORE_LABELS = {
    # Similar containers are deliberately grouped: zero-shot fine categories are unreliable.
    "bottle": "瓶罐类", "paper": "纸屑", "plastic bag": "塑料袋", "can": "瓶罐类",
}
EXTRA_LABELS = {
    "cardboard": "纸板/纸箱", "cup": "一次性杯", "wrapper": "包装袋/包装纸",
    "food container": "餐盒/外卖盒", "cigarette butt": "烟头", "tissue": "纸巾",
    "banana peel": "果皮", "food scraps": "食物残渣", "face mask": "口罩",
    "glove": "手套", "battery": "废电池",
}
LABELS = {**CORE_LABELS, **EXTRA_LABELS}


def inspection_windows(width, height, detailed=False):
    windows = [(0, 0, width, height)]
    if detailed and min(width, height) >= 320:
        # Four overlapping crops preserve small targets near tile boundaries.
        w, h = math.ceil(width * .6), math.ceil(height * .6)
        windows.extend((x, y, x + w, y + h) for y in (0, height - h) for x in (0, width - w))
    return windows


def merge_candidates(candidates, limit=100):
    kept = []
    # A crop can confidently mislabel a fragment; preserve the full-image detection first.
    for target in sorted(candidates, key=lambda item: (not item.get("full_frame", False), -item["confidence"], item.get("priority", 0))):
        a = target["bbox"]
        duplicate = False
        for other in kept:
            b = other["bbox"]
            intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
            union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
            if union > 0 and intersection / union > .5:
                duplicate = True
                break
        if not duplicate:
            kept.append(target)
            if len(kept) == limit:
                break
    return kept


def touches_crop_edge(box, window, image_size):
    left, top, right, bottom = window
    width, height = image_size
    margin_x, margin_y = (right - left) * .02, (bottom - top) * .02
    return ((left > 0 and box[0] <= margin_x)
            or (top > 0 and box[1] <= margin_y)
            or (right < width and box[2] >= right - left - margin_x)
            or (bottom < height and box[3] >= bottom - top - margin_y))


class Detector:
    def __init__(self, model_path, device="cpu"):
        self.model_path = Path(model_path)
        self.requested_device = device
        self.model = None
        self.device = device

    def load(self):
        if self.model is not None:
            return
        import torch
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        torch.set_num_threads(4)
        self.device = "cuda:0" if self.requested_device == "auto" and torch.cuda.is_available() else self.requested_device
        if self.device == "auto":
            self.device = "cpu"
        self.processor = AutoProcessor.from_pretrained(str(self.model_path), local_files_only=True)
        model = AutoModelForZeroShotObjectDetection.from_pretrained(str(self.model_path), local_files_only=True)
        try:
            model.to(self.device)
        except RuntimeError:
            if self.requested_device != "auto":
                raise
            self.device = "cpu"
            model.to("cpu")
        self.model = model.eval()

    def infer(self, image, detailed=False, threshold=.25):
        if all(low == high for low, high in image.getextrema()):
            raise ValueError("图片为纯色，没有可识别的场景细节，请上传清晰的地面垃圾图片。")
        import torch
        self.load()
        started = time.monotonic()
        width, height = image.size
        candidates = []
        windows = inspection_windows(width, height, detailed)
        groups = []
        for labels in (CORE_LABELS, EXTRA_LABELS):
            prompt = " . ".join(labels) + " ."
            offsets = self.processor.tokenizer(prompt, return_offsets_mapping=True)["offset_mapping"]
            spans, start = [], 0
            for label in labels:
                begin = prompt.index(label, start)
                end = begin + len(label)
                spans.append([i for i, (a, b) in enumerate(offsets) if b > a and a < end and b > begin])
                start = end
            groups.append((prompt, spans, list(labels)))
        # Keep the proven core prompt unchanged; inspect extra categories once at full frame.
        inspections = [(window, 0) for window in windows] + [(windows[0], 1)]
        for (left, top, right, bottom), priority in inspections:
            prompt, spans, labels = groups[priority]
            crop = image.crop((left, top, right, bottom))
            inputs = self.processor(images=crop, text=prompt, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                outputs = self.model(**inputs)
            # Score each complete category phrase, avoiding mixed labels from unrelated text tokens.
            probabilities = outputs.logits[0].sigmoid()
            category_scores = torch.stack([probabilities[:, indices].mean(dim=1) for indices in spans], dim=1)
            scores, label_indices = category_scores.max(dim=1)
            keep = scores >= threshold
            center_boxes = outputs.pred_boxes[0][keep]
            boxes = torch.cat((center_boxes[:, :2] - center_boxes[:, 2:] / 2,
                               center_boxes[:, :2] + center_boxes[:, 2:] / 2), dim=1)
            boxes *= boxes.new_tensor([crop.width, crop.height, crop.width, crop.height])
            for score, box, label_index in zip(scores[keep].tolist(), boxes.tolist(), label_indices[keep].tolist()):
                # Ignore fragments cut by an internal tile edge; full frame and overlapping tiles cover them.
                if touches_crop_edge(box, (left, top, right, bottom), image.size):
                    continue
                label = labels[label_index]
                box = [max(0, min(1000, (box[0] + left) / width * 1000)),
                       max(0, min(1000, (box[1] + top) / height * 1000)),
                       max(0, min(1000, (box[2] + left) / width * 1000)),
                       max(0, min(1000, (box[3] + top) / height * 1000))]
                if box[0] >= box[2] or box[1] >= box[3]:
                    continue
                candidates.append({"label": LABELS[label], "confidence": round(score, 4),
                                   "bbox": [round(v, 2) for v in box],
                                   "full_frame": (left, top, right, bottom) == windows[0], "priority": priority})
        targets = merge_candidates(candidates)
        # Reuse the same validated image coordinates for both camera and uploaded images.
        result = validate_result(json.dumps({"has_garbage": bool(targets), "targets": targets}))
        result.update({"engine": "Grounding DINO Tiny", "device": self.device, "passes": len(inspections),
                       "categories": list(dict.fromkeys(LABELS.values())),
                       "threshold": threshold, "inference_seconds": round(time.monotonic() - started, 2),
                       "scene_description": f"发现 {len(targets)} 个疑似垃圾目标" if targets else "本次未检出符合阈值的垃圾目标",
                       "reason": "按纸屑、瓶罐、包装物、餐盒、烟头等 14 类外观定位；类别不等于是否已被丢弃，也不等于当地垃圾投放分类，请结合原图复核。" if targets else "未检出不代表没有垃圾；小目标可使用局部放大复检，或适当降低阈值。"})
        return result
