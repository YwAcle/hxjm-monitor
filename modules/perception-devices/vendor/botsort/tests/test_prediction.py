import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import torch

from tracker.bot_sort import BoTSORT, STrack, remove_duplicate_stracks
from tools.demo import make_parser, track_frame
from yolox.utils.visualize import get_color, plot_tracking


def options(**overrides):
    values = dict(track_high_thresh=0.6, track_low_thresh=0.1,
                  new_track_thresh=0.7, track_buffer=120, match_thresh=0.8,
                  proximity_thresh=0.5, appearance_thresh=0.25,
                  prediction_max_age=5, crossing_guard=True, with_reid=False, cmc_method='none',
                  name=None, ablation=False, mot20=False,
                  min_box_area=10, aspect_ratio_thresh=1.6)
    values.update(overrides)
    return SimpleNamespace(**values)


def detection(x=60, width=40, height=100, score=0.95):
    return np.array([[x, 80, x + width, 80 + height, score]], dtype=np.float32)


class PredictionTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((300, 400, 3), dtype=np.uint8)
        self.empty = np.empty((0, 5), dtype=np.float32)

    def test_shared_process_tracker_creation_does_not_reuse_live_ids(self):
        first = BoTSORT(options(), frame_rate=20, reset_id=False)
        tid = first.update(detection(), self.frame)[0].track_id
        second = BoTSORT(options(), frame_rate=20, reset_id=False)
        other_tid = second.update(detection(), self.frame)[0].track_id
        self.assertGreater(other_tid, tid)
        BoTSORT(options(), frame_rate=20, reset_id=False)
        first.update(self.empty, self.frame)
        new_tracks = first.update(detection(x=250), self.frame)
        self.assertTrue(new_tracks)
        self.assertTrue(any(track.track_id > other_tid for track in new_tracks))
        self.assertEqual(len({track.track_id for track in new_tracks}), len(new_tracks))

    def test_online_time_expires_predictions_and_retains_id_for_four_seconds(self):
        tracker = BoTSORT(options(recover_lost=True), frame_rate=20)
        tid = tracker.update(detection(width=12, height=30), self.frame, timestamp_ms=1000)[0].track_id
        result = tracker.update(self.empty, self.frame, timestamp_ms=1250)
        self.assertEqual(result[0].track_id, tid)
        self.assertEqual(result[0].missed_frames, 5)
        self.assertEqual(tracker.update(self.empty, self.frame, timestamp_ms=1300), [])
        recovered = tracker.update(detection(width=12, height=30), self.frame, timestamp_ms=2000)
        self.assertEqual(recovered[0].track_id, tid)
        self.assertFalse(recovered[0].is_prediction)
        tracker.update(self.empty, self.frame, timestamp_ms=6100)
        self.assertEqual(tracker.lost_stracks, [])
        self.assertTrue(any(track.track_id == tid for track in tracker.removed_stracks))

    def test_online_nominal_cadence_matches_offline_filter(self):
        offline = BoTSORT(options(), frame_rate=20)
        expected = []
        for boxes in [detection(), detection(64), self.empty, detection(72)]:
            expected.append([track.tlwh.copy() for track in offline.update(boxes, self.frame)])
        online = BoTSORT(options(), frame_rate=20)
        for index, boxes in enumerate([detection(), detection(64), self.empty, detection(72)]):
            actual = online.update(boxes, self.frame, timestamp_ms=1000 + index * 50)
            np.testing.assert_allclose([track.tlwh for track in actual], expected[index])

    def test_kalman_skip_matches_multiple_nominal_predictions(self):
        from tracker.kalman_filter import KalmanFilter
        kf = KalmanFilter()
        mean, covariance = kf.initiate(np.array([100., 100., 12., 30.]))
        mean[4:6] = [2., -1.]
        sequential_mean, sequential_cov = mean[None].copy(), covariance[None].copy()
        for _ in range(5):
            sequential_mean, sequential_cov = kf.multi_predict(sequential_mean, sequential_cov)
        skipped_mean, skipped_cov = kf.multi_predict(mean[None], covariance[None], dt=5)
        np.testing.assert_allclose(skipped_mean, sequential_mean)
        np.testing.assert_allclose(skipped_cov, sequential_cov)

    def test_kalman_correction_keeps_covariance_positive_for_large_uncertainty(self):
        from tracker.kalman_filter import KalmanFilter
        kf = KalmanFilter()
        rng = np.random.default_rng(17)
        for power in (4, 8, 12, 16):
            for _ in range(100):
                a = rng.normal(size=(8, 8))
                covariance = a @ a.T * 10. ** power
                mean = np.array([100., 100., 1., 2., 0., 0., 0., 0.])
                for _ in range(4):
                    mean, covariance = kf.update(mean, covariance, mean[:4])
                    np.testing.assert_allclose(covariance, covariance.T, atol=1e-12)
                    np.linalg.cholesky(covariance)

    def test_motion_limit_and_recovery_keep_identity(self):
        tracker = BoTSORT(options(), frame_rate=20)
        first = tracker.update(detection(), self.frame)[0]
        tid = first.track_id
        observed = tracker.update(detection(64), self.frame)[0]
        last_x = observed.tlwh[0]
        for missed in range(1, 6):
            predicted = tracker.update(self.empty, self.frame)
            self.assertEqual(len(predicted), 1)
            self.assertEqual(predicted[0].track_id, tid)
            self.assertTrue(predicted[0].is_prediction)
            self.assertEqual(predicted[0].missed_frames, missed)
            self.assertEqual(predicted[0].end_frame, 2)
            self.assertGreater(predicted[0].tlwh[0], last_x)
            last_x = predicted[0].tlwh[0]
        self.assertEqual(tracker.update(self.empty, self.frame), [])
        self.assertEqual(len(tracker.lost_stracks), 1)
        self.assertEqual(tracker.removed_stracks, [])
        recovered = tracker.update(detection(last_x), self.frame)[0]
        self.assertEqual(recovered.track_id, tid)
        self.assertFalse(recovered.is_prediction)
        self.assertEqual(recovered.missed_frames, 0)
        self.assertEqual(tracker.lost_stracks, [])

    def test_unconfirmed_track_and_empty_scene_do_not_get_predictions(self):
        tracker = BoTSORT(options(), frame_rate=20)
        self.assertEqual(tracker.update(self.empty, self.frame), [])
        tracker.update(detection(), self.frame)
        self.assertEqual(tracker.update(self.empty, self.frame), [])

    def test_one_missing_person_does_not_hide_other_person(self):
        tracker = BoTSORT(options(), frame_rate=20)
        first = tracker.update(np.vstack([detection(), detection(220)]), self.frame)
        observed_id, missing_id = [t.track_id for t in first]
        tracks = tracker.update(detection(), self.frame)
        self.assertEqual({t.track_id: t.is_prediction for t in tracks},
                         {observed_id: False, missing_id: True})

    def test_prediction_can_be_disabled(self):
        tracker = BoTSORT(options(prediction_max_age=0), frame_rate=20)
        tracker.update(detection(), self.frame)
        self.assertEqual(tracker.update(self.empty, self.frame), [])

    def test_track_expiry_still_runs_while_predicting(self):
        tracker = BoTSORT(options(track_buffer=2), frame_rate=30)
        tid = tracker.update(detection(), self.frame)[0].track_id
        self.assertEqual(len(tracker.update(self.empty, self.frame)), 1)
        self.assertEqual(len(tracker.update(self.empty, self.frame)), 1)
        self.assertEqual(tracker.update(self.empty, self.frame), [])
        self.assertEqual(tracker.lost_stracks, [])
        new = tracker.update(detection(), self.frame)[0]
        self.assertNotEqual(new.track_id, tid)

    def test_predictions_do_not_extract_or_update_appearance(self):
        with patch('tracker.bot_sort.FastReIDInterface') as encoder:
            encoder.return_value.inference.return_value = np.array([[1., 0., 0.]])
            tracker = BoTSORT(options(with_reid=True, fast_reid_config='',
                                     fast_reid_weights='', device='cpu'), frame_rate=20)
            track = tracker.update(detection(), self.frame)[0]
            feature = track.smooth_feat.copy()
            encoder.return_value.inference.reset_mock()
            for _ in range(5):
                tracker.update(self.empty, self.frame)
            # Empty batches never need an appearance encoder.
            encoder.return_value.inference.assert_not_called()
            np.testing.assert_array_equal(track.smooth_feat, feature)
            self.assertEqual(len(track.features), 1)

    def test_demo_updates_empty_frames_and_marks_saved_predictions(self):
        args = options()
        tracker = BoTSORT(args, frame_rate=20)
        info = dict(raw_img=self.frame, ratio=1.)
        results, predictions = [], []
        output = torch.tensor([[60., 80., 100., 180., 0.95, 1., 0.]])
        _, ids = track_frame([output], info, tracker, args, 0, results, predictions)
        for frame_id in range(1, 6):
            _, predicted_ids = track_frame(
                [None], info, tracker, args, frame_id, results, predictions)
            self.assertEqual(ids, predicted_ids)
        self.assertEqual(tracker.frame_id, 6)
        self.assertEqual(len(predictions), 5)
        self.assertEqual(float(results[-1].split(',')[6]), -1.)
        record = json.loads(predictions[-1])
        self.assertTrue(record['is_prediction'])
        self.assertEqual(record['missed_frames'], 5)
        self.assertIsNone(record['confidence'])
        boxes, ids = track_frame([None], info, tracker, args, 6, results, predictions)
        self.assertEqual((boxes, ids), ([], []))
        self.assertEqual(len(predictions), 5)

    def test_prediction_uses_same_solid_box_and_label_as_detection(self):
        args = options()
        tracker = BoTSORT(args, frame_rate=20)
        info = dict(raw_img=self.frame, ratio=1.)
        results, predictions = [], []
        output = torch.tensor([[60., 80., 100., 180., 0.95, 1., 0.]])
        boxes, ids = track_frame([output], info, tracker, args, 0, results, predictions)
        detected = plot_tracking(self.frame, boxes, ids)
        boxes, ids = track_frame([None], info, tracker, args, 1, results, predictions)
        predicted = plot_tracking(self.frame, boxes, ids)
        np.testing.assert_array_equal(predicted, detected)
        self.assertEqual(tuple(predicted[92, 60]), get_color(ids[0]))
        self.assertEqual(tuple(predicted[84, 60]), get_color(ids[0]))

    def test_lost_small_target_recovers_from_low_score_detection(self):
        tracker = BoTSORT(options(recover_lost=True), frame_rate=20)
        tid = tracker.update(detection(width=16, height=40), self.frame)[0].track_id
        for _ in range(10):
            tracker.update(self.empty, self.frame)
        tracks = tracker.update(detection(width=16, height=40, score=0.35), self.frame)
        self.assertEqual([track.track_id for track in tracks], [tid])
        self.assertFalse(tracks[0].is_prediction)
        self.assertEqual(tracker.lost_stracks, [])

    def test_small_target_recovers_despite_low_iou_before_creating_new_id(self):
        tracker = BoTSORT(options(recover_lost=True), frame_rate=20)
        tid = tracker.update(detection(width=16, height=40), self.frame)[0].track_id
        tracker.update(self.empty, self.frame)
        tracks = tracker.update(detection(72, width=16, height=40), self.frame)
        self.assertEqual([track.track_id for track in tracks], [tid])
        self.assertFalse(tracks[0].is_prediction)

    def test_recovery_rejects_far_or_different_size_low_score_boxes(self):
        for box in (detection(200, width=16, height=40, score=0.35),
                    detection(60, width=64, height=160, score=0.35)):
            with self.subTest(box=box):
                tracker = BoTSORT(options(recover_lost=True, prediction_max_age=0), frame_rate=20)
                tracker.update(detection(width=16, height=40), self.frame)
                tracker.update(self.empty, self.frame)
                self.assertEqual(tracker.update(box, self.frame), [])
                self.assertEqual(len(tracker.lost_stracks), 1)

    def test_recovery_does_not_choose_between_two_equally_close_lost_people(self):
        tracker = BoTSORT(options(recover_lost=True, prediction_max_age=0), frame_rate=20)
        tracker.update(np.vstack([detection(60, width=16, height=40),
                                  detection(84, width=16, height=40)]), self.frame)
        tracker.update(self.empty, self.frame)
        tracks = tracker.update(detection(72, width=16, height=40, score=0.35), self.frame)
        self.assertEqual(tracks, [])
        self.assertEqual(len(tracker.lost_stracks), 2)

    def test_recovery_does_not_reuse_expired_identity(self):
        tracker = BoTSORT(options(recover_lost=True, track_buffer=2), frame_rate=30)
        tid = tracker.update(detection(), self.frame)[0].track_id
        tracker.update(self.empty, self.frame)
        tracker.update(self.empty, self.frame)
        tracks = tracker.update(detection(), self.frame)
        self.assertEqual(len(tracks), 1)
        self.assertNotEqual(tracks[0].track_id, tid)

    def test_low_score_detection_cannot_create_identity(self):
        tracker = BoTSORT(options(recover_lost=True), frame_rate=20)
        self.assertEqual(tracker.update(detection(score=0.35), self.frame), [])
        self.assertEqual(tracker.tracked_stracks, [])

    def test_immediate_low_score_recovery_does_not_duplicate_track_lists(self):
        tracker = BoTSORT(options(recover_lost=True), frame_rate=20)
        tid = tracker.update(detection(width=16, height=40), self.frame)[0].track_id
        tracks = tracker.update(detection(66, width=16, height=40, score=0.35), self.frame)
        self.assertEqual([track.track_id for track in tracks], [tid])
        self.assertFalse(tracks[0].is_prediction)
        self.assertEqual(tracker.lost_stracks, [])
        self.assertEqual(len(tracker.update(self.empty, self.frame)), 1)

    def test_recovery_preserves_priority_of_active_person(self):
        tracker = BoTSORT(options(recover_lost=True), frame_rate=20)
        tracks = tracker.update(np.vstack([detection(60, width=16, height=40),
                                          detection(100, width=16, height=40)]), self.frame)
        lost_id, active_id = [track.track_id for track in tracks]
        tracker.update(detection(100, width=16, height=40), self.frame)
        tracks = tracker.update(detection(100, width=16, height=40, score=0.35), self.frame)
        self.assertEqual({track.track_id: track.is_prediction for track in tracks},
                         {active_id: False, lost_id: True})

    def test_recovery_rejects_one_track_with_two_equally_close_detections(self):
        tracker = BoTSORT(options(recover_lost=True, prediction_max_age=0), frame_rate=20)
        tracker.update(detection(width=16, height=40), self.frame)
        tracker.update(self.empty, self.frame)
        boxes = np.vstack([detection(48, width=16, height=40, score=0.35),
                           detection(72, width=16, height=40, score=0.35)])
        self.assertEqual(tracker.update(boxes, self.frame), [])
        self.assertEqual(len(tracker.lost_stracks), 1)

    def test_recovery_uses_reliable_reid_without_refreshing_appearance(self):
        for feature in ([1., 0., 0.], [-1., 0., 0.]):
            with self.subTest(feature=feature), patch('tracker.bot_sort.FastReIDInterface') as encoder:
                encoder.return_value.inference.return_value = np.array([[1., 0., 0.]])
                tracker = BoTSORT(options(recover_lost=True, prediction_max_age=0,
                                         with_reid=True, fast_reid_config='',
                                         fast_reid_weights='', device='cpu'), frame_rate=20)
                original = tracker.update(detection(), self.frame)[0]
                for _ in range(10):
                    tracker.update(self.empty, self.frame)
                encoder.return_value.inference.return_value = np.array([feature])
                tracks = tracker.update(detection(100), self.frame)
                self.assertEqual(len(tracks), 1)
                if feature[0] > 0:
                    self.assertEqual(tracks[0].track_id, original.track_id)
                    self.assertFalse(tracks[0].is_prediction)
                else:
                    self.assertNotEqual(tracks[0].track_id, original.track_id)
                self.assertEqual(len(original.features), 1)
                np.testing.assert_array_equal(original.smooth_feat, [1., 0., 0.])

    def test_recovery_does_not_trust_small_target_reid(self):
        with patch('tracker.bot_sort.FastReIDInterface') as encoder:
            encoder.return_value.inference.return_value = np.array([[1., 0., 0.]])
            tracker = BoTSORT(options(recover_lost=True, with_reid=True, fast_reid_config='',
                                     fast_reid_weights='', device='cpu'), frame_rate=20)
            original = tracker.update(detection(width=16, height=40), self.frame)[0]
            tracker.update(self.empty, self.frame)
            encoder.return_value.inference.return_value = np.array([[-1., 0., 0.]])
            tracks = tracker.update(detection(72, width=16, height=40), self.frame)
            self.assertEqual([track.track_id for track in tracks], [original.track_id])
            np.testing.assert_array_equal(original.smooth_feat, [1., 0., 0.])

    def test_demo_recovery_settings_keep_four_second_buffer(self):
        args = make_parser().parse_args(['video', '--fps', '20', '--recover-lost'])
        self.assertTrue(args.recover_lost)
        self.assertTrue(args.crossing_guard)
        self.assertFalse(make_parser().parse_args(['video', '--no-crossing-guard']).crossing_guard)
        self.assertEqual(args.prediction_max_age, 5)
        self.assertEqual(int(args.fps / 30.0 * args.track_buffer), 80)


class CrossingTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((300, 400, 3), dtype=np.uint8)
        self.empty = np.empty((0, 5), dtype=np.float32)
        encoder_patch = patch('tracker.bot_sort.FastReIDInterface')
        self.encoder = encoder_patch.start().return_value
        self.addCleanup(encoder_patch.stop)
        self.tracker = BoTSORT(options(recover_lost=True, with_reid=True,
                                      fast_reid_config='', fast_reid_weights='', device='cpu'), frame_rate=20)

    def step(self, boxes, features):
        self.encoder.inference.return_value = np.array(features, dtype=np.float32)
        return self.tracker.update(boxes, self.frame)

    def warm_up(self):
        for frame in range(7):
            tracks = self.step(np.vstack([detection(40 + 12 * frame), detection(200 - 12 * frame)]),
                               [[1., 0., 0.], [0., 1., 0.]])
        return {track.track_id: track for track in tracks}

    def test_ambiguous_overlap_does_not_correct_motion_or_pollute_appearance(self):
        original = self.warm_up()
        expected = {tid: track.kalman_filter.predict(track.mean, track.covariance)[0]
                    for tid, track in original.items()}
        feature_counts = {tid: len(track.features) for tid, track in original.items()}
        tracks = self.step(np.vstack([detection(120), detection(120)]), [[1., 1., 0.], [1., 1., 0.]])
        self.assertEqual({track.track_id for track in tracks}, set(original))
        for track in tracks:
            self.assertTrue(track.crossing)
            self.assertTrue(track.is_prediction)
            np.testing.assert_allclose(track.mean, expected[track.track_id])
            self.assertEqual(len(track.features), feature_counts[track.track_id])
        np.testing.assert_array_equal(original[1].smooth_feat, [1., 0., 0.])
        np.testing.assert_array_equal(original[2].smooth_feat, [0., 1., 0.])

    def test_separation_restores_identity_and_later_resumes_feature_updates(self):
        original = self.warm_up()
        feature_counts = {tid: len(track.features) for tid, track in original.items()}
        self.step(np.vstack([detection(120), detection(120)]), [[1., 1., 0.], [1., 1., 0.]])
        for frame, (left, right) in enumerate(((104, 136), (92, 148), (80, 160)), 1):
            # Reverse detector order after crossing: ID 1 must follow the right-hand person.
            tracks = self.step(np.vstack([detection(left), detection(right)]), [[0., 1., 0.], [1., 0., 0.]])
            by_id = {track.track_id: track for track in tracks}
            self.assertEqual(set(by_id), set(original))
            self.assertFalse(any(track.is_prediction for track in tracks))
            self.assertGreater(by_id[1].tlwh[0], by_id[2].tlwh[0])
            if frame <= 2:
                self.assertEqual(len(by_id[1].features), feature_counts[1])
            else:
                self.assertFalse(by_id[1].crossing)
                self.assertGreater(len(by_id[1].features), feature_counts[1])

    def test_confident_overlapping_position_updates_still_freeze_features(self):
        tracks = self.step(np.vstack([detection(80), detection(90)]), [[1., 0., 0.], [0., 1., 0.]])
        tracks = self.step(np.vstack([detection(80), detection(90)]), [[1., 1., 0.], [1., 1., 0.]])
        self.assertEqual(len(tracks), 2)
        self.assertFalse(any(track.is_prediction for track in tracks))
        for track in tracks:
            self.assertTrue(track.crossing)
            self.assertEqual(len(track.features), 1)
        np.testing.assert_array_equal(tracks[0].smooth_feat, [1., 0., 0.])
        np.testing.assert_array_equal(tracks[1].smooth_feat, [0., 1., 0.])

    def test_merged_high_score_box_does_not_create_or_replace_identity(self):
        self.step(np.vstack([detection(80), detection(84)]), [[1., 0., 0.], [0., 1., 0.]])
        for age in range(1, 8):
            tracks = self.step(detection(82), [[1., 1., 0.]])
            self.assertEqual({track.track_id for track in self.tracker.lost_stracks}, {1, 2})
            self.assertEqual(self.tracker.tracked_stracks, [])
            self.assertEqual(len(tracks), 2 if age <= 5 else 0)
            self.assertTrue(all(track.is_prediction for track in tracks))

    def test_merged_low_score_box_cannot_bypass_guard_through_recovery(self):
        self.step(np.vstack([detection(80), detection(84)]), [[1., 0., 0.], [0., 1., 0.]])
        tracks = self.step(detection(82, score=0.35), [])
        self.assertEqual({track.track_id for track in tracks}, {1, 2})
        self.assertTrue(all(track.is_prediction for track in tracks))
        self.assertEqual(len(self.tracker.lost_stracks), 2)

    def test_low_score_association_considers_crossing_partner_already_lost(self):
        self.step(np.vstack([detection(80), detection(90)]), [[1., 0., 0.], [0., 1., 0.]])
        tracks = self.step(detection(80), [[1., 1., 0.]])
        self.assertEqual({track.track_id: track.is_prediction for track in tracks}, {1: False, 2: True})
        tracks = self.step(detection(85, score=0.35), [])
        self.assertEqual({track.track_id for track in tracks}, {1, 2})
        self.assertTrue(all(track.is_prediction for track in tracks))

    def test_unconfirmed_track_cannot_consume_ambiguous_crossing_box(self):
        self.step(np.vstack([detection(80), detection(84)]), [[1., 0., 0.], [0., 1., 0.]])
        unconfirmed = STrack([82, 80, 40, 100], 0.95, np.array([1., 0., 0.]))
        unconfirmed.activate(self.tracker.kalman_filter, frame_id=2)
        self.tracker.tracked_stracks.append(unconfirmed)
        tracks = self.step(detection(82), [[1., 1., 0.]])
        self.assertEqual({track.track_id for track in tracks}, {1, 2})
        self.assertTrue(all(track.is_prediction for track in tracks))
        self.assertIn(unconfirmed, self.tracker.removed_stracks)

    def test_coverage_detects_small_person_inside_larger_box(self):
        boxes = np.vstack([detection(80), detection(88, width=16, height=40)])
        self.step(boxes, [[1., 0., 0.], [0., 1., 0.]])
        tracks = self.step(boxes, [[1., 1., 0.], [1., 1., 0.]])
        self.assertEqual({track.track_id for track in tracks}, {1, 2})
        self.assertTrue(all(track.crossing for track in tracks))
        self.assertFalse(any(track.is_prediction for track in tracks))

    def test_crossing_tracks_are_not_removed_as_duplicates(self):
        tracks = self.step(np.vstack([detection(80), detection(82)]), [[1., 0., 0.], [0., 1., 0.]])
        tracks[0].crossing = tracks[1].crossing = True
        tracks[1].mark_lost()
        active, lost = remove_duplicate_stracks([tracks[0]], [tracks[1]])
        self.assertEqual(active, [tracks[0]])
        self.assertEqual(lost, [tracks[1]])

    def test_isolated_small_target_is_not_marked_crossing_by_duplicate_detections(self):
        self.step(detection(width=16, height=40), [[1., 0., 0.]])
        tracks = self.step(np.vstack([detection(width=16, height=40), detection(64, width=16, height=40)]),
                           [[1., 0., 0.], [1., 0., 0.]])
        original = next(track for track in tracks if track.track_id == 1)
        self.assertFalse(original.crossing)
        self.assertFalse(original.is_prediction)

    def test_unrelated_small_target_recovery_is_identical_with_guard_on_or_off(self):
        traces = []
        for enabled in (False, True):
            tracker = BoTSORT(options(recover_lost=True, crossing_guard=enabled), frame_rate=20)
            tracks = tracker.update(np.vstack([detection(80), detection(84),
                                              detection(280, width=16, height=40)]), self.frame)
            small_id = tracks[2].track_id
            trace = []
            frames = [np.vstack([detection(82), detection(280, width=16, height=40, score=0.35)])]
            frames += [detection(82) for _ in range(10)]
            frames += [np.vstack([detection(82), detection(292, width=16, height=40, score=0.35)])]
            for boxes in frames:
                tracks = tracker.update(boxes, self.frame)
                small = [track for track in tracks if track.track_id == small_id]
                trace.append([(track.track_id, track.is_prediction, track.missed_frames, track.tlwh.tolist())
                              for track in small])
            self.assertTrue(trace[-1])
            self.assertFalse(trace[-1][0][1])
            traces.append(trace)
        self.assertEqual(traces[0], traces[1])


if __name__ == '__main__':
    unittest.main()
