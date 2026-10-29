# vim: expandtab:ts=4:sw=4
import os
import errno
import argparse
import numpy as np
import cv2
from pathlib import Path
import sys
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from deep_sort.deep.BasicBlock import Net


def _run_in_batches(f, data_dict, out, batch_size):
    data_len = len(out)
    num_batches = int(data_len / batch_size)

    s, e = 0, 0
    for i in range(num_batches):
        s, e = i * batch_size, (i + 1) * batch_size
        batch_data_dict = {k: v[s:e] for k, v in data_dict.items()}
        out[s:e] = f(batch_data_dict)
    if e < len(out):
        batch_data_dict = {k: v[e:] for k, v in data_dict.items()}
        out[e:] = f(batch_data_dict)


def extract_image_patch(image, bbox, patch_shape):
    """Extract image patch from bounding box.

    Parameters
    ----------
    image : ndarray
        The full image.
    bbox : array_like
        The bounding box in format (x, y, width, height).
    patch_shape : Optional[array_like]
        This parameter can be used to enforce a desired patch shape
        (height, width). First, the `bbox` is adapted to the aspect ratio
        of the patch shape, then it is clipped at the image boundaries.
        If None, the shape is computed from :arg:`bbox`.

    Returns
    -------
    ndarray | NoneType
        An image patch showing the :arg:`bbox`, optionally reshaped to
        :arg:`patch_shape`.
        Returns None if the bounding box is empty or fully outside of the image
        boundaries.

    """
    bbox = np.array(bbox)
    if patch_shape is not None:
        # correct aspect ratio to patch shape
        target_aspect = float(patch_shape[1]) / patch_shape[0]
        new_width = target_aspect * bbox[3]
        bbox[0] -= (new_width - bbox[2]) / 2
        bbox[2] = new_width

    # convert to top left, bottom right
    bbox[2:] += bbox[:2]
    bbox = bbox.astype(np.int64)

    # clip at image boundaries
    bbox[:2] = np.maximum(0, bbox[:2])
    bbox[2:] = np.minimum(np.asarray(image.shape[:2][::-1]) - 1, bbox[2:])
    if np.any(bbox[:2] >= bbox[2:]):
        return None
    sx, sy, ex, ey = bbox
    image = image[sy:ey, sx:ex]
    image = cv2.resize(image, tuple(patch_shape[::-1]))
    return image


class ImageEncoder(object):
    """Market-1501 ckpt.t7 ReID feature encoder."""

    def __init__(self, model_path, device="cuda", image_size=(128, 64)):
        if device.startswith("cuda") and not torch.cuda.is_available():
            device = "cpu"

        self.device = torch.device(device)
        self.feature_dim = 512
        self.image_shape = (image_size[0], image_size[1], 3)

        checkpoint = torch.load(model_path, map_location=self.device)
        self.model = Net(num_classes=751, reid=True).to(self.device)
        self.model.load_state_dict(checkpoint["net_dict"])
        self.model.eval()

        self.mean = torch.tensor(
            [0.485, 0.456, 0.406], device=self.device
        ).view(1, 3, 1, 1)
        self.std = torch.tensor(
            [0.229, 0.224, 0.225], device=self.device
        ).view(1, 3, 1, 1)

    def __call__(self, data_x, batch_size=32):
        out = np.zeros((len(data_x), self.feature_dim), dtype=np.float32)
        _run_in_batches(
            lambda data: self._extract(data),
            {"images": data_x},
            out,
            batch_size,
        )
        return out

    def _extract(self, data_dict):
        # 裁剪图为 BGR uint8，转换为 RGB 并转为 NCHW tensor。
        rgb_images = np.ascontiguousarray(data_dict["images"][..., ::-1])
        images = torch.from_numpy(rgb_images).permute(0, 3, 1, 2)
        images = images.float().div_(255.0).to(self.device)
        images = (images - self.mean) / self.std

        with torch.no_grad():
            features = self.model(images)

        return features.cpu().numpy().astype(np.float32)


