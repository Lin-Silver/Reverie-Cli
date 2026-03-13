"""
Generate images using ComfyUI's backend logic.
Standalone script with minimal external dependencies.
Embedded ComfyUI core is bundled as base64 to avoid external imports.
"""

import sys
import os
import argparse
import torch
import numpy as np
from PIL import Image
from pathlib import Path
import time
from datetime import datetime
import logging
import base64
import tempfile
import io
import importlib.util
import secrets
import types

# --- Embedded ComfyUI zip (base64) ---
# Primary source is the external embedded_comfy.b64 file to keep this script readable.
# The inline string is a fallback and may be incomplete; ensure embedded_comfy.b64 exists.
EMBEDDED_COMFY_B64_INLINE = ""
MIN_TORCH_SEED = -(1 << 63)
MAX_TORCH_SEED = (1 << 64) - 1


def load_embedded_comfy():
    """
    Decode and load the embedded ComfyUI zip into sys.path so imports work
    without relying on external ComfyUI installation.
    Extraction is forced to a local temp folder under the repo to avoid writing to C:.
    """
    if getattr(load_embedded_comfy, "_done", False):
        return
    data = None
    b64_path = Path(__file__).with_name("embedded_comfy.b64")
    if b64_path.exists():
        data = base64.b64decode(b64_path.read_text())
    elif EMBEDDED_COMFY_B64_INLINE:
        data = base64.b64decode(EMBEDDED_COMFY_B64_INLINE)
    else:
        print("Error: embedded_comfy.b64 missing and no inline fallback.")
        sys.exit(1)

    # use repo-local temp directory and extract there
    local_tmp = Path(__file__).parent / "_embedded_tmp"
    local_tmp.mkdir(parents=True, exist_ok=True)
    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=local_tmp)
    tmp_zip.write(data)
    tmp_zip.flush()
    tmp_zip.close()

    extract_dir = local_tmp / "embedded_comfy"
    if extract_dir.exists():
        pass
    else:
        extract_dir.mkdir(parents=True, exist_ok=True)
    import zipfile
    with zipfile.ZipFile(tmp_zip.name, "r") as zf:
        zf.extractall(extract_dir)
    zip_path = tmp_zip.name
    if extract_dir.as_posix() not in sys.path:
        sys.path.insert(0, extract_dir.as_posix())
    load_embedded_comfy._done = True


def install_comfy_aimdo_stub():
    """
    Provide a no-op fallback for bundled Comfy builds that expect the optional
    comfy_aimdo extension. Standard generation can run without DynamicVRAM.
    """
    try:
        if importlib.util.find_spec("comfy_aimdo") is not None:
            return
    except Exception:
        pass

    if "comfy_aimdo" in sys.modules:
        return

    control = types.ModuleType("comfy_aimdo.control")
    control.init = lambda: False
    control.init_device = lambda *args, **kwargs: False
    control.analyze = lambda *args, **kwargs: None
    control.set_log_debug = lambda *args, **kwargs: None
    control.set_log_critical = lambda *args, **kwargs: None
    control.set_log_error = lambda *args, **kwargs: None
    control.set_log_warning = lambda *args, **kwargs: None
    control.set_log_info = lambda *args, **kwargs: None
    control.get_total_vram_usage = lambda *args, **kwargs: 0

    model_vbar = types.ModuleType("comfy_aimdo.model_vbar")

    class _ModelVBAR:
        def __init__(self, *args, **kwargs):
            self._loaded_size = 0

        def loaded_size(self):
            return self._loaded_size

        def prioritize(self):
            return None

    model_vbar.ModelVBAR = _ModelVBAR
    model_vbar.vbars_analyze = lambda *args, **kwargs: 0
    model_vbar.vbars_reset_watermark_limits = lambda *args, **kwargs: None
    model_vbar.vbar_fault = lambda *args, **kwargs: None
    model_vbar.vbar_signature_compare = lambda *args, **kwargs: False
    model_vbar.vbar_unpin = lambda *args, **kwargs: None

    aimdo_torch = types.ModuleType("comfy_aimdo.torch")
    aimdo_torch.aimdo_to_tensor = lambda *args, **kwargs: None

    package = types.ModuleType("comfy_aimdo")
    package.control = control
    package.model_vbar = model_vbar
    package.torch = aimdo_torch
    package.__path__ = []

    sys.modules["comfy_aimdo"] = package
    sys.modules["comfy_aimdo.control"] = control
    sys.modules["comfy_aimdo.model_vbar"] = model_vbar
    sys.modules["comfy_aimdo.torch"] = aimdo_torch
    print("[INFO] comfy_aimdo not found; using compatibility fallback (DynamicVRAM disabled).")


