"""Image-only Dream1 experiment; the existing runner owns all robot control."""
from dataclasses import replace
import io
import math

from PIL import Image


def brightness_factor(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 2:
        raise ValueError('Choose an image brightness from 0% to 200%.')
    return float(value)


def transform_image(data, factor):
    """Scale decoded RGB channel values. PNG avoids an extra lossy JPEG pass."""
    factor = brightness_factor(factor)
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert('RGB')
        if factor != 1:
            table = [min(255, int(channel * factor)) for channel in range(256)]
            image = image.point(table * 3)
        return image


def transformed_frame(frame, factor):
    if factor == 1:
        return frame
    image = transform_image(frame.jpeg, factor)
    output = io.BytesIO()
    image.save(output, format='PNG', compress_level=1)
    return replace(frame, jpeg=output.getvalue())


def preview_jpeg(frame, factor):
    image = transform_image(frame.jpeg, factor)
    output = io.BytesIO()
    image.resize((320, 176), Image.Resampling.LANCZOS).save(output, format='JPEG', quality=85)
    return output.getvalue()


class BrightnessCameraSource:
    def __init__(self, source, factor):
        self.source = source
        self.factor = brightness_factor(factor)

    @property
    def allowed_origin(self):
        return self.source.allowed_origin

    def capture_for_policy(self, observation, **kwargs):
        frames = self.source.capture_for_policy(observation, **kwargs)
        return [transformed_frame(frame, self.factor) for frame in frames]


def configure_policy(policy, factor):
    """Run before preparation; no capture, inference, queue or movement here."""
    factor = brightness_factor(factor)
    policy.camera_source = BrightnessCameraSource(policy.camera_source, factor)
    original_config = policy.public_config
    experiment = dict(name='Dream1 image brightness', brightness_factor=factor,
                      brightness_percent=round(factor * 100),
                      variant='baseline' if factor == 1 else 'brightness',
                      operation='RGB channel multiplication before resize/JPEG',
                      cameras=['overhead', 'wrist_l', 'wrist_r'],
                      fixed_for_run=True, additional_random_noise=False)
    policy.public_config = lambda: {**original_config(), 'image_experiment': experiment}
    return policy
