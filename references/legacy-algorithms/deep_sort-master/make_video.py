import os
import cv2
import numpy as np


def make_video(sequence_dir, result_file, output_video, fps=None):
    # 图片序列
    img_dir = os.path.join(sequence_dir, "img1")
    image_filenames = {
        int(os.path.splitext(f)[0]): os.path.join(img_dir, f)
        for f in os.listdir(img_dir)
    }
    min_frame, max_frame = min(image_filenames), max(image_filenames)

    # 轨迹: 帧号, id, x, y, w, h
    results = np.loadtxt(result_file, delimiter=',')
    if results.ndim == 1:
        results = results[None, :]

    # 帧率(有 seqinfo.ini 就读,否则默认 20)
    if fps is None:
        fps = 20
        info_file = os.path.join(sequence_dir, "seqinfo.ini")
        if os.path.exists(info_file):
            for line in open(info_file).read().splitlines():
                if line.startswith("frameRate"):
                    fps = int(float(line.split('=')[1].strip()))
                    break

    first = cv2.imread(image_filenames[min_frame])
    h, w = first.shape[:2]
    writer = cv2.VideoWriter(
        output_video, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h))

    for frame_idx in range(min_frame, max_frame + 1):
        if frame_idx not in image_filenames:
            continue
        img = cv2.imread(image_filenames[frame_idx])
        mask = results[:, 0].astype(int) == frame_idx
        for row in results[mask]:
            track_id = int(row[1])
            x, y, ww, hh = [int(v) for v in row[2:6]]
            color = ((track_id * 37) % 256, (track_id * 73) % 256,
                     (track_id * 109) % 256)
            cv2.rectangle(img, (x, y), (x + ww, y + hh), color, 2)
            cv2.putText(img, str(track_id), (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        writer.write(img)
        print("Frame %d/%d" % (frame_idx, max_frame))

    writer.release()
    print("Saved video to", output_video)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--sequence_dir", required=True)
    p.add_argument("--result_file", required=True)
    p.add_argument("--output_video", required=True)
    p.add_argument("--fps", type=int, default=None)
    a = p.parse_args()
    make_video(a.sequence_dir, a.result_file, a.output_video, a.fps)