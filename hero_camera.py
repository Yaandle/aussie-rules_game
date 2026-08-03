"""hero_camera.py — pure projection math for the AFL Hero diorama camera.

No Pygame, no drawing, no game rules: a pinhole camera standing on the
southern boundary, slightly above head height, looking north across the
oval. World space maps the logical field grid onto a ground plane:

    world x = field x        (goals left/right, YELLOW attacks +x)
    world z = field y        (depth: small z is the far side of the oval)
    world h = height above the turf (0 = grass)

The camera has no yaw or roll — it tracks its focus by translating only,
so the view stays calm and the goals always read left/right. hero_render
feeds it a focus point (carrier or ball) and a zoom flag each frame.
"""

import math

import settings


class HeroCamera:
    """Smoothed follow-camera with project/unproject onto the ground plane."""

    def __init__(self, focus):
        self.fx, self.fz = float(focus[0]), float(focus[1])
        self.zoom = 1.0
        self._rebuild()

    # ── Per-frame state ─────────────────────────────────────────────

    def update(self, dt, focus, zooming):
        """Ease the camera toward a new focus point and zoom level."""
        k = min(1.0, settings.HERO_CAM_LERP * dt)
        self.fx += (focus[0] - self.fx) * k
        self.fz += (focus[1] - self.fz) * k
        target_zoom = settings.HERO_CAM_ZOOM if zooming else 1.0
        self.zoom += (target_zoom - self.zoom) * k
        self._rebuild()

    def _rebuild(self):
        """Recompute the camera basis from the current focus."""
        # Camera position: behind the focus (south, +z) and up.
        self.cx = self.fx
        self.cy = settings.HERO_CAM_HEIGHT
        self.cz = self.fz + settings.HERO_CAM_BACK

        # Forward vector: from camera toward the focus at waist height.
        fwd = (0.0, 1.0 - self.cy, -settings.HERO_CAM_BACK)
        length = math.sqrt(fwd[1] ** 2 + fwd[2] ** 2)
        self.f = (0.0, fwd[1] / length, fwd[2] / length)
        # Right is world +x (no yaw/roll); up completes the basis.
        self.r = (1.0, 0.0, 0.0)
        self.u = (0.0, -self.f[2], self.f[1])

        self.focal = settings.HERO_CAM_FOCAL * self.zoom
        self.horizon_px = settings.WINDOW_H * settings.HERO_HORIZON_Y

    # ── Projection ──────────────────────────────────────────────────

    def project(self, x, z, h=0.0):
        """World point → (screen_x, screen_y, scale, depth).

        Returns None when the point is behind the camera. `scale` converts
        one world unit at that depth into display pixels.
        """
        vx = x - self.cx
        vy = h - self.cy
        vz = z - self.cz
        depth = vy * self.f[1] + vz * self.f[2]          # v · forward
        if depth < 1.0:
            return None
        xc = vx                                          # v · right
        yc = vy * self.u[1] + vz * self.u[2]             # v · up
        sx = settings.WINDOW_W / 2 + self.focal * xc / depth
        sy = self.horizon_px - self.focal * yc / depth
        return (sx, sy, self.focal / depth, depth)

    def unproject(self, sx, sy):
        """Screen pixel → ground-plane (field x, field y), or None if it
        points at or above the horizon."""
        a = (sx - settings.WINDOW_W / 2) / self.focal
        b = (self.horizon_px - sy) / self.focal
        denom = b * self.u[1] + self.f[1]
        if denom >= -1e-6:                # ray parallel to / above the ground
            return None
        depth = -self.cy / denom
        x = self.cx + a * depth
        z = self.cz + (b * self.u[2] + self.f[2]) * depth
        return (x, z)
