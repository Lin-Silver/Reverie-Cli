"""Blender authoring for a source-preserving, parameter-driven 2D avatar.

Eye/mouth coordinates must be authored against the actual portrait. This builds
2D mesh deformation and expression masks; it does not generate Cubism binaries.
"""

from pathlib import Path
import hashlib
import json
import math
import shutil
import sys

import bpy
import numpy as np


PARAMETERS = ("lookX", "lookY", "breath", "hairSway", "blinkLeft", "blinkRight", "mouthOpen", "smile")


def smoothstep(low, high, value):
    t = np.clip((value - low) / (high - low), 0, 1)
    return t * t * (3 - 2 * t)


def deformation(points, rig, parameter):
    x, y = points[:, 0], points[:, 1]
    pivot = rig["headPivot"]
    head = 1 - smoothstep(*rig["headBand"], y)
    body = smoothstep(*rig["bodyBand"], y) * (1 - smoothstep(*rig["feetBand"], y))
    hair = smoothstep(*rig["hairSides"], abs(x - pivot[0]))
    hair *= smoothstep(*rig["hairStart"], y) * (1 - smoothstep(*rig["hairEnd"], y))
    delta = np.zeros_like(points)
    if parameter == "lookX":
        delta[:, 0] = head * (24 + .055 * (y - pivot[1]))
        delta[:, 1] = -head * .055 * (x - pivot[0])
    elif parameter == "lookY":
        delta[:, 1] = head * 18
    elif parameter == "breath":
        delta[:, 0] = (x - pivot[0]) * .008 * body
        delta[:, 1] = -3 * body
    elif parameter == "hairSway":
        delta[:, 0] = 8 * hair
    return delta


def expression_patch(pixels, feature, kind, destination):
    height, width = pixels.shape[:2]
    cx, cy = map(float, feature["center"])
    rx, ry = map(float, feature["radius"])
    angle = math.radians(float(feature.get("angle", 0)))
    if rx <= 0 or ry <= 0 or not all(math.isfinite(v) for v in (cx, cy, rx, ry, angle)):
        raise ValueError(f"Invalid {kind} feature coordinates")
    margin = math.ceil(max(rx, ry) + 7)
    x0, y0 = math.floor(cx - margin), math.floor(cy - margin)
    x1, y1 = math.ceil(cx + margin), math.ceil(cy + margin)
    if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
        raise ValueError(f"{kind} feature must fit inside the source image")
    sx, sy = map(int, feature["skinSample"])
    if not (0 <= sx < width and 0 <= sy < height) or pixels[sy, sx, 3] < .5:
        raise ValueError(f"{kind} skinSample must be on the opaque face")
    yy, xx = np.mgrid[y0:y1, x0:x1]
    dx, dy = xx - cx, yy - cy
    u = dx * math.cos(angle) + dy * math.sin(angle)
    v = -dx * math.sin(angle) + dy * math.cos(angle)
    distance = np.sqrt((u / rx) ** 2 + (v / ry) ** 2)
    mask = 1 - smoothstep(.90, 1.10, distance)
    sample = pixels[max(0, sy - 2):sy + 3, max(0, sx - 2):sx + 3, :3].mean(axis=(0, 1))
    result = pixels[y0:y1, x0:x1].copy()
    unknown = mask > .02
    result[unknown, :3] = sample
    # Extend the portrait's surrounding skin colors into the removed feature.
    # Fixed boundary pixels retain its blush, shadows and adjoining hair detail.
    for _ in range(240):
        neighbors = (result[:-2, 1:-1, :3] + result[2:, 1:-1, :3]
                     + result[1:-1, :-2, :3] + result[1:-1, 2:, :3]) * .25
        interior = result[1:-1, 1:-1, :3]
        interior[unknown[1:-1, 1:-1]] = neighbors[unknown[1:-1, 1:-1]]
    ink = np.asarray(feature.get("ink", [.28, .13, .39]), dtype=np.float32)
    if kind.startswith("blink"):
        q = u / (rx * .91)
        curve = .6 + 2.2 * (1 - q * q)
        stroke = (1 - smoothstep(.3, 1.0, abs(v - curve))) * (abs(q) < 1)
        result[:, :, :3] = result[:, :, :3] * (1 - stroke[:, :, None]) + ink * stroke[:, :, None]
    elif kind == "mouthOpen":
        ellipse = np.sqrt((u / (rx * .68)) ** 2 + (v / (ry * .95)) ** 2)
        lip = 1 - smoothstep(.88, 1.15, ellipse)
        interior = np.asarray([.29, .10, .20], dtype=np.float32)
        result[:, :, :3] = result[:, :, :3] * (1 - lip[:, :, None]) + interior * lip[:, :, None]
        tongue = (1 - smoothstep(.4, 1.2, abs(v - ry * .40))) * (abs(u) < rx * .35) * lip
        result[:, :, :3] = result[:, :, :3] * (1 - tongue[:, :, None]) + np.asarray([.69, .37, .48]) * tongue[:, :, None]
    else:
        q = u / (rx * .85)
        curve = -2.0 + 3.0 * (1 - q * q)
        stroke = (1 - smoothstep(.4, 1.15, abs(v - curve))) * (abs(q) < 1)
        result[:, :, :3] = result[:, :, :3] * (1 - stroke[:, :, None]) + ink * stroke[:, :, None]
    result[:, :, 3] = mask
    image = bpy.data.images.new(kind, x1 - x0, y1 - y0, alpha=True)
    image.colorspace_settings.name = "sRGB"
    image.pixels.foreach_set(np.ascontiguousarray(result[::-1]).ravel())
    image.filepath_raw = str(destination)
    image.file_format = "PNG"
    image.save()
    image.pack()
    return image, [x0, y0, x1 - x0, y1 - y0]


