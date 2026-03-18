"""Physics services for Reverie Engine, inspired by Godot's space-state APIs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, TYPE_CHECKING

from .components import ColliderComponent, RigidBodyComponent
from .math3d import Vector3

if TYPE_CHECKING:
    from .scene import Node


EPSILON = 0.000001
KINEMATIC_EPSILON = 0.001


@dataclass
class CollisionRecord:
    node_name: str
    layer: str
    is_trigger: bool
    normal: Vector3 = field(default_factory=lambda: Vector3(0.0, 1.0, 0.0))
    depth: float = 0.0


@dataclass
class RaycastResult:
    """Result of a raycast query."""

    node_name: str
    layer: str
    is_trigger: bool
    position: Vector3
    normal: Vector3
    distance: float


@dataclass
class PhysicsRayQueryParameters:
    """Ray query parameters modeled after Godot's direct space state APIs."""

    origin: Vector3 = field(default_factory=Vector3.zero)
    direction: Vector3 = field(default_factory=lambda: Vector3(1.0, 0.0, 0.0))
    max_distance: float = 100.0
    collision_mask: Optional[list[str]] = None
    exclude: set[str] = field(default_factory=set)
    collide_with_bodies: bool = True
    collide_with_areas: bool = True

    def __post_init__(self) -> None:
        self.origin = Vector3.from_any(self.origin)
        self.direction = Vector3.from_any(self.direction).normalized()
        self.max_distance = max(float(self.max_distance), 0.0)
        self.collision_mask = _normalize_mask(self.collision_mask)
        self.exclude = _normalize_exclude(self.exclude)


@dataclass
class PhysicsShapeQueryParameters:
    """Shape query parameters for overlap and motion tests."""

    shape: str = "box"
    position: Vector3 = field(default_factory=Vector3.zero)
    extents: Vector3 = field(default_factory=lambda: Vector3(0.5, 0.5, 0.5))
    radius: float = 0.5
    motion: Vector3 = field(default_factory=Vector3.zero)
    margin: float = 0.0
    collision_mask: Optional[list[str]] = None
    exclude: set[str] = field(default_factory=set)
    collide_with_bodies: bool = True
    collide_with_areas: bool = True

    def __post_init__(self) -> None:
        self.shape = str(self.shape or "box").strip().lower()
        self.position = Vector3.from_any(self.position)
        self.extents = Vector3.from_any(self.extents or [0.5, 0.5, 0.5])
        self.radius = max(float(self.radius), 0.0)
        self.motion = Vector3.from_any(self.motion)
        self.margin = max(float(self.margin), 0.0)
        self.collision_mask = _normalize_mask(self.collision_mask)
        self.exclude = _normalize_exclude(self.exclude)


@dataclass
class PhysicsMotionResult:
    """Result of a swept motion query."""

    collided: bool
    travel: Vector3
    remainder: Vector3
    safe_fraction: float = 1.0
    unsafe_fraction: float = 1.0
    collision: Optional[CollisionRecord] = None


class PhysicsSpaceState:
    """Queryable view of a physics space, similar to Godot's direct space state."""

    def __init__(
        self,
        nodes: Optional[Iterable["Node"]] = None,
        *,
        provider: Optional[Callable[[], Iterable["Node"]]] = None,
    ) -> None:
        self._nodes = list(nodes) if nodes is not None else None
        self._provider = provider

    def intersect_ray(
        self,
        parameters: PhysicsRayQueryParameters,
        *,
        nodes: Optional[Iterable["Node"]] = None,
    ) -> Optional[RaycastResult]:
        best: Optional[RaycastResult] = None
        for node in self._resolve_nodes(nodes):
            collider = _get_collider(node)
            if not collider or not _matches_query(node, collider, parameters):
                continue

            hit = _intersect_ray_with_collider(
                parameters.origin,
                parameters.direction,
                parameters.max_distance,
                node,
                collider,
            )
            if hit is None:
                continue

            distance, position, normal = hit
            result = RaycastResult(
                node_name=node.name,
                layer=collider.layer,
                is_trigger=collider.is_trigger,
                position=position,
                normal=normal,
                distance=distance,
            )
            if best is None or result.distance < best.distance:
                best = result

        return best

    def intersect_shape(
        self,
        parameters: PhysicsShapeQueryParameters,
        *,
        nodes: Optional[Iterable["Node"]] = None,
        max_results: int = 32,
    ) -> list[CollisionRecord]:
        results: list[CollisionRecord] = []
        for node in self._resolve_nodes(nodes):
            collider = _get_collider(node)
            if not collider or not _matches_query(node, collider, parameters):
                continue

            manifold = _overlap_shape_with_collider(parameters, node, collider)
            if manifold is None:
                continue

            normal, depth = manifold
            results.append(
                CollisionRecord(
                    node_name=node.name,
                    layer=collider.layer,
                    is_trigger=collider.is_trigger,
                    normal=normal,
                    depth=depth,
                )
            )
            if len(results) >= max(int(max_results), 0):
                break

        return results

    def cast_motion(
        self,
        parameters: PhysicsShapeQueryParameters,
        *,
        nodes: Optional[Iterable["Node"]] = None,
    ) -> PhysicsMotionResult:
        existing = self.intersect_shape(parameters, nodes=nodes, max_results=1)
        if existing:
            return PhysicsMotionResult(
                collided=True,
                travel=Vector3.zero(),
                remainder=Vector3.from_any(parameters.motion),
                safe_fraction=0.0,
                unsafe_fraction=0.0,
                collision=existing[0],
            )

        motion = Vector3.from_any(parameters.motion)
        distance = motion.length()
        if distance <= EPSILON:
            return PhysicsMotionResult(
                collided=False,
                travel=Vector3.zero(),
                remainder=Vector3.zero(),
                safe_fraction=1.0,
                unsafe_fraction=1.0,
                collision=None,
            )

        direction = motion.scale(1.0 / distance)
        best_fraction = 1.0
        best_collision: Optional[CollisionRecord] = None

        for node in self._resolve_nodes(nodes):
            collider = _get_collider(node)
            if not collider or not _matches_query(node, collider, parameters):
                continue

            hit = _cast_shape_against_collider(parameters, direction, distance, node, collider)
            if hit is None:
                continue

            fraction, normal = hit
            if fraction < best_fraction:
                best_fraction = fraction
                best_collision = CollisionRecord(
                    node_name=node.name,
                    layer=collider.layer,
                    is_trigger=collider.is_trigger,
                    normal=normal,
                    depth=0.0,
                )

        if best_collision is None:
            return PhysicsMotionResult(
                collided=False,
                travel=motion,
                remainder=Vector3.zero(),
                safe_fraction=1.0,
                unsafe_fraction=1.0,
                collision=None,
            )

        safe_fraction = max(min(best_fraction, 1.0) - KINEMATIC_EPSILON, 0.0)
        unsafe_fraction = min(best_fraction, 1.0)
        travel = motion.scale(safe_fraction)
        remainder = motion - travel
        return PhysicsMotionResult(
            collided=True,
            travel=travel,
            remainder=remainder,
            safe_fraction=safe_fraction,
            unsafe_fraction=unsafe_fraction,
            collision=best_collision,
        )

    def _resolve_nodes(self, nodes: Optional[Iterable["Node"]]) -> list["Node"]:
        if nodes is not None:
            return list(nodes)
        if self._nodes is not None:
            return list(self._nodes)
        if self._provider is not None:
            return list(self._provider())
        return []


class PhysicsWorld:
    """Physics simulation world with query and simulation service layers."""

    def __init__(self) -> None:
        self.gravity = Vector3(0.0, -9.8, 0.0)
        self.bodies: list["Node"] = []
        self.space_state = PhysicsSpaceState(provider=lambda: self.bodies)

    def add_body(self, node: "Node") -> None:
        if node not in self.bodies:
            self.bodies.append(node)

    def remove_body(self, node: "Node") -> None:
        if node in self.bodies:
            self.bodies.remove(node)

    def step(self, delta: float) -> None:
        for body in self.bodies:
            rb = body.get_component("RigidBody")
            if not isinstance(rb, RigidBodyComponent) or not rb.enabled:
                continue
            if rb.is_kinematic:
                continue

            if rb.gravity_scale != 0:
                rb.velocity = rb.velocity + self.gravity.scale(rb.gravity_scale * delta)

            if rb.linear_damp > 0:
                damp_factor = max(0.0, 1.0 - rb.linear_damp * delta)
                rb.velocity = rb.velocity.scale(damp_factor)

            if rb.angular_damp > 0:
                damp_factor = max(0.0, 1.0 - rb.angular_damp * delta)
                rb.angular_velocity = rb.angular_velocity.scale(damp_factor)

            displacement = rb.velocity.scale(delta)
            body.transform.position = body.transform.position + displacement

            if not rb.freeze_rotation:
                rotation_delta = rb.angular_velocity.scale(delta)
                body.transform.rotation = body.transform.rotation + rotation_delta

    def resolve_collisions(self) -> list[CollisionRecord]:
        collisions: list[CollisionRecord] = []
        for index, body_a in enumerate(self.bodies):
            collider_a = _get_collider(body_a)
            if not collider_a:
                continue

            for body_b in self.bodies[index + 1 :]:
                collider_b = _get_collider(body_b)
                if not collider_b or not _pair_should_collide(collider_a, collider_b):
                    continue

                manifold = _overlap_between_nodes(body_a, collider_a, body_b, collider_b)
                if manifold is None:
                    continue

                normal, depth = manifold
                collisions.append(
                    CollisionRecord(
                        node_name=body_b.name,
                        layer=collider_b.layer,
                        is_trigger=collider_b.is_trigger,
                        normal=normal,
                        depth=depth,
                    )
                )

                if not collider_a.is_trigger and not collider_b.is_trigger:
                    self._resolve_collision(body_a, body_b, normal, depth)

        return collisions

    def intersect_ray(self, parameters: PhysicsRayQueryParameters) -> Optional[RaycastResult]:
        return self.space_state.intersect_ray(parameters)

    def intersect_shape(self, parameters: PhysicsShapeQueryParameters, *, max_results: int = 32) -> list[CollisionRecord]:
        return self.space_state.intersect_shape(parameters, max_results=max_results)

    def cast_motion(self, parameters: PhysicsShapeQueryParameters) -> PhysicsMotionResult:
        return self.space_state.cast_motion(parameters)

    def _resolve_collision(self, body_a: "Node", body_b: "Node", normal: Vector3, depth: float) -> None:
        rb_a = body_a.get_component("RigidBody")
        rb_b = body_b.get_component("RigidBody")

        correction = normal.scale(max(depth, 0.0) * 0.5)

        if isinstance(rb_a, RigidBodyComponent) and not rb_a.is_kinematic:
            body_a.transform.position = body_a.transform.position - correction
        if isinstance(rb_b, RigidBodyComponent) and not rb_b.is_kinematic:
            body_b.transform.position = body_b.transform.position + correction

        if not isinstance(rb_a, RigidBodyComponent) or not isinstance(rb_b, RigidBodyComponent):
            return

        relative_velocity = rb_b.velocity - rb_a.velocity
        velocity_along_normal = relative_velocity.dot(normal)
        if velocity_along_normal > 0:
            return

        mass_a = max(float(rb_a.mass), EPSILON)
        mass_b = max(float(rb_b.mass), EPSILON)
        restitution = 0.5
        impulse_scalar = -(1.0 + restitution) * velocity_along_normal
        impulse_scalar /= (1.0 / mass_a) + (1.0 / mass_b)
        impulse = normal.scale(impulse_scalar)

        if not rb_a.is_kinematic:
            rb_a.velocity = rb_a.velocity - impulse.scale(1.0 / mass_a)
        if not rb_b.is_kinematic:
            rb_b.velocity = rb_b.velocity + impulse.scale(1.0 / mass_b)


def _get_collider(node: "Node") -> Optional[ColliderComponent]:
    component = node.get_component("Collider")
    if isinstance(component, ColliderComponent) and component.enabled:
        return component
    return None


def _normalize_mask(mask: Optional[Iterable[str]]) -> Optional[list[str]]:
    if mask is None:
        return None
    values = [str(item).strip() for item in mask if str(item).strip()]
    return values


def _normalize_exclude(values: Iterable[str]) -> set[str]:
    return {str(item).strip() for item in values if str(item).strip()}


