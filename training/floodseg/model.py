"""Model and loss.

U-Net (segmentation_models_pytorch) with an ImageNet-pretrained ResNet encoder. smp adapts the
first convolution to our number of input channels (the pretrained RGB filters are reused and
retrained). Output: 3 classes, 0 no water, 1 permanent water, 2 flood (Kuro Siwo labels).
"""

from __future__ import annotations

import segmentation_models_pytorch as smp
import torch
import torch.nn.functional as F

NUM_CLASSES = 3
CLASS_NAMES = {0: "no water", 1: "permanent water", 2: "flood"}


def build_model(in_channels: int, arch: str = "Unet", encoder: str = "resnet34",
                pretrained: bool = True) -> torch.nn.Module:
    model_cls = getattr(smp, arch)
    return model_cls(
        encoder_name=encoder,
        encoder_weights="imagenet" if pretrained else None,
        in_channels=in_channels,
        classes=NUM_CLASSES,
    )


class CEDiceLoss(torch.nn.Module):
    """Cross-entropy + soft Dice over the water classes (1, 2), ignoring label 255.

    Cross-entropy alone tends to under-predict the rare water classes; Dice optimises overlap
    directly and is insensitive to class imbalance.
    """

    def __init__(self, ignore_index: int = 255, dice_weight: float = 1.0, class_weights=None):
        super().__init__()
        self.ignore_index = ignore_index
        self.dice_weight = dice_weight
        self.register_buffer("class_weights", None if class_weights is None else torch.tensor(class_weights))

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        ce = F.cross_entropy(logits, target, weight=self.class_weights, ignore_index=self.ignore_index)
        if self.dice_weight == 0:
            return ce
        valid = (target != self.ignore_index).unsqueeze(1).float()
        probs = logits.float().softmax(1) * valid
        onehot = F.one_hot(target.clamp(0, NUM_CLASSES - 1), NUM_CLASSES).permute(0, 3, 1, 2).float() * valid
        dims = (0, 2, 3)
        inter = (probs * onehot).sum(dims)
        denom = probs.sum(dims) + onehot.sum(dims)
        dice = 1 - (2 * inter + 1.0) / (denom + 1.0)
        return ce + self.dice_weight * dice[1:].mean()
