# Reverie-Gamer 大型 3D 游戏升级路线图

## 当前版本补充说明（2026-04-04）

当前仓库最新版本为 **v2.1.21**。

这一版的重点不是继续堆新的大型玩法模块，而是先把 Reverie 本体的交互速度、TUI 输出质量、设置系统和上下文检索稳定性打牢。这样做的意义是：后续 Reverie-Gamer 的长链路游戏创建流程，必须建立在一个更快、更稳定、更可控的 CLI 基座上，否则“一句话 -> 蓝图 -> 脚手架 -> 可玩切片”的体验会被工具链延迟和输出噪音拖垮。

本次与游戏创建能力直接相关的现实影响：

- 更快的流式链路与工具调用展示，让 Prompt Compiler、Scaffolder、Slice Builder 这类长步骤更容易观察与调试。
- 更强的设置系统，可以显式控制工具输出与 thinking 输出的可见性，适合长时游戏项目生成时查看完整过程。
- 更稳的 Context Engine 检索和索引修复，为后续更复杂的 `reverie/gamer/` 多模块工作流提供更可靠的上下文基础。

## 近期更新时间预估

以下时间是 **2026-04-04** 时点的当前预估，不是硬承诺，但可以作为近期路线参考：

- **2026-04-11 到 2026-04-18**：下一轮 Reverie-Gamer 重点更新窗口。目标是继续强化 `一句提示词 -> 蓝图 -> 项目骨架 -> 首个可运行切片` 的闭环稳定性。
- **2026 年 4 月下旬**：重点推进资产流水线、验证闭环、生成后 smoke/playtest 校验的衔接。
- **2026 年 5 月**：继续推进长周期项目续作、更多区域/内容扩展生成，以及更稳的多阶段项目生成体验。

## 当前结论

当前版本的 `Reverie-Gamer` 还不能稳定、完整、高质量地通过一句提示词，直接生成接近《原神》或《鸣潮》这一级别的大型 3D 游戏。

当前最合理的升级目标，不是直接追求“一句话生成完整大型商业游戏”，而是先把能力升级到：

**一句提示词 -> 自动拆解需求 -> 生成蓝图 -> 生成 3D 项目骨架 -> 跑通首个可玩切片 -> 进入持续扩展流水线**

这条路线更适合当前仓库的实现基础，也能真正落地。

## 本项目当前已经具备的基础

仓库已经有一批很重要的 Gamer 基础能力，可以直接作为下一阶段升级的起点：

- `game_design_orchestrator`：负责蓝图、系统扩展、垂直切片规划、范围分析。
- `game_project_scaffolder`：负责项目结构、模块图、内容流水线骨架。
- `reverie_engine` / `reverie_engine_lite`：负责内置运行时、项目创建、场景/预制体、校验、冒烟、打包、基准。
- `game_modeling_workbench`：负责 Blockbench / Ashfox MCP / 模型导入 / 注册表同步。
- `game_playtest_lab`：负责测试计划、遥测 schema、质量门、日志分析。

这些能力已经足够支撑“AI 生成 3D 游戏切片”的第一阶段，但还不足以支撑大型 3D 动作 RPG 的完整生产闭环。

## 总体升级目标

建议把 Reverie-Gamer 的升级拆成 4 个可交付阶段。

### 阶段 1

目标：

**一句提示词 -> 自动生成 3D 游戏蓝图 + 可运行项目骨架 + 首个可玩切片**

这应该是下一阶段的主目标。

### 阶段 2

目标：

**从“可玩切片生成器”升级到“可持续扩展的 3D Action RPG 生产底座”**

这一阶段要开始解决内容、资产、系统组合、验证、扩展性问题。

### 阶段 3

目标：

**接入外部正式 runtime，形成真正可扩展的大型 3D 工程生产链**

建议优先 Godot，保留内置 `reverie_engine` 作为原型 runtime，再延后评估 O3DE。

### 阶段 4

目标：

**多轮会话、多阶段流水线、多代理协同，持续长周期生成大型项目**

这时再讨论更接近大型商业项目的自动化生产。

## 建议的升级主线

### 1. 先做 Prompt Compiler，而不是继续堆提示词

现在的 Gamer 模式已经有了不错的工具面，但还缺少一个真正的“游戏需求编译器”。

下一步应新增一层：