def _layer_in_mask(layer: str, mask: Optional[list[str]]) -> bool:
    if mask is None:
        return True
    return str(layer) in mask


def _pair_should_collide(collider_a: ColliderComponent, collider_b: ColliderComponent) -> bool:
    return _layer_in_mask(collider_b.layer, list(collider_a.mask)) or _layer_in_mask(
        collider_a.layer,
        list(collider_b.mask),
    )


def _matches_query(
    node: "Node",
    collider: ColliderComponent,
    query: PhysicsRayQueryParameters | PhysicsShapeQueryParameters,
) -> bool:
    if node.name in query.exclude or node.node_path in query.exclude:
        return False
    if collider.is_trigger and not query.collide_with_areas:
        return False
    if not collider.is_trigger and not query.collide_with_bodies:
        return False
    return _layer_in_mask(collider.layer, query.collision_mask)


def half_extents(collider: ColliderComponent) -> Vector3:
    if collider.shape == "sphere":
        return Vector3(collider.radius, collider.radius, collider.radius)
    size = Vector3.from_any(collider.size)
    return Vector3(size.x * 0.5, size.y * 0.5, size.z * 0.5 if abs(size.z) > EPSILON else 0.5)


def world_center(node: "Node") -> Vector3:
    return node.world_transform().position


def _vector_on_axis(axis: str, value: float) -> Vector3:
    if axis == "x":
        return Vector3(value, 0.0, 0.0)
    if axis == "y":
        return Vector3(0.0, value, 0.0)
    return Vector3(0.0, 0.0, value)


def _closest_point(point: Vector3, minimum: Vector3, maximum: Vector3) -> Vector3:
    return Vector3(
        max(minimum.x, min(point.x, maximum.x)),
        max(minimum.y, min(point.y, maximum.y)),
        max(minimum.z, min(point.z, maximum.z)),
    )


def _box_bounds(center: Vector3, extents: Vector3) -> tuple[Vector3, Vector3]:
    return center - extents, center + extents


def _collider_bounds(node: "Node", collider: ColliderComponent) -> tuple[Vector3, Vector3]:
    center = world_center(node)
    extents = half_extents(collider)
    return _box_bounds(center, extents)


def _box_box_manifold(center_a: Vector3, extents_a: Vector3, center_b: Vector3, extents_b: Vector3) -> Optional[tuple[Vector3, float]]:
    delta = center_b - center_a
    overlap_x = (extents_a.x + extents_b.x) - abs(delta.x)
    overlap_y = (extents_a.y + extents_b.y) - abs(delta.y)
    overlap_z = (extents_a.z + extents_b.z) - abs(delta.z)
    if overlap_x < 0 or overlap_y < 0 or overlap_z < 0:
        return None

    axes = [
        ("x", overlap_x, delta.x),
        ("y", overlap_y, delta.y),
        ("z", overlap_z, delta.z),
    ]
    axis, depth, axis_delta = min(axes, key=lambda item: item[1])
    direction = 1.0 if axis_delta >= 0 else -1.0
    return _vector_on_axis(axis, direction), depth


def _sphere_sphere_manifold(center_a: Vector3, radius_a: float, center_b: Vector3, radius_b: float) -> Optional[tuple[Vector3, float]]:
    delta = center_b - center_a
    distance = delta.length()
    radius_sum = radius_a + radius_b
    if distance > radius_sum:
        return None
    if distance <= EPSILON:
        return Vector3(0.0, 1.0, 0.0), radius_sum
    return delta.normalized(), radius_sum - distance


def _sphere_box_manifold(
    sphere_center: Vector3,
    sphere_radius: float,
    box_center: Vector3,
    box_extents: Vector3,
    *,
    box_is_target: bool,
) -> Optional[tuple[Vector3, float]]:
    minimum, maximum = _box_bounds(box_center, box_extents)
    closest = _closest_point(sphere_center, minimum, maximum)
    delta = box_center - sphere_center if box_is_target else sphere_center - closest
    offset = sphere_center - closest
    distance = offset.length()
    if distance > sphere_radius:
        return None
    if distance <= EPSILON:
        fallback = delta.normalized() if delta.length() > EPSILON else Vector3(0.0, 1.0, 0.0)
        return fallback, sphere_radius
    normal = offset.normalized()
    return (normal if box_is_target else normal.scale(-1.0)), sphere_radius - distance


