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


SSL4EO_S1_URL = ("https://huggingface.co/torchgeo/resnet50_sentinel1_all_moco/resolve/main/"
                 "resnet50_sentinel1_all_moco-906e4356.pth")


def load_ssl4eo_s1(encoder: nn.Module, in_channels: int) -> None:
    """Initialise a ResNet50 encoder with SSL4EO-S12 weights pretrained (MoCo) on Sentinel-1 GRD VV/VH.

    Wang et al., SSL4EO-S12 (2023), CC BY 4.0, via TorchGeo. The first convolution has 2 input channels
    (VV, VH); our inputs are pre/post/diff VV/VH (+ slope), so the VV filters are reused for every VV channel,
    the VH filters for every VH channel, the mean of both for slope, scaled to keep the activation size.
    """
    sd = torch.hub.load_state_dict_from_url(SSL4EO_S1_URL, map_location="cpu", progress=False)
    sd = {k: v for k, v in sd.items() if not k.startswith("fc.")}
    w = sd["conv1.weight"]  # [64, 2, 7, 7]
    cols = []
    for c in range(in_channels):
        cols.append(w[:, c % 2] if c < EXTRA_FROM else w.mean(1))
    sd["conv1.weight"] = torch.stack(cols, 1) * (2.0 / in_channels)
    # smp's encoder overrides load_state_dict; use the plain nn.Module one to get the key report
    missing, unexpected = nn.Module.load_state_dict(encoder, sd, strict=False)
    if unexpected or [m for m in missing if not m.startswith("fc")]:
        raise RuntimeError(f"SSL4EO weights did not match: missing={missing} unexpected={unexpected}")


def build_model(in_channels: int, arch: str = "Unet", encoder: str = "resnet34",
                pretrained: bool = True, encoder_weights: str | None = None) -> nn.Module:
    """encoder_weights: "imagenet" (default when pretrained), "ssl4eo_s1" (resnet50 only) or None."""
    weights = encoder_weights if encoder_weights is not None else ("imagenet" if pretrained else None)
    if arch == "SiamUnet":
        return SiamUnet(in_channels, encoder, weights == "imagenet")
    model_cls = getattr(smp, arch)  # Unet, UnetPlusPlus, ...
    model = model_cls(
        encoder_name=encoder,
        encoder_weights="imagenet" if weights == "imagenet" else None,
        in_channels=in_channels,
        classes=NUM_CLASSES,
    )
    if weights == "ssl4eo_s1":
        if encoder != "resnet50":
            raise ValueError("ssl4eo_s1 weights exist only for resnet50")
        load_ssl4eo_s1(model.encoder, in_channels)
    return model


def _ce_with_unknown(logp: torch.Tensor, target: torch.Tensor, unknown_label: int) -> torch.Tensor:
    """Cross-entropy; label `unknown_label` = water of unknown type -> -log(P(permanent) + P(flood))."""
    known = target < NUM_CLASSES
    unknown = target == unknown_label
    n = (known.sum() + unknown.sum()).clamp(min=1)
    nll = -logp.gather(1, target.clamp(0, NUM_CLASSES - 1).unsqueeze(1)).squeeze(1)
    ce = (nll * known).sum()
    if unknown.any():
        ce = ce - (torch.logsumexp(logp[:, 1:], dim=1) * unknown).sum()
    return ce / n


def _lovasz_grad(gt_sorted: torch.Tensor) -> torch.Tensor:
    gts = gt_sorted.sum()
    inter = gts - gt_sorted.cumsum(0)
    union = gts + (1 - gt_sorted).cumsum(0)
    jac = 1.0 - inter / union
    jac[1:] = jac[1:] - jac[:-1]
    return jac


def lovasz_softmax(probs: torch.Tensor, target: torch.Tensor, classes=(1, 2)) -> torch.Tensor:
    """Lovasz-Softmax loss (Berman et al., CVPR 2018): a smooth surrogate that optimises IoU directly.

    probs [B,C,H,W] softmax probabilities; pixels with target >= NUM_CLASSES are ignored.
    """
    p = probs.permute(0, 2, 3, 1).reshape(-1, probs.shape[1])
    t = target.reshape(-1)
    keep = t < NUM_CLASSES
    p, t = p[keep], t[keep]
    losses = []
    for c in classes:
        fg = (t == c).float()
        if fg.sum() == 0:
            continue
        err = (fg - p[:, c]).abs()
        err_sorted, perm = torch.sort(err, descending=True)
        losses.append(torch.dot(err_sorted, _lovasz_grad(fg[perm])))
    return torch.stack(losses).mean() if losses else probs.sum() * 0.0


class CEDiceLoss(nn.Module):
    """Cross-entropy + an overlap term over the water classes (1, 2), ignoring label 255.

    Cross-entropy alone tends to under-predict the rare water classes; the overlap term ("dice" = soft
    Dice, "lovasz" = Lovasz-Softmax, a direct IoU surrogate) is insensitive to class imbalance.

    Label 3 = "water of unknown type" (Sen1Floods11 has no permanent/flood distinction): its
    cross-entropy term is -log(P(permanent) + P(flood)); it is left out of the overlap term.
    """

    WATER_UNKNOWN = 3

    def __init__(self, ignore_index: int = 255, dice_weight: float = 1.0, overlap: str = "dice"):
        super().__init__()
        self.ignore_index = ignore_index
        self.dice_weight = dice_weight
        self.overlap = overlap

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        logp = logits.float().log_softmax(1)
        ce = _ce_with_unknown(logp, target, self.WATER_UNKNOWN)
        if self.dice_weight == 0:
            return ce
        if self.overlap == "lovasz":
            return ce + self.dice_weight * lovasz_softmax(logp.exp(), target)
        known = target < NUM_CLASSES
        valid = known.unsqueeze(1).float()
        probs = logp.exp() * valid
        onehot = F.one_hot(target.clamp(0, NUM_CLASSES - 1), NUM_CLASSES).permute(0, 3, 1, 2).float() * valid
        dims = (0, 2, 3)
        inter = (probs * onehot).sum(dims)
        denom = probs.sum(dims) + onehot.sum(dims)
        dice = 1 - (2 * inter + 1.0) / (denom + 1.0)
        return ce + self.dice_weight * dice[1:].mean()
