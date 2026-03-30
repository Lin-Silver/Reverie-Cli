# Reverie-Gamer 未来计划

## 当前阶段

本阶段只做两件事：

1. 下载后续升级需要参考的开源项目源码到 `references/`
2. 明确下一阶段要在两种 runtime 方案之间做技术决策

本阶段**不做实际集成**，**不修改现有 Reverie-Gamer 运行逻辑**，**不编译第三方 runtime**。

## 已下载参考项目

所有仓库已放入 `references/`。

| 项目 | 目录 | 用途 |
| --- | --- | --- |
| Godot Engine | `references/godot` | 轻中型 3D 正式运行时候选 |
| Godot Demo Projects | `references/godot-demo-projects` | 官方样例结构参考 |
| Godot TPS Demo | `references/godot-tps-demo` | 第三人称 3D 样板参考 |
| Blender | `references/blender` | 3D 内容制作与导出参考 |
| Blockbench | `references/blockbench` | 低模建模与桌面工具参考 |
| Blockbench Plugins | `references/blockbench-plugins` | Blockbench 插件机制参考 |
| Blockbench MCP | `references/blockbench-mcp` | MCP / 插件式工作流参考 |
| glTF Blender IO | `references/gltf-blender-io` | Blender 与 glTF 交换链路参考 |
| glTF Validator | `references/gltf-validator` | glTF 校验链路参考 |
| glTF Sample Assets | `references/gltf-sample-assets` | 标准资产样本参考 |
| O3DE | `references/o3de` | 重型 3D 运行时候选 |
| O3DE Multiplayer Sample | `references/o3de-multiplayersample` | O3DE 工程结构参考 |
| O3DE Multiplayer Sample Assets | `references/o3de-multiplayersample-assets` | O3DE 大型资产组织参考 |

## 未来目标

下一阶段的目标不是直接做“大型 3D 游戏自动生成”。

下一阶段的目标是先把 Reverie-Gamer 升级成：

**Prompt -> 3D 游戏工程骨架 + 可玩切片 + 可接入外部 runtime 的统一入口**

## 待决策的两种 runtime 路线

### 方案 A：内置单 exe runtime

思路：

- 将第三方 runtime 或其必要执行层直接并入 Reverie 的单个 exe
- 启动后无需额外下载，开箱即用

优点：

- 用户体验统一
- 安装成本低
- 启动路径简单

缺点：

- 打包体积会明显变大
- 更新第三方 runtime 成本高
- License、依赖和平台兼容性处理更复杂

### 方案 B：插件式单 exe runtime

思路：

- Reverie 主程序保持轻量
- 第三方 runtime 作为独立单 exe 或独立 runtime 包放入 `.reverie/plugins/`
- 启动 Reverie 时自动扫描并检测是否存在可用 runtime

建议目录形态：

```text
.reverie/
  plugins/
    godot-runtime/
    o3de-runtime/
    blockbench-runtime/
```

优点：

- 主程序更轻
- 第三方 runtime 可独立升级
- 更适合后续多引擎并存

缺点：

- 首次使用需要额外下载
- 运行时发现、版本匹配、健康检查要额外实现

## 当前更推荐的方向

优先建议先按**插件式单 exe runtime**思路设计。

原因只有三点：

1. 风险更小
2. 更适合 Godot / O3DE / Blockbench 并存
3. 更容易逐步接入，不会一次性把主程序打包得过大

## 下一阶段实施顺序

后续如果进入实际开发阶段，建议按下面顺序推进：

1. 先做 `runtime registry` 与自动检测机制
2. 先接入 `Godot runtime` 作为第一正式目标
3. 把 `Godot TPS Demo` 抽象成 Reverie-Gamer 的 3D 模板来源
4. 保留 `reverie_engine_lite` 作为内置原型运行时
5. 再评估是否需要引入 `O3DE runtime`
6. 最后再评估 `Blockbench` / `Blender` 是否需要插件化包装

## 下一阶段需要落地的最小能力

真正开始更新时，优先做这 5 项：

1. `references` 中参考项目的结构梳理
2. runtime 插件目录规范
3. 启动时自动检测 runtime
4. runtime 健康检查与版本信息展示
5. Reverie-Gamer 生成项目时可选择目标 runtime

## 本阶段完成情况

- `references/` 参考仓库已下载完成
- 文档已切换为精简未来计划版本
- 尚未开始任何 runtime 集成与功能更新

## 备注

- `references/blender` 已按“可参考源码、跳过 LFS 大资源”的方式整理完成，适合当前阶段做架构与接入评估
- 体积最大的参考项目是 `o3de-multiplayersample-assets`，后续如果决定不走 O3DE 路线，可以再清理
