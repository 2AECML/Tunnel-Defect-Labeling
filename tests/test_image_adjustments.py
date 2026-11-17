import numpy as np
import pytest

from utils.mask_utils import adjust_brightness_contrast


@pytest.mark.parametrize(
    ("brightness", "contrast", "expected"),
    [
        (0, 1.0, [[0, 10, 30], [96, 128, 160], [180, 220, 255]]),
        (-30, 1.0, [[0, 0, 0], [66, 98, 130], [150, 190, 225]]),
        (30, 1.0, [[30, 40, 60], [126, 158, 190], [210, 250, 255]]),
        (0, 1.5, [[0, 0, 0], [80, 128, 176], [206, 255, 255]]),
        (0, 0.5, [[64, 69, 79], [112, 128, 144], [154, 174, 192]]),
        (-10, 1.5, [[0, 0, 0], [70, 118, 166], [196, 255, 255]]),
    ],
)
def test_brightness_and_contrast_clip_around_middle_gray(brightness, contrast, expected):
    image = np.array([[[0, 10, 30], [96, 128, 160], [180, 220, 255]]], dtype=np.uint8)
    before = image.copy()

    adjusted = adjust_brightness_contrast(image, brightness, contrast)

    np.testing.assert_array_equal(adjusted, np.array([expected], dtype=np.uint8))
    np.testing.assert_array_equal(image, before)