- 将一句用户提示词拆解为世界观、镜头、战斗、移动、关卡、成长、存档、任务、UI、资产、目标 runtime。
- 自动判断是原型、垂直切片、完整项目，避免一上来就生成过大范围。
- 自动生成结构化产物，而不是只生成散文式规划。

建议新增模块：

- `reverie/gamer/prompt_compiler.py`
- `reverie/gamer/scope_estimator.py`
- `reverie/gamer/production_plan.py`

阶段 1 TODO：

- 把一句提示词编译为统一的 `game_request.json`
- 自动抽取 genre、camera、dimension、core loop、meta loop、content scale、target runtime
- 为 `game_design_orchestrator` 增加 `compile_request` / `plan_production` 能力
- 为 `game_project_scaffolder` 增加“按 request 直接建项目”的入口
- 输出 `artifacts/game_request.json`、`artifacts/game_blueprint.json`、`artifacts/vertical_slice_plan.md`

### 2. 建立 Runtime Registry，优先接 Godot

现在内置 `reverie_engine` 更适合原型、切片、轻量验证，不适合直接承接“大型 3D 动作开放世界”目标。

建议引入正式 runtime 适配层，而不是让 Gamer 直接耦合某一个引擎。

建议新增模块：

- `reverie/gamer/runtime_registry.py`
- `reverie/gamer/runtime_adapters/base.py`
- `reverie/gamer/runtime_adapters/godot.py`
- `reverie/gamer/runtime_adapters/reverie_engine.py`
- `reverie/gamer/runtime_adapters/o3de.py`

推荐顺序：

1. 先接 `Godot`
2. 保留 `reverie_engine` 作为内置原型 runtime
3. O3DE 放在更后面

阶段 1-2 TODO：

- 启动时自动发现已安装或已接入的 runtime
- Gamer 生成项目时可显式选择 runtime
- 输出 runtime health、版本、能力标签、模板支持情况
- 为每个 runtime 提供统一能力接口：
  - `create_project`
  - `generate_scene`
  - `generate_character_controller`
  - `generate_combat_slice`
  - `run_smoke`
  - `validate_project`
- 将 `godot-tps-demo` 抽象为“第三人称 3D 模板源”

### 3. 从“骨架生成”升级到“系统生成”

大型 3D 游戏的核心不是目录结构，而是系统装配能力。

需要把蓝图继续编译成系统级产物。

建议新增模块：

- `reverie/gamer/system_generators/character_controller.py`
- `reverie/gamer/system_generators/combat.py`
- `reverie/gamer/system_generators/quest.py`
- `reverie/gamer/system_generators/save_load.py`
- `reverie/gamer/system_generators/progression.py`
- `reverie/gamer/system_generators/world_structure.py`

阶段 2 TODO：

- 生成第三人称角色控制器
- 生成目标锁定、闪避、受击、技能冷却、敌人基础 AI
- 生成任务数据表、对话结构、奖励配置
- 生成存档/读档、进度状态、版本迁移框架
- 生成成长系统、装备或技能树数据结构
- 生成 3D 关卡切片和交互点布局

### 4. 把资产流水线做成正式能力

目前模型链路已经起步，但大型 3D 项目远不止模型导入。

下一步应该把资产生产链标准化。

建议新增模块：

- `reverie/gamer/asset_pipeline/contracts.py`
- `reverie/gamer/asset_pipeline/importers.py`
- `reverie/gamer/asset_pipeline/validators.py`
- `reverie/gamer/asset_pipeline/budgets.py`

阶段 2 TODO：

- 建立 source asset 与 runtime asset 的统一 contract
- 接入 glTF 验证、命名校验、依赖校验、预算校验
- 增加动画、材质、贴图、碰撞、LOD、预览图的注册表
- 支持按 runtime 自动转换导入规则
- 让 `game_modeling_workbench` 不只管模型，还能进入完整资产链路

### 5. 增加“可玩切片生成器”

这是最关键的一步。

真正有价值的目标不是“生成满项目文件”，而是“自动生成一个能跑、能玩、能验证的 3D 切片”。

建议新增模块：

- `reverie/gamer/vertical_slice_builder.py`
- `reverie/gamer/playable_templates/third_person_action/`
- `reverie/gamer/playable_templates/action_rpg/`

