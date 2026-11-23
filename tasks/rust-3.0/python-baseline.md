# Rust 3.0 的最终 Python 2.5.5 来源与证据

此记录对应已经公开的最终纯 Python 2.5.5。它固定后续 Rust 的源码、协议和发行对照身份；性能、检索质量与桌面空闲内存尚须阶段0B实测，不能从构建结果推导达标。

## 已验证身份

| 对象 | 固定身份 |
|---|---|
| 来源提交 | `070fa25b07692c90c56a6b00a9a969ff2abb7804` |
| 源码树 | `b7835e45d0cea95e9e5b0790d24b7604c7681002` |
| 注释版本标签对象 | `c3c160329c2af044ef8e2061266a48df03aca5ee` |
| 正式版本 | `v2.5.5` |
| 正式 Release | ID `454958491`，2026-11-23 04:17:20 UTC公开，非草稿、非预发布 |
| main及Python完整归档 | `main`、`Reverie-Cli-py`均为同一来源；保留完整项目和Python import API |
| 第一方Context Engine | Python，in-process；旧Rust worker不再构建或随发行包附带 |
| 正式资产 | 17项，合计3,844,907,528字节；源码ZIP为GitHub另行提供的源码导出，不计入17项 |
| Windows独立CLI | 272,002,525字节；SHA-256 `4ffe83790c184707ad3f77ef5fd0de68d779889d1636aaeffcc4da40694b442d` |

入口：[正式 Release](https://github.com/Lin-Silver/Reverie-Cli/releases/tag/v2.5.5)、[固定源码](https://github.com/Lin-Silver/Reverie-Cli/tree/070fa25b07692c90c56a6b00a9a969ff2abb7804)、[Python归档](https://github.com/Lin-Silver/Reverie-Cli/tree/Reverie-Cli-py)。

## 实际核对与边界

[最终main Test 45103601291](https://github.com/Lin-Silver/Reverie-Cli/actions/runs/45103601291)的最新尝试成功；[最终标签Build 45103608624](https://github.com/Lin-Silver/Reverie-Cli/actions/runs/45103608624)的四平台原生构建及草稿上传成功。最初失败、原包和诊断继续保全；成功重试不能解释原失败原因。

全部17项草稿资产已完整下载并逐项计算SHA-256，与不可变资产ID、GitHub digest、SHA256SUMS、发行清单和四平台native-tested程序身份一致。公开后回读同一Release ID及资产ID、大小和摘要，资产未变；公开下载路由另核对程序前65,536字节及Range大小，元数据核对完整字节。后者是公开路由复验，不宣称公开路由重新全量下载了全部程序。

实际下载的最终Windows EXE通过CLI/SDK/Context Engine 6项、历史索引一致性备份与实际恢复9项、2.5.5历史忽略兼容11项检查。四平台的每个原生报告均有P2 24项、P3 28项、rich 88项、P4 31项及隔离检查通过；每份P4均为60次输入样本：

| 平台 | 输入p50 / p95 / max（ms） | 真实模型质量样本 |
|---|---|---|
| Windows x64 | 28.2 / 34.2 / 36.0 | 0 |
| Linux x64 | 29.6 / 35.1 / 39.2 | 0 |
| macOS arm64 | 28.3 / 39.6 / 59.0 | 0 |
| macOS x64 | 60.4 / 74.2 / 104.1 | 0 |

这些受控安装包和本地夹具结果不能证明真实模型产品质量、物理DPI或Rust性能。

公开源码ZIP共有1,567个文件。与原Git blob直接比较时，42个Windows脚本因仓库的`eol=crlf`声明具有CRLF差异；所有差异在LF规范化后相同，其余文件与blob一致。固定Git导出换行配置后，同一提交标准导出的全部1,567个文件与公开ZIP逐字节一致，无缺失、额外文件或源码内容差异。ZIP压缩字节可因元数据不同而具有不同摘要，比较依据为完整成员集合及其解压后的字节。

公开ZIP为23,050,236字节，SHA-256 `fdb0172146ed1130d433b3ad0e99691cc59ac5f2987c565d50e494e42266f7ae`。标准导出ZIP摘要为`6c5e7c0575d762fd88dd66af81713a31fabfe0cddeb99df3ff243973fd70003f`，逐文件比对记录为`public-source-canonical-comparison-lf.json`。

## 维护者最终决定与未验证项

维护者原文：“算了，这个功能等到Rust版本再去测试吧，现在就算了”。该决定于2026-11-23 UTC落实：停止Python阶段剩余真实单屏DPI验收，最终源码正式DPI通过数为0，四档整体状态为未验证，测试窗口已停止、最后回读DPI为96。这是公开Python发行前置的明确豁免，不是测试通过。

Rust仍须对最终程序真实验证100%、125%、150%、200%系统缩放、坐标转换、点击拖拽、普通/最大化/Snap窗口及运行中缩放后的旧图拒绝。原八小时AiO、物理多屏、完整前台/干净宿主、真实模型产品及文学验收的未完成项继续明确为未验证；其作为Rust开工前置的豁免不降低Rust验收门槛。

[原混合版2.5.5](https://github.com/Lin-Silver/Reverie-Cli/releases/tag/history/python-2.5.5-mixed-f029496)保留来源`f029496d19138176b857bedb54f7eeb225973471`、原Release ID `454302327`及17项原资产。其成绩仅为历史对照，不归属于最终纯Python基线。

Rust默认忽略规则已另行确认采用Git标准语义；最终Python仍保留历史兼容。小说和游戏资源采用本仓库许可明确的独立测试语料并经独立标注、交叉复核后冻结。两项决定不会改动上述冻结的Python归档来源。