def image_material(image, controls, parameter=None):
    material = bpy.data.materials.new(image.name + " portrait emission")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    emission = nodes.new("ShaderNodeEmission")
    links.new(texture.outputs["Color"], emission.inputs["Color"])
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    mix = nodes.new("ShaderNodeMixShader")
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(emission.outputs[0], mix.inputs[2])
    if parameter:
        factor = nodes.new("ShaderNodeMath")
        factor.operation = "MULTIPLY"
        links.new(texture.outputs["Alpha"], factor.inputs[0])
        factor.inputs[1].default_value = 0
        driver = factor.inputs[1].driver_add("default_value").driver
        variable = driver.variables.new()
        variable.name, variable.type = "value", "SINGLE_PROP"
        variable.targets[0].id = controls
        variable.targets[0].data_path = f'["{parameter}"]'
        driver.expression = "value"
        links.new(factor.outputs[0], mix.inputs[0])
    else:
        links.new(texture.outputs["Alpha"], mix.inputs[0])
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(mix.outputs[0], output.inputs["Surface"])
    material.surface_render_method = "DITHERED"
    return material


def portrait_mesh(name, points, faces, image, image_box, rig, controls, height, depth=0, parameter=None):
    scale = 1.8 / height
    vertices = [(x * scale, depth, (height - y) * scale) for x, y in points]
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.parent = controls
    uv = data.uv_layers.new(name="UVMap")
    for loop in data.loops:
        x, y = points[loop.vertex_index]
        uv.data[loop.index].uv = ((x - image_box[0]) / image_box[2], 1 - (y - image_box[1]) / image_box[3])
    data.materials.append(image_material(image, controls, parameter))
    obj.shape_key_add(name="Basis", from_mix=False)
    for name in PARAMETERS[:4]:
        key = obj.shape_key_add(name=name, from_mix=False)
        offsets = deformation(points, rig, name)
        for vertex, delta in zip(key.data, offsets):
            vertex.co.x += float(delta[0] * scale)
            vertex.co.z -= float(delta[1] * scale)
        key.value = 0
        key.slider_min, key.slider_max = -1, 1
        driver = key.driver_add("value").driver
        variable = driver.variables.new()
        variable.name, variable.type = "value", "SINGLE_PROP"
        variable.targets[0].id = controls
        variable.targets[0].data_path = f'["{name}"]'
        driver.expression = "value"
    return obj


