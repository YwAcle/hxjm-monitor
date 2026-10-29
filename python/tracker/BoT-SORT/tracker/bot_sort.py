import cv2
import matplotlib.pyplot as plt
import numpy as np
from collections import deque

from tracker import matching
from tracker.gmc import GMC
from tracker.basetrack import BaseTrack, TrackState
from tracker.kalman_filter import KalmanFilter, chi2inv95

from fast_reid.fast_reid_interfece import FastReIDInterface


class STrack(BaseTrack):
    shared_kalman = KalmanFilter()

    def __init__(self, tlwh, score, feat=None, feat_history=50):

        # wait activate
        self._tlwh = np.asarray(tlwh, dtype=np.float)
        self.kalman_filter = None
        self.mean, self.covariance = None, None
        self.is_activated = False

        self.score = score
        self.tracklet_len = 0
        self.is_prediction = False
        self.missed_frames = 0
        self.crossing = False
        self.crossing_clear_frames = 0
        self.occluded = False

        self.smooth_feat = None
        self.curr_feat = None
        self.features = deque([], maxlen=feat_history)
        self.alpha = 0.9
        if feat is not None:
            self.update_features(feat)

    def update_features(self, feat):
        feat /= np.linalg.norm(feat)
        self.curr_feat = feat
        if self.smooth_feat is None:
            self.smooth_feat = feat
        else:
            self.smooth_feat = self.alpha * self.smooth_feat + (1 - self.alpha) * feat
        self.features.append(feat)
        self.smooth_feat /= np.linalg.norm(self.smooth_feat)

    def predict(self):
        mean_state = self.mean.copy()
        if self.state != TrackState.Tracked:
            mean_state[6] = 0
            mean_state[7] = 0

        self.mean, self.covariance = self.kalman_filter.predict(mean_state, self.covariance)

    @staticmethod
    def multi_predict(stracks, dt=1.):
        if len(stracks) > 0:
            multi_mean = np.asarray([st.mean.copy() for st in stracks])
            multi_covariance = np.asarray([st.covariance for st in stracks])
            for i, st in enumerate(stracks):
                if st.state != TrackState.Tracked:
                    multi_mean[i][6] = 0
                    multi_mean[i][7] = 0
            multi_mean, multi_covariance = STrack.shared_kalman.multi_predict(multi_mean, multi_covariance, dt=dt)
            for i, (mean, cov) in enumerate(zip(multi_mean, multi_covariance)):
                stracks[i].mean = mean
                stracks[i].covariance = cov

    @staticmethod
    def multi_gmc(stracks, H=np.eye(2, 3)):
        if len(stracks) > 0:
            multi_mean = np.asarray([st.mean.copy() for st in stracks])
            multi_covariance = np.asarray([st.covariance for st in stracks])

            R = H[:2, :2]
            R8x8 = np.kron(np.eye(4, dtype=float), R)
            t = H[:2, 2]

            for i, (mean, cov) in enumerate(zip(multi_mean, multi_covariance)):
                mean = R8x8.dot(mean)
                mean[:2] += t
                cov = R8x8.dot(cov).dot(R8x8.transpose())

                stracks[i].mean = mean
                stracks[i].covariance = cov

    def activate(self, kalman_filter, frame_id):
        """Start a new tracklet"""
        self.kalman_filter = kalman_filter
        self.track_id = self.next_id()

        self.mean, self.covariance = self.kalman_filter.initiate(self.tlwh_to_xywh(self._tlwh))

        self.tracklet_len = 0
        self.state = TrackState.Tracked
        if frame_id == 1:
            self.is_activated = True
        self.frame_id = frame_id
        self.start_frame = frame_id

    def re_activate(self, new_track, frame_id, new_id=False, update_feature=True):

        self.mean, self.covariance = self.kalman_filter.update(self.mean, self.covariance, self.tlwh_to_xywh(new_track.tlwh))
        if update_feature and new_track.curr_feat is not None:
            self.update_features(new_track.curr_feat)
        self.tracklet_len = 0
        self.state = TrackState.Tracked
        self.is_activated = True
        self.frame_id = frame_id
        if new_id:
            self.track_id = self.next_id()
        self.score = new_track.score

    def update(self, new_track, frame_id, update_feature=True):
        """
        Update a matched track
        :type new_track: STrack
        :type frame_id: int
        :type update_feature: bool
        :return:
        """
        self.frame_id = frame_id
        self.tracklet_len += 1

        new_tlwh = new_track.tlwh

        self.mean, self.covariance = self.kalman_filter.update(self.mean, self.covariance, self.tlwh_to_xywh(new_tlwh))

        if update_feature and new_track.curr_feat is not None:
            self.update_features(new_track.curr_feat)

        self.state = TrackState.Tracked
        self.is_activated = True

        self.score = new_track.score

    @property
    def tlwh(self):
        """Get current position in bounding box format `(top left x, top left y,
                width, height)`.
        """
        if self.mean is None:
            return self._tlwh.copy()
        ret = self.mean[:4].copy()
        ret[:2] -= ret[2:] / 2
        return ret

    @property
    def tlbr(self):
        """Convert bounding box to format `(min x, min y, max x, max y)`, i.e.,
        `(top left, bottom right)`.
        """
        ret = self.tlwh.copy()
        ret[2:] += ret[:2]
        return ret

    @property
    def xywh(self):
        """Convert bounding box to format `(min x, min y, max x, max y)`, i.e.,
        `(top left, bottom right)`.
        """
        ret = self.tlwh.copy()
        ret[:2] += ret[2:] / 2.0
        return ret

    @staticmethod
    def tlwh_to_xyah(tlwh):
        """Convert bounding box to format `(center x, center y, aspect ratio,
        height)`, where the aspect ratio is `width / height`.
        """
        ret = np.asarray(tlwh).copy()
        ret[:2] += ret[2:] / 2
        ret[2] /= ret[3]
        return ret

    @staticmethod
    def tlwh_to_xywh(tlwh):
        """Convert bounding box to format `(center x, center y, width,
        height)`.
        """
        ret = np.asarray(tlwh).copy()
        ret[:2] += ret[2:] / 2
        return ret

    def to_xywh(self):
        return self.tlwh_to_xywh(self.tlwh)

    @staticmethod
    def tlbr_to_tlwh(tlbr):
        ret = np.asarray(tlbr).copy()
        ret[2:] -= ret[:2]
        return ret

    @staticmethod
    def tlwh_to_tlbr(tlwh):
        ret = np.asarray(tlwh).copy()
        ret[2:] += ret[:2]
        return ret

    def __repr__(self):
        return 'OT_{}_({}-{})'.format(self.track_id, self.start_frame, self.end_frame)