阶段 1-2 TODO：

- 根据蓝图自动选择模板
- 自动生成主场景、主角、敌人、交互物、任务触发器、UI 基础层
- 自动写入默认输入映射、相机、HUD、基础敌人逻辑
- 自动生成第一轮 smoke case
- 自动生成第一轮 playtest checklist

### 6. 建立长期生产用的验证闭环

如果目标是大型 3D 项目，验证系统必须升级。

`game_playtest_lab` 已经是良好起点，但还需要把 runtime 验证、性能、内容质量门彻底接起来。

建议新增模块：

- `reverie/gamer/verification/runtime_smoke_runner.py`
- `reverie/gamer/verification/perf_gate.py`
- `reverie/gamer/verification/content_gate.py`
- `reverie/gamer/verification/slice_score.py`

阶段 2-3 TODO：

- 自动跑构建、冒烟、场景加载、输入、存档、战斗、任务基础验证
- 自动记录帧率、内存、场景加载耗时、资源数量
- 自动对切片打分，输出“可继续扩展 / 需返工 / 阻塞”
- 接入截图、视频、日志、遥测统一归档

### 7. 增加长周期任务图，而不是只靠一次回答

大型 3D 项目一定是长周期工作，不能继续依赖单次对话内的临时组织方式。

建议新增模块：

- `reverie/gamer/build_graph.py`
- `reverie/gamer/task_graph.py`
- `reverie/gamer/resume_state.py`

阶段 2-3 TODO：

- 将任务拆成 blueprint、runtime、assets、systems、slice、verification 六大阶段
- 每个阶段可恢复、可重跑、可增量继续
- 每次生成都输出阶段状态和下一步行动
- 允许 AI 在长会话中继续之前的游戏工程，而不是重复从头规划

### 8. 后面再做多代理协同

如果后续要追求更复杂的大型 3D 项目，最终一定需要多代理协作。

但这不是当前第一优先级。

推荐放到阶段 4 再做：

- Planner Agent：拆解大型项目
- Runtime Agent：生成引擎工程代码
- Asset Agent：资产导入与注册
- QA Agent：冒烟、性能、playtest、报告

## 建议的近期实施顺序

最推荐的执行顺序如下：

1. 精简并稳定 Gamer 模式提示词与工具发现逻辑
2. 新增 `prompt_compiler`
3. 新增 `runtime_registry`
4. 优先接入 `Godot` adapter
5. 抽象 `godot-tps-demo` 成第三人称 3D 模板
6. 实现“单提示词 -> 可玩切片”最小闭环
7. 再扩展系统生成器
8. 再扩展资产流水线
9. 再扩展质量门和性能门
10. 最后再做多代理与大规模内容扩张

## references 目录是否足够

### 当前阶段是否够用

对于阶段 1 和阶段 2 的早期工作，当前 `references/` 已经够用了。

当前最有价值的参考包括：

- `references/godot`
- `references/godot-demo-projects`
- `references/godot-tps-demo`
- `references/blockbench`
- `references/blockbench-mcp`
- `references/blockbench-plugins`
- `references/gltf-blender-io`
- `references/gltf-validator`
- `references/gltf-sample-assets`
- `references/o3de`
- `references/o3de-multiplayersample`
- `references/o3de-multiplayersample-assets`

这些已经足够支撑：

- runtime adapter 设计
- 3D 模板抽象
- 建模与导出链路
- glTF 资产校验链路
- Godot / O3DE 的项目结构参考

### 是否还需要额外开源项目代码示例

需要，但不是现在立刻全部补齐。

建议在阶段 2 开始后，按优先级补充这几类代码示例：

1. 3D 第三人称动作战斗示例
2. 动画状态机 / Root Motion / 命中框示例
3. Quest / Dialogue / SaveLoad 示例
4. NavMesh / 敌人 AI / 行为树示例
5. 开放区域流式加载 / 地形 / LOD 示例
6. 大型 3D UI / 背包 / 装备 / 成长数据驱动示例

如果你的目标继续逼近《原神》或《鸣潮》这种大型 3D 动作 RPG，那么这些额外示例会明显提高后续升级效率。

## 下一轮最值得直接开工的 TODO

建议下一轮直接开做下面这 8 项：

