"""Models and loss.

Two architectures, both from segmentation_models_pytorch building blocks with an ImageNet-pretrained
encoder (smp adapts the first convolution to our number of input channels):

- "Unet" (early fusion): all channels (pre, post, post - pre) enter one encoder together.
- "SiamUnet" (change detection): the same encoder (shared weights) looks at the pre image and the post
  image separately; at every scale the two feature maps and their difference are fused before the U-Net
  decoder. The Kuro Siwo paper found change-detection designs of this kind to be the strongest on GRD.

Output: 3 classes, 0 no water, 1 permanent water, 2 flood (Kuro Siwo labels).
"""

from __future__ import annotations

import segmentation_models_pytorch as smp
import torch
import torch.nn.functional as F
from torch import nn

NUM_CLASSES = 3
CLASS_NAMES = {0: "no water", 1: "permanent water", 2: "flood"}

# Indices of the feature channels (see features.CHANNELS): pre_vv, pre_vh, post_vv, post_vh, diff_vv, diff_vh, [slope]
PRE, POST, EXTRA_FROM = (0, 1), (2, 3), 6


class SiamUnet(nn.Module):
    def __init__(self, in_channels: int, encoder: str = "resnet34", pretrained: bool = True):
        super().__init__()
        self.n_extra = in_channels - EXTRA_FROM  # e.g. slope, given to both branches
        branch_ch = 2 + self.n_extra
        base = smp.Unet(encoder_name=encoder, encoder_weights="imagenet" if pretrained else None,
                        in_channels=branch_ch, classes=NUM_CLASSES)
        self.encoder, self.decoder, self.head = base.encoder, base.decoder, base.segmentation_head
        self.fuse = nn.ModuleList(
            nn.Sequential(nn.Conv2d(3 * c, c, 1, bias=False), nn.BatchNorm2d(c), nn.ReLU(inplace=True)) if c > 0
            else nn.Identity()
            for c in self.encoder.out_channels
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        extra = x[:, EXTRA_FROM:]
        pre = torch.cat([x[:, list(PRE)], extra], 1)
        post = torch.cat([x[:, list(POST)], extra], 1)
        f_pre, f_post = self.encoder(pre), self.encoder(post)
        fused = [f(torch.cat([b, a, b - a], 1)) if a.shape[1] > 0 else b
                 for f, a, b in zip(self.fuse, f_pre, f_post)]
        return self.head(self.decoder(fused))


def build_model(in_channels: int, arch: str = "Unet", encoder: str = "resnet34",
                pretrained: bool = True) -> nn.Module:
    if arch == "SiamUnet":
        return SiamUnet(in_channels, encoder, pretrained)
    model_cls = getattr(smp, arch)  # Unet, UnetPlusPlus, ...
    return model_cls(
        encoder_name=encoder,
        encoder_weights="imagenet" if pretrained else None,
        in_channels=in_channels,
        classes=NUM_CLASSES,
    )


class CEDiceLoss(nn.Module):
    """Cross-entropy + soft Dice over the water classes (1, 2), ignoring label 255.

    Cross-entropy alone tends to under-predict the rare water classes; Dice optimises overlap
    directly and is insensitive to class imbalance.

    Label 3 = "water of unknown type" (Sen1Floods11 has no permanent/flood distinction): its
    cross-entropy term is -log(P(permanent) + P(flood)); it is left out of the Dice term.
    """

    WATER_UNKNOWN = 3

    def __init__(self, ignore_index: int = 255, dice_weight: float = 1.0):
        super().__init__()
        self.ignore_index = ignore_index
        self.dice_weight = dice_weight

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        logits = logits.float()
        logp = logits.log_softmax(1)
        known = target < NUM_CLASSES
        unknown = target == self.WATER_UNKNOWN
        n = (known.sum() + unknown.sum()).clamp(min=1)
        nll = -logp.gather(1, target.clamp(0, NUM_CLASSES - 1).unsqueeze(1)).squeeze(1)
        ce = (nll * known).sum()
        if unknown.any():
            water = torch.logsumexp(logp[:, 1:], dim=1)
            ce = ce - (water * unknown).sum()
        ce = ce / n
        if self.dice_weight == 0:
            return ce
        valid = known.unsqueeze(1).float()
        probs = logp.exp() * valid
        onehot = F.one_hot(target.clamp(0, NUM_CLASSES - 1), NUM_CLASSES).permute(0, 3, 1, 2).float() * valid
        dims = (0, 2, 3)
        inter = (probs * onehot).sum(dims)
        denom = probs.sum(dims) + onehot.sum(dims)
        dice = 1 - (2 * inter + 1.0) / (denom + 1.0)
        return ce + self.dice_weight * dice[1:].mean()