def _overlap_shape_with_collider(
    query: PhysicsShapeQueryParameters,
    node: "Node",
    collider: ColliderComponent,
) -> Optional[tuple[Vector3, float]]:
    collider_center = world_center(node)
    collider_extents = half_extents(collider)
    collider_radius = float(collider.radius)

    if query.shape == "sphere" and collider.shape == "sphere":
        return _sphere_sphere_manifold(query.position, query.radius + query.margin, collider_center, collider_radius)

    if query.shape == "sphere":
        return _sphere_box_manifold(
            query.position,
            query.radius + query.margin,
            collider_center,
            collider_extents,
            box_is_target=True,
        )

    if collider.shape == "sphere":
        return _sphere_box_manifold(
            collider_center,
            collider_radius,
            query.position,
            Vector3(
                query.extents.x + query.margin,
                query.extents.y + query.margin,
                query.extents.z + query.margin,
            ),
            box_is_target=False,
        )

    query_extents = Vector3(
        query.extents.x + query.margin,
        query.extents.y + query.margin,
        query.extents.z + query.margin,
    )
    return _box_box_manifold(query.position, query_extents, collider_center, collider_extents)


def _overlap_between_nodes(
    node_a: "Node",
    collider_a: ColliderComponent,
    node_b: "Node",
    collider_b: ColliderComponent,
) -> Optional[tuple[Vector3, float]]:
    query = PhysicsShapeQueryParameters(
        shape=collider_a.shape,
        position=world_center(node_a),
        extents=half_extents(collider_a),
        radius=float(collider_a.radius),
        collision_mask=list(collider_a.mask),
    )
    return _overlap_shape_with_collider(query, node_b, collider_b)


def overlaps(node_a: "Node", node_b: "Node") -> bool:
    collider_a = _get_collider(node_a)
    collider_b = _get_collider(node_b)
    if not collider_a or not collider_b:
        return False
    if not _pair_should_collide(collider_a, collider_b):
        return False
    return _overlap_between_nodes(node_a, collider_a, node_b, collider_b) is not None


def collect_overlaps(subject: "Node", candidates: Iterable["Node"]) -> list[CollisionRecord]:
    subject_collider = _get_collider(subject)
    if not subject_collider:
        return []

    query = PhysicsShapeQueryParameters(
        shape=subject_collider.shape,
        position=subject.world_transform().position,
        extents=half_extents(subject_collider),
        radius=float(subject_collider.radius),
        collision_mask=list(subject_collider.mask),
        exclude={subject.name, subject.node_path},
    )
    return PhysicsSpaceState(candidates).intersect_shape(query)


def _intersect_ray_aabb(
    origin: Vector3,
    direction: Vector3,
    max_distance: float,
    minimum: Vector3,
    maximum: Vector3,
) -> Optional[tuple[float, Vector3, Vector3]]:
    t_min = 0.0
    t_max = max_distance
    hit_normal = Vector3(0.0, 1.0, 0.0)

    for axis in ("x", "y", "z"):
        origin_axis = getattr(origin, axis)
        direction_axis = getattr(direction, axis)
        min_axis = getattr(minimum, axis)
        max_axis = getattr(maximum, axis)

        if abs(direction_axis) <= EPSILON:
            if origin_axis < min_axis or origin_axis > max_axis:
                return None
            continue

        inverse = 1.0 / direction_axis
        near = (min_axis - origin_axis) * inverse
        far = (max_axis - origin_axis) * inverse
        near_normal = _vector_on_axis(axis, -1.0 if direction_axis > 0 else 1.0)

        if near > far:
            near, far = far, near
            near_normal = _vector_on_axis(axis, 1.0 if direction_axis > 0 else -1.0)

        if near > t_min:
            t_min = near
            hit_normal = near_normal
        t_max = min(t_max, far)
        if t_min > t_max:
            return None

    if t_min < 0.0:
        t_min = 0.0
    if t_min > max_distance:
        return None

    position = origin + direction.scale(t_min)
    return t_min, position, hit_normal


