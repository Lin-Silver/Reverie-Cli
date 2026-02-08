"""
Game GDD Manager Tool - Manage Game Design Documents

Advanced features:
- create: Create new GDD from template (standard, RPG, minimal)
- view: View existing GDD with formatting
- update: Update GDD sections intelligently
- summary: Generate comprehensive GDD summary
- append_section: Append new section to GDD
- set_metadata: Set GDD metadata (team, version, status)
- validate: Validate GDD structure and completeness (NEW)
- version: Manage GDD versions (backup, compare, rollback) (NEW)
- compare: Compare two GDD versions for changes (NEW)
- export: Export GDD to PDF/HTML format (NEW)
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
import json
from datetime import datetime

from .base import BaseTool, ToolResult


class GameGDDManagerTool(BaseTool):
    name = "game_gdd_manager"
    description = "Manage Game Design Documents: create, view, update, summary, append sections, set metadata."

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "view", "update", "summary", "append_section", "set_metadata", "validate", "version", "compare", "export"],
                "description": "GDD management action"
            },
            "gdd_path": {
                "type": "string",
                "description": "Path to GDD file (default: docs/GDD.md)"
            },
            "project_name": {
                "type": "string",
                "description": "Project name for create action"
            },
            "genre": {
                "type": "string",
                "description": "Game genre (RPG, Action, Puzzle, etc.)"
            },
            "target_engine": {
                "type": "string",
                "description": "Target engine (custom, phaser, pygame, love2d, godot, etc.)"
            },
            "target_platform": {
                "type": "string",
                "description": "Target platform (PC, Web, Mobile, etc.)"
            },
            "is_rpg": {
                "type": "boolean",
                "description": "Whether this is an RPG game (enables RPG-specific sections)"
            },
            "section_name": {
                "type": "string",
                "description": "Section name for update/append"
            },
            "section_content": {
                "type": "string",
                "description": "Section content for update/append"
            },
            "metadata": {
                "type": "object",
                "description": "Metadata to set (key-value pairs)"
            },
            "template_type": {
                "type": "string",
                "enum": ["standard", "rpg", "minimal"],
                "description": "GDD template type (default: standard)"
            }
        },
        "required": ["action"]
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        gdd_path = self._resolve_path(kwargs.get("gdd_path", "docs/GDD.md"))

        try:
            if action == "create":
                project_name = kwargs.get("project_name", "Untitled Game")
                genre = kwargs.get("genre", "Game")
                target_engine = kwargs.get("target_engine", "Custom")
                target_platform = kwargs.get("target_platform", "PC")
                is_rpg = kwargs.get("is_rpg", False)
                template_type = kwargs.get("template_type", "rpg" if is_rpg else "standard")
                
                return self._create_gdd(
                    gdd_path, project_name, genre, target_engine,
                    target_platform, is_rpg, template_type
                )
            
            elif action == "view":
                return self._view_gdd(gdd_path)
            
            elif action == "update":
                section_name = kwargs.get("section_name")
                section_content = kwargs.get("section_content")
                if not section_name or not section_content:
                    return ToolResult.fail("section_name and section_content are required for update")
                
                return self._update_section(gdd_path, section_name, section_content)
            
            elif action == "summary":
                return self._generate_summary(gdd_path)
            
            elif action == "append_section":
                section_name = kwargs.get("section_name")
                section_content = kwargs.get("section_content")
                if not section_name or not section_content:
                    return ToolResult.fail("section_name and section_content are required for append_section")
                
                return self._append_section(gdd_path, section_name, section_content)
            
            elif action == "set_metadata":
                metadata = kwargs.get("metadata")
                if not metadata:
                    return ToolResult.fail("metadata is required for set_metadata")
                
                return self._set_metadata(gdd_path, metadata)
            
            elif action == "validate":
                return self._validate_gdd(gdd_path)
            
            elif action == "version":
                version_action = kwargs.get("version_action", "create")
                return self._manage_version(gdd_path, version_action)
            
            elif action == "compare":
                compare_path = kwargs.get("compare_path")
                if not compare_path:
                    return ToolResult.fail("compare_path is required for compare")
                return self._compare_gdd(gdd_path, self._resolve_path(compare_path))
            
            elif action == "export":
                export_format = kwargs.get("export_format", "markdown")
                export_path = kwargs.get("export_path")
                return self._export_gdd(gdd_path, export_format, export_path)
            
            else:
                return ToolResult.fail(f"Unknown action: {action}")

        except Exception as e:
            return ToolResult.fail(f"Error executing {action}: {str(e)}")

    def _create_gdd(
        self,
        gdd_path: Path,
        project_name: str,
        genre: str,
        target_engine: str,
        target_platform: str,
        is_rpg: bool,
        template_type: str
    ) -> ToolResult:
        """Create new GDD from template"""
        if gdd_path.exists():
            return ToolResult.fail(f"GDD already exists at {gdd_path}. Use 'update' to modify it.")

        # Generate GDD content based on template
        if template_type == "rpg":
            content = self._generate_rpg_template(project_name, genre, target_engine, target_platform)
        elif template_type == "minimal":
            content = self._generate_minimal_template(project_name, genre, target_engine, target_platform)
        else:
            content = self._generate_standard_template(project_name, genre, target_engine, target_platform, is_rpg)

        # Save GDD
        gdd_path.parent.mkdir(parents=True, exist_ok=True)
        gdd_path.write_text(content, encoding="utf-8")

        output = f"Created GDD at {gdd_path}\n"
        output += f"Project: {project_name}\n"
        output += f"Genre: {genre}\n"
        output += f"Engine: {target_engine}\n"
        output += f"Platform: {target_platform}\n"
        output += f"Template: {template_type}"

        return ToolResult.ok(output, {
            "gdd_path": str(gdd_path.relative_to(self.project_root)),
            "project_name": project_name,
            "template_type": template_type
        })

    def _view_gdd(self, gdd_path: Path) -> ToolResult:
        """View existing GDD"""
        if not gdd_path.exists():
            return ToolResult.fail(f"GDD not found at {gdd_path}")

        content = gdd_path.read_text(encoding="utf-8")
        
        # Truncate if too long
        max_length = 5000
        if len(content) > max_length:
            content = content[:max_length] + f"\n\n... (truncated, total length: {len(content)} characters)"

        return ToolResult.ok(content, {
            "gdd_path": str(gdd_path.relative_to(self.project_root)),
            "length": len(content)
        })

    def _update_section(self, gdd_path: Path, section_name: str, section_content: str) -> ToolResult:
        """Update GDD section"""
        if not gdd_path.exists():
            return ToolResult.fail(f"GDD not found at {gdd_path}")

        content = gdd_path.read_text(encoding="utf-8")
        
        # Find section
        section_header = f"## {section_name}"
        if section_header not in content:
            return ToolResult.fail(f"Section '{section_name}' not found in GDD")

        # Replace section content
        lines = content.split("\n")
        new_lines = []
        in_section = False
        section_replaced = False

        for i, line in enumerate(lines):
            if line.strip() == section_header:
                in_section = True
                new_lines.append(line)
                new_lines.append("")
                new_lines.append(section_content)
                new_lines.append("")
                section_replaced = True
                continue
            
            if in_section and line.startswith("## "):
                in_section = False
            
            if not in_section or not section_replaced:
                new_lines.append(line)

        if not section_replaced:
            return ToolResult.fail(f"Failed to replace section '{section_name}'")

        # Save updated GDD
        gdd_path.write_text("\n".join(new_lines), encoding="utf-8")

        output = f"Updated section '{section_name}' in GDD\n"
        output += f"GDD path: {gdd_path}"

        return ToolResult.ok(output, {
            "gdd_path": str(gdd_path.relative_to(self.project_root)),
            "section_name": section_name
        })

    def _generate_summary(self, gdd_path: Path) -> ToolResult:
        """Generate GDD summary"""
        if not gdd_path.exists():
            return ToolResult.fail(f"GDD not found at {gdd_path}")

        content = gdd_path.read_text(encoding="utf-8")
        
        # Extract metadata
        metadata = {}
        lines = content.split("\n")
        for line in lines:
            if line.startswith("- ") and ":" in line:
                key, value = line[2:].split(":", 1)
                metadata[key.strip()] = value.strip()

        # Extract sections
        sections = []
        current_section = None
        for line in lines:
            if line.startswith("## "):
                if current_section:
                    sections.append(current_section)
                current_section = line[3:].strip()
        if current_section:
            sections.append(current_section)

        # Generate summary
        output = "GDD Summary:\n\n"
        
        if metadata:
            output += "Metadata:\n"
            for key, value in metadata.items():
                output += f"  - {key}: {value}\n"
            output += "\n"
        
        output += f"Sections ({len(sections)}):\n"
        for section in sections:
            output += f"  - {section}\n"
        
        # Count words
        word_count = len(content.split())
        output += f"\nTotal words: {word_count}"

        return ToolResult.ok(output, {
            "gdd_path": str(gdd_path.relative_to(self.project_root)),
            "metadata": metadata,
            "sections": sections,
            "word_count": word_count
        })

    def _append_section(self, gdd_path: Path, section_name: str, section_content: str) -> ToolResult:
        """Append new section to GDD"""
        if not gdd_path.exists():
            return ToolResult.fail(f"GDD not found at {gdd_path}")

        content = gdd_path.read_text(encoding="utf-8")
        
        # Check if section already exists
        section_header = f"## {section_name}"
        if section_header in content:
            return ToolResult.fail(f"Section '{section_name}' already exists. Use 'update' to modify it.")

        # Append section
        new_section = f"\n\n## {section_name}\n\n{section_content}\n"
        content += new_section

        # Save updated GDD
        gdd_path.write_text(content, encoding="utf-8")

        output = f"Appended section '{section_name}' to GDD\n"
        output += f"GDD path: {gdd_path}"

        return ToolResult.ok(output, {
            "gdd_path": str(gdd_path.relative_to(self.project_root)),
            "section_name": section_name
        })

    def _set_metadata(self, gdd_path: Path, metadata: Dict[str, Any]) -> ToolResult:
        """Set GDD metadata"""
        if not gdd_path.exists():
            return ToolResult.fail(f"GDD not found at {gdd_path}")

        content = gdd_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        
        # Find metadata section
        metadata_start = -1
        metadata_end = -1
        for i, line in enumerate(lines):
            if line.strip() == "## 元数据" or line.strip() == "## Metadata":
                metadata_start = i
            elif metadata_start >= 0 and line.startswith("## "):
                metadata_end = i
                break
        
        if metadata_start < 0:
            return ToolResult.fail("Metadata section not found in GDD")

        # Update metadata
        new_lines = lines[:metadata_start + 1]
        new_lines.append("")
        for key, value in metadata.items():
            new_lines.append(f"- {key}: {value}")
        new_lines.append("")
        
        if metadata_end > 0:
            new_lines.extend(lines[metadata_end:])
        else:
            new_lines.extend(lines[metadata_start + 1:])

        # Save updated GDD
        gdd_path.write_text("\n".join(new_lines), encoding="utf-8")

        output = f"Updated metadata in GDD\n"
        output += f"GDD path: {gdd_path}\n"
        output += "Updated fields:\n"
        for key, value in metadata.items():
            output += f"  - {key}: {value}\n"

        return ToolResult.ok(output, {
            "gdd_path": str(gdd_path.relative_to(self.project_root)),
            "metadata": metadata
        })

    def _generate_standard_template(
        self, project_name: str, genre: str, target_engine: str, target_platform: str, is_rpg: bool
    ) -> str:
        """Generate standard GDD template"""
        template = f"""# 游戏设计文档 - {project_name}