def resolve_seed(seed_value):
    """
    Generate a safe default seed and validate manually provided values against
    the range accepted by torch.manual_seed.
    """
    if seed_value is None:
        return secrets.randbits(64)

    seed = int(seed_value)
    if seed < MIN_TORCH_SEED or seed > MAX_TORCH_SEED:
        raise ValueError(
            f"seed must be between {MIN_TORCH_SEED} and {MAX_TORCH_SEED}"
        )
    return seed


# Initialize embedded ComfyUI before importing modules
load_embedded_comfy()
install_comfy_aimdo_stub()

# Force Comfy base directory to repo root so folder_paths uses local models/output
import comfy.cli_args
comfy_base = Path(__file__).parent
if not getattr(comfy.cli_args.args, "base_directory", None):
    comfy.cli_args.args.base_directory = str(comfy_base)
    os.environ["COMFY_BASE_DIR"] = str(comfy_base)

# 检测CUDA并设置CPU模式
cpu_mode = False
if '--cpu' in sys.argv:
    cpu_mode = True
else:
    # 检查CUDA是否可用且可初始化
    cuda_available = torch.cuda.is_available()
    if cuda_available:
        try:
            torch.cuda.current_device()
        except (AssertionError, RuntimeError):
            cuda_available = False
    if not cuda_available:
        cpu_mode = True
if cpu_mode:
    comfy.cli_args.args.cpu = True
    print(f"[INFO] CUDA not available, using CPU mode")

# Import necessary ComfyUI backend modules from embedded extracted folder
try:
    import folder_paths
    import comfy.sd
    import comfy.utils
    import comfy.model_management
    import comfy.samplers
    import comfy.sample
except ImportError as e:
    print(f"Error importing embedded ComfyUI modules: {e}")
    sys.exit(1)

# Enable ComfyUI progress bar
comfy.utils.PROGRESS_BAR_ENABLED = True

# --- Local Helper Functions ---

def local_prepare_callback(model, steps):
    """
    Local progress bar callback to avoid importing latent_preview.
    """
    pbar = comfy.utils.ProgressBar(steps)
    def callback(step, x0, x, total_steps):
        pbar.update_absolute(step + 1, total_steps, None)
    return callback

# --- Node Logic (Inlined from nodes.py) ---

class CLIPTextEncode:
    def encode(self, clip, text):
        if clip is None:
            raise RuntimeError("ERROR: clip input is invalid: None")
        tokens = clip.tokenize(text)
        return (clip.encode_from_tokens_scheduled(tokens), )

