# Reverie-Gamer 大型 3D 游戏升级路线图

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