1. 新增 `reverie/gamer/prompt_compiler.py`
2. 新增 `reverie/gamer/runtime_registry.py`
3. 新增 `reverie/gamer/runtime_adapters/godot.py`
4. 为 `game_design_orchestrator` 增加 request 编译入口
5. 为 `game_project_scaffolder` 增加“按 request 建项目”入口
6. 抽象 `godot-tps-demo` 为 3D 第三人称模板
7. 新增 `vertical_slice_builder`
8. 新增 Gamer 质量门与 slice 评分输出

## 最终建议

下一阶段不要再把目标写成“直接一句话生成大型 3D 游戏”。

建议把产品目标改成：

**Reverie-Gamer 能够通过一句提示词，稳定生成一个可运行、可验证、可继续扩展的 3D 游戏垂直切片工程。**

只要这个目标先做扎实，后续再往大型 3D 项目扩张，整个升级路径会清晰很多。

## 当前仓库已落地的基础设施

本轮升级后，仓库里已经补上了阶段 1 最关键的几个核心点：

- 新增 `reverie/gamer/prompt_compiler.py`
- 新增 `reverie/gamer/scope_estimator.py`
- 新增 `reverie/gamer/production_plan.py`
- 新增 `reverie/gamer/runtime_registry.py`
- 新增 `reverie/gamer/runtime_adapters/reverie_engine.py`
- 新增 `reverie/gamer/runtime_adapters/godot.py`
- 新增 `reverie/gamer/runtime_adapters/o3de.py`
- 新增 `reverie/gamer/vertical_slice_builder.py`

同时，现有工具也已经完成接入：

- `game_design_orchestrator` 现在支持 `compile_request`
- `game_design_orchestrator` 现在支持 `plan_production`
- `game_project_scaffolder` 现在支持 `create_from_request`
- `game_project_scaffolder` 现在支持 `generate_vertical_slice`

当前已经可以形成以下最小闭环：

**一句提示词 -> `game_request.json` -> runtime 选择 -> `game_blueprint.json` -> `production_plan.json` -> `vertical_slice_plan.md` -> 生成内置 Reverie Engine 可验证切片或 Godot 3D 工程骨架**

这还不等于“直接生成《原神》或《鸣潮》完整商业成品”，但已经把 Reverie-Gamer 从“偏提示词驱动的流程说明”升级成了“真实可执行的单提示词游戏切片流水线”。

## 当前仓库已落地的第二阶段增强

在上一轮 request 编译、runtime 选择、vertical slice builder 的基础上，仓库这次又补上了 3 个关键层：

- `artifacts/system_specs.json` / `artifacts/system_specs.md`
- `artifacts/task_graph.json` / `artifacts/task_graph.md`
- `playtest/slice_score.json` / `playtest/slice_score.md`

同时新增了 `reverie/gamer/system_generators/`，把之前缺失的核心 3D ARPG 子系统正式结构化为可生成的 packet：

- `character_controller`
- `combat`
- `quest`
- `save_load`
- `progression`
- `world_structure`

这些 packet 不再只是 prompt 里的“建议实现项”，而是会真实参与工程输出：

- 进入 `plan_production` 产物
- 进入 `generate_vertical_slice` 产物
- 参与 Reverie Engine 内容 YAML 生成
- 参与 Godot `engine/godot/data/` 下的数据合同生成
- 参与 slice readiness 评分与 blocker 结论

同时，Godot 侧现在也不再只是“原始脚手架 + 原始脚本”：

- `project.godot` 现在会注册 `GameState` 与 `SaveService`
- `GameState` 会读取 `quest_flow.json`、`progression.json`、`world_slice.json`、`save_schema.json`、`slice_manifest.json`
- 生成的 3D slice 已带基础 save/load
- 敌人已经从纯静态 dummy 升级为带追击、wind-up、恢复阶段的基础状态机
- 主场景会按 `slice_manifest.json` 的内容生成地标、敌人、出生点与神殿目标
- Godot 生成物现在还支持近战/远程敌人分型，远程单位会读取 `combat.json` 默认值并生成基础投射物攻击
- 玩家战斗层现在也开始读取 `combat.json` 的 `player_actions`，支持基础锁定和技能攻击，不再只是单一普通攻击原型
- 这次又补上了 `combat_feedback.gd`、dash i-frame、技能冷却展示和基础命中表现，让 Godot 生成物从“有战斗规则”进一步走向“有基础战斗手感”