## 元数据

- 项目名称: {project_name}
- 类型: {genre}
- 目标引擎: {target_engine}
- 目标平台: {target_platform}
- RPG 重点: {"是" if is_rpg else "否"}
- 创建日期: {datetime.now().strftime("%Y-%m-%d")}
- 最后更新: {datetime.now().strftime("%Y-%m-%d")}

## 概述

[游戏概述 - 描述游戏的核心概念、目标受众和独特卖点]

## 核心机制

[核心游戏机制 - 描述玩家如何与游戏互动]

### 游戏循环

[描述核心游戏循环]

### 控制方式

[描述玩家控制方式]

## 角色系统

[角色设计 - 描述玩家角色和NPC]

### 玩家角色

[玩家角色设计]

### NPC

[NPC设计]

"""

        if is_rpg:
            template += """## 剧情系统

[剧情设计 - 描述游戏的故事和叙事]

### 世界观

[世界观设定]

### 主线剧情

[主线剧情概述]

## 任务系统

[任务设计 - 描述任务类型和结构]

### 任务类型

[任务类型说明]

### 任务奖励

[任务奖励系统]

"""

        template += """## 技术架构

[技术设计 - 描述技术实现方案]

### 引擎选择

[引擎选择理由]

### 架构设计

[系统架构设计]