class BoTSORT(object):
    def __init__(self, args, frame_rate=30, encoder=None, reset_id=True):

        self.tracked_stracks = []  # type: list[STrack]
        self.lost_stracks = []  # type: list[STrack]
        self.removed_stracks = []  # type: list[STrack]
        if reset_id:
            BaseTrack.clear_count()

        self.frame_id = 0
        self.frame_rate = frame_rate
        self.timestamp_ms = None
        self.time_frames = 0.
        self.args = args

        self.track_high_thresh = args.track_high_thresh
        self.track_low_thresh = args.track_low_thresh
        self.new_track_thresh = args.new_track_thresh

        self.buffer_size = int(frame_rate / 30.0 * args.track_buffer)
        self.max_time_lost = self.buffer_size
        self.prediction_max_age = getattr(args, 'prediction_max_age', 0)
        if self.prediction_max_age < 0:
            raise ValueError('prediction_max_age must be non-negative')
        self.recover_lost = getattr(args, 'recover_lost', False)
        self.crossing_guard = getattr(args, 'crossing_guard', False)
        self.kalman_filter = KalmanFilter()

        # ReID module
        self.proximity_thresh = args.proximity_thresh
        self.appearance_thresh = args.appearance_thresh

        if args.with_reid:
            self.encoder = encoder if encoder is not None else FastReIDInterface(args.fast_reid_config, args.fast_reid_weights, args.device)

        self.gmc = GMC(method=args.cmc_method, verbose=[args.name, args.ablation])

    @staticmethod
    def _high_overlap(tracks, others):
        if not tracks or not others:
            return np.zeros((len(tracks), len(others)), dtype=bool)
        a = np.asarray([track.tlbr for track in tracks])
        b = np.asarray([track.tlbr for track in others])
        intersection = np.maximum(0., np.minimum(a[:, None, 2:], b[None, :, 2:])
                                  - np.maximum(a[:, None, :2], b[None, :, :2])).prod(axis=2)
        area_a = np.maximum(0., a[:, 2:] - a[:, :2]).prod(axis=1)[:, None]
        area_b = np.maximum(0., b[:, 2:] - b[:, :2]).prod(axis=1)[None, :]
        iou = intersection / np.maximum(area_a + area_b - intersection, 1e-6)
        coverage = intersection / np.maximum(np.minimum(area_a, area_b), 1e-6)
        return (iou >= 0.6) | (coverage >= 0.7)

    def _mark_crossings(self, tracks, detections):
        confirmed = [track for track in tracks if track.is_activated]
        if len(confirmed) < 2:
            return
        overlap = self._high_overlap(confirmed, confirmed)
        np.fill_diagonal(overlap, False)
        involved = overlap.any(axis=1)
        detection_overlap = self._high_overlap(detections, detections)
        np.fill_diagonal(detection_overlap, False)
        iou_distance = matching.iou_distance(confirmed, detections)
        # Detection overlap alone must not put an isolated small target into crossing mode.
        for first, second in np.argwhere(np.triu(detection_overlap, 1)):
            nearby = iou_distance[:, [first, second]].min(axis=1) < 0.8
            if nearby.sum() >= 2:
                involved |= nearby
        coverage = self._high_overlap(confirmed, detections)
        merged = coverage.sum(axis=0) >= 2
        if merged.any():
            involved |= coverage[:, merged].any(axis=1)
        for track, crossing in zip(confirmed, involved):
            if crossing:
                track.crossing = True
                track.crossing_clear_frames = 0
        protected = np.asarray([track.crossing for track in confirmed])
        for col, det in enumerate(detections):
            det.occluded = bool(merged[col] or (detection_overlap[col].any()
                                and np.any(protected & (iou_distance[:, col] < 0.8))))

    def _crossing_costs(self, costs, tracks, detections):
        if not self.crossing_guard or not tracks or not detections:
            return costs
        costs = costs.copy()
        measurements = np.asarray([det.to_xywh() for det in detections])
        for row, track in enumerate(tracks):
            if not track.crossing:
                continue
            position, covariance = self.kalman_filter.project(track.mean, track.covariance)
            delta = measurements[:, :2] - position[:2]
            covariance = covariance[:2, :2] + np.eye(2) * 16.0
            motion = np.sum(delta * np.linalg.solve(covariance, delta.T).T, axis=1)
            costs[row] = np.inf
            for col, det in enumerate(detections):
                sizes = np.asarray([position[2:4], measurements[col, 2:4]])
                if not np.isfinite(sizes).all() or np.any(sizes <= 0):
                    continue
                ratio = np.max(np.maximum(sizes[0] / sizes[1], sizes[1] / sizes[0]))
                center = np.linalg.norm(delta[col] / np.maximum(sizes.mean(axis=0), (8., 16.)))
                if not np.isfinite(motion[col]) or motion[col] > chi2inv95[2] or ratio > 2.0:
                    continue
                cost = 0.5 * center / 1.5 + 0.5 * motion[col] / chi2inv95[2]
                reliable = (self.args.with_reid and not det.occluded and det.score > self.track_high_thresh
                            and np.all(sizes[:, 0] >= 24) and np.all(sizes[:, 1] >= 64)
                            and track.smooth_feat is not None and det.curr_feat is not None)
                if reliable:
                    norm = np.linalg.norm(track.smooth_feat) * np.linalg.norm(det.curr_feat)
                    if not np.isfinite(norm) or norm <= 0:
                        continue
                    appearance = (1. - np.clip(np.dot(track.smooth_feat, det.curr_feat) / norm, -1., 1.)) / 2.
                    if appearance > self.appearance_thresh or center > 1.5:
                        continue
                    cost = 0.6 * appearance / max(self.appearance_thresh, 1e-6) + 0.4 * cost
                elif center > 1.0:
                    continue
                if np.isfinite(cost):
                    costs[row, col] = cost
        return costs

    def _associate(self, costs, tracks, detections, threshold, rivals=()):
        costs = self._crossing_costs(costs, tracks, detections)
        matches, unmatched_tracks, unmatched_detections = matching.linear_assignment(costs, thresh=threshold)
        if not self.crossing_guard:
            return matches, unmatched_tracks, unmatched_detections
        # Low-score association must still consider a crossing partner already in Lost state.
        rival_tracks = [track for track in rivals if track not in tracks and track.crossing
                        and track.is_activated and track.frame_id != self.frame_id]
        rival_costs = self._crossing_costs(np.full((len(rival_tracks), len(detections)), np.inf),
                                         rival_tracks, detections)
        accepted = []
        for row, col in matches:
            if tracks[row].crossing:
                alternatives = np.r_[np.delete(costs[row], col), np.delete(costs[:, col], row),
                                     rival_costs[:, col]]
                alternatives = alternatives[alternatives <= threshold]
                if alternatives.size and alternatives.min() < costs[row, col] + 0.1:
                    continue
            accepted.append((row, col))
        return (np.asarray(accepted, dtype=int).reshape(-1, 2),
                tuple(sorted(set(range(len(tracks))) - {row for row, _ in accepted})),
                tuple(sorted(set(range(len(detections))) - {col for _, col in accepted})))

    def _crossing_birth_blocked(self, det, tracks):
        if not self.crossing_guard:
            return False
        for track in tracks:
            if track.crossing and track.is_activated:
                size = np.maximum((track.tlwh[2:] + det.tlwh[2:]) / 2., (8., 16.))
                if np.linalg.norm((track.xywh[:2] - det.xywh[:2]) / size) <= 1.5:
                    return True
        return False

    def _clear_crossing(self, track, det):
        if track.crossing:
            track.crossing_clear_frames = (track.crossing_clear_frames + 1
                                           if not det.occluded and det.score > self.track_high_thresh else 0)
            if track.crossing_clear_frames >= 2:
                track.crossing = False

    def _recovery_matches(self, tracks, detections):
        costs = np.full((len(tracks), len(detections)), np.inf)
        if not tracks or not detections:
            return []
        measurements = np.asarray([det.to_xywh() for det in detections])
        for row, track in enumerate(tracks):
            position, covariance = self.kalman_filter.project(track.mean, track.covariance)
            # A four-pixel noise floor accommodates small-box detector jitter.
            delta = measurements[:, :2] - position[:2]
            position_covariance = covariance[:2, :2] + np.eye(2) * 16.0
            motion_distance = np.sum(delta * np.linalg.solve(position_covariance, delta.T).T, axis=1)
            for col, det in enumerate(detections):
                sizes = np.asarray([position[2:4], measurements[col, 2:4]])
                if not np.isfinite(sizes).all() or np.any(sizes <= 0):
                    continue
                size_ratio = np.max(np.maximum(sizes[0] / sizes[1], sizes[1] / sizes[0]))
                center_distance = np.linalg.norm(delta[col] / np.maximum(sizes.mean(axis=0), (8., 16.)))
                if (not np.isfinite(motion_distance[col]) or motion_distance[col] > chi2inv95[2]
                        or size_ratio > 2.0):
                    continue
                cost = 0.7 * center_distance + 0.3 * (size_ratio - 1.0)
                reliable_appearance = (self.args.with_reid and det.score > self.track_high_thresh
                                       and np.all(sizes[:, 0] >= 24) and np.all(sizes[:, 1] >= 64)
                                       and track.smooth_feat is not None and det.curr_feat is not None)
                if reliable_appearance:
                    feature_norm = np.linalg.norm(track.smooth_feat) * np.linalg.norm(det.curr_feat)
                    if not np.isfinite(feature_norm) or feature_norm <= 0:
                        continue
                    appearance = (1.0 - np.clip(np.dot(track.smooth_feat, det.curr_feat) / feature_norm, -1., 1.)) / 2.0
                    if appearance > self.appearance_thresh or center_distance > 1.5:
                        continue
                    cost = 0.7 * cost + 0.3 * appearance / max(self.appearance_thresh, 1e-6)
                elif center_distance > 1.0:
                    continue
                if np.isfinite(cost) and cost <= 0.65:
                    costs[row, col] = cost
        costs = self._crossing_costs(costs, tracks, detections)
        matches, _, _ = matching.linear_assignment(costs, thresh=0.65)
        recovered = []
        for row, col in matches:
            alternatives = np.r_[np.delete(costs[row], col), np.delete(costs[:, col], row)]
            # Ambiguous candidates stay unmatched rather than borrowing another person's ID.
            if alternatives.size and alternatives.min() < costs[row, col] + 0.1:
                continue
            recovered.append((row, col))
        return recovered

    def _age(self, track):
        if self.timestamp_ms is not None:
            return self.time_frames - track.observed_time_frames
        return self.frame_id - track.end_frame

    def update(self, output_results, img, timestamp_ms=None):
        dt = 1.
        if timestamp_ms is not None:
            if not np.isfinite(timestamp_ms) or (self.timestamp_ms is not None and timestamp_ms <= self.timestamp_ms):
                raise ValueError('Tracking timestamps must be finite and strictly increasing')
            if self.timestamp_ms is not None:
                dt = (timestamp_ms - self.timestamp_ms) * self.frame_rate / 1000.
            self.timestamp_ms = timestamp_ms
        self.time_frames += dt
        self.frame_id += 1
        activated_starcks = []
        refind_stracks = []
        lost_stracks = []
        removed_stracks = []

        # Expire before association so an overdue trajectory cannot be reactivated.
        for track in self.lost_stracks:
            if self._age(track) > self.max_time_lost:
                track.mark_removed()
                removed_stracks.append(track)
        self.lost_stracks = sub_stracks(self.lost_stracks, removed_stracks)
        if timestamp_ms is not None:
            for track in self.tracked_stracks:
                if self._age(track) > self.max_time_lost:
                    track.mark_removed()
                    removed_stracks.append(track)
            self.tracked_stracks = sub_stracks(self.tracked_stracks, removed_stracks)

        if len(output_results):
            if output_results.shape[1] == 5:
                scores = output_results[:, 4]
                bboxes = output_results[:, :4]
                classes = output_results[:, -1]
            else:
                scores = output_results[:, 4] * output_results[:, 5]
                bboxes = output_results[:, :4]  # x1y1x2y2
                classes = output_results[:, -1]

            # Remove bad detections
            lowest_inds = scores > self.track_low_thresh
            bboxes = bboxes[lowest_inds]
            scores = scores[lowest_inds]
            classes = classes[lowest_inds]

            # Find high threshold detections
            remain_inds = scores > self.args.track_high_thresh
            dets = bboxes[remain_inds]
            scores_keep = scores[remain_inds]
            classes_keep = classes[remain_inds]

        else:
            bboxes = []
            scores = []
            classes = []
            dets = []
            scores_keep = []
            classes_keep = []

        '''Extract embeddings '''
        if self.args.with_reid and len(dets) > 0:
            features_keep = self.encoder.inference(img, dets)

        if len(dets) > 0:
            '''Detections'''
            if self.args.with_reid:
                detections = [STrack(STrack.tlbr_to_tlwh(tlbr), s, f) for
                              (tlbr, s, f) in zip(dets, scores_keep, features_keep)]
            else:
                detections = [STrack(STrack.tlbr_to_tlwh(tlbr), s) for
                              (tlbr, s) in zip(dets, scores_keep)]
        else:
            detections = []

        if len(scores):
            inds_second = (scores <= self.track_high_thresh) & (scores > self.track_low_thresh)
            detections_second = [STrack(STrack.tlbr_to_tlwh(box), score)
                                 for box, score in zip(bboxes[inds_second], scores[inds_second])]
        else:
            detections_second = []

        ''' Add newly detected tracklets to tracked_stracks'''
        unconfirmed = []
        tracked_stracks = []  # type: list[STrack]
        for track in self.tracked_stracks:
            if not track.is_activated:
                unconfirmed.append(track)
            else:
                tracked_stracks.append(track)

        ''' Step 2: First association, with high score detection boxes'''
        strack_pool = joint_stracks(tracked_stracks, self.lost_stracks)

        # Predict the current location with KF
        STrack.multi_predict(strack_pool, dt=dt)

        # Fix camera motion
        warp = self.gmc.apply(img, dets)
        STrack.multi_gmc(strack_pool, warp)
        STrack.multi_gmc(unconfirmed, warp)
        if self.crossing_guard:
            self._mark_crossings(strack_pool, detections + detections_second)

        # Associate with high score detection boxes
        ious_dists = matching.iou_distance(strack_pool, detections)
        ious_dists_mask = (ious_dists > self.proximity_thresh)

        if not self.args.mot20:
            ious_dists = matching.fuse_score(ious_dists, detections)

        if self.args.with_reid:
            emb_dists = matching.embedding_distance(strack_pool, detections) / 2.0
            raw_emb_dists = emb_dists.copy()
            emb_dists[emb_dists > self.appearance_thresh] = 1.0
            emb_dists[ious_dists_mask] = 1.0
            dists = np.minimum(ious_dists, emb_dists)

            # Popular ReID method (JDE / FairMOT)
            # raw_emb_dists = matching.embedding_distance(strack_pool, detections)
            # dists = matching.fuse_motion(self.kalman_filter, raw_emb_dists, strack_pool, detections)
            # emb_dists = dists

            # IoU making ReID
            # dists = matching.embedding_distance(strack_pool, detections)
            # dists[ious_dists_mask] = 1.0
        else:
            dists = ious_dists

        matches, u_track, u_detection = self._associate(dists, strack_pool, detections, self.args.match_thresh)

        for itracked, idet in matches:
            track = strack_pool[itracked]
            det = detections[idet]
            update_feature = not (track.crossing or det.occluded)
            if track.state == TrackState.Tracked:
                track.update(det, self.frame_id, update_feature=update_feature)
                activated_starcks.append(track)
            else:
                track.re_activate(det, self.frame_id, new_id=False, update_feature=update_feature)
                refind_stracks.append(track)
            self._clear_crossing(track, det)

        ''' Step 3: Second association, with low score detection boxes'''
        r_tracked_stracks = [strack_pool[i] for i in u_track if strack_pool[i].state == TrackState.Tracked]
        dists = matching.iou_distance(r_tracked_stracks, detections_second)
        matches, u_track, u_detection_second = self._associate(dists, r_tracked_stracks, detections_second,
                                                             0.5, rivals=strack_pool)
        for itracked, idet in matches:
            track = r_tracked_stracks[itracked]
            det = detections_second[idet]
            if track.state == TrackState.Tracked:
                track.update(det, self.frame_id)
                activated_starcks.append(track)
            else:
                track.re_activate(det, self.frame_id, new_id=False)
                refind_stracks.append(track)
            self._clear_crossing(track, det)

        for it in u_track:
            track = r_tracked_stracks[it]
            if not track.state == TrackState.Lost:
                track.mark_lost()
                lost_stracks.append(track)

        '''Deal with unconfirmed tracks, usually tracks with only one beginning frame'''
        detections = [detections[i] for i in u_detection]
        ious_dists = matching.iou_distance(unconfirmed, detections)
        ious_dists_mask = (ious_dists > self.proximity_thresh)
        if not self.args.mot20:
            ious_dists = matching.fuse_score(ious_dists, detections)

        if self.args.with_reid:
            emb_dists = matching.embedding_distance(unconfirmed, detections) / 2.0
            raw_emb_dists = emb_dists.copy()
            emb_dists[emb_dists > self.appearance_thresh] = 1.0
            emb_dists[ious_dists_mask] = 1.0
            dists = np.minimum(ious_dists, emb_dists)
        else:
            dists = ious_dists

        for col, det in enumerate(detections):
            if self._crossing_birth_blocked(det, strack_pool):
                dists[:, col] = np.inf
        matches, u_unconfirmed, u_detection = matching.linear_assignment(dists, thresh=0.7)
        for itracked, idet in matches:
            unconfirmed[itracked].update(detections[idet], self.frame_id)
            activated_starcks.append(unconfirmed[itracked])
        for it in u_unconfirmed:
            track = unconfirmed[it]
            track.mark_removed()
            removed_stracks.append(track)

        if self.recover_lost:
            recovery_tracks = [track for track in joint_stracks(self.lost_stracks, lost_stracks)
                               if track.state == TrackState.Lost and track.is_activated
                               and self._age(track) <= self.max_time_lost]
            remaining_high = list(u_detection)
            recovery_detections = ([detections[i] for i in remaining_high]
                                   + [detections_second[i] for i in u_detection_second])
            recovered_high = set()
            for itracked, idet in self._recovery_matches(recovery_tracks, recovery_detections):
                track = recovery_tracks[itracked]
                # Keep pre-occlusion appearance until a subsequent normal association.
                track.re_activate(recovery_detections[idet], self.frame_id, new_id=False, update_feature=False)
                self._clear_crossing(track, recovery_detections[idet])
                refind_stracks.append(track)
                if idet < len(remaining_high):
                    recovered_high.add(remaining_high[idet])
            u_detection = [i for i in u_detection if i not in recovered_high]

        """ Step 4: Init new stracks"""
        for inew in u_detection:
            track = detections[inew]
            if track.score < self.new_track_thresh or self._crossing_birth_blocked(track, strack_pool):
                continue

            track.activate(self.kalman_filter, self.frame_id)
            activated_starcks.append(track)

        """ Merge """
        self.tracked_stracks = [t for t in self.tracked_stracks if t.state == TrackState.Tracked]
        self.tracked_stracks = joint_stracks(self.tracked_stracks, activated_starcks)
        self.tracked_stracks = joint_stracks(self.tracked_stracks, refind_stracks)
        self.lost_stracks = sub_stracks(self.lost_stracks, self.tracked_stracks)
        self.lost_stracks.extend(track for track in lost_stracks if track.state == TrackState.Lost)
        self.lost_stracks = sub_stracks(self.lost_stracks, removed_stracks)
        # Removed tracks never participate again; bound diagnostic history in long-running services.
        self.removed_stracks = (self.removed_stracks + removed_stracks)[-1000:]
        self.tracked_stracks, self.lost_stracks = remove_duplicate_stracks(self.tracked_stracks, self.lost_stracks)

        # output_stracks = [track for track in self.tracked_stracks if track.is_activated]
        output_stracks = [track for track in self.tracked_stracks]
        for track in self.tracked_stracks:
            track.observed_time_frames = self.time_frames
            track.is_prediction = False
            track.missed_frames = 0
        for track in self.lost_stracks:
            track.crossing_clear_frames = 0
            track.is_prediction = True
            age = self._age(track)
            track.missed_frames = int(np.ceil(age - 1e-6))
            # Prediction is output only; it must not confirm a track or refresh its age/ReID.
            if (track.state == TrackState.Lost and track.is_activated
                    and age <= min(self.prediction_max_age, self.max_time_lost) + 1e-6
                    and np.isfinite(track.tlwh).all() and np.all(track.tlwh[2:] > 0)):
                output_stracks.append(track)

        return output_stracks


def joint_stracks(tlista, tlistb):
    exists = {}
    res = []
    for t in tlista:
        exists[t.track_id] = 1
        res.append(t)
    for t in tlistb:
        tid = t.track_id
        if not exists.get(tid, 0):
            exists[tid] = 1
            res.append(t)
    return res


def sub_stracks(tlista, tlistb):
    stracks = {}
    for t in tlista:
        stracks[t.track_id] = t
    for t in tlistb:
        tid = t.track_id
        if stracks.get(tid, 0):
            del stracks[tid]
    return list(stracks.values())


def remove_duplicate_stracks(stracksa, stracksb):
    pdist = matching.iou_distance(stracksa, stracksb)
    pairs = np.where(pdist < 0.15)
    dupa, dupb = list(), list()
    for p, q in zip(*pairs):
        if stracksa[p].crossing or stracksb[q].crossing:
            continue
        timep = stracksa[p].frame_id - stracksa[p].start_frame
        timeq = stracksb[q].frame_id - stracksb[q].start_frame
        if timep > timeq:
            dupb.append(q)
        else:
            dupa.append(p)
    resa = [t for i, t in enumerate(stracksa) if not i in dupa]
    resb = [t for i, t in enumerate(stracksb) if not i in dupb]
    return resa, resb
