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
import importlib
import importlib.util
import secrets
import types
import json

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
        return getattr(load_embedded_comfy, "_extract_dir", None)
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
    load_embedded_comfy._extract_dir = extract_dir
    return extract_dir


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

    host_buffer = types.ModuleType("comfy_aimdo.host_buffer")

    class _HostBuffer:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("comfy_aimdo host buffers are unavailable in embedded fallback")

    host_buffer.HostBuffer = _HostBuffer

    model_mmap = types.ModuleType("comfy_aimdo.model_mmap")

    class _ModelMMAP:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("comfy_aimdo mmap is unavailable in embedded fallback")

    model_mmap.ModelMMAP = _ModelMMAP

    aimdo_torch = types.ModuleType("comfy_aimdo.torch")
    aimdo_torch.aimdo_to_tensor = lambda *args, **kwargs: None
    aimdo_torch.hostbuf_to_tensor = lambda *args, **kwargs: None

    package = types.ModuleType("comfy_aimdo")
    package.control = control
    package.model_vbar = model_vbar
    package.torch = aimdo_torch
    package.host_buffer = host_buffer
    package.model_mmap = model_mmap
    package.__path__ = []

    sys.modules["comfy_aimdo"] = package
    sys.modules["comfy_aimdo.control"] = control
    sys.modules["comfy_aimdo.model_vbar"] = model_vbar
    sys.modules["comfy_aimdo.host_buffer"] = host_buffer
    sys.modules["comfy_aimdo.model_mmap"] = model_mmap
    sys.modules["comfy_aimdo.torch"] = aimdo_torch
    print("[INFO] comfy_aimdo not found; using compatibility fallback (DynamicVRAM disabled).")


