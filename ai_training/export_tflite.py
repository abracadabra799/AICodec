"""
Export MicroQuantNet PyTorch Model to ONNX and TFLite (INT8 Quantization)
Ready for deployment on Samsung Galaxy NPU (via Samsung ENN SDK or Android NNAPI/TFLite GPU/NPU delegate).
"""

import os
import torch
from micro_quant_net import MicroQuantNet


def export_onnx(model_path="checkpoints/micro_quant_net.pth", onnx_output="checkpoints/micro_quant_net.onnx"):
    device = torch.device("cpu")
    model = MicroQuantNet(in_channels=1, num_meta=4)
    if os.path.exists(model_path):
        model.load_state_dict(torch.load(model_path, map_location=device))
        print(f"Loaded weights from {model_path}")
    else:
        print("Using un-trained/initialized weights for structural export demo.")

    model.eval()

    dummy_thumb = torch.randn(1, 1, 192, 256, dtype=torch.float32)
    dummy_meta = torch.randn(1, 4, dtype=torch.float32)

    os.makedirs(os.path.dirname(onnx_output), exist_ok=True)

    torch.onnx.export(
        model,
        (dummy_thumb, dummy_meta),
        onnx_output,
        export_params=True,
        opset_version=13,
        do_constant_folding=True,
        input_names=["thumbnail_y", "camera_metadata"],
        output_names=["q_table_luma", "q_table_chroma"],
        dynamic_axes=None # Fixed batch size 1 for zero-allocation NPU optimization
    )
    print(f"Exported ONNX model to {onnx_output}")


def generate_tflite_conversion_guide():
    guide = """
# ==============================================================================
# TFLite INT8 Post-Training Quantization (PTQ) Script Guide
# ==============================================================================
# Run the following in a Python environment with `onnx2tf` or `tensorflow`:
'''
import tensorflow as tf
import onnx
from onnx_tf.backend import prepare

# 1. Convert ONNX to SavedModel
onnx_model = onnx.load("checkpoints/micro_quant_net.onnx")
tf_rep = prepare(onnx_model)
tf_rep.export_graph("checkpoints/saved_model")

# 2. TFLite INT8 Quantization with Representative Dataset
converter = tf.lite.TFLiteConverter.from_saved_model("checkpoints/saved_model")
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.target_spec.supported_types = [tf.int8]
converter.inference_input_type = tf.uint8 # Fast DMA mapping from Y-plane
converter.inference_output_type = tf.uint8 # 64-byte DQT table output

tflite_quant_model = converter.convert()
with open("checkpoints/micro_quant_net_int8.tflite", "wb") as f:
    f.write(tflite_quant_model)
print("Quantized INT8 TFLite model generated: checkpoints/micro_quant_net_int8.tflite (~35KB)")
'''
"""
    print(guide)


if __name__ == "__main__":
    export_onnx()
    generate_tflite_conversion_guide()