这一步非常重要，因为它把 Godot 输出从“可运行 demo”进一步推进成了“可持续扩展的数据驱动 ARPG 模板工程”。

这意味着 Reverie-Gamer 现在已经从“会生成切片骨架”继续升级到“会生成切片骨架 + 核心子系统合同 + 依赖任务图 + 自动质量评分”。

离《原神》/《鸣潮》级完整大型 3D 游戏仍然有明显距离，但当前模式已经更接近：

**一句提示词 -> 结构化 request -> runtime 决策 -> blueprint -> production plan -> system packets -> task graph -> vertical slice project -> slice score**
## 2026-04-03 Continuity Upgrade

This repo now has a durable in-repo continuation layer for Reverie-Gamer.

- `artifacts/content_expansion.json` stores region seeds, NPC roster, quest arcs, and phase-based scale-up planning.
- `artifacts/expansion_backlog.json` stores the queued follow-up work after the current slice is verified.
- `artifacts/resume_state.json` stores the first-open continuation state for later sessions.

This does not create literal cross-session model memory. Instead, it turns "permanent memory" into repository-backed production memory that future sessions can reliably reopen and continue from.

The generated runtime outputs now also mirror this continuity layer:

- Reverie Engine slices emit `region_seeds.yaml`, `npc_roster.yaml`, and `quest_arcs.yaml`.
- Godot slices emit `region_seeds.json`, `npc_roster.json`, and `quest_arcs.json`, and the generated `GameState` now loads these files directly.

That moves Reverie-Gamer one step further from "generate one isolated slice" toward "grow the same 3D ARPG project over many implementation sessions."

## 2026-04-03 Runtime Expansion Follow-Up

The generated Godot scaffold now does more than save expansion seeds as data files.

- `slice_manifest.json` now includes `npc_beacons`, `region_gateways`, and `active_arc`.
- `main.gd` now spawns NPC anchors and region gateways directly into the playable scene.
- `hud.gd` now surfaces the active quest arc, next region target, and anchor counts.
- `GameState` now exposes the expansion path to runtime code instead of leaving it stranded in planning artifacts.

This is still not equivalent to a true multi-region open-world runtime. But it is a meaningful shift from "future expansion exists only in docs" to "future expansion is already represented inside the generated playable scaffold."

## 2026-04-03 Guardian Finale Upgrade

The generated Godot slice now also includes the first guardian-style finale pattern instead of ending at two standard enemies and a shrine trigger.

- The combat packet now seeds a `shrine_warden` boss archetype.
- `combat.json` now includes encounter templates such as `shrine_guardian_finale`.
- The generated enemy runtime now understands boss-tier settings like phase thresholds and radial burst attacks.
- The generated `slice_manifest.json` now includes a boss-tier enemy near the shrine route.

This still is not a full action-game boss framework with authored animation, hitboxes, cinematic transitions, or bespoke encounter scripting. But it is a real step from "basic combat slice" toward "slice with a recognizable finale encounter structure."

## 2026-04-03 Guided Quest Arc Upgrade

The generated Godot slice now also has a clearer quest arc shape instead of one flat objective chain.

- The route now begins with a guide contact beat.
- The combat route now separates sentinel escort cleanup from guardian defeat.
- Region gateways can now be primed by completing the current slice instead of existing as static future markers.
- Save data now persists NPC contact and arc progression state.

This still is not a full narrative quest framework with branching dialogue, authored cutscenes, faction systems, or cinematic mission scripting. But it moves the generated runtime from "single linear task prompt" toward "recognizable ARPG quest arc staging."

## 2026-04-03 Guard Loop Upgrade

The generated Godot slice now also includes a real defensive layer instead of only offense, dash, and boss pressure.

- `combat.json` now emits a `player_actions.guard` contract with stamina drain, damage reduction, perfect-guard timing, and counter-poise output.
- The generated `player_controller.gd` now supports held guard, perfect-guard timing, and different outcomes for blocked versus perfectly read hits.
- Enemy melee and projectile attacks now pass source context into the player damage path so a defensive response can create a meaningful counter window.
- The generated HUD now exposes live guard state so the player can read when the perfect-guard window is still active.