def install_av_stub():
    """
    Let image-only generation import recent ComfyUI builds without PyAV.

    ComfyUI imports video/audio helpers at module import time even when Reverie
    only uses still-image sampling. A real PyAV install is still required for
    video/audio nodes; this stub exists only so the still-image path does not
    block on an unrelated optional wheel.
    """
    try:
        if importlib.util.find_spec("av") is not None:
            return
    except Exception:
        pass

    if "av" in sys.modules:
        return

    def _unavailable(*args, **kwargs):
        raise RuntimeError(
            "PyAV is not installed. Install the 'av' package to use ComfyUI "
            "video or audio import/export nodes."
        )

    class _StubFrame:
        pts = 0
        sample_rate = 1
        samples = 0
        time = 0

        @classmethod
        def from_ndarray(cls, *args, **kwargs):
            return cls()

        def reformat(self, *args, **kwargs):
            return self

        def to_ndarray(self, *args, **kwargs):
            _unavailable()

    class _StubStream:
        type = "video"
        width = 0
        height = 0
        frames = 0
        average_rate = None
        duration = None
        time_base = 1
        channels = 0
        sample_rate = 1
        index = 0
        pix_fmt = ""
        bit_rate = 0
        options = {}

        def __init__(self, *args, **kwargs):
            self.codec = types.SimpleNamespace(capabilities=0, name="")
            self.codec_context = types.SimpleNamespace(sample_rate=1, qscale=0)

        def encode(self, *args, **kwargs):
            _unavailable()

    class _InputContainer:
        duration = None
        metadata = {}
        format = types.SimpleNamespace(name="")

        def __init__(self, *args, **kwargs):
            self.streams = types.SimpleNamespace(video=[], audio=[])

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __iter__(self):
            return iter(())

        def close(self):
            return None

        def add_stream(self, *args, **kwargs):
            _unavailable()

        def add_stream_from_template(self, *args, **kwargs):
            _unavailable()

        def decode(self, *args, **kwargs):
            _unavailable()

        def demux(self, *args, **kwargs):
            _unavailable()

        def mux(self, *args, **kwargs):
            _unavailable()

        def seek(self, *args, **kwargs):
            _unavailable()

    class _AudioResampler:
        def __init__(self, *args, **kwargs):
            pass

        def resample(self, *args, **kwargs):
            _unavailable()

    av_module = types.ModuleType("av")
    av_module.__spec__ = importlib.machinery.ModuleSpec("av", loader=None, is_package=True)
    av_module.open = _unavailable
    av_module.VideoFrame = _StubFrame
    av_module.AudioFrame = _StubFrame
    av_module.VideoStream = type("VideoStream", (_StubStream,), {"type": "video"})
    av_module.AudioStream = type("AudioStream", (_StubStream,), {"type": "audio"})
    av_module.FFmpegError = RuntimeError
    av_module.AVError = RuntimeError
    av_module.time_base = 1_000_000
    av_module.__path__ = []

    container_module = types.ModuleType("av.container")
    container_module.__spec__ = importlib.machinery.ModuleSpec("av.container", loader=None)
    container_module.InputContainer = _InputContainer
    container_module.OutputContainer = _InputContainer

    subtitles_module = types.ModuleType("av.subtitles")
    subtitles_module.__spec__ = importlib.machinery.ModuleSpec("av.subtitles", loader=None, is_package=True)
    subtitles_module.__path__ = []
    subtitle_stream_module = types.ModuleType("av.subtitles.stream")
    subtitle_stream_module.__spec__ = importlib.machinery.ModuleSpec("av.subtitles.stream", loader=None)
    subtitle_stream_module.SubtitleStream = type("SubtitleStream", (_StubStream,), {"type": "subtitle"})
    subtitles_module.stream = subtitle_stream_module

    audio_module = types.ModuleType("av.audio")
    audio_module.__spec__ = importlib.machinery.ModuleSpec("av.audio", loader=None, is_package=True)
    audio_module.__path__ = []
    resampler_module = types.ModuleType("av.audio.resampler")
    resampler_module.__spec__ = importlib.machinery.ModuleSpec("av.audio.resampler", loader=None)
    resampler_module.AudioResampler = _AudioResampler
    audio_module.resampler = resampler_module
    av_module.audio = audio_module

    video_module = types.ModuleType("av.video")
    video_module.__spec__ = importlib.machinery.ModuleSpec("av.video", loader=None, is_package=True)
    video_module.__path__ = []
    video_frame_module = types.ModuleType("av.video.frame")
    video_frame_module.__spec__ = importlib.machinery.ModuleSpec("av.video.frame", loader=None)
    video_frame_module.VideoFrame = _StubFrame
    _StubFrame.pict_type = None
    video_module.frame = video_frame_module
    av_module.video = video_module

    logging_module = types.SimpleNamespace(ERROR=40, set_level=lambda *args, **kwargs: None)
    av_module.logging = logging_module

    error_module = types.ModuleType("av.error")
    error_module.__spec__ = importlib.machinery.ModuleSpec("av.error", loader=None)
    error_module.FFmpegError = RuntimeError
    error_module.InvalidDataError = RuntimeError
    av_module.container = container_module
    av_module.subtitles = subtitles_module
    av_module.error = error_module

    sys.modules["av"] = av_module
    sys.modules["av.container"] = container_module
    sys.modules["av.subtitles"] = subtitles_module
    sys.modules["av.subtitles.stream"] = subtitle_stream_module
    sys.modules["av.audio"] = audio_module
    sys.modules["av.audio.resampler"] = resampler_module
    sys.modules["av.video"] = video_module
    sys.modules["av.video.frame"] = video_frame_module
    sys.modules["av.error"] = error_module
    print("[INFO] PyAV not found; using image-only compatibility fallback.")


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


def infer_model_format(path, requested):
    requested = (requested or "auto").strip().lower()
    if requested in {"checkpoint", "ckpt", "safetensors"}:
        return "checkpoint"
    if requested == "gguf":
        return "gguf"
    return "gguf" if str(path).lower().endswith(".gguf") else "checkpoint"


def _read_gguf_scalar(reader, key):
    try:
        import gguf
    except Exception:
        return None
    field = reader.get_field(key)
    if field is None:
        return None
    try:
        if len(field.types) == 1 and field.types[0] == gguf.GGUFValueType.STRING:
            return str(field.parts[field.data[-1]], encoding="utf-8")
        value = field.parts[field.data[-1]]
        if hasattr(value, "item"):
            return value.item()
        return value
    except Exception:
        return None