def _intersect_ray_sphere(
    origin: Vector3,
    direction: Vector3,
    max_distance: float,
    center: Vector3,
    radius: float,
) -> Optional[tuple[float, Vector3, Vector3]]:
    offset = origin - center
    b = offset.dot(direction)
    c = offset.dot(offset) - radius * radius
    if c > 0.0 and b > 0.0:
        return None

    discriminant = b * b - c
    if discriminant < 0.0:
        return None

    distance = -b - discriminant**0.5
    if distance < 0.0:
        distance = 0.0
    if distance > max_distance:
        return None

    position = origin + direction.scale(distance)
    normal = (position - center).normalized()
    if normal.length() <= EPSILON:
        normal = Vector3(0.0, 1.0, 0.0)
    return distance, position, normal


def _intersect_ray_with_collider(
    origin: Vector3,
    direction: Vector3,
    max_distance: float,
    node: "Node",
    collider: ColliderComponent,
) -> Optional[tuple[float, Vector3, Vector3]]:
    if collider.shape == "sphere":
        return _intersect_ray_sphere(origin, direction, max_distance, world_center(node), float(collider.radius))
    minimum, maximum = _collider_bounds(node, collider)
    return _intersect_ray_aabb(origin, direction, max_distance, minimum, maximum)


def _query_cast_extents(query: PhysicsShapeQueryParameters) -> Vector3:
    if query.shape == "sphere":
        radius = query.radius + query.margin
        return Vector3(radius, radius, radius)
    return Vector3(
        query.extents.x + query.margin,
        query.extents.y + query.margin,
        query.extents.z + query.margin,
    )


def _cast_shape_against_collider(
    query: PhysicsShapeQueryParameters,
    direction: Vector3,
    distance: float,
    node: "Node",
    collider: ColliderComponent,
) -> Optional[tuple[float, Vector3]]:
    if distance <= EPSILON:
        return None

    query_extents = _query_cast_extents(query)
    target_center = world_center(node)

    if query.shape == "sphere" and collider.shape == "sphere":
        hit = _intersect_ray_sphere(
            query.position,
            direction,
            distance,
            target_center,
            query.radius + query.margin + float(collider.radius),
        )
        if hit is None:
            return None
        hit_distance, _, normal = hit
        return hit_distance / max(distance, EPSILON), normal

    target_extents = half_extents(collider)
    expanded_extents = Vector3(
        target_extents.x + query_extents.x,
        target_extents.y + query_extents.y,
        target_extents.z + query_extents.z,
    )
    minimum, maximum = _box_bounds(target_center, expanded_extents)
    hit = _intersect_ray_aabb(query.position, direction, distance, minimum, maximum)
    if hit is None:
        return None
    hit_distance, _, normal = hit
    return hit_distance / max(distance, EPSILON), normal


def move_and_slide(
    subject: "Node",
    desired_delta: Vector3,
    blockers: Iterable["Node"],
    *,
    max_slides: int = 4,
) -> list[CollisionRecord]:
    desired_delta = Vector3.from_any(desired_delta)
    if desired_delta.length() <= EPSILON:
        return []

    subject_collider = _get_collider(subject)
    if not subject_collider:
        subject.transform.position = subject.transform.position + desired_delta
        return []

    blockers_list = list(blockers)
    space_state = PhysicsSpaceState(blockers_list)
    remaining = desired_delta
    collisions: list[CollisionRecord] = []
    seen: set[str] = set()

    for _ in range(max(max_slides, 0) + 1):
        if remaining.length() <= EPSILON:
            break

        motion = space_state.cast_motion(
            PhysicsShapeQueryParameters(
                shape=subject_collider.shape,
                position=subject.world_transform().position,
                extents=half_extents(subject_collider),
                radius=float(subject_collider.radius),
                motion=remaining,
                collision_mask=list(subject_collider.mask),
                exclude={subject.name, subject.node_path},
                collide_with_bodies=True,
                collide_with_areas=False,
            )
        )
        subject.transform.position = subject.transform.position + motion.travel

        if not motion.collided or motion.collision is None:
            break

        if motion.collision.node_name not in seen:
            collisions.append(motion.collision)
            seen.add(motion.collision.node_name)

        slide_normal = motion.collision.normal.normalized()
        remaining = Vector3.from_any(motion.remainder)
        into_surface = remaining.dot(slide_normal)
        if into_surface < 0.0:
            remaining = remaining - slide_normal.scale(into_surface)
        if remaining.length() <= EPSILON:
            break
        subject.transform.position = subject.transform.position + slide_normal.scale(KINEMATIC_EPSILON)

    for record in collect_overlaps(subject, blockers_list):
        if not record.is_trigger or record.node_name in seen:
            continue
        collisions.append(record)
        seen.add(record.node_name)

    return collisions


