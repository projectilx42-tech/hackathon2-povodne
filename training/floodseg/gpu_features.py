"""Batched torch version of features.build_features + training augmentations, run on the GPU.

Doing this per sample in numpy on Kaggle's 4 CPU cores was the bottleneck (~25 ms/sample). The maths
is identical to features.py; tests/test_features.py checks that both give the same numbers.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

from .features import CHANNELS, DB_MAX, DB_MIN, DEFAULT_NORM, SLOPE_SCALE_DEG

IGNORE = 255


def u8_to_db(q: torch.Tensor) -> torch.Tensor:
    db = (q.float() - 1.0) / 254.0 * (DB_MAX - DB_MIN) + DB_MIN
    return db.masked_fill(q == 0, float("nan"))


def combine_pre_db(a: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
    lin = torch.stack([torch.pow(10.0, a / 10.0), torch.pow(10.0, b / 10.0)])
    mean = torch.nanmean(lin, dim=0)
    return 10.0 * torch.log10(mean.clamp(min=1e-6))  # NaN where both missing (nanmean -> NaN)


def build_features(pre_vv, pre_vh, post_vv, post_vh, slope_deg=None, norm=None) -> torch.Tensor:
    """[B,H,W] dB tensors -> [B,C,H,W] normalised features (same as features.build_features)."""
    norm = norm or DEFAULT_NORM
    pre_vv, pre_vh = pre_vv.clamp(DB_MIN, DB_MAX), pre_vh.clamp(DB_MIN, DB_MAX)
    post_vv, post_vh = post_vv.clamp(DB_MIN, DB_MAX), post_vh.clamp(DB_MIN, DB_MAX)
    raw = {"pre_vv": pre_vv, "pre_vh": pre_vh, "post_vv": post_vv, "post_vh": post_vh,
           "diff_vv": post_vv - pre_vv, "diff_vh": post_vh - pre_vh}
    chans = [(raw[n] - norm[n][0]) / norm[n][1] for n in CHANNELS]
    if slope_deg is not None:
        chans.append(slope_deg / SLOPE_SCALE_DEG)
    return torch.nan_to_num(torch.stack(chans, 1), nan=0.0, posinf=0.0, neginf=0.0)


def slope_from_dem(dem: torch.Tensor, pixel_m: float = 10.0) -> torch.Tensor:
    """[B,H,W] DEM (NaN = nodata) -> slope degrees, central differences like numpy.gradient."""
    fill = torch.nanmean(dem.flatten(1), 1).nan_to_num(0.0)[:, None, None]
    d = torch.where(torch.isfinite(dem), dem, fill)
    gy = torch.empty_like(d)
    gx = torch.empty_like(d)
    gy[:, 1:-1] = (d[:, 2:] - d[:, :-2]) / (2 * pixel_m)
    gy[:, 0], gy[:, -1] = (d[:, 1] - d[:, 0]) / pixel_m, (d[:, -1] - d[:, -2]) / pixel_m
    gx[:, :, 1:-1] = (d[:, :, 2:] - d[:, :, :-2]) / (2 * pixel_m)
    gx[:, :, 0], gx[:, :, -1] = (d[:, :, 1] - d[:, :, 0]) / pixel_m, (d[:, :, -1] - d[:, :, -2]) / pixel_m
    return torch.rad2deg(torch.atan(torch.hypot(gx, gy)))


@torch.no_grad()
def make_batch(sar_u8: torch.Tensor, label: torch.Tensor, slope_u8: torch.Tensor | None, norm: dict,
               augment: bool, gain_db: float = 0.5, speckle_p: float = 0.3, scale_p: float = 0.3,
               gen: torch.Generator | None = None):
    """sar_u8 [B,6,H,W] uint8 (post vv/vh, pre1 vv/vh, pre2 vv/vh), label [B,H,W], slope_u8 [B,H,W] degrees or None.

    Returns x [B,C,H,W] float32, y [B,H,W] int64. Augmentations as described in data.KuroSiwoDataset.
    """
    dev = sar_u8.device
    b = sar_u8.shape[0]
    db = u8_to_db(sar_u8)
    post_vv, post_vh = db[:, 0], db[:, 1]
    pre_mean_vv, pre_mean_vh = combine_pre_db(db[:, 2], db[:, 4]), combine_pre_db(db[:, 3], db[:, 5])
    y = label.long()
    if augment:
        def rnd(*shape):
            return torch.rand(*shape, device=dev, generator=gen)

        def rndn(*shape):
            return torch.randn(*shape, device=dev, generator=gen)

        # which pre image: 0 = pre1, 1 = pre2, 2 = mean of both
        choice = (rnd(b) * 3).long().clamp(max=2)[:, None, None]
        pre_vv = torch.where(choice == 0, db[:, 2], torch.where(choice == 1, db[:, 4], pre_mean_vv))
        pre_vh = torch.where(choice == 0, db[:, 3], torch.where(choice == 1, db[:, 5], pre_mean_vh))
        # pre1/pre2 alone may be missing where the mean exists: fall back to the mean
        pre_vv = torch.where(torch.isfinite(pre_vv), pre_vv, pre_mean_vv)
        pre_vh = torch.where(torch.isfinite(pre_vh), pre_vh, pre_mean_vh)
        if gain_db > 0:
            g = rndn(b, 2) * gain_db  # common offset: pre, post
            gp = rndn(b, 2, 2) * gain_db / 3  # extra per polarisation
            pre_vv = pre_vv + (g[:, 0] + gp[:, 0, 0])[:, None, None]
            pre_vh = pre_vh + (g[:, 0] + gp[:, 0, 1])[:, None, None]
            post_vv = post_vv + (g[:, 1] + gp[:, 1, 0])[:, None, None]
            post_vh = post_vh + (g[:, 1] + gp[:, 1, 1])[:, None, None]
        if speckle_p > 0:
            on = (rnd(b) < speckle_p)[:, None, None]
            looks = (4 + rnd(b) * 26)[:, None, None]

            def speckle(t):
                gam = torch.distributions.Gamma(looks.expand_as(t), looks.expand_as(t)).sample()
                return torch.where(on, t + 10 * torch.log10(gam.clamp(min=1e-6)), t)

            pre_vv, pre_vh, post_vv, post_vh = speckle(pre_vv), speckle(pre_vh), speckle(post_vv), speckle(post_vh)
    else:
        pre_vv, pre_vh = pre_mean_vv, pre_mean_vh

    slope = slope_u8.float() if slope_u8 is not None and slope_u8.numel() else None
    x = build_features(pre_vv, pre_vh, post_vv, post_vh, slope, norm)

    if augment:
        x, y = _flip_rot(x, y, gen)
        if scale_p > 0:
            x, y = _rescale(x, y, scale_p, gen)
    return x, y


def _flip_rot(x, y, gen):
    out_x, out_y = torch.empty_like(x), torch.empty_like(y)
    ks = torch.randint(0, 4, (x.shape[0],), device=x.device, generator=gen).tolist()
    fl = (torch.rand(x.shape[0], device=x.device, generator=gen) < 0.5).tolist()
    for i, (k, f) in enumerate(zip(ks, fl)):
        xi, yi = torch.rot90(x[i], k, (1, 2)), torch.rot90(y[i], k, (0, 1))
        if f:
            xi, yi = xi.flip(-1), yi.flip(-1)
        out_x[i], out_y[i] = xi, yi
    return out_x, out_y


def _rescale(x, y, p, gen):
    """Per sample, with probability p: zoom 0.7-1.4x, crop or pad (padding ignored by the loss)."""
    b, _, h, w = x.shape
    on = (torch.rand(b, device=x.device, generator=gen) < p).tolist()
    scales = (0.7 + torch.rand(b, device=x.device, generator=gen) * 0.7).tolist()
    offs = torch.rand(b, 2, device=x.device, generator=gen).tolist()
    for i in range(b):
        if not on[i]:
            continue
        s = scales[i]
        nh, nw = max(int(round(h * s)), 8), max(int(round(w * s)), 8)
        xs = F.interpolate(x[i:i + 1], size=(nh, nw), mode="bilinear", align_corners=False)[0]
        ys = F.interpolate(y[i:i + 1, None].float(), size=(nh, nw), mode="nearest")[0, 0].long()
        if s >= 1:
            r, c = int(offs[i][0] * (nh - h)), int(offs[i][1] * (nw - w))
            x[i], y[i] = xs[:, r:r + h, c:c + w], ys[r:r + h, c:c + w]
        else:
            r, c = int(offs[i][0] * (h - nh)), int(offs[i][1] * (w - nw))
            x[i].zero_()
            y[i].fill_(IGNORE)
            x[i, :, r:r + nh, c:c + nw], y[i, r:r + nh, c:c + nw] = xs, ys
    return x, y