def inspect_gguf_model(model_path):
    try:
        import gguf
    except ImportError as exc:
        raise RuntimeError(
            "GGUF support requires the 'gguf' Python package. Install it with: "
            "pip install gguf"
        ) from exc

    reader = gguf.GGUFReader(str(model_path))
    tensor_names = [tensor.name for tensor in reader.tensors[:64]]
    architecture = _read_gguf_scalar(reader, "general.architecture")
    detected_family = "ernie-image" if any(
        name == "layers.0.mlp.linear_fc2.weight" for name in tensor_names
    ) else str(architecture or "unknown")
    return {
        "path": str(model_path),
        "format": "gguf",
        "architecture": architecture,
        "detected_family": detected_family,
        "tensor_count": len(reader.tensors),
        "first_tensors": tensor_names[:20],
    }


def load_comfyui_gguf_nodes():
    """Import the embedded ComfyUI-GGUF custom node package."""
    extract_dir = getattr(load_embedded_comfy, "_extract_dir", None)
    candidates = []
    if extract_dir:
        candidates.append(Path(extract_dir) / "custom_nodes" / "ComfyUI-GGUF")
    candidates.extend(
        [
            Path(__file__).parent / "custom_nodes" / "ComfyUI-GGUF",
            Path(__file__).parent / "add-on" / "ComfyUI-GGUF",
        ]
    )

    node_dir = next((candidate for candidate in candidates if (candidate / "__init__.py").exists()), None)
    if node_dir is None:
        raise RuntimeError(
            "ComfyUI-GGUF custom node is not bundled. Repack Comfy/embedded_comfy.b64 "
            "with Comfy/add-on/ComfyUI-GGUF included."
        )

    module_name = "reverie_embedded_comfyui_gguf"
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(
        module_name,
        node_dir / "__init__.py",
        submodule_search_locations=[str(node_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load ComfyUI-GGUF from {node_dir}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_gguf_diffusion_model(model_path):
    gguf_pkg = load_comfyui_gguf_nodes()
    nodes_mod = importlib.import_module(f"{gguf_pkg.__name__}.nodes")
    loader_mod = importlib.import_module(f"{gguf_pkg.__name__}.loader")
    ops_mod = importlib.import_module(f"{gguf_pkg.__name__}.ops")

    sd, extra = loader_mod.gguf_sd_loader(str(model_path))
    kwargs = {}
    try:
        import inspect
        valid_params = inspect.signature(comfy.sd.load_diffusion_model_state_dict).parameters
        if "metadata" in valid_params:
            kwargs["metadata"] = extra.get("metadata", {})
    except Exception:
        pass

    model = comfy.sd.load_diffusion_model_state_dict(
        sd,
        model_options={"custom_operations": ops_mod.GGMLOps()},
        **kwargs,
    )
    if model is None:
        raise RuntimeError(f"Could not detect diffusion model type for GGUF file: {model_path}")
    return nodes_mod.GGUFModelPatcher.clone(model)


def resolve_aux_model_path(raw_path, kind):
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if path.exists():
        return path.resolve()
    comfy_base = Path(__file__).parent
    search_dirs = {
        "clip": ["models/text_encoders", "models/clip"],
        "vae": ["models/vae"],
        "prompt_enhancer": ["models/text_encoders", "models/clip"],
    }.get(kind, ["models"])
    for folder in search_dirs:
        candidate = comfy_base / folder / raw_path
        if candidate.exists():
            return candidate.resolve()
    return path


def load_clip_from_path(clip_path, model_format, clip_type_name):
    if model_format == "gguf":
        gguf_pkg = load_comfyui_gguf_nodes()
        loader_mod = importlib.import_module(f"{gguf_pkg.__name__}.loader")
        sd = loader_mod.gguf_clip_loader(str(clip_path))
        model_options = {
            "custom_operations": importlib.import_module(f"{gguf_pkg.__name__}.ops").GGMLOps,
            "initial_device": comfy.model_management.text_encoder_offload_device(),
        }
    else:
        if str(clip_path).lower().endswith(".safetensors"):
            from safetensors.torch import load_file
            sd = load_file(str(clip_path), device="cpu")
        else:
            sd = comfy.utils.load_torch_file(str(clip_path), safe_load=True)
        model_options = {}

    clip_type = getattr(
        comfy.sd.CLIPType,
        str(clip_type_name or "stable_diffusion").upper(),
        comfy.sd.CLIPType.STABLE_DIFFUSION,
    )
    return comfy.sd.load_text_encoder_state_dicts(
        clip_type=clip_type,
        state_dicts=[sd],
        model_options=model_options,
        embedding_directory=folder_paths.get_folder_paths("embeddings"),
    )


def load_vae_from_path(vae_path):
    if str(vae_path).lower().endswith(".safetensors"):
        from safetensors.torch import load_file
        vae_sd = load_file(str(vae_path), device="cpu")
    else:
        vae_sd = comfy.utils.load_torch_file(str(vae_path), safe_load=True)
    return comfy.sd.VAE(sd=vae_sd)


# Initialize embedded ComfyUI before importing modules
load_embedded_comfy()
install_comfy_aimdo_stub()
install_av_stub()

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
        dtype = getattr(comfy.model_management, "intermediate_dtype", lambda: torch.float32)()
        latent = torch.zeros([batch_size, 4, height // 8, width // 8], device=self.device, dtype=dtype)
        return ({"samples": latent, "downscale_ratio_spacial": 8}, )

class VAEDecode:
    def decode(self, vae, samples):
        images = vae.decode(samples["samples"])
        if len(images.shape) == 5: #Combine batches
            images = images.reshape(-1, images.shape[-3], images.shape[-2], images.shape[-1])
        return (images, )

def common_ksampler(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent, denoise=1.0, disable_noise=False, start_step=None, last_step=None, force_full_denoise=False):
    latent_image = latent["samples"]
    try:
        latent_image = comfy.sample.fix_empty_latent_channels(model, latent_image, latent.get("downscale_ratio_spacial", None))
    except TypeError:
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
    out.pop("downscale_ratio_spacial", None)
    out["samples"] = samples
    return (out, )

class KSampler:
    def sample(self, model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, denoise=1.0):
        return common_ksampler(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent_image, denoise=denoise)

# --- Main Execution ---

def parse_args():
    parser = argparse.ArgumentParser(description="Generate image using ComfyUI backend")
    parser.add_argument("--model", required=True, help="Path to checkpoint or GGUF diffusion model file")
    parser.add_argument("--model-format", default="auto", choices=["auto", "checkpoint", "gguf"], help="Model file format")
    parser.add_argument("--clip-model", default="", help="Text encoder path/name for GGUF diffusion models")
    parser.add_argument("--vae-model", default="", help="VAE path/name for GGUF diffusion models")
    parser.add_argument("--prompt-enhancer-model", default="", help="Optional ERNIE prompt enhancer text encoder path/name")
    parser.add_argument("--clip-type", default="stable_diffusion", help="ComfyUI CLIPType name")
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
    parser.add_argument("--diagnose-only", action="store_true", help="Validate model wiring without sampling")
    return parser.parse_args()

def resolve_model_path(model_arg):
    path = Path(model_arg).expanduser()
    if path.is_dir():
        discovered = discover_model_file(path)
        if discovered:
            return str(discovered)
    if path.exists():
        return str(path)
    local_models = Path("models") / model_arg
    if local_models.exists():
        return str(local_models)
    comfy_models = Path(__file__).parent / "models" / "checkpoints" / model_arg
    if comfy_models.exists():
        return str(comfy_models)
    return str(path)


def discover_model_file(model_dir):
    model_dir = Path(model_dir)
    patterns = [
        "*ernie*image*turbo*.gguf",
        "*.gguf",
        "diffusion_models/*ernie*image*turbo*.safetensors",
        "diffusion_models/*.safetensors",
        "*.safetensors",
        "*.ckpt",
    ]
    for pattern in patterns:
        matches = sorted(
            (path for path in model_dir.glob(pattern) if path.is_file()),
            key=lambda path: (len(path.parts), str(path).lower()),
        )
        if matches:
            return matches[0].resolve()
    return None


def discover_aux_model(model_dir, kind):
    model_dir = Path(model_dir)
    patterns = {
        "clip": [
            "text_encoders/ministral-3-3b.safetensors",
            "ministral-3-3b.safetensors",
            "text_encoders/*ministral*.safetensors",
            "**/ministral-3-3b.safetensors",
            "**/*ministral*.safetensors",
        ],
        "vae": [
            "vae/flux2-vae.safetensors",
            "flux2-vae.safetensors",
            "vae/*vae*.safetensors",
            "**/flux2-vae.safetensors",
            "**/*vae*.safetensors",
        ],
        "prompt_enhancer": [
            "text_encoders/ernie-image-prompt-enhancer.safetensors",
            "ernie-image-prompt-enhancer.safetensors",
            "**/*prompt*enhancer*.safetensors",
        ],
    }.get(kind, [])
    for pattern in patterns:
        matches = sorted(
            (path for path in model_dir.glob(pattern) if path.is_file()),
            key=lambda path: (len(path.parts), str(path).lower()),
        )
        if matches:
            return matches[0].resolve()
    return None

def main():
    args = parse_args()
    model_arg_path = Path(args.model).expanduser()
    model_package_dir = model_arg_path if model_arg_path.is_dir() else None
    
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

    model_path = resolve_model_path(args.model)
    if not os.path.exists(model_path):
        print(f"Error: Model file not found at {model_path}")
        sys.exit(1)

    model_format = infer_model_format(model_path, args.model_format)
    print(f"  - Model format: {model_format}")

    try:
        if model_format == "gguf":
            model_info = inspect_gguf_model(model_path)
            print("[GGUF] Model info:")
            print(json.dumps(model_info, indent=2, ensure_ascii=False))

            clip_model_arg = args.clip_model
            vae_model_arg = args.vae_model
            prompt_enhancer_arg = args.prompt_enhancer_model
            if model_package_dir is not None:
                if not clip_model_arg:
                    discovered_clip = discover_aux_model(model_package_dir, "clip")
                    clip_model_arg = str(discovered_clip) if discovered_clip else ""
                if not vae_model_arg:
                    discovered_vae = discover_aux_model(model_package_dir, "vae")
                    vae_model_arg = str(discovered_vae) if discovered_vae else ""
                if not prompt_enhancer_arg:
                    discovered_prompt_enhancer = discover_aux_model(model_package_dir, "prompt_enhancer")
                    prompt_enhancer_arg = str(discovered_prompt_enhancer) if discovered_prompt_enhancer else ""

            clip_path = resolve_aux_model_path(clip_model_arg, "clip")
            vae_path = resolve_aux_model_path(vae_model_arg, "vae")
            missing_aux = []
            if clip_path is None or not clip_path.exists():
                missing_aux.append("--clip-model")
            if vae_path is None or not vae_path.exists():
                missing_aux.append("--vae-model")
            if missing_aux:
                print(
                    "Error: GGUF diffusion models require auxiliary ComfyUI models: "
                    + ", ".join(missing_aux)
                    + ". For ERNIE-Image-Turbo use a Ministral 3.3B text encoder "
                    "and flux2-vae.safetensors, stored outside C: under your chosen local model folder."
                )
                sys.exit(1)

            if args.diagnose_only:
                print("[DIAGNOSE] GGUF model and auxiliary paths are present.")
                print(f"[DIAGNOSE] clip_model={clip_path}")
                print(f"[DIAGNOSE] vae_model={vae_path}")
                if prompt_enhancer_arg:
                    print(f"[DIAGNOSE] prompt_enhancer_model={prompt_enhancer_arg}")
                return

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading GGUF diffusion model...")
            model = load_gguf_diffusion_model(model_path)

            clip_format = "gguf" if str(clip_path).lower().endswith(".gguf") else "checkpoint"
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading text encoder...")
            clip = load_clip_from_path(clip_path, clip_format, args.clip_type)

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading VAE...")
            vae = load_vae_from_path(vae_path)
        else:
            if args.diagnose_only:
                print("[DIAGNOSE] Checkpoint model path is present.")
                return

            print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading checkpoint...")
            model, clip, vae, clipvision = comfy.sd.load_checkpoint_guess_config(
                model_path,
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
