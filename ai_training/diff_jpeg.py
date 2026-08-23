"""
Differentiable JPEG Simulator in PyTorch
Enables end-to-end Rate-Distortion optimization for learning optimal JPEG Quantization Tables (DQT).
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F

# Standard JPEG Luminance & Chrominance Quantization Tables (IJG 50)
STD_LUMA_QTABLE = torch.tensor([
    [16, 11, 10, 16, 24, 40, 51, 61],
    [12, 12, 14, 19, 26, 58, 60, 55],
    [14, 13, 16, 24, 40, 57, 69, 56],
    [14, 17, 22, 29, 51, 87, 80, 62],
    [18, 22, 37, 56, 68, 109, 103, 77],
    [24, 35, 55, 64, 81, 104, 113, 92],
    [49, 64, 78, 87, 103, 121, 120, 101],
    [72, 92, 95, 98, 112, 100, 103, 99]
], dtype=torch.float32)

STD_CHROMA_QTABLE = torch.tensor([
    [17, 18, 24, 47, 99, 99, 99, 99],
    [18, 21, 26, 66, 99, 99, 99, 99],
    [24, 26, 56, 99, 99, 99, 99, 99],
    [47, 66, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99],
    [99, 99, 99, 99, 99, 99, 99, 99]
], dtype=torch.float32)


def generate_dct_basis_8x8():
    """Generates the 8x8 2D-DCT transform basis matrix."""
    basis = torch.zeros((8, 8, 8, 8), dtype=torch.float32)
    for u in range(8):
        for v in range(8):
            alpha_u = 1.0 / math.sqrt(2.0) if u == 0 else 1.0
            alpha_v = 1.0 / math.sqrt(2.0) if v == 0 else 1.0
            for x in range(8):
                for y in range(8):
                    basis[u, v, x, y] = 0.25 * alpha_u * alpha_v * \
                        math.cos((2 * x + 1) * u * math.pi / 16.0) * \
                        math.cos((2 * y + 1) * v * math.pi / 16.0)
    # Reshape to (64, 1, 8, 8) for 2D Conv
    return basis.view(64, 1, 8, 8)


class DifferentiableJPEG(nn.Module):
    """
    Differentiable JPEG Encoder & Decoder for Rate-Distortion training.
    """
    def __init__(self):
        super().__init__()
        dct_basis = generate_dct_basis_8x8()
        self.register_buffer("dct_conv_kernel", dct_basis)
        self.register_buffer("idct_conv_kernel", dct_basis)

        # Color Space Conversion Matrices (RGB to YCbCr)
        rgb_to_ycbcr_matrix = torch.tensor([
            [ 0.29900,  0.58700,  0.11400],
            [-0.16874, -0.33126,  0.50000],
            [ 0.50000, -0.41869, -0.08131]
        ], dtype=torch.float32)
        self.register_buffer("rgb_to_ycbcr_weight", rgb_to_ycbcr_matrix.view(3, 3, 1, 1))

        ycbcr_to_rgb_matrix = torch.tensor([
            [1.0,  0.00000,  1.40200],
            [1.0, -0.34414, -0.71414],
            [1.0,  1.77200,  0.00000]
        ], dtype=torch.float32)
        self.register_buffer("ycbcr_to_rgb_weight", ycbcr_to_rgb_matrix.view(3, 3, 1, 1))

    def rgb_to_ycbcr(self, x):
        return F.conv2d(x, self.rgb_to_ycbcr_weight)

    def ycbcr_to_rgb(self, ycbcr):
        return F.conv2d(ycbcr, self.ycbcr_to_rgb_weight)

    def forward_dct(self, channel):
        return F.conv2d(channel - 128.0, self.dct_conv_kernel, stride=8)

    def inverse_dct(self, dct_coeffs):
        return F.conv_transpose2d(dct_coeffs, self.idct_conv_kernel, stride=8) + 128.0

    def soft_quantize(self, dct_coeffs, q_table):
        """
        Differentiable soft quantization using STE (Straight-Through Estimator).
        """
        scaled = dct_coeffs / torch.clamp(q_table, min=1.0)
        hard_round = torch.round(scaled)
        quantized = hard_round + (scaled - scaled.detach()) # Straight-Through Estimator
        return quantized

    def estimate_rate(self, quantized_coeffs):
        """
        Surrogate for JPEG Entropy / Bitrate.
        """
        # Shannon entropy / zero-sparsity proxy
        rate_proxy = torch.mean(torch.log1p(torch.abs(quantized_coeffs)))
        return rate_proxy

    def forward(self, rgb_images, q_luma, q_chroma):
        """
        rgb_images: (B, 3, H, W) in range [0, 255]
        q_luma: (B, 64)
        q_chroma: (B, 64)
        """
        B, C, H, W = rgb_images.shape
        pad_h = (8 - H % 8) % 8
        pad_w = (8 - W % 8) % 8
        if pad_h > 0 or pad_w > 0:
            rgb_images = F.pad(rgb_images, (0, pad_w, 0, pad_h), mode='reflect')

        ycbcr = self.rgb_to_ycbcr(rgb_images)
        y, cb, cr = torch.split(ycbcr, 1, dim=1)

        # 1. Forward DCT
        dct_y = self.forward_dct(y)
        dct_cb = self.forward_dct(cb)
        dct_cr = self.forward_dct(cr)

        # 2. Quantization
        q_luma_4d = q_luma.view(B, 64, 1, 1)
        q_chroma_4d = q_chroma.view(B, 64, 1, 1)

        q_dct_y = self.soft_quantize(dct_y, q_luma_4d)
        q_dct_cb = self.soft_quantize(dct_cb, q_chroma_4d)
        q_dct_cr = self.soft_quantize(dct_cr, q_chroma_4d)

        # 3. Rate Estimation
        rate_y = self.estimate_rate(q_dct_y)
        rate_cb = self.estimate_rate(q_dct_cb)
        rate_cr = self.estimate_rate(q_dct_cr)
        total_rate = rate_y + 0.5 * (rate_cb + rate_cr)

        # 4. Dequantization
        deq_dct_y = q_dct_y * q_luma_4d
        deq_dct_cb = q_dct_cb * q_chroma_4d
        deq_dct_cr = q_dct_cr * q_chroma_4d

        # 5. Inverse DCT
        recon_y = self.inverse_dct(deq_dct_y)
        recon_cb = self.inverse_dct(deq_dct_cb)
        recon_cr = self.inverse_dct(deq_dct_cr)

        recon_ycbcr = torch.cat([recon_y, recon_cb, recon_cr], dim=1)
        recon_rgb = self.ycbcr_to_rgb(recon_ycbcr)
        recon_rgb = torch.clamp(recon_rgb, 0.0, 255.0)

        if pad_h > 0 or pad_w > 0:
            recon_rgb = recon_rgb[:, :, :H, :W]

        return recon_rgb, total_rate