## 美术风格

[美术设计 - 描述视觉风格]

## 音效音乐

[音频设计 - 描述音效和音乐]

## 开发计划

[开发计划 - 描述开发阶段和里程碑]

### 阶段划分

- 设计阶段
- 实现阶段
- 内容制作阶段
- 测试阶段
- 发布阶段

## 附录

[附加信息和参考资料]
"""
        return template

    def _generate_rpg_template(
        self, project_name: str, genre: str, target_engine: str, target_platform: str
    ) -> str:
        """Generate RPG-specific GDD template"""
        template = f"""# RPG 游戏设计文档 - {project_name}

## 元数据

- 项目名称: {project_name}
- 类型: {genre} (RPG)
- 目标引擎: {target_engine}
- 目标平台: {target_platform}
- RPG 重点: 是
- 创建日期: {datetime.now().strftime("%Y-%m-%d")}
- 最后更新: {datetime.now().strftime("%Y-%m-%d")}

## 概述

[游戏概述 - 描述RPG游戏的核心概念和独特之处]

## 世界观设定

### 世界背景

[世界的历史、地理和文化背景]

### 阵营系统

[游戏中的各个阵营及其关系]

### 时间线

[游戏世界的重要历史事件]

## 剧情系统

### 主线剧情

[主线剧情概述，包括起承转合]

