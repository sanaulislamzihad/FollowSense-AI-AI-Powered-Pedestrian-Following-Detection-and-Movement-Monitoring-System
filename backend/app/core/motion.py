"""Camera motion compensation.

Handheld or PTZ cameras move, which shifts every pedestrian in the image by the same
amount. Without compensation, a camera pan looks like everybody walking in the same
direction and produces false "same direction" / "following" relationships.

We estimate the global (background) motion between processed frames with sparse
optical flow on features *outside* the person boxes, fit a similarity transform with
RANSAC and accumulate it, so every foot point can be expressed in the coordinate frame
of the first video frame ("reference" coordinates). For a fixed CCTV camera the
estimated motion is ~0 and the transform stays the identity.
"""
from __future__ import annotations

import cv2
import numpy as np


class CameraMotionCompensator:
    def __init__(self, enabled: bool = True, work_width: int = 640):
        self.enabled = enabled
        self.work_width = work_width
        self.prev_gray: np.ndarray | None = None
        self.scale = 1.0
        self.T = np.eye(3)  # current frame -> reference frame
        self.T_inv = np.eye(3)
        self.last_shift = 0.0  # magnitude of last frame-to-frame motion (px)
        self.total_shift = 0.0

    def update(self, frame: np.ndarray, boxes: list[tuple[float, float, float, float]]) -> np.ndarray:
        if not self.enabled:
            return self.T
        h, w = frame.shape[:2]
        self.scale = self.work_width / float(w)
        small = cv2.resize(frame, (self.work_width, max(1, int(h * self.scale))), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        if self.prev_gray is None or self.prev_gray.shape != gray.shape:
            self.prev_gray = gray
            return self.T

        mask = np.full(gray.shape, 255, np.uint8)
        for x1, y1, x2, y2 in boxes:  # people move on their own: ignore them
            cv2.rectangle(mask, (int(x1 * self.scale) - 4, int(y1 * self.scale) - 4),
                          (int(x2 * self.scale) + 4, int(y2 * self.scale) + 4), 0, -1)
        pts = cv2.goodFeaturesToTrack(self.prev_gray, maxCorners=400, qualityLevel=0.01,
                                      minDistance=8, mask=mask, blockSize=7)
        A = None
        if pts is not None and len(pts) >= 12:
            nxt, status, _ = cv2.calcOpticalFlowPyrLK(self.prev_gray, gray, pts, None,
                                                      winSize=(21, 21), maxLevel=3)
            good = status.reshape(-1) == 1
            if good.sum() >= 10:
                # maps current-frame points -> previous-frame points
                A, inliers = cv2.estimateAffinePartial2D(nxt[good], pts[good], method=cv2.RANSAC,
                                                         ransacReprojThreshold=2.0, maxIters=500)
                if A is not None and (inliers is None or inliers.sum() < 8):
                    A = None
        self.prev_gray = gray
        if A is None:
            self.last_shift = 0.0
            return self.T

        S = np.diag([self.scale, self.scale, 1.0])
        M = np.vstack([A, [0, 0, 1]])
        M = np.linalg.inv(S) @ M @ S  # back to full-resolution pixels
        self.last_shift = float(np.hypot(M[0, 2], M[1, 2]))
        if self.last_shift < 0.3 and abs(M[0, 0] - 1) < 1e-3 and abs(M[0, 1]) < 1e-3:
            return self.T  # dead band: static camera, avoid drift
        self.total_shift += self.last_shift
        self.T = self.T @ M
        self.T_inv = np.linalg.inv(self.T)
        return self.T

    @staticmethod
    def _apply(T: np.ndarray, pts: np.ndarray) -> np.ndarray:
        if len(pts) == 0:
            return pts
        p = np.hstack([pts, np.ones((len(pts), 1))]) @ T.T
        return p[:, :2]

    def to_reference(self, pts) -> np.ndarray:
        return self._apply(self.T, np.asarray(pts, float).reshape(-1, 2))

    def to_frame(self, pts) -> np.ndarray:
        return self._apply(self.T_inv, np.asarray(pts, float).reshape(-1, 2))
