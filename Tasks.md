[x] Audit Godot Node lifecycle and SceneTree architecture
[x] Audit Godot ResourceLoader and PackedScene architecture
[x] Audit Godot rendering server architecture entry points
[x] Audit Godot physics server architecture entry points
[x] Audit Godot animation system entry points
[x] Audit Godot Control UI architecture entry points
[x] Write docs/engine/godot_architecture_notes.md
[x] Write docs/engine/reverie_engine_gap_report.md
[x] Write docs/engine/reverie_engine_target_architecture.md
[x] Establish reverie/engine as the canonical engine package entry
[x] Keep reverie_engine_lite as a compatibility alias
[x] Update CLI and tool surfaces to present Reverie Engine as the canonical runtime
[x] Add SceneTree lifecycle hooks for enter_tree ready and exit_tree
[x] Add Node.node_path support
[x] Add process and physics_process scheduling hooks
[x] Add group call support to the scene tree
[x] Add deferred call support to the scene tree
[x] Add timer scheduling support to the scene tree
[x] Add queue delete support to the scene tree
[x] Add process mode support to nodes
[x] Add pause and unpause notifications
[x] Add generic node notification hooks
[x] Add relative and absolute node path lookup
[x] Add scene change protocol support
[x] Add resource loader registry support
[x] Add resource cache mode controls
[x] Add resource remap support
[x] Add load_many clear_cache and exists resource utilities
[x] Add content bundle dependency tracking
[x] Add PackedSceneDocument abstraction
[x] Add pack_scene support
[x] Add save_packed_scene support
[x] Add load_packed_scene support
[x] Make load_scene accept raw scenes and packed scene wrappers
[x] Add scene tree lifecycle and scheduling tests
[x] Add resource system tests
[x] Add packed scene tests
[x] Keep engine runtime and integration tests passing
[x] Clone Godot reference source into references/godot for architecture study
[x] Convert root project planning into a checklist-oriented roadmap
[x] Rewrite Tasks.md into checklist-only format with no prose or headings
[x] Update task_manager to treat Tasks.md as the canonical human-facing artifact
[x] Add task_manager persistence sync between task_list.json and Tasks.md
[x] Add task_manager fallback loading from checklist-only Tasks.md
[x] Remove rich text and metadata rendering from task_manager output
[x] Update tool descriptions to require checklist-only task artifacts
[x] Update system prompt guidance to prefer many small verifiable checklist tasks
[x] Add automated tests that lock Tasks.md to checklist-only formatting
[x] Run targeted syntax checks for task_manager and prompt modules
[x] Run the full test suite after task system changes
[x] Add SceneTree notification propagation tests for edge cases
[x] Add scene switching regression tests for deferred deletion cases
[x] Add resource dependency graph export support
[x] Add packed scene local override support
[x] Add packed scene schema version migration support
[x] Design engine.yaml schema for core engine configuration
[x] Design gameplay_manifest.yaml schema for gameplay modules and content bundles
[x] Add schema validation for engine.yaml
[x] Add schema validation for gameplay_manifest.yaml
[x] Add archetype or blueprint document support for reusable entities
[x] Add AI-facing scene authoring commands for structured generation
[x] Add AI-facing prefab authoring commands for structured generation
[x] Add AI-facing validation commands for engine projects
[x] Refactor rendering.py into server-style rendering layers
[x] Add deterministic headless renderer support for smoke tests
[x] Add 2D sprite rendering primitives
[x] Add 2D camera support
[x] Add tilemap rendering support
[x] Add parallax rendering support
[x] Add 2.5D isometric rendering support
[x] Add billboard sprite support in hybrid scenes
[x] Add 3D camera support
[x] Add mesh instance support
[x] Add basic material support
[x] Add directional point and spot light support
[x] Refactor physics.py into query and simulation service layers
[x] Add 2D raycast overlap and shape cast queries
[x] Add kinematic move and slide support
[x] Add collision layers and masks
[x] Add 3D raycast and trigger query support
[x] Add grid navigation support
[x] Add waypoint path support
[x] Add tower defense lane path support
[x] Build unified animation track playback support
[x] Add cutscene timeline support
[x] Add generic state machine support
[x] Add dialogue timeline support
[x] Extend Live2D runtime manifest validation and motion routing
[x] Wire live2dcubismcore.min.js into the Live2D web bridge
[x] Add Galgame dialogue and Live2D sample verification
[x] Build Control-style UI node system
[x] Add label button panel image and progress bar controls
[x] Add dialogue box and choice list controls
[x] Add HUD controls for resource bars and tower defense build panels
[x] Extend gameplay systems for Galgame flow control
[x] Extend gameplay systems for tower defense wave and tower logic
[x] Add reusable sample templates for 2D platformer projects
[x] Add reusable sample templates for topdown action projects
[x] Add reusable sample templates for 2.5D exploration projects
[x] Add reusable sample templates for 3D third-person projects
[x] Add reusable sample templates for Galgame projects
[x] Add reusable sample templates for tower defense projects
[x] Add save and load state support for narrative and strategy games
[x] Add audio bus and mixer controls
[x] Add localization table support
[x] Expand CLI /engine commands for validate smoke package and benchmark flows
[x] Add project health report commands for engine projects
[x] Add smoke validation for every bundled sample template
[x] Add performance baselines for scene instantiation and AI command latency
[x] Write user-facing engine architecture and workflow documentation