### 支线剧情

[支线剧情类型和设计原则]

### 剧情分支

[剧情分支和玩家选择的影响]

## 角色系统

### 玩家角色

[玩家角色的成长系统、属性、技能]

#### 属性系统

[力量、敏捷、智力等属性说明]

#### 技能系统

[技能树、技能获取和升级]

#### 装备系统

[装备类型、品质、强化]

### NPC 系统

[NPC类型、对话系统、好感度系统]

## 任务系统

### 任务类型

- 主线任务
- 支线任务
- 日常任务
- 隐藏任务

### 任务结构

[任务的触发、进行、完成流程]

### 任务奖励

[经验值、金币、物品、声望等奖励]

## 战斗系统

### 战斗机制

[回合制/即时制/动作战斗等]

### 技能系统

[技能释放、冷却、消耗]

### 敌人设计

[敌人类型、AI行为、难度曲线]

## 经济系统

### 货币系统

[货币类型和获取方式]

### 商店系统

[商店类型、商品刷新]

### 交易系统

[玩家间交易、拍卖行]

## 社交系统

### 队伍系统

[组队机制、队伍加成]

### 公会系统

[公会功能、公会活动]

### 好友系统

[好友功能、互动方式]

## 进度系统

### 等级系统

[等级上限、经验曲线]

### 成就系统

[成就类型、奖励]

### 收集系统

[图鉴、收藏品]

## 技术架构

[技术实现方案]

## 美术风格

[视觉风格、UI设计]

## 音效音乐

[BGM、音效设计]

## 开发计划

### 里程碑

- M1: 核心系统原型
- M2: 剧情和任务实现
- M3: 内容填充
- M4: 平衡调整
- M5: 测试和优化

## 附录

[参考资料、灵感来源]
"""
        return template

    def _generate_minimal_template(
        self, project_name: str, genre: str, target_engine: str, target_platform: str
    ) -> str:
        """Generate minimal GDD template"""
        template = f"""# {project_name} - Game Design Document

## Metadata