class EmptyLatentImage:
    def __init__(self):
        self.device = comfy.model_management.intermediate_device()

    def generate(self, width, height, batch_size=1):
        latent = torch.zeros([batch_size, 4, height // 8, width // 8], device=self.device)
        return ({"samples":latent}, )

class VAEDecode:
    def decode(self, vae, samples):
        images = vae.decode(samples["samples"])
        if len(images.shape) == 5: #Combine batches
            images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
        return (images, )

def common_ksampler(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent, denoise=1.0, disable_noise=False, start_step=None, last_step=None, force_full_denoise=False):
    latent_image = latent["samples"]
    latent_image = comfy.sample.fix_empty_latent_channels(model, latent_image)

    if disable_noise:
        noise = torch.zeros(latent_image.size(), dtype=latent_image.dtype, layout=latent_image.layout, device="cpu")
    else:
        batch_inds = latent["batch_index"] if "batch_index" in latent else None
        noise = comfy.sample.prepare_noise(latent_image, seed, batch_inds)

    noise_mask = None
    if "noise_mask" in latent:
        noise_mask = latent["noise_mask"]

    # Use local callback
    callback = local_prepare_callback(model, steps)
    disable_pbar = not comfy.utils.PROGRESS_BAR_ENABLED
    
    # Call comfy.sample.sample directly
    samples = comfy.sample.sample(model, noise, steps, cfg, sampler_name, scheduler, positive, negative, latent_image,
                                  denoise=denoise, disable_noise=disable_noise, start_step=start_step, last_step=last_step,
                                  force_full_denoise=force_full_denoise, noise_mask=noise_mask, callback=callback, disable_pbar=disable_pbar, seed=seed)
    out = latent.copy()
    out["samples"] = samples
    return (out, )

class KSampler:
    def sample(self, model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, denoise=1.0):
        return common_ksampler(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, denoise=denoise)

# --- Main Execution ---

def parse_args():
    parser = argparse.ArgumentParser(description="Generate image using ComfyUI backend")
    parser.add_argument("--model", required=True, help="Path to checkpoint file")
    parser.add_argument("--prompt", required=True, help="Positive prompt")
    parser.add_argument("--negative-prompt", default="", help="Negative prompt")
    parser.add_argument("--width", type=int, default=512, help="Image width")
    parser.add_argument("--height", type=int, default=512, help="Image height")
    parser.add_argument("--steps", type=int, default=20, help="Sampling steps")
    parser.add_argument("--cfg", type=float, default=8.0, help="CFG Scale")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--sampler", default="euler", help="Sampler name")
    parser.add_argument("--scheduler", default="normal", help="Scheduler name")
    parser.add_argument("--output", default="output", help="Output directory")
    parser.add_argument("--batch-size", type=int, default=1, help="Batch size")
    parser.add_argument("--cpu", action="store_true", help="Use CPU mode (no CUDA)")
    return parser.parse_args()

def resolve_model_path(model_arg):
    path = Path(model_arg).expanduser()
    if path.exists():
        return str(path)
    local_models = Path("models") / model_arg
    if local_models.exists():
        return str(local_models)
    comfy_models = Path(__file__).parent / "models" / "checkpoints" / model_arg
    if comfy_models.exists():
        return str(comfy_models)
    return str(path)

def main():
    args = parse_args()
    
    # 1. Randomize Seed if not provided
    try:
        seed = resolve_seed(args.seed)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    # 2. Print Prompt and Settings
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Settings:")
    print(f"  - Model: {args.model}")
    print(f"  - Prompt: {args.prompt}")
    print(f"  - Negative Prompt: {args.negative_prompt}")
    print(f"  - Size: {args.width}x{args.height}")
    print(f"  - Steps: {args.steps} | CFG: {args.cfg}")
    print(f"  - Sampler: {args.sampler} | Scheduler: {args.scheduler}")
    print(f"  - Seed: {seed}")

    ckpt_path = resolve_model_path(args.model)
    if not os.path.exists(ckpt_path):
        print(f"Error: Model file not found at {ckpt_path}")
        sys.exit(1)
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading checkpoint...")
    
    try:
        model, clip, vae, clipvision = comfy.sd.load_checkpoint_guess_config(
            ckpt_path, 
            output_vae=True, 
            output_clip=True, 
            embedding_directory=folder_paths.get_folder_paths("embeddings")
        )
    except Exception as e:
        print(f"Error loading model: {e}")
        sys.exit(1)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Encoding prompts...")
    clip_encoder = CLIPTextEncode()
    pos_cond = clip_encoder.encode(clip, args.prompt)[0]
    neg_cond = clip_encoder.encode(clip, args.negative_prompt)[0]
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Creating latent...")
    empty_latent_node = EmptyLatentImage()
    latent = empty_latent_node.generate(args.width, args.height, args.batch_size)[0]
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sampling...")
    ksampler = KSampler()
    
    try:
        samples = ksampler.sample(
            model=model,
            seed=seed,
            steps=args.steps,
            cfg=args.cfg,
            sampler_name=args.sampler,
            scheduler=args.scheduler,
            positive=pos_cond,
            negative=neg_cond,
            latent_image=latent,
            denoise=1.0
        )[0]
    except Exception as e:
        print(f"Error during sampling: {e}")
        sys.exit(1)
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Decoding...")
    vae_decoder = VAEDecode()
    decoded_images = vae_decoder.decode(vae, samples)[0]
    
    # 3. Save with Timestamped Filename
    output_dir = Path(args.output)
    if output_dir.suffix: # if user provided a file path (e.g. out.png), use its parent
        output_dir = output_dir.parent
    
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Saving images...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for i, image in enumerate(decoded_images):
        # Fix: Detach before numpy conversion
        img_array = 255. * image.detach().cpu().numpy()
        img = Image.fromarray(np.clip(img_array, 0, 255).astype(np.uint8))
        
        filename = f"{timestamp}_{i}.png" if len(decoded_images) > 1 else f"{timestamp}.png"
        save_path = output_dir / filename
            
        img.save(save_path)
        print(f"Saved image to: {save_path}")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Done.")

if __name__ == "__main__":
    with torch.inference_mode():
        main()
