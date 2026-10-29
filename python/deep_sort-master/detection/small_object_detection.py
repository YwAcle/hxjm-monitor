from sahi.models.ultralytics import UltralyticsDetectionModel
from sahi.predict import get_sliced_prediction
from pathlib import Path


MODEL_PATH = "/data/nfs_storage/hxjm/python/deep_sort-master/detection/yolov5mu.pt"
IMAGE_PATH = "/data/nfs_storage/hxjm/python/deep_sort-master/detection/image.png"


def main():
    # COCO 和单类别 person 模型都将行人作为类别 0。
    detection_model = UltralyticsDetectionModel(
        model_path=MODEL_PATH,
        confidence_threshold=0.3,
        device="cuda",  # 没有 GPU 时改为 "cpu"
    )

    result = get_sliced_prediction(
        IMAGE_PATH,
        detection_model,
        slice_height=256,
        slice_width=256,
        overlap_height_ratio=0.2,
        overlap_width_ratio=0.2,
    )

    # SAHI 版本不同，类别 id/name 的暴露方式可能略有差异；任一方式识别为 person 即保留。
    person_predictions = [
        pred
        for pred in result.object_prediction_list
        if pred.category.id == 0
        or str(pred.category.name).strip().lower() == "person"
    ]
    result.object_prediction_list = person_predictions

    for pred in person_predictions:
        x1, y1, x2, y2 = map(int, pred.bbox.to_xyxy())
        print("person: bbox=(%d, %d, %d, %d), confidence=%.4f" %
              (x1, y1, x2, y2, pred.score.value))

    output_dir = Path(__file__).resolve().parent / "runs" / "predictions"
    result.export_visuals(export_dir=str(output_dir))
    print("Detected %d persons; visuals saved to %s" %
          (len(person_predictions), output_dir))


if __name__ == "__main__":
    main()
