"""Procedural 3D asset generation helpers for Reverie Engine projects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable
import base64
import json
import math
import struct

from PIL import Image, ImageDraw

from .modeling import project_modeling_paths, sync_model_registry


PRIMITIVE_MODEL_TYPES = ("box", "plane", "pyramid", "sphere")


@dataclass
class PrimitiveMesh:
    vertices: list[float]
    normals: list[float]
    uvs: list[float]
    indices: list[int]


def _sanitize_name(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_") or "primitive"


def _pad4(payload: bytes) -> bytes:
    while len(payload) % 4:
        payload += b"\x00"
    return payload


def _pack_floats(values: Iterable[float]) -> bytes:
    data = [float(item) for item in values]
    return struct.pack(f"<{len(data)}f", *data) if data else b""


def _pack_indices(values: Iterable[int]) -> tuple[bytes, int]:
    data = [int(item) for item in values]
    if not data:
        return b"", 5125
    component_type = 5123 if max(data) < 65536 else 5125
    if component_type == 5123:
        return struct.pack(f"<{len(data)}H", *data), component_type
    return struct.pack(f"<{len(data)}I", *data), component_type


def _min_max(values: list[float], stride: int) -> tuple[list[float], list[float]]:
    grouped = [values[index:index + stride] for index in range(0, len(values), stride)]
    mins = [min(item[column] for item in grouped) for column in range(stride)]
    maxs = [max(item[column] for item in grouped) for column in range(stride)]
    return mins, maxs


def _resolve_dimension(explicit: Any, fallback: float) -> float:
    try:
        value = float(explicit)
    except Exception:
        value = fallback
    return max(0.001, value)


def _project_vertex(x: float, y: float, z: float, width: int, height: int, scale: float) -> tuple[float, float]:
    screen_x = width * 0.5 + (x - z * 0.8) * scale
    screen_y = height * 0.62 - y * scale - (x + z) * scale * 0.18
    return screen_x, screen_y


def _build_box(width: float, height: float, depth: float) -> PrimitiveMesh:
    hw = width / 2.0
    hh = height / 2.0
    hd = depth / 2.0
    vertices = [
        -hw, -hh, hd, hw, -hh, hd, hw, hh, hd, -hw, hh, hd,
        hw, -hh, -hd, -hw, -hh, -hd, -hw, hh, -hd, hw, hh, -hd,
        -hw, hh, hd, hw, hh, hd, hw, hh, -hd, -hw, hh, -hd,
        -hw, -hh, -hd, hw, -hh, -hd, hw, -hh, hd, -hw, -hh, hd,
        hw, -hh, hd, hw, -hh, -hd, hw, hh, -hd, hw, hh, hd,
        -hw, -hh, -hd, -hw, -hh, hd, -hw, hh, hd, -hw, hh, -hd,
    ]
    normals = [
        0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1,
        0, 0, -1, 0, 0, -1, 0, 0, -1, 0, 0, -1,
        0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0,
        0, -1, 0, 0, -1, 0, 0, -1, 0, 0, -1, 0,
        1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0,
        -1, 0, 0, -1, 0, 0, -1, 0, 0, -1, 0, 0,
    ]
    uvs = [
        0, 1, 1, 1, 1, 0, 0, 0,
        0, 1, 1, 1, 1, 0, 0, 0,
        0, 1, 1, 1, 1, 0, 0, 0,
        0, 1, 1, 1, 1, 0, 0, 0,
        0, 1, 1, 1, 1, 0, 0, 0,
        0, 1, 1, 1, 1, 0, 0, 0,
    ]
    indices = [
        0, 1, 2, 0, 2, 3,
        4, 5, 6, 4, 6, 7,
        8, 9, 10, 8, 10, 11,
        12, 13, 14, 12, 14, 15,
        16, 17, 18, 16, 18, 19,
        20, 21, 22, 20, 22, 23,
    ]
    return PrimitiveMesh(vertices=vertices, normals=normals, uvs=uvs, indices=indices)


def _build_plane(width: float, depth: float) -> PrimitiveMesh:
    hw = width / 2.0
    hd = depth / 2.0
    return PrimitiveMesh(
        vertices=[-hw, 0.0, -hd, hw, 0.0, -hd, hw, 0.0, hd, -hw, 0.0, hd],
        normals=[0.0, 1.0, 0.0] * 4,
        uvs=[0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
        indices=[0, 1, 2, 0, 2, 3],
    )


def _build_pyramid(width: float, height: float, depth: float) -> PrimitiveMesh:
    hw = width / 2.0
    hh = height / 2.0
    hd = depth / 2.0
    apex = (0.0, hh, 0.0)
    base_a = (-hw, -hh, -hd)
    base_b = (hw, -hh, -hd)
    base_c = (hw, -hh, hd)
    base_d = (-hw, -hh, hd)

    def face_normal(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> tuple[float, float, float]:
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cross = (
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        )
        length = math.sqrt(cross[0] ** 2 + cross[1] ** 2 + cross[2] ** 2) or 1.0
        return (cross[0] / length, cross[1] / length, cross[2] / length)

    faces = [
        (base_a, base_b, base_c, base_d, (0.0, -1.0, 0.0)),
        (base_d, base_c, apex, None, face_normal(base_d, base_c, apex)),
        (base_c, base_b, apex, None, face_normal(base_c, base_b, apex)),
        (base_b, base_a, apex, None, face_normal(base_b, base_a, apex)),
        (base_a, base_d, apex, None, face_normal(base_a, base_d, apex)),
    ]
    vertices: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    indices: list[int] = []
    cursor = 0

    for first, second, third, fourth, normal in faces:
        verts = [first, second, third] if fourth is None else [first, second, third, fourth]
        vertices.extend([component for item in verts for component in item])
        normals.extend(list(normal) * len(verts))
        if len(verts) == 4:
            uvs.extend([0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
            indices.extend([cursor, cursor + 1, cursor + 2, cursor, cursor + 2, cursor + 3])
            cursor += 4
        else:
            uvs.extend([0.0, 1.0, 1.0, 1.0, 0.5, 0.0])
            indices.extend([cursor, cursor + 1, cursor + 2])
            cursor += 3

    return PrimitiveMesh(vertices=vertices, normals=normals, uvs=uvs, indices=indices)


def _build_sphere(radius: float, segments: int) -> PrimitiveMesh:
    lat_segments = max(6, int(segments))
    lon_segments = max(12, int(segments) * 2)
    vertices: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    indices: list[int] = []

    for lat in range(lat_segments + 1):
        v = lat / lat_segments
        phi = math.pi * v
        sin_phi = math.sin(phi)
        cos_phi = math.cos(phi)
        for lon in range(lon_segments + 1):
            u = lon / lon_segments
            theta = u * math.pi * 2.0
            sin_theta = math.sin(theta)
            cos_theta = math.cos(theta)
            x = radius * sin_phi * cos_theta
            y = radius * cos_phi
            z = radius * sin_phi * sin_theta
            vertices.extend([x, y, z])
            length = math.sqrt(x * x + y * y + z * z) or 1.0
            normals.extend([x / length, y / length, z / length])
            uvs.extend([u, 1.0 - v])

    ring = lon_segments + 1
    for lat in range(lat_segments):
        for lon in range(lon_segments):
            first = lat * ring + lon
            second = first + ring
            indices.extend([first, second, first + 1, second, second + 1, first + 1])

    return PrimitiveMesh(vertices=vertices, normals=normals, uvs=uvs, indices=indices)


def build_primitive_mesh(
    primitive: str,
    *,
    size: float = 1.0,
    width: float | None = None,
    height: float | None = None,
    depth: float | None = None,
    radius: float | None = None,
    segments: int = 12,
) -> PrimitiveMesh:
    primitive_key = str(primitive or "box").strip().lower()
    base_size = _resolve_dimension(size, 1.0)
    resolved_width = _resolve_dimension(width, base_size)
    resolved_height = _resolve_dimension(height, base_size)
    resolved_depth = _resolve_dimension(depth, base_size)
    resolved_radius = _resolve_dimension(radius, base_size / 2.0)

    if primitive_key == "plane":
        return _build_plane(resolved_width, resolved_depth)
    if primitive_key == "pyramid":
        return _build_pyramid(resolved_width, resolved_height, resolved_depth)
    if primitive_key == "sphere":
        return _build_sphere(resolved_radius, segments)
    return _build_box(resolved_width, resolved_height, resolved_depth)


def build_gltf_document(mesh: PrimitiveMesh, *, model_name: str) -> Dict[str, Any]:
    positions_blob = _pad4(_pack_floats(mesh.vertices))
    normals_blob = _pad4(_pack_floats(mesh.normals))
    uvs_blob = _pad4(_pack_floats(mesh.uvs))
    index_blob, index_component_type = _pack_indices(mesh.indices)
    index_blob = _pad4(index_blob)
    joined = positions_blob + normals_blob + uvs_blob + index_blob
    positions_min, positions_max = _min_max(mesh.vertices, 3)
    buffer_uri = "data:application/octet-stream;base64," + base64.b64encode(joined).decode("ascii")
    index_count = len(mesh.indices)
    return {
        "asset": {
            "version": "2.0",
            "generator": "Reverie Engine Primitive Builder",
        },
        "scene": 0,
        "scenes": [{"name": model_name, "nodes": [0]}],
        "nodes": [{"name": model_name, "mesh": 0}],
        "meshes": [
            {
                "name": model_name,
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "NORMAL": 1,
                            "TEXCOORD_0": 2,
                        },
                        "indices": 3,
                        "material": 0,
                        "mode": 4,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": "reverie_default",
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.72, 0.78, 0.9, 1.0],
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.88,
                }
            }
        ],
        "buffers": [{"byteLength": len(joined), "uri": buffer_uri}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions_blob), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions_blob), "byteLength": len(normals_blob), "target": 34962},
            {"buffer": 0, "byteOffset": len(positions_blob) + len(normals_blob), "byteLength": len(uvs_blob), "target": 34962},
            {
                "buffer": 0,
                "byteOffset": len(positions_blob) + len(normals_blob) + len(uvs_blob),
                "byteLength": len(index_blob),
                "target": 34963,
            },
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": len(mesh.vertices) // 3,
                "type": "VEC3",
                "min": positions_min,
                "max": positions_max,
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": len(mesh.normals) // 3,
                "type": "VEC3",
            },
            {
                "bufferView": 2,
                "componentType": 5126,
                "count": len(mesh.uvs) // 2,
                "type": "VEC2",
            },
            {
                "bufferView": 3,
                "componentType": index_component_type,
                "count": index_count,
                "type": "SCALAR",
                "min": [min(mesh.indices) if mesh.indices else 0],
                "max": [max(mesh.indices) if mesh.indices else 0],
            },
        ],
    }


def _draw_preview(mesh: PrimitiveMesh, *, width: int = 768, height: int = 768) -> Image.Image:
    image = Image.new("RGBA", (width, height), (246, 248, 252, 255))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, width, height), fill=(241, 244, 250, 255))

    vertices = [
        tuple(mesh.vertices[index:index + 3])
        for index in range(0, len(mesh.vertices), 3)
    ]
    triangles: list[tuple[float, tuple[tuple[float, float], tuple[float, float], tuple[float, float]], int]] = []
    scale = min(width, height) * 0.28

    for start in range(0, len(mesh.indices), 3):
        a = vertices[mesh.indices[start]]
        b = vertices[mesh.indices[start + 1]]
        c = vertices[mesh.indices[start + 2]]
        projected = (
            _project_vertex(a[0], a[1], a[2], width, height, scale),
            _project_vertex(b[0], b[1], b[2], width, height, scale),
            _project_vertex(c[0], c[1], c[2], width, height, scale),
        )
        average_depth = (a[2] + b[2] + c[2]) / 3.0
        shade = max(86, min(210, int(150 + average_depth * 80)))
        triangles.append((average_depth, projected, shade))

    for _, polygon, shade in sorted(triangles, key=lambda item: item[0]):
        draw.polygon(polygon, fill=(shade, shade + 12, min(255, shade + 36), 220), outline=(62, 74, 94, 180))

    draw.rounded_rectangle((32, 32, width - 32, height - 32), radius=24, outline=(82, 96, 118, 110), width=2)
    return image


def create_primitive_model(
    project_root: str | Path,
    model_name: str,
    *,
    primitive: str = "box",
    size: float = 1.0,
    width: float | None = None,
    height: float | None = None,
    depth: float | None = None,
    radius: float | None = None,
    segments: int = 12,
    overwrite: bool = False,
    create_preview: bool = True,
) -> Dict[str, Any]:
    paths = project_modeling_paths(project_root)
    runtime_dir = paths["runtime_models"]
    preview_dir = paths["preview_renders"]
    runtime_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    normalized_name = _sanitize_name(model_name)
    mesh = build_primitive_mesh(
        primitive,
        size=size,
        width=width,
        height=height,
        depth=depth,
        radius=radius,
        segments=segments,
    )
    gltf_path = runtime_dir / f"{normalized_name}.gltf"
    preview_path = preview_dir / f"{normalized_name}.png"

    if gltf_path.exists() and not overwrite:
        raise FileExistsError(f"Target already exists: {gltf_path}")
    if create_preview and preview_path.exists() and not overwrite:
        raise FileExistsError(f"Target already exists: {preview_path}")

    gltf_payload = build_gltf_document(mesh, model_name=str(model_name or normalized_name))
    gltf_path.write_text(json.dumps(gltf_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    preview_written = ""
    if create_preview:
        preview = _draw_preview(mesh)
        preview.save(preview_path, format="PNG")
        preview_written = str(preview_path)

    registry = sync_model_registry(paths["project_root"], overwrite=True)
    return {
        "primitive": str(primitive or "box").strip().lower(),
        "runtime_path": str(gltf_path),
        "preview_path": preview_written,
        "registry": registry,
        "mesh_summary": {
            "vertex_count": len(mesh.vertices) // 3,
            "triangle_count": len(mesh.indices) // 3,
            "segments": int(max(3, segments)),
        },
    }


__all__ = [
    "PRIMITIVE_MODEL_TYPES",
    "PrimitiveMesh",
    "build_gltf_document",
    "build_primitive_mesh",
    "create_primitive_model",
]
