"""External resource production only; the Rust application never invokes Python.

Install the fixed production packages in an isolated directory and provide its
path explicitly. The produced ONNX files have no Python runtime dependency.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        while data := source.read(1024 * 1024):
            value.update(data)
    return value.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest_sha256")
    parser.add_argument("--packages", type=Path, required=True)
    parser.add_argument("--pip-report", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.packages.resolve()))
    import onnx
    import onnxruntime
    from onnxruntime.quantization import QuantType, quantize_dynamic

    if onnx.__version__ != "1.23.2" or onnxruntime.__version__ != "1.31.0":
        raise RuntimeError("Production requires ONNX 1.23.2 and ONNX Runtime 1.31.0")
    source = args.source.resolve(strict=True)
    manifest_path = source / "manifest.json"
    if digest(manifest_path) != args.manifest_sha256:
        raise RuntimeError("Input manifest SHA-256 mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if any(manifest[role]["precision"] != "fp32" for role in ("embedding", "reranker")):
        raise RuntimeError("Quantization must start from the fixed FP32 control")
    for name, asset in manifest["files"].items():
        path = (source / name).resolve(strict=True)
        if not path.is_relative_to(source) or path.stat().st_size != asset["bytes"] or digest(path) != asset["sha256"]:
            raise RuntimeError(f"Invalid source asset: {name}")
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError("Output directory already exists; select a new directory")
    output.mkdir(parents=True)
    model_files = {manifest[role]["onnx"] for role in ("embedding", "reranker")}
    for name in manifest["files"]:
        if name not in model_files:
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target)
    started = time.monotonic()
    parameters = {
        "op_types_to_quantize": ["MatMul", "Gemm", "Gather"],
        "per_channel": True,
        "reduce_range": True,
        "weight_type": "QInt8",
        "use_external_data_format": False,
        "extra_options": {"MatMulConstBOnly": True},
    }
    quantized = {}
    for role in ("embedding", "reranker"):
        name = manifest[role]["onnx"]
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        quantize_dynamic(
            str(source / name), str(target),
            op_types_to_quantize=parameters["op_types_to_quantize"],
            per_channel=True, reduce_range=True, weight_type=QuantType.QInt8,
            use_external_data_format=False, extra_options=parameters["extra_options"],
        )
        onnx.checker.check_model(str(target))
        quantized[role] = {
            "input_sha256": manifest["files"][name]["sha256"],
            "output_sha256": digest(target), "bytes": target.stat().st_size,
        }
        manifest[role]["precision"] = "dynamic-int8"
        print(json.dumps({"quantized": role, **quantized[role]}, ensure_ascii=False), flush=True)
    manifest["version"] = "e5-bge-generic-int8-v2"
    for name in manifest["files"]:
        path = output / name
        manifest["files"][name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    package_report = json.loads(args.pip_report.read_text(encoding="utf-8"))
    manifest["provenance"]["quantization"] = {
        "source_manifest_sha256": args.manifest_sha256,
        "producer_python": sys.version,
        "producer_script_sha256": digest(Path(__file__)),
        "onnx": onnx.__version__, "onnxruntime": onnxruntime.__version__,
        "packages": [{"name": item["metadata"]["name"], "version": item["metadata"]["version"],
                      "sha256": item["download_info"]["archive_info"]["hashes"]["sha256"]}
                     for item in package_report["install"]],
        "parameters": parameters, "models": quantized,
        "seconds": time.monotonic() - started,
        "scope": "Generic dynamic INT8 production; cross-platform loading, quality and latency require actual Rust validation.",
    }
    manifest["provenance"]["purpose"] = "Generic CPU INT8 candidate produced from fixed official FP32 weights; quality acceptance remains separate."
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"directory": str(output), "manifest_sha256": digest(manifest_path),
                      "bytes": sum(asset["bytes"] for asset in manifest["files"].values())}), flush=True)


if __name__ == "__main__":
    main()