This is still not the same as a full commercial combat stack with authored animation blending, hitstop, root motion, cinematic parry cameras, or final-quality VFX. But it is another concrete move from "can attack through a slice" toward "has the beginning of a fuller ARPG combat loop."

## 2026-04-03 Encounter Director Upgrade

The generated Godot slice now also has a clearer encounter layer instead of only spawning enemies into space and letting local AI handle everything in isolation.

- `combat.json` now emits a `pattern_library` for sentinel melee, sentinel ranged, and shrine guardian behaviors.
- `slice_manifest.json` now emits explicit `encounters` with start positions, activation radius, enemy membership, and finale metadata.
- The generated runtime now includes `encounter_director.gd`, which activates encounter beats, marks them complete, and keeps the runtime aligned with the authored encounter contracts.
- Boss enemies now consume phase profiles for windup timing, recovery timing, lunge distance, burst cadence, and phase callout text.

This still is not a full encounter production stack with authored boss arenas, cinematic transitions, navmesh-driven movement, designer-authored ability graphs, or final-quality animation and VFX. But it moves the generated runtime from "combat slice with a boss enemy" toward "combat slice with a recognizable encounter layer and data-driven boss pacing."

## 2026-04-03 Detour Reward Upgrade

The generated Godot slice now also supports optional side-route content instead of only one strictly linear combat lane.

- `combat.json` now emits an elite detour encounter and an elite behavior profile.
- `slice_manifest.json` now emits `reward_sites`, so optional caches are explicit authored runtime objects instead of implicit design notes.
- The generated runtime now includes `reward_cache.gd`, spawns optional reward sites into the scene, and unlocks them only after the related elite detour is cleared.
- Save/load now persists completed encounters and claimed reward caches, so optional progression does not vanish between sessions.
- Optional detour rewards now feed back into combat and survivability instead of existing as flavor-only pickups.

This still is not a true open-world content stack with authored dungeons, layered traversal verbs, streaming subregions, or large-scale systemic exploration. But it moves the generated runtime from "one authored combat corridor" toward "a slice with critical path plus optional payoff routes," which is materially closer to how large action RPG regions actually feel.

## 2026-04-03 Region Travel Upgrade

The generated Godot slice now also has the beginning of a multi-region runtime layer instead of treating expansion as a purely future-facing plan.

- `slice_manifest.json` now emits `region_layouts`, `world_graph`, and an `active_region_id`.
- Gateway contracts now include `from_region`, `target_spawn`, and travel-gating data instead of only a target label.
- The generated runtime now includes `region_manager.gd`, which activates only the currently selected region content.
- Gateways now perform actual region travel through `GameState.travel_to_region(...)` instead of only posting hints.
- Save/load now persists the current region and discovered regions, so world traversal state survives across sessions.

This still is not a final large-world stack with streaming terrain, navmesh-backed regional AI populations, authored dungeons, persistent economies, or final-quality open-world traversal. But it moves the generated runtime from "single-region slice plus future gateways" toward "a real multi-region runtime scaffold," which is a more credible foundation for eventually growing a large 3D action RPG project.

## 2026-04-04 Region Objective Upgrade

The generated Godot slice now treats secondary regions as playable expansion beats instead of only future-facing travel destinations.

- `slice_manifest.json` now emits `region_objectives`, and `world_graph.json` now includes `regional_goals` plus `region_objective_id` links on region nodes.
- The generated runtime now includes `region_objective_site.gd`, which spawns interactable objective sites directly into Cloudstep Basin and Echo Watch.
- `GameState` now persists completed regional objectives, and save/load restores them alongside region travel, encounters, detours, and rewards.
- Regional rewards like `basin_insight` and `watch_resonance` now feed back into runtime movement, cooldown, dash, stamina, and skill-range tuning.
- HUD expansion status now shows regional goal progress, so the generated runtime exposes multi-region payoff loops in play instead of only in artifacts.

This still is not a shipping large-world stack with authored quests, navmesh-backed frontier combat, streaming terrain, or final-quality assets and animation. But it moves the generated runtime from "multi-region travel scaffold" toward "multi-region runtime with concrete side goals and persistent payoff," which is materially closer to how a large 3D action RPG project grows over time.

## 2026-04-04 Regional Encounter Upgrade

The generated Godot slice now gives secondary regions their own combat pockets instead of leaving them as travel destinations with props and objective markers only.

