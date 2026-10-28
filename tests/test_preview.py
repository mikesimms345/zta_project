import unittest

import numpy as np

from zta.media import CameraIntrinsics, RGBDFrame
from zta.preview import SideBySidePreviewRenderer


class SideBySidePreviewTests(unittest.TestCase):
    def test_composes_rgb_and_depth_at_double_width(self):
        color = np.zeros((12, 16, 3), dtype=np.uint8)
        frame = RGBDFrame(
            color_bgr=color,
            color_rgb=color[:, :, ::-1],
            aligned_depth=np.full((12, 16), 700, dtype=np.uint16),
            depth_scale=0.001,
            intrinsics=CameraIntrinsics(16, 12, 1, 1, 8, 6, "none", ()),
            frame_number=1,
            captured_at=1.0,
        )

        image = SideBySidePreviewRenderer().compose(frame)

        self.assertEqual((12, 32, 3), image.shape)


if __name__ == "__main__":
    unittest.main()