def main(root):
    config = json.loads((root / "avatar-config.json").read_text(encoding="utf-8-sig"))
    source = (root / config["image"]).resolve()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source_image = bpy.data.images.load(str(source))
    width, height = source_image.size[:]
    pixels = np.empty(width * height * 4, dtype=np.float32)
    source_image.pixels.foreach_get(pixels)
    pixels = pixels.reshape(height, width, 4)[::-1].copy()
    if pixels[:, :, 3].min() > .1 or pixels[:, :, 3].max() < .5:
        raise ValueError("The avatar needs a nonempty portrait with real background transparency")
    rig = config["rig"]
    for name in ("headBand", "bodyBand", "feetBand", "hairSides", "hairStart", "hairEnd"):
        if len(rig[name]) != 2 or not all(math.isfinite(float(v)) for v in rig[name]) or rig[name][1] <= rig[name][0]:
            raise ValueError(f"{name} must contain two increasing, finite pixel coordinates")
    for name in ("headPivot", "faceCenter"):
        if len(rig[name]) != 2 or not all(math.isfinite(float(v)) for v in rig[name]):
            raise ValueError(f"{name} must contain two finite pixel coordinates")
    web = root / "web"
    assets = web / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, assets / "source.png")
    source_image.name = "Original portrait (unchanged)"
    source_image.pack()
    source_image.filepath = "//web/assets/source.png"
    controls = bpy.data.objects.new("Avatar controls", None)
    bpy.context.scene.collection.objects.link(controls)
    for name in PARAMETERS:
        controls[name] = 0.0
        controls.id_properties_ui(name).update(min=-1 if name in ("lookX", "lookY", "hairSway") else 0, max=1)
    columns, rows = 48, 72
    points = np.asarray([(width * x / columns, height * y / rows)
                         for y in range(rows + 1) for x in range(columns + 1)], dtype=np.float32)
    faces = [(y * (columns + 1) + x, y * (columns + 1) + x + 1,
              (y + 1) * (columns + 1) + x + 1, (y + 1) * (columns + 1) + x)
             for y in range(rows) for x in range(columns)]
    portrait_mesh("Portrait deform mesh", points, faces, source_image, [0, 0, width, height], rig, controls, height)
    expressions = {}
    for name, feature in (("blinkLeft", config["eyes"]["left"]), ("blinkRight", config["eyes"]["right"]),
                          ("mouthOpen", config["mouth"]), ("smile", config["mouth"])):
        filename = f"{name}.png"
        image, box = expression_patch(pixels, feature, name, assets / filename)
        image.filepath = f"//web/assets/{filename}"
        x, y, w, h = box
        corners = np.asarray([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], dtype=np.float32)
        portrait_mesh(name + " expression mask", corners, [(0, 1, 2, 3)], image, box, rig, controls, height,
                      depth=-.001 if name.startswith("blink") else -.002, parameter=name)
        expressions[name] = {"image": f"./assets/{filename}", "box": box}
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 8
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    camera_data = bpy.data.cameras.new("Portrait orthographic camera")
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    scene.collection.objects.link(camera)
    camera.location = (width / height * .9, -4, .9)
    camera.rotation_euler = (math.pi / 2, 0, 0)
    camera_data.type, camera_data.ortho_scale = "ORTHO", 1.8
    scene.camera = camera
    controls.select_set(True)
    bpy.context.view_layer.objects.active = controls
    bpy.ops.wm.save_as_mainfile(filepath=str(root / "avatar.blend"), compress=True)
    template = Path(__file__).resolve().parents[1] / "assets/avatar-template"
    shutil.copytree(template, web, dirs_exist_ok=True)
    manifest = {"schema": "reverie.2d-avatar.v1", "name": config.get("name", "Portrait avatar"),
                "width": width, "height": height, "image": "./assets/source.png", "rig": rig,
                "grid": [columns, rows], "expressions": expressions,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    (web / "avatar.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"passed": True, "blender_version": bpy.app.version_string,
              "source_size": [width, height], "source_sha256": manifest["source_sha256"],
              "source_bytes_preserved": source.read_bytes() == (assets / "source.png").read_bytes(),
              "deform_vertices": len(points), "parameters": list(PARAMETERS),
              "expression_masks": expressions, "images_packed": all(image.packed_file for image in bpy.data.images)}
    (root / "avatar-build-verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (root / "start-avatar.cmd").write_text('@echo off\ncd /d "%~dp0"\nnode web\\server.mjs\n', encoding="ascii")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[sys.argv.index("--") + 1]).resolve())
