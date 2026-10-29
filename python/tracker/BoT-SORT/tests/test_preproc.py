import unittest

import cv2
import numpy as np

from yolox.data.data_augment import preproc


def reference_preproc(image, input_size, mean, std, swap=(2, 0, 1)):
    if len(image.shape) == 3:
        padded = np.ones((input_size[0], input_size[1], 3)) * 114.0
    else:
        padded = np.ones(input_size) * 114.0
    copied = np.array(image)
    ratio = min(input_size[0] / copied.shape[0], input_size[1] / copied.shape[1])
    resized = cv2.resize(copied, (int(copied.shape[1] * ratio), int(copied.shape[0] * ratio)),
                         interpolation=cv2.INTER_LINEAR).astype(np.float32)
    padded[:int(copied.shape[0] * ratio), :int(copied.shape[1] * ratio)] = resized
    padded = padded[:, :, ::-1]
    padded /= 255.0
    if mean is not None:
        padded -= mean
    if std is not None:
        padded /= std
    return np.ascontiguousarray(padded.transpose(swap), dtype=np.float32), ratio


class PreprocTests(unittest.TestCase):
    mean = (0.485, 0.456, 0.406)
    std = (0.229, 0.224, 0.225)

    def assert_reference(self, image, size, mean, std, swap=(2, 0, 1)):
        unchanged = image.copy()
        expected, expected_ratio = reference_preproc(image, size, mean, std, swap)
        actual, ratio = preproc(image, size, mean, std, swap)
        self.assertEqual(expected_ratio, ratio)
        self.assertTrue(np.array_equal(actual, expected))
        self.assertEqual(np.float32, actual.dtype)
        self.assertTrue(actual.flags.c_contiguous)
        self.assertTrue(np.array_equal(image, unchanged))

    def test_every_byte_and_channel_matches_original_float64_rounding(self):
        values = np.arange(256, dtype=np.uint8)
        image = np.stack((values, np.roll(values, 85), values[::-1]), axis=1)[None]
        for mean in (None, self.mean, np.array(self.mean, dtype=np.float32)):
            for std in (None, self.std, np.array(self.std, dtype=np.float32)):
                with self.subTest(mean=mean, std=std):
                    self.assert_reference(image, (3, 256), mean, std)

    def test_random_sizes_resize_and_padding_match_exactly(self):
        rng = np.random.default_rng(33)
        for shape in ((17, 29, 3), (29, 17, 3), (1080, 1920, 3), (23, 23, 3)):
            image = rng.integers(0, 256, shape, dtype=np.uint8)
            for size in ((40, 40), (64, 96), (800, 1440)):
                for mean, std in ((self.mean, self.std), (None, None),
                                  (None, self.std), (self.mean, None)):
                    with self.subTest(shape=shape, size=size, mean=mean, std=std):
                        self.assert_reference(image, size, mean, std)

    def test_noncontiguous_input_and_scalar_normalization_match(self):
        image = np.random.default_rng(9).integers(0, 256, (31, 49, 3), dtype=np.uint8)
        for selected in (image[:, ::-1], image[::2, ::2]):
            self.assert_reference(selected, (48, 80), 0.4, 0.2)

    def test_special_dtype_swap_and_broadcast_parameters_keep_original_path(self):
        rng = np.random.default_rng(51)
        image = rng.integers(0, 256, (13, 21, 3), dtype=np.uint8)
        for dtype in (np.float32, np.float64, np.uint16):
            self.assert_reference(image.astype(dtype), (31, 51), self.mean, self.std)
        for swap in ((0, 1, 2), (1, 2, 0), [2, 0, 1]):
            self.assert_reference(image, (31, 51), self.mean, self.std, swap)
        self.assert_reference(image, (31, 51), np.array([self.mean]), np.array([self.std]))
