"""
MicroQuantNet: Ultra-lightweight Neural JPEG Quantization Table (DQT) Generator
Designed for Mobile NPU deployment (<0.15ms latency on Samsung Galaxy NPU / Qualcomm Hexagon).
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

# Standard JPEG base quantization tables (Q50)
BASE_LUMA_64 = torch.tensor([
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99
], dtype=torch.float32)

BASE_CHROMA_64 = torch.tensor([
    17, 18, 24, 47, 99, 99, 99, 99,
    18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99
], dtype=torch.float32)


class ConvBNReLU(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size=3, stride=1, padding=1):
        super().__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, kernel_size, stride=stride, padding=padding, bias=False)
        self.bn = nn.BatchNorm2d(out_ch)
        self.relu = nn.ReLU6(inplace=True)

    def forward(self, x):
        return self.relu(self.bn(self.conv(x)))


class DepthwiseSeparableConv(nn.Module):
    def __init__(self, in_ch, out_ch, stride=1):
        super().__init__()
        self.dw = nn.Conv2d(in_ch, in_ch, 3, stride=stride, padding=1, groups=in_ch, bias=False)
        self.bn1 = nn.BatchNorm2d(in_ch)
        self.pw = nn.Conv2d(in_ch, out_ch, 1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_ch)
        self.relu = nn.ReLU6(inplace=True)

    def forward(self, x):
        x = self.relu(self.bn1(self.dw(x)))
        x = self.relu(self.bn2(self.pw(x)))
        return x


class MicroQuantNet(nn.Module):
    """
    Ultra-lightweight CNN (<35k parameters) predicting 64 Luma + 64 Chroma Q-table values.
    Accepts:
      - thumbnail: (B, 1, 192, 256) or (B, 3, 192, 256)
      - metadata: (B, 4) -> [normalized_iso, normalized_exposure, avg_brightness, face_flag]
    """
    def __init__(self, in_channels=1, num_meta=4):
        super().__init__()
        self.register_buffer("base_luma", BASE_LUMA_64.unsqueeze(0))
        self.register_buffer("base_chroma", BASE_CHROMA_64.unsqueeze(0))

        # Backbone: 4 Conv Stages (Feature Map: 192x256 -> 96x128 -> 48x64 -> 24x32 -> 12x16)
        self.stage1 = ConvBNReLU(in_channels, 16, stride=2)              # 96x128
        self.stage2 = DepthwiseSeparableConv(16, 24, stride=2)           # 48x64
        self.stage3 = DepthwiseSeparableConv(24, 32, stride=2)           # 24x32
        self.stage4 = DepthwiseSeparableConv(32, 48, stride=2)           # 12x16

        self.gap = nn.AdaptiveAvgPool2d(1)

        # Metadata Fusion & Multi-Layer Regression Head
        self.meta_fc = nn.Sequential(
            nn.Linear(num_meta, 16),
            nn.ReLU6(inplace=True)
        )

        self.head = nn.Sequential(
            nn.Linear(48 + 16, 64),
            nn.ReLU6(inplace=True),
            nn.Linear(64, 128) # 64 Luma Scale Multipliers + 64 Chroma Scale Multipliers
        )

    def forward(self, thumbnail, metadata=None):
        """
        thumbnail: (B, C, H, W) normalized to [0, 1]
        metadata: (B, 4) optional
        Returns:
          q_luma: (B, 64) in range [1, 255]
          q_chroma: (B, 64) in range [1, 255]
        """
        B = thumbnail.shape[0]
        if metadata is None:
            metadata = torch.zeros((B, 4), dtype=torch.float32, device=thumbnail.device)

        # Extract Visual Features
        x = self.stage1(thumbnail)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.stage4(x)
        feat = self.gap(x).view(B, -1) # (B, 48)

        # Process Camera Metadata
        meta_feat = self.meta_fc(metadata) # (B, 16)

        # Fuse
        fused = torch.cat([feat, meta_feat], dim=1) # (B, 64)

        # Predict Multiplicative Scaling Factors (Range: [0.1, 4.0])
        raw_multipliers = self.head(fused) # (B, 128)
        multipliers = 0.1 + 3.9 * torch.sigmoid(raw_multipliers)

        mult_luma = multipliers[:, :64]
        mult_chroma = multipliers[:, 64:]

        # Multiply by base JPEG Q-tables
        q_luma = torch.clamp(self.base_luma * mult_luma, min=1.0, max=255.0)
        q_chroma = torch.clamp(self.base_chroma * mult_chroma, min=1.0, max=255.0)

        return q_luma, q_chroma


if __name__ == "__main__":
    model = MicroQuantNet(in_channels=1, num_meta=4)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"MicroQuantNet Total Parameters: {total_params} (~{total_params*4/1024:.1f} KB in FP32)")

    dummy_thumb = torch.rand(2, 1, 192, 256)
    dummy_meta = torch.tensor([[0.2, 0.5, 0.6, 1.0], [0.8, 0.1, 0.3, 0.0]])
    q_y, q_c = model(dummy_thumb, dummy_meta)
    print("Output Q_Y shape:", q_y.shape, "Sample values:", q_y[0, :8].detach().numpy())
    print("Output Q_C shape:", q_c.shape, "Sample values:", q_c[0, :8].detach().numpy())