def move_kinematic(subject: "Node", desired_delta: Vector3, blockers: Iterable["Node"]) -> list[CollisionRecord]:
    return move_and_slide(subject, desired_delta, blockers, max_slides=4)


def raycast(
    nodes: Iterable["Node"],
    origin: Vector3,
    direction: Vector3,
    max_distance: float = 100.0,
) -> Optional[RaycastResult]:
    return PhysicsSpaceState(nodes).intersect_ray(
        PhysicsRayQueryParameters(
            origin=origin,
            direction=direction,
            max_distance=max_distance,
            collide_with_bodies=True,
            collide_with_areas=True,
        )
    )


def overlap_shape(
    nodes: Iterable["Node"],
    *,
    shape: str = "box",
    position: Vector3,
    extents: Vector3 | None = None,
    radius: float = 0.5,
    collision_mask: Optional[list[str]] = None,
    exclude: Optional[Iterable[str]] = None,
    collide_with_bodies: bool = True,
    collide_with_areas: bool = True,
    max_results: int = 32,
) -> list[CollisionRecord]:
    return PhysicsSpaceState(nodes).intersect_shape(
        PhysicsShapeQueryParameters(
            shape=shape,
            position=position,
            extents=extents or Vector3(0.5, 0.5, 0.5),
            radius=radius,
            collision_mask=collision_mask,
            exclude=set(exclude or []),
            collide_with_bodies=collide_with_bodies,
            collide_with_areas=collide_with_areas,
        ),
        max_results=max_results,
    )


def shape_cast(
    nodes: Iterable["Node"],
    *,
    shape: str = "box",
    position: Vector3,
    motion: Vector3,
    extents: Vector3 | None = None,
    radius: float = 0.5,
    margin: float = 0.0,
    collision_mask: Optional[list[str]] = None,
    exclude: Optional[Iterable[str]] = None,
    collide_with_bodies: bool = True,
    collide_with_areas: bool = True,
) -> PhysicsMotionResult:
    return PhysicsSpaceState(nodes).cast_motion(
        PhysicsShapeQueryParameters(
            shape=shape,
            position=position,
            extents=extents or Vector3(0.5, 0.5, 0.5),
            radius=radius,
            motion=motion,
            margin=margin,
            collision_mask=collision_mask,
            exclude=set(exclude or []),
            collide_with_bodies=collide_with_bodies,
            collide_with_areas=collide_with_areas,
        )
    )


def sphere_cast(
    nodes: Iterable["Node"],
    origin: Vector3,
    direction: Vector3,
    radius: float = 0.5,
    max_distance: float = 100.0,
) -> list[RaycastResult]:
    direction = Vector3.from_any(direction).normalized()
    motion = direction.scale(max(max_distance, 0.0))
    results: list[RaycastResult] = []

    for node in list(nodes):
        cast = shape_cast(
            [node],
            shape="sphere",
            position=origin,
            motion=motion,
            radius=radius,
            collide_with_bodies=True,
            collide_with_areas=True,
        )
        collider = _get_collider(node)
        if collider is None or not cast.collided or cast.collision is None:
            continue

        hit_position = Vector3.from_any(origin) + motion.scale(cast.unsafe_fraction)
        results.append(
            RaycastResult(
                node_name=node.name,
                layer=collider.layer,
                is_trigger=collider.is_trigger,
                position=hit_position,
                normal=cast.collision.normal,
                distance=motion.length() * cast.unsafe_fraction,
            )
        )

    return sorted(results, key=lambda result: result.distance)
