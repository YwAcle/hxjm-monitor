import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from tracker.gmc import GMC


def original_matching_points(previous, current, pairs, width, height):
    matches, distances = [], []
    for m, n in pairs:
        if m.distance < 0.9 * n.distance:
            old, new = previous[m.queryIdx].pt, current[m.trainIdx].pt
            distance = (old[0] - new[0], old[1] - new[1])
            if abs(distance[0]) < 0.25 * width and abs(distance[1]) < 0.25 * height:
                matches.append(m)
                distances.append(distance)
    if not distances:
        return np.empty((0, 2)), np.empty((0, 2))
    inliers = (distances - np.mean(distances, 0)) < 2.5 * np.std(distances, 0)
    selected = [match for match, keep in zip(matches, inliers) if keep[0] and keep[1]]
    return (np.array([previous[m.queryIdx].pt for m in selected]),
            np.array([current[m.trainIdx].pt for m in selected]))


class GMCTests(unittest.TestCase):
    def test_orb_points_and_transform_equal_original_filters(self):
        rng = np.random.default_rng(91)
        image = rng.integers(0, 256, (400, 640, 3), dtype=np.uint8)
        estimate = cv2.estimateAffinePartial2D
        threads = cv2.getNumThreads()
        self.addCleanup(cv2.setNumThreads, threads)
        for thread_count in (1, 8):
            cv2.setNumThreads(thread_count)
            tracker = GMC('orb')
            tracker.apply(image)
            for angle in (0.35, 0.7):
                transform = cv2.getRotationMatrix2D((320, 200), angle, 1.)
                transform[:, 2] += [2.7, -1.4]
                frame = cv2.warpAffine(image, transform, (640, 400))
                previous = tracker.prevKeyPoints
                recorded = []
                matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

                def match(*args):
                    pairs = matcher.knnMatch(*args)
                    recorded.append(pairs)
                    return pairs

                tracker.matcher = SimpleNamespace(knnMatch=match)
                cv2.setRNGSeed(12345)
                with patch('tracker.gmc.cv2.estimateAffinePartial2D', wraps=estimate) as called:
                    actual = tracker.apply(frame)
                expected_points = original_matching_points(previous, tracker.prevKeyPoints,
                                                           recorded[0], 320, 200)
                self.assertGreater(len(expected_points[0]), 4)
                called.assert_called_once()
                for expected, passed in zip(expected_points, called.call_args.args[:2]):
                    np.testing.assert_array_equal(passed, expected)
                cv2.setRNGSeed(12345)
                expected, _ = estimate(*expected_points, cv2.RANSAC)
                expected[:, 2] *= tracker.downscale
                np.testing.assert_array_equal(actual, expected)

    def test_empty_incomplete_and_rejected_matches_advance_reference_frame(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        points = [cv2.KeyPoint(10., 10., 7.)]
        descriptors = np.zeros((1, 32), dtype=np.uint8)
        single = cv2.DMatch(0, 0, 1.)
        cases = ((), ((single,),), ((single, cv2.DMatch(0, 0, 1.)),))
        for matches in cases:
            with self.subTest(matches=matches):
                tracker = GMC('orb')
                tracker.detector = SimpleNamespace(detect=lambda *args: points)
                tracker.extractor = SimpleNamespace(compute=lambda *args: (points, descriptors))
                tracker.matcher = SimpleNamespace(knnMatch=lambda *args: matches)
                tracker.apply(frame)
                next_frame = frame.copy()
                next_frame[30, 30] = 255
                with patch('tracker.gmc.cv2.estimateAffinePartial2D') as estimate:
                    result = tracker.apply(next_frame)
                estimate.assert_not_called()
                np.testing.assert_array_equal(result, np.eye(2, 3))
                np.testing.assert_array_equal(tracker.prevFrame,
                                              cv2.resize(cv2.cvtColor(next_frame, cv2.COLOR_BGR2GRAY), (50, 50)))
                self.assertEqual(tracker.prevKeyPoints, points)
                np.testing.assert_array_equal(tracker.prevDescriptors, descriptors)