- Project: {project_name}
- Genre: {genre}
- Engine: {target_engine}
- Platform: {target_platform}
- Created: {datetime.now().strftime("%Y-%m-%d")}

## Overview

[Brief game description]

## Core Mechanics

[Core gameplay mechanics]

## Technical Notes

[Technical implementation notes]

## Development Plan

[Development milestones]
"""
        return template

    def _resolve_path(self, raw: str) -> Path:
        """Resolve path relative to project root"""
        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path)

    def get_execution_message(self, **kwargs) -> str:
        action = kwargs.get("action", "unknown")
        return f"Managing GDD: {action}"

    def _validate_gdd(self, gdd_path: Path) -> ToolResult:
        """Validate GDD structure and completeness"""
        if not gdd_path.exists():
            return ToolResult.fail(f"GDD not found at {gdd_path}")
        
        content = gdd_path.read_text(encoding="utf-8")
        issues = []
        warnings = []
        
        # Required sections for complete GDD
        required_sections = ["概述", "核心机制", "技术架构"]
        recommended_sections = ["角色系统", "美术风格", "音效音乐", "开发计划"]
        
        for section in required_sections:
            if f"## {section}" not in content and f"# {section}" not in content:
                issues.append(f"缺少必需章节: {section}")
        
        for section in recommended_sections:
            if f"## {section}" not in content and f"# {section}" not in content:
                warnings.append(f"建议添加: {section}")
        
        # Check for empty sections
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("## ") or line.startswith("# "):
                # Check if next non-empty line is another section
                has_content = False
                for j in range(i+1, min(i+10, len(lines))):
                    if lines[j].strip() and not lines[j].startswith("#"):
                        has_content = True
                        break
                if not has_content:
                    warnings.append(f"空章节可能: {line.strip()}")
        
        # Check metadata
        if "元数据" not in content and "Metadata" not in content:
            warnings.append("缺少元数据部分")
        
        # Generate report
        word_count = len(content.split())
        section_count = content.count("## ") + content.count("# ")
        
        output = f"GDD 验证报告\n"
        output += f"{'='*50}\n"
        output += f"文件: {gdd_path}\n"
        output += f"字数: {word_count}\n"
        output += f"章节数: {section_count}\n\n"
        
        if issues:
            output += f"严重问题 ({len(issues)}):\n"
            for issue in issues:
                output += f"  ✗ {issue}\n"
            output += "\n"
        
        if warnings:
            output += f"建议改进 ({len(warnings)}):\n"
            for warning in warnings:
                output += f"  ⚠ {warning}\n"
            output += "\n"
        
        if not issues:
            output += "✓ 所有必需章节完整\n"
        
        return ToolResult.ok(output, {
            "word_count": word_count,
            "section_count": section_count,
            "issues": issues,
            "warnings": warnings,
            "valid": len(issues) == 0
        })

    def _manage_version(self, gdd_path: Path, version_action: str) -> ToolResult:
        """Manage GDD version (backup, list, restore)"""
        if not gdd_path.exists():
            return ToolResult.fail(f"GDD not found at {gdd_path}")
        
        version_dir = gdd_path.parent / ".gdd_versions"
        
        if version_action == "create":
            # Create backup
            version_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = version_dir / f"GDD_{timestamp}.md"
            
            import shutil
            shutil.copy2(gdd_path, backup_path)
            
            output = f"创建GDD备份\n"
            output += f"备份文件: {backup_path.name}\n"
            output += f"保存位置: {version_dir}"
            
            return ToolResult.ok(output, {
                "backup_path": str(backup_path.relative_to(self.project_root)),
                "timestamp": timestamp
            })
        
        elif version_action == "list":
            if not version_dir.exists():
                return ToolResult.ok("没有版本备份")
            
            versions = sorted(version_dir.glob("GDD_*.md"), reverse=True)
            output = f"GDD 版本历史 ({len(versions)} 个备份):\n"
            for i, v in enumerate(versions[:10], 1):
                output += f"{i}. {v.name}\n"
            
            return ToolResult.ok(output, {
                "versions": [str(v.relative_to(self.project_root)) for v in versions[:10]]
            })
        
        else:
            return ToolResult.fail(f"未知版本操作: {version_action}")

    def _compare_gdd(self, gdd_path1: Path, gdd_path2: Path) -> ToolResult:
        """Compare two GDD versions"""
        if not gdd_path1.exists() or not gdd_path2.exists():
            return ToolResult.fail(f"One or both GDD files not found")
        
        content1 = gdd_path1.read_text(encoding="utf-8")
        content2 = gdd_path2.read_text(encoding="utf-8")
        
        # Extract sections
        def extract_sections(content):
            sections = {}
            current = None
            for line in content.split("\n"):
                if line.startswith("## "):
                    current = line[3:].strip()
                    sections[current] = ""
                elif current:
                    sections[current] += line + "\n"
            return sections
        
        sections1 = extract_sections(content1)
        sections2 = extract_sections(content2)
        
        # Compare
        added = set(sections2.keys()) - set(sections1.keys())
        removed = set(sections1.keys()) - set(sections2.keys())
        modified = []
        
        for section in set(sections1.keys()) & set(sections2.keys()):
            if sections1[section] != sections2[section]:
                modified.append(section)
        
        output = "GDD 对比报告\n"
        output += f"{'='*50}\n"
        output += f"文件1: {gdd_path1.name}\n"
        output += f"文件2: {gdd_path2.name}\n\n"
        
        if added:
            output += f"新增章节 ({len(added)}):\n"
            for section in added:
                output += f"  + {section}\n"
            output += "\n"
        
        if removed:
            output += f"删除章节 ({len(removed)}):\n"
            for section in removed:
                output += f"  - {section}\n"
            output += "\n"
        
        if modified:
            output += f"修改章节 ({len(modified)}):\n"
            for section in modified:
                output += f"  ~ {section}\n"
            output += "\n"
        
        if not added and not removed and not modified:
            output += "✓ 两个GDD完全相同\n"
        
        return ToolResult.ok(output, {
            "added": list(added),
            "removed": list(removed),
            "modified": modified
        })

    def _export_gdd(self, gdd_path: Path, export_format: str, export_path: Optional[str]) -> ToolResult:
        """Export GDD to different formats"""
        if not gdd_path.exists():
            return ToolResult.fail(f"GDD not found at {gdd_path}")
        
        content = gdd_path.read_text(encoding="utf-8")
        
        if export_format == "markdown":
            # Default markdown, just return the content
            return ToolResult.ok(f"GDD内容已准备好导出\n字数: {len(content.split())}", {
                "format": "markdown",
                "content_preview": content[:500]
            })
        
        elif export_format == "html":
            # Convert markdown to simple HTML
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Game Design Document</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }}
        h1, h2, h3 {{ color: #333; }}
        h2 {{ border-bottom: 2px solid #0078d4; padding-bottom: 10px; }}
        code {{ background: #f5f5f5; padding: 2px 6px; }}
        pre {{ background: #f5f5f5; padding: 10px; overflow-x: auto; }}
    </style>
</head>
<body>
"""
            # Simple markdown to HTML conversion
            for line in content.split("\n"):
                if line.startswith("# "):
                    html_content += f"<h1>{line[2:]}</h1>\n"
                elif line.startswith("## "):
                    html_content += f"<h2>{line[3:]}</h2>\n"
                elif line.startswith("### "):
                    html_content += f"<h3>{line[4:]}</h3>\n"
                elif line.startswith("- "):
                    html_content += f"<li>{line[2:]}</li>\n"
                elif line.strip():
                    html_content += f"<p>{line}</p>\n"
            
            html_content += "</body></html>"
            
            if export_path:
                export_file = self._resolve_path(export_path)
                export_file.parent.mkdir(parents=True, exist_ok=True)
                export_file.write_text(html_content, encoding="utf-8")
                return ToolResult.ok(f"已导出为HTML: {export_file}", {
                    "export_path": str(export_file.relative_to(self.project_root))
                })
            
            return ToolResult.ok(f"HTML转换完成，共{len(html_content)}字符", {
                "format": "html"
            })
        
        else:
            return ToolResult.fail(f"不支持的导出格式: {export_format}")