- Enemy instances can now inherit from shared combat archetypes through `archetype_id`, which makes it possible to scale the runtime to more regions without reusing one global enemy identifier per role.
- `slice_manifest.json` now emits frontier enemies for Cloudstep Basin and Echo Watch, plus new encounters such as `cloudstep_relay_push` and `echo_spire_hold`.
- Regional objectives now include `encounter_id`, and the generated runtime will not let the player secure a relay or spire until the local encounter has been cleared.
- HUD purification counts now reflect the active region instead of all spawned enemies globally, so multi-region combat reads correctly in play.
- Root-region shrine logic now ignores frontier defenders, which keeps the original critical path stable while secondary regions gain their own combat pacing.

This still is not a full open-world combat population system with navmesh-backed patrols, layered traversal pressure, authored encounter spaces, or final-quality enemy presentation. But it moves the generated runtime from "multi-region exploration shell" toward "multi-region slice with region-specific combat beats," which is a more credible foundation for eventually growing into a large 3D action RPG production stack.

## 2026-04-04 Patrol Route Upgrade

The generated multi-region slice now also has the beginning of a real world-population layer instead of treating every enemy as a stationary encounter prop.

- `patrol_routes.yaml` and `patrol_routes.json` are now generated as first-class contracts.
- `slice_manifest.json` now emits `patrol_routes`, and `world_graph.json` now emits `patrol_lanes`.
- Godot runtime enemies now resolve patrol routes from shared data and move through waypoint loops when they are not actively pressuring the player.
- Frontier enemies in Cloudstep Basin and Echo Watch can now inherit from shared combat archetypes while following their own regional sweep routes.
- Region purification counts now stay scoped to the active region, so expanding the world no longer breaks local combat readability.

This still is not a full navmesh-backed population stack with crowd simulation, perception cones, squad coordination, streaming AI budgets, or authored regional schedules. But it moves the generated runtime from "multi-region encounters exist" toward "multi-region enemies actually inhabit routes inside the world," which is an important step toward the feel of a much larger 3D action RPG.

## 2026-04-04 Alert Network Upgrade

The generated multi-region slice now also has the beginning of local defender coordination instead of treating every enemy as an isolated combat node.

- `alert_networks.yaml` and `alert_networks.json` are now generated as first-class runtime contracts.
- `world_graph.json` now emits `guard_networks`, which gives regional coordination a formal representation alongside patrol lanes and route links.
- Godot runtime enemies now raise alerts when they make contact or take damage, and nearby defenders in the same network will converge on the alert point.
- Patrol and alert layers now work together, so a region can feel occupied and reactive instead of only populated by static route walkers.
- Cloudstep Basin and Echo Watch now feel more like defended frontier spaces instead of disconnected two-enemy encounter pads.

This still is not a full squad-AI stack with perception cones, navmesh-backed searches, shared target priorities, communication latency, or encounter-director-level tactical orchestration. But it moves the generated runtime from "enemies patrol lanes" toward "regional defenders coordinate inside those lanes," which is another meaningful step toward the feel of a larger 3D action RPG world.

## 2026-04-04 Squad Search Upgrade

The generated multi-region slice now also keeps local defenders in a search state after the initial alert pulse instead of instantly snapping back to passive patrol behavior.

- Godot enemy specs now emit `squad_role`, so generated defenders can react as vanguards, suppressors, anchors, or boss anchors instead of sharing one generic alert response.
- `alert_networks.yaml/json` now include `search_duration_seconds` and `anchor_point`, and `world_graph.guard_networks` mirrors those values so regional AI coordination remains visible inside the generated world-state graph.
- The generated runtime now routes those contracts into `enemy_dummy.gd`, where suppressors hold more ranged positions, anchors bias toward defended ground, and alerted units keep searching for a short window after contact is lost.
- The automated tests now verify both the manifest contracts and the emitted GDScript search behavior, which makes this AI layer harder to regress while the 3D runtime keeps expanding.

This still is not a full tactical squad-AI stack with navmesh-driven search volumes, perception cones, communication latency, shared threat scoring, or authored battlefield roles. But it moves the generated runtime from "alerts cause local convergence" toward "alerts create short-lived role-based search behavior," which is another concrete step toward more believable large-world ARPG populations.
