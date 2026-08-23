"""
Training Script for MicroQuantNet with Differentiable JPEG Rate-Distortion Loss
"""

import os
import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
import torchvision.transforms as T
from PIL import Image

from micro_quant_net import MicroQuantNet
from diff_jpeg import DifferentiableJPEG


class SyntheticOrFolderDataset(Dataset):
    """
    Dataset loader for full images & downscaled thumbnails.
    Generates realistic random patches if no folder is provided.
    """
    def __init__(self, root_dir=None, patch_size=256, num_samples=1000):
        self.root_dir = root_dir
        self.patch_size = patch_size
        self.num_samples = num_samples
        self.image_files = []
        if root_dir and os.path.isdir(root_dir):
            for ext in [".jpg", ".png", ".jpeg"]:
                self.image_files.extend([
                    os.path.join(root_dir, f) for f in os.listdir(root_dir) if f.lower().endswith(ext)
                ])

    def __len__(self):
        return len(self.image_files) if self.image_files else self.num_samples

    def __getitem__(self, idx):
        if self.image_files:
            img_path = self.image_files[idx % len(self.image_files)]
            img = Image.open(img_path).convert("RGB")
            # Random crop or resize to patch_size
            crop = T.RandomCrop((self.patch_size, self.patch_size))(img)
            tensor_img = T.ToTensor()(crop) * 255.0 # [0, 255]
        else:
            # Synthetic patch generation (smooth gradients + random noise/edges)
            tensor_img = torch.rand(3, self.patch_size, self.patch_size) * 255.0

        # Downscale to 192x256 Y-plane thumbnail for AI model input
        y_channel = 0.299 * tensor_img[0:1] + 0.587 * tensor_img[1:2] + 0.114 * tensor_img[2:3]
        thumb = T.Resize((192, 256))(y_channel) / 255.0 # [0, 1]

        # Dummy metadata: [normalized_iso (0~1), exposure (0~1), mean_brightness (0~1), face_roi (0 or 1)]
        metadata = torch.tensor([0.4, 0.5, tensor_img.mean().item() / 255.0, 0.0], dtype=torch.float32)

        return tensor_img, thumb, metadata


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Training MicroQuantNet on device: {device}")

    model = MicroQuantNet(in_channels=1, num_meta=4).to(device)
    diff_jpeg = DifferentiableJPEG().to(device)

    dataset = SyntheticOrFolderDataset(root_dir=args.data_dir, num_samples=args.num_samples)
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)

    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    l1_loss_fn = nn.L1Loss()

    for epoch in range(args.epochs):
        model.train()
        total_distortion = 0.0
        total_rate = 0.0
        total_loss = 0.0

        for batch_idx, (full_img, thumb, meta) in enumerate(dataloader):
            full_img = full_img.to(device)
            thumb = thumb.to(device)
            meta = meta.to(device)

            optimizer.zero_grad()

            # 1. MicroQuantNet predicts optimal Q-tables
            q_luma, q_chroma = model(thumb, meta)

            # 2. Differentiable JPEG performs simulation
            recon_img, estimated_rate = diff_jpeg(full_img, q_luma, q_chroma)

            # 3. Rate-Distortion Loss
            # Distortion: L1 reconstruction error (Pixel & Perceptual fidelity)
            distortion_loss = l1_loss_fn(recon_img, full_img) / 255.0

            # Total Lagrangian Cost: J = Distortion + lambda * Rate
            loss = distortion_loss + args.rate_weight * estimated_rate

            loss.backward()
            optimizer.step()

            total_distortion += distortion_loss.item()
            total_rate += estimated_rate.item()
            total_loss += loss.item()

        scheduler.step()
        avg_dist = total_distortion / len(dataloader)
        avg_rate = total_rate / len(dataloader)
        avg_loss = total_loss / len(dataloader)

        print(f"Epoch [{epoch+1}/{args.epochs}] | Loss: {avg_loss:.4f} | Distortion: {avg_dist:.4f} | Rate Proxy: {avg_rate:.4f}")

    # Save Model Weights
    os.makedirs(args.output_dir, exist_ok=True)
    save_path = os.path.join(args.output_dir, "micro_quant_net.pth")
    torch.save(model.state_dict(), save_path)
    print(f"Model saved successfully to {save_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", type=str, default=None, help="Path to image training folder")
    parser.add_argument("--output_dir", type=str, default="./checkpoints", help="Output directory")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--rate_weight", type=float, default=0.08, help="Lagrange multiplier lambda for bitrate penalty")
    parser.add_argument("--num_samples", type=int, default=500)
    args = parser.parse_args()

    train(args)
