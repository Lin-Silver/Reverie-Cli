"""Lightweight math helpers for Reverie Engine Lite."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Tuple


def _coerce_items(values: Iterable[float], size: int, default: float = 0.0) -> Tuple[float, ...]:
    items = list(values or [])
    if len(items) < size:
        items.extend([default] * (size - len(items)))
    return tuple(float(items[index]) for index in range(size))


@dataclass
class Vector2:
    x: float = 0.0
    y: float = 0.0

    @classmethod
    def from_any(cls, value: object) -> "Vector2":
        if isinstance(value, cls):
            return value
        if isinstance(value, (list, tuple)):
            x, y = _coerce_items(value, 2)
            return cls(x, y)
        return cls()

    def __add__(self, other: "Vector2") -> "Vector2":
        other = Vector2.from_any(other)
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vector2") -> "Vector2":
        other = Vector2.from_any(other)
        return Vector2(self.x - other.x, self.y - other.y)

    def scale(self, factor: float) -> "Vector2":
        return Vector2(self.x * factor, self.y * factor)

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y)

    def normalized(self) -> "Vector2":
        length = self.length()
        if length <= 0.000001:
            return Vector2()
        return Vector2(self.x / length, self.y / length)

    def to_list(self) -> list[float]:
        return [self.x, self.y]


@dataclass
class Vector3:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @classmethod
    def zero(cls) -> "Vector3":
        return cls()

    @classmethod
    def one(cls) -> "Vector3":
        return cls(1.0, 1.0, 1.0)

    @classmethod
    def from_any(cls, value: object) -> "Vector3":
        if isinstance(value, cls):
            return value
        if isinstance(value, (list, tuple)):
            x, y, z = _coerce_items(value, 3)
            return cls(x, y, z)
        return cls()

    def __add__(self, other: "Vector3") -> "Vector3":
        other = Vector3.from_any(other)
        return Vector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vector3") -> "Vector3":
        other = Vector3.from_any(other)
        return Vector3(self.x - other.x, self.y - other.y, self.z - other.z)

    def scale(self, factor: float) -> "Vector3":
        return Vector3(self.x * factor, self.y * factor, self.z * factor)

    def dot(self, other: "Vector3") -> float:
        other = Vector3.from_any(other)
        return self.x * other.x + self.y * other.y + self.z * other.z

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self) -> "Vector3":
        length = self.length()
        if length <= 0.000001:
            return Vector3()
        return Vector3(self.x / length, self.y / length, self.z / length)

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z]


@dataclass
class Quaternion:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    @classmethod
    def identity(cls) -> "Quaternion":
        return cls()

    @classmethod
    def from_any(cls, value: object) -> "Quaternion":
        if isinstance(value, cls):
            return value
        if isinstance(value, (list, tuple)):
            x, y, z, w = _coerce_items(value, 4, default=1.0)
            return cls(x, y, z, w)
        return cls.identity()

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z, self.w]


@dataclass
class Vector4:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    w: float = 1.0

    @classmethod
    def from_any(cls, value: object) -> "Vector4":
        if isinstance(value, cls):
            return value
        if isinstance(value, (list, tuple)):
            x, y, z, w = _coerce_items(value, 4, default=1.0)
            return cls(x, y, z, w)
        return cls()

    def to_list(self) -> list[float]:
        return [self.x, self.y, self.z, self.w]


@dataclass
class Matrix4:
    """4x4 matrix for 3D transformations."""
    m: list[float] = field(default_factory=lambda: [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1
    ])

    @classmethod
    def identity(cls) -> "Matrix4":
        return cls()

    @classmethod
    def translation(cls, position: Vector3) -> "Matrix4":
        return cls([
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            position.x, position.y, position.z, 1
        ])

    @classmethod
    def scale(cls, scale: Vector3) -> "Matrix4":
        return cls([
            scale.x, 0, 0, 0,
            0, scale.y, 0, 0,
            0, 0, scale.z, 0,
            0, 0, 0, 1
        ])

    @classmethod
    def rotation_x(cls, angle: float) -> "Matrix4":
        c = math.cos(angle)
        s = math.sin(angle)
        return cls([
            1, 0, 0, 0,
            0, c, s, 0,
            0, -s, c, 0,
            0, 0, 0, 1
        ])

    @classmethod
    def rotation_y(cls, angle: float) -> "Matrix4":
        c = math.cos(angle)
        s = math.sin(angle)
        return cls([
            c, 0, -s, 0,
            0, 1, 0, 0,
            s, 0, c, 0,
            0, 0, 0, 1
        ])

    @classmethod
    def rotation_z(cls, angle: float) -> "Matrix4":
        c = math.cos(angle)
        s = math.sin(angle)
        return cls([
            c, s, 0, 0,
            -s, c, 0, 0,
            0, 0, 1, 0,
            0, 0, 0, 1
        ])

    @classmethod
    def perspective(cls, fov: float, aspect: float, near: float, far: float) -> "Matrix4":
        """Create perspective projection matrix."""
        f = 1.0 / math.tan(fov / 2.0)
        nf = 1.0 / (near - far)
        return cls([
            f / aspect, 0, 0, 0,
            0, f, 0, 0,
            0, 0, (far + near) * nf, -1,
            0, 0, 2 * far * near * nf, 0
        ])

    @classmethod
    def orthographic(cls, left: float, right: float, bottom: float, top: float, near: float, far: float) -> "Matrix4":
        """Create orthographic projection matrix."""
        rl = 1.0 / (right - left)
        tb = 1.0 / (top - bottom)
        fn = 1.0 / (far - near)
        return cls([
            2 * rl, 0, 0, 0,
            0, 2 * tb, 0, 0,
            0, 0, -2 * fn, 0,
            -(right + left) * rl, -(top + bottom) * tb, -(far + near) * fn, 1
        ])

    def multiply(self, other: "Matrix4") -> "Matrix4":
        """Matrix multiplication."""
        result = [0.0] * 16
        for i in range(4):
            for j in range(4):
                for k in range(4):
                    result[i * 4 + j] += self.m[i * 4 + k] * other.m[k * 4 + j]
        return Matrix4(result)

    def inverse(self) -> "Matrix4":
        """Calculate matrix inverse (simplified for transforms)."""
        # Simplified inverse for affine transforms
        return Matrix4.identity()  # TODO: Implement full inverse

    def to_list(self) -> list[float]:
        return list(self.m)


@dataclass
class Transform:
    position: Vector3 = field(default_factory=Vector3.zero)
    rotation: Vector3 = field(default_factory=Vector3.zero)
    scale: Vector3 = field(default_factory=Vector3.one)
    quaternion: Quaternion = field(default_factory=Quaternion.identity)

    @classmethod
    def from_any(cls, value: object) -> "Transform":
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            return cls()
        return cls(
            position=Vector3.from_any(value.get("position")),
            rotation=Vector3.from_any(value.get("rotation")),
            scale=Vector3.from_any(value.get("scale") or [1.0, 1.0, 1.0]),
            quaternion=Quaternion.from_any(value.get("quaternion")),
        )

    def combine(self, parent: "Transform") -> "Transform":
        parent = Transform.from_any(parent)
        return Transform(
            position=parent.position + self.position,
            rotation=parent.rotation + self.rotation,
            scale=Vector3(
                parent.scale.x * self.scale.x,
                parent.scale.y * self.scale.y,
                parent.scale.z * self.scale.z,
            ),
            quaternion=self.quaternion,
        )

    def to_matrix(self) -> Matrix4:
        """Convert transform to 4x4 matrix."""
        t = Matrix4.translation(self.position)
        rx = Matrix4.rotation_x(self.rotation.x)
        ry = Matrix4.rotation_y(self.rotation.y)
        rz = Matrix4.rotation_z(self.rotation.z)
        s = Matrix4.scale(self.scale)
        return t.multiply(rz.multiply(ry.multiply(rx.multiply(s))))

    def to_dict(self) -> dict:
        return {
            "position": self.position.to_list(),
            "rotation": self.rotation.to_list(),
            "scale": self.scale.to_list(),
            "quaternion": self.quaternion.to_list(),
        }