def create_box_encoder(model_path, device="cuda", batch_size=32):
    image_encoder = ImageEncoder(model_path, device=device)
    image_shape = image_encoder.image_shape

    def encoder(image, boxes):
        image_patches = []
        for box in boxes:
            patch = extract_image_patch(image, box, image_shape[:2])
            if patch is None:
                print("WARNING: Failed to extract image patch: %s." % str(box))
                patch = np.random.uniform(
                    0., 255., image_shape).astype(np.uint8)
            image_patches.append(patch)
        image_patches = np.asarray(image_patches)
        return image_encoder(image_patches, batch_size)

    return encoder


def generate_detections(encoder, mot_dir, output_dir, detection_dir=None):
    """Generate detections with features.

    Parameters
    ----------
    encoder : Callable[image, ndarray] -> ndarray
        The encoder function takes as input a BGR color image and a matrix of
        bounding boxes in format `(x, y, w, h)` and returns a matrix of
        corresponding feature vectors.
    mot_dir : str
        Path to the MOTChallenge directory (can be either train or test).
    output_dir
        Path to the output directory. Will be created if it does not exist.
    detection_dir
        Path to custom detections. The directory structure should be the default
        MOTChallenge structure: `[sequence]/det/det.txt`. If None, uses the
        standard MOTChallenge detections.

    """
    if detection_dir is None:
        detection_dir = mot_dir
    try:
        os.makedirs(output_dir)
    except OSError as exception:
        if exception.errno == errno.EEXIST and os.path.isdir(output_dir):
            pass
        else:
            raise ValueError(
                "Failed to created output directory '%s'" % output_dir)

    for sequence in os.listdir(mot_dir):
        print("Processing %s" % sequence)
        sequence_dir = os.path.join(mot_dir, sequence)

        image_dir = os.path.join(sequence_dir, "img1")
        image_filenames = {
            int(os.path.splitext(f)[0]): os.path.join(image_dir, f)
            for f in os.listdir(image_dir)}

        detection_file = os.path.join(
            detection_dir, sequence, "det/det.txt")
        detections_in = np.loadtxt(detection_file, delimiter=',')
        detections_out = []

        frame_indices = detections_in[:, 0].astype(np.int64)
        min_frame_idx = frame_indices.astype(np.int64).min()
        max_frame_idx = frame_indices.astype(np.int64).max()
        for frame_idx in range(min_frame_idx, max_frame_idx + 1):
            print("Frame %05d/%05d" % (frame_idx, max_frame_idx))
            mask = frame_indices == frame_idx
            rows = detections_in[mask]

            if frame_idx not in image_filenames:
                print("WARNING could not find image for frame %d" % frame_idx)
                continue
            bgr_image = cv2.imread(
                image_filenames[frame_idx], cv2.IMREAD_COLOR)
            features = encoder(bgr_image, rows[:, 2:6].copy())
            detections_out += [np.r_[(row, feature)] for row, feature
                               in zip(rows, features)]

        output_filename = os.path.join(output_dir, "%s.npy" % sequence)
        np.save(
            output_filename, np.asarray(detections_out), allow_pickle=False)


def parse_args():
    parser = argparse.ArgumentParser(description="Re-ID feature extractor")
    parser.add_argument("--model_path", required=True,
                        help="Path to OSNet .pth weights.")
    parser.add_argument("--device", default="cuda", help="'cuda' or 'cpu'.")
    parser.add_argument("--mot_dir", required=True,
                        help="Path to MOTChallenge directory (train or test)")
    parser.add_argument("--detection_dir", default=None,
                        help="Path to custom detections.")
    parser.add_argument("--output_dir", default="detections",
                        help="Output directory.")
    return parser.parse_args()


def main():
    args = parse_args()
    encoder = encoder = create_box_encoder(
        args.model_path, device=args.device, batch_size=32
    )
    generate_detections(encoder, args.mot_dir, args.output_dir,
                        args.detection_dir)


if __name__ == "__main__":
    main()
