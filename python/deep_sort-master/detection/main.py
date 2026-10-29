from ultralytics import YOLO
import cv2
import os

def main():
    model = YOLO("/data/nfs_storage/hxjm/python/deep_sort-master/detection/yolov5mu.pt")

    img_dir = "/data/nfs_storage/hxjm/python/deep_sort-master/MOTSChallenge/train/0001/img1"   # 图片文件夹(改成你的实际路径)
    out_dir = "/data/nfs_storage/hxjm/python/deep_sort-master/MOTSChallenge/train/0001/det"    # det.txt 输出目录
    vis_dir = "/data/nfs_storage/hxjm/python/deep_sort-master/MOTSChallenge/train/0001/det_images"
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(vis_dir, exist_ok=True)

    det_path = os.path.join(out_dir, "det.txt")
    f_out = open(det_path, "w")

    files = sorted(os.listdir(img_dir))          # 排序,保证帧号从小到大
    for fname in files:
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        frame_id = int(os.path.splitext(fname)[0])   # 000001.jpg -> 1
        image_path = os.path.join(img_dir, fname)

        result = model(image_path, classes=[0], conf=0.45, iou=0.5, verbose=False, imgsz=1280)[0]
        cv2.imwrite(os.path.join(vis_dir, fname), result.plot())

        if result.boxes is None or len(result.boxes) == 0:
            continue

        # xyxy = (左上x, 左上y, 右下x, 右下y)
        xyxy = result.boxes.xyxy.cpu().numpy()
        confs = result.boxes.conf.cpu().numpy()

        for box, conf in zip(xyxy, confs):
            x1, y1, x2, y2 = box
            w = x2 - x1
            h = y2 - y1
            # MOT 格式: 帧号, -1, x, y, w, h, 置信度, -1, -1, -1
            f_out.write("%d,-1,%.2f,%.2f,%.2f,%.2f,%.4f,-1,-1,-1\n"
                        % (frame_id, x1, y1, w, h, conf))

        print("Frame %d: %d persons" % (frame_id, len(xyxy)))

    f_out.close()
    print("Saved det.txt ->", det_path)
    print("Saved detection images ->", vis_dir)

if __name__ == "__main__":
    main()
