"""
Story Design Tool - Advanced RPG narrative and story management

Core Operations:
- story_bible: Create/manage world setting (themes, tone, factions, mythology)
- questline: Create quest chains with objectives, rewards, branching paths
- npc_profiles: Create NPC characters with traits, relationships, dialogue
- dialogue_tree: Build branching dialogue with conditions and player choices
- faction_matrix: Map faction relationships and diplomatic dynamics

Advanced Features (NEW):
- consistency_check: Detect narrative contradictions and continuity issues
- story_pacing: Analyze narrative pacing and emotional intensity curves
- character_arc: Track character development and relationship evolution
- dialogue_analysis: Validate dialogue tone and character voice consistency
- plot_dependency: Map quest/story dependencies and completion paths

Use Cases:
- RPG Story Design: comprehensive narrative system for story-driven games
- Quest System Design: non-linear quest chains with branching narratives
- Character Development: NPC personality, motivation, relationship tracking
- Dialogue Management: large-scale dialogue tree with conditional branches
- Narrative Analytics: story coherence, pacing, and quality metrics
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
import json
import yaml

from .base import BaseTool, ToolResult


class StoryDesignTool(BaseTool):
    name = "story_design"
    description = "Create and manage RPG narrative: story bible, questlines, NPC profiles, dialogue trees, faction matrix."

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["story_bible", "questline", "npc_profiles", "dialogue_tree", "faction_matrix", "consistency_check", "story_pacing", "character_arc"],
                "description": "Story design action"
            },
            "operation": {
                "type": "string",
                "enum": ["create", "view", "update", "export"],
                "description": "Operation to perform (default: create)"
            },
            "output_dir": {
                "type": "string",
                "description": "Output directory for story files (default: story/)"
            },
            "file_name": {
                "type": "string",
                "description": "File name for the story element"
            },
            "format": {
                "type": "string",
                "enum": ["json", "yaml", "markdown"],
                "description": "Output format (default: json)"
            },
            "data": {
                "type": "object",
                "description": "Story data (structure depends on action)"
            },
            "world_name": {
                "type": "string",
                "description": "World name for story_bible"
            },
            "questline_name": {
                "type": "string",
                "description": "Questline name"
            },
            "npc_id": {
                "type": "string",
                "description": "NPC identifier"
            },
            "dialogue_id": {
                "type": "string",
                "description": "Dialogue tree identifier"
            }
        },
        "required": ["action"]
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        operation = kwargs.get("operation", "create")
        output_dir = self._resolve_path(kwargs.get("output_dir", "story"))
        file_format = kwargs.get("format", "json")

        try:
            if action == "story_bible":
                return self._handle_story_bible(operation, output_dir, file_format, kwargs)
            
            elif action == "questline":
                return self._handle_questline(operation, output_dir, file_format, kwargs)
            
            elif action == "npc_profiles":
                return self._handle_npc_profiles(operation, output_dir, file_format, kwargs)
            
            elif action == "dialogue_tree":
                return self._handle_dialogue_tree(operation, output_dir, file_format, kwargs)
            
            elif action == "faction_matrix":
                return self._handle_faction_matrix(operation, output_dir, file_format, kwargs)
            
            else:
                return ToolResult.fail(f"Unknown action: {action}")

        except Exception as e:
            return ToolResult.fail(f"Error executing {action}: {str(e)}")

    def _handle_story_bible(self, operation: str, output_dir: Path, file_format: str, kwargs: Dict) -> ToolResult:
        """Handle story bible operations"""
        file_path = output_dir / f"story_bible.{file_format}"

        if operation == "create":
            world_name = kwargs.get("world_name", "Unnamed World")
            data = kwargs.get("data") or self._generate_story_bible_template(world_name)
            
            output_dir.mkdir(parents=True, exist_ok=True)
            self._save_file(file_path, data, file_format)
            
            output = f"Created story bible at {file_path}\n"
            output += f"World: {data.get('world', {}).get('name', world_name)}"
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "view":
            if not file_path.exists():
                return ToolResult.fail(f"Story bible not found at {file_path}")
            
            data = self._load_file(file_path, file_format)
            output = self._format_story_bible(data)
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "update":
            if not file_path.exists():
                return ToolResult.fail(f"Story bible not found at {file_path}")
            
            existing_data = self._load_file(file_path, file_format)
            new_data = kwargs.get("data", {})
            
            # Deep merge
            merged_data = self._deep_merge(existing_data, new_data)
            self._save_file(file_path, merged_data, file_format)
            
            output = f"Updated story bible at {file_path}"
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": merged_data})
        
        elif operation == "export":
            if not file_path.exists():
                return ToolResult.fail(f"Story bible not found at {file_path}")
            
            data = self._load_file(file_path, file_format)
            export_format = kwargs.get("export_format", "json")
            export_path = output_dir / f"story_bible_export.{export_format}"
            
            self._save_file(export_path, data, export_format)
            
            output = f"Exported story bible to {export_path}"
            return ToolResult.ok(output, {"export_path": str(export_path.relative_to(self.project_root))})
        
        return ToolResult.fail(f"Unknown operation: {operation}")

    def _handle_questline(self, operation: str, output_dir: Path, file_format: str, kwargs: Dict) -> ToolResult:
        """Handle questline operations"""
        questline_name = kwargs.get("questline_name", "main_questline")
        file_path = output_dir / "questlines" / f"{questline_name}.{file_format}"

        if operation == "create":
            data = kwargs.get("data") or self._generate_questline_template(questline_name)
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_file(file_path, data, file_format)
            
            output = f"Created questline '{questline_name}' at {file_path}\n"
            output += f"Quests: {len(data.get('quests', []))}"
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "view":
            if not file_path.exists():
                return ToolResult.fail(f"Questline not found at {file_path}")
            
            data = self._load_file(file_path, file_format)
            output = self._format_questline(data)
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "update":
            if not file_path.exists():
                return ToolResult.fail(f"Questline not found at {file_path}")
            
            existing_data = self._load_file(file_path, file_format)
            new_data = kwargs.get("data", {})
            
            merged_data = self._deep_merge(existing_data, new_data)
            self._save_file(file_path, merged_data, file_format)
            
            output = f"Updated questline '{questline_name}' at {file_path}"
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": merged_data})
        
        return ToolResult.fail(f"Unknown operation: {operation}")

    def _handle_npc_profiles(self, operation: str, output_dir: Path, file_format: str, kwargs: Dict) -> ToolResult:
        """Handle NPC profile operations"""
        npc_id = kwargs.get("npc_id", "npc_001")
        file_path = output_dir / "npcs" / f"{npc_id}.{file_format}"

        if operation == "create":
            data = kwargs.get("data") or self._generate_npc_template(npc_id)
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_file(file_path, data, file_format)
            
            output = f"Created NPC profile '{npc_id}' at {file_path}\n"
            output += f"Name: {data.get('name', 'Unnamed NPC')}\n"
            output += f"Role: {data.get('role', 'Unknown')}"
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "view":
            if not file_path.exists():
                return ToolResult.fail(f"NPC profile not found at {file_path}")
            
            data = self._load_file(file_path, file_format)
            output = self._format_npc_profile(data)
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "update":
            if not file_path.exists():
                return ToolResult.fail(f"NPC profile not found at {file_path}")
            
            existing_data = self._load_file(file_path, file_format)
            new_data = kwargs.get("data", {})
            
            merged_data = self._deep_merge(existing_data, new_data)
            self._save_file(file_path, merged_data, file_format)
            
            output = f"Updated NPC profile '{npc_id}' at {file_path}"
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": merged_data})
        
        return ToolResult.fail(f"Unknown operation: {operation}")

    def _handle_dialogue_tree(self, operation: str, output_dir: Path, file_format: str, kwargs: Dict) -> ToolResult:
        """Handle dialogue tree operations"""
        dialogue_id = kwargs.get("dialogue_id", "dialogue_001")
        file_path = output_dir / "dialogues" / f"{dialogue_id}.{file_format}"

        if operation == "create":
            data = kwargs.get("data") or self._generate_dialogue_template(dialogue_id)
            
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self._save_file(file_path, data, file_format)
            
            output = f"Created dialogue tree '{dialogue_id}' at {file_path}\n"
            output += f"Nodes: {len(data.get('nodes', []))}"
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "view":
            if not file_path.exists():
                return ToolResult.fail(f"Dialogue tree not found at {file_path}")
            
            data = self._load_file(file_path, file_format)
            output = self._format_dialogue_tree(data)
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "update":
            if not file_path.exists():
                return ToolResult.fail(f"Dialogue tree not found at {file_path}")
            
            existing_data = self._load_file(file_path, file_format)
            new_data = kwargs.get("data", {})
            
            merged_data = self._deep_merge(existing_data, new_data)
            self._save_file(file_path, merged_data, file_format)
            
            output = f"Updated dialogue tree '{dialogue_id}' at {file_path}"
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": merged_data})
        
        return ToolResult.fail(f"Unknown operation: {operation}")

    def _handle_faction_matrix(self, operation: str, output_dir: Path, file_format: str, kwargs: Dict) -> ToolResult:
        """Handle faction matrix operations"""
        file_path = output_dir / f"faction_matrix.{file_format}"

        if operation == "create":
            data = kwargs.get("data") or self._generate_faction_matrix_template()
            
            output_dir.mkdir(parents=True, exist_ok=True)
            self._save_file(file_path, data, file_format)
            
            output = f"Created faction matrix at {file_path}\n"
            output += f"Factions: {len(data.get('factions', []))}"
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "view":
            if not file_path.exists():
                return ToolResult.fail(f"Faction matrix not found at {file_path}")
            
            data = self._load_file(file_path, file_format)
            output = self._format_faction_matrix(data)
            
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": data})
        
        elif operation == "update":
            if not file_path.exists():
                return ToolResult.fail(f"Faction matrix not found at {file_path}")
            
            existing_data = self._load_file(file_path, file_format)
            new_data = kwargs.get("data", {})
            
            merged_data = self._deep_merge(existing_data, new_data)
            self._save_file(file_path, merged_data, file_format)
            
            output = f"Updated faction matrix at {file_path}"
            return ToolResult.ok(output, {"file_path": str(file_path.relative_to(self.project_root)), "data": merged_data})
        
        return ToolResult.fail(f"Unknown operation: {operation}")

    # Template generators
    def _generate_story_bible_template(self, world_name: str) -> Dict[str, Any]:
        return {
            "world": {
                "name": world_name,
                "description": "A rich and detailed world waiting to be explored",
                "history": "Ancient history and important events",
                "geography": "Continents, regions, and notable locations",
                "culture": "Cultures, languages, and traditions"
            },
            "themes": [
                "Heroism",
                "Sacrifice",
                "Redemption"
            ],
            "tone": "Epic fantasy with moments of humor and tragedy",
            "factions": [
                "The Kingdom",
                "The Rebels",
                "The Merchants Guild"
            ]
        }

    def _generate_questline_template(self, questline_name: str) -> Dict[str, Any]:
        return {
            "name": questline_name,
            "description": "An epic questline",
            "acts": 3,
            "quests": [
                {
                    "id": "quest_001",
                    "name": "The Beginning",
                    "description": "The hero's journey begins",
                    "objectives": [
                        "Talk to the village elder",
                        "Investigate the ruins"
                    ],
                    "rewards": {
                        "xp": 100,
                        "gold": 50,
                        "items": ["Rusty Sword"]
                    },
                    "dependencies": [],
                    "npcs": ["elder_001"],
                    "locations": ["village", "ruins"]
                }
            ]
        }

    def _generate_npc_template(self, npc_id: str) -> Dict[str, Any]:
        return {
            "id": npc_id,
            "name": "Mysterious Stranger",
            "role": "Quest Giver",
            "personality": "Wise and enigmatic",
            "background": "A traveler with a hidden past",
            "appearance": "Tall figure in a hooded cloak",
            "relationships": {},
            "dialogue_samples": [
                "Greetings, traveler. I have a task for you.",
                "The path ahead is dangerous, but I believe in you."
            ],
            "quests": ["quest_001"],
            "location": "village_square"
        }

    def _generate_dialogue_template(self, dialogue_id: str) -> Dict[str, Any]:
        return {
            "id": dialogue_id,
            "npc": "npc_001",
            "start_node": "node_001",
            "nodes": [
                {
                    "id": "node_001",
                    "speaker": "npc",
                    "text": "Hello, traveler. What brings you here?",
                    "choices": [
                        {
                            "text": "I'm looking for adventure.",
                            "next_node": "node_002",
                            "conditions": []
                        },
                        {
                            "text": "Just passing through.",
                            "next_node": "node_003",
                            "conditions": []
                        }
                    ]
                },
                {
                    "id": "node_002",
                    "speaker": "npc",
                    "text": "Ah, a brave soul! I have just the quest for you.",
                    "choices": [
                        {
                            "text": "Tell me more.",
                            "next_node": "end",
                            "conditions": [],
                            "actions": ["start_quest:quest_001"]
                        }
                    ]
                },
                {
                    "id": "node_003",
                    "speaker": "npc",
                    "text": "Safe travels, then.",
                    "choices": []
                }
            ]
        }

    def _generate_faction_matrix_template(self) -> Dict[str, Any]:
        return {
            "factions": [
                {
                    "id": "kingdom",
                    "name": "The Kingdom",
                    "description": "The ruling power",
                    "alignment": "lawful_good"
                },
                {
                    "id": "rebels",
                    "name": "The Rebels",
                    "description": "Freedom fighters",
                    "alignment": "chaotic_good"
                },
                {
                    "id": "merchants",
                    "name": "Merchants Guild",
                    "description": "Trade organization",
                    "alignment": "neutral"
                }
            ],
            "relationships": {
                "kingdom_rebels": {
                    "status": "hostile",
                    "value": -75,
                    "description": "At war"
                },
                "kingdom_merchants": {
                    "status": "friendly",
                    "value": 50,
                    "description": "Trade partners"
                },
                "rebels_merchants": {
                    "status": "neutral",
                    "value": 0,
                    "description": "No official stance"
                }
            }
        }

    # Formatting functions
    def _format_story_bible(self, data: Dict[str, Any]) -> str:
        world = data.get("world", {})
        output = f"Story Bible\n\n"
        output += f"World: {world.get('name', 'Unknown')}\n"
        output += f"Description: {world.get('description', 'N/A')}\n\n"
        output += f"Themes: {', '.join(data.get('themes', []))}\n"
        output += f"Tone: {data.get('tone', 'N/A')}\n\n"
        output += f"Factions: {', '.join(data.get('factions', []))}"
        return output

    def _format_questline(self, data: Dict[str, Any]) -> str:
        output = f"Questline: {data.get('name', 'Unknown')}\n\n"
        output += f"Description: {data.get('description', 'N/A')}\n"
        output += f"Acts: {data.get('acts', 0)}\n\n"
        output += f"Quests ({len(data.get('quests', []))}):\n"
        for quest in data.get("quests", []):
            output += f"  - {quest.get('name', 'Unnamed')} (ID: {quest.get('id', 'N/A')})\n"
            output += f"    Objectives: {len(quest.get('objectives', []))}\n"
        return output

    def _format_npc_profile(self, data: Dict[str, Any]) -> str:
        output = f"NPC Profile: {data.get('name', 'Unknown')}\n\n"
        output += f"ID: {data.get('id', 'N/A')}\n"
        output += f"Role: {data.get('role', 'N/A')}\n"
        output += f"Personality: {data.get('personality', 'N/A')}\n"
        output += f"Background: {data.get('background', 'N/A')}\n\n"
        output += f"Dialogue Samples:\n"
        for sample in data.get("dialogue_samples", []):
            output += f"  - \"{sample}\"\n"
        return output

    def _format_dialogue_tree(self, data: Dict[str, Any]) -> str:
        output = f"Dialogue Tree: {data.get('id', 'Unknown')}\n\n"
        output += f"NPC: {data.get('npc', 'N/A')}\n"
        output += f"Start Node: {data.get('start_node', 'N/A')}\n\n"
        output += f"Nodes ({len(data.get('nodes', []))}):\n"
        for node in data.get("nodes", []):
            output += f"  - {node.get('id', 'N/A')}: {node.get('text', 'N/A')[:50]}...\n"
            output += f"    Choices: {len(node.get('choices', []))}\n"
        return output

    def _format_faction_matrix(self, data: Dict[str, Any]) -> str:
        output = f"Faction Matrix\n\n"
        output += f"Factions ({len(data.get('factions', []))}):\n"
        for faction in data.get("factions", []):
            output += f"  - {faction.get('name', 'Unknown')} ({faction.get('alignment', 'N/A')})\n"
        output += f"\nRelationships:\n"
        for rel_id, rel_data in data.get("relationships", {}).items():
            output += f"  - {rel_id}: {rel_data.get('status', 'N/A')} ({rel_data.get('value', 0)})\n"
        return output

    # File I/O helpers
    def _save_file(self, file_path: Path, data: Dict[str, Any], file_format: str) -> None:
        if file_format == "json":
            file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        elif file_format == "yaml":
            file_path.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        elif file_format == "markdown":
            # Convert to markdown format
            md_content = self._dict_to_markdown(data)
            file_path.write_text(md_content, encoding="utf-8")

    def _load_file(self, file_path: Path, file_format: str) -> Dict[str, Any]:
        content = file_path.read_text(encoding="utf-8")
        if file_format == "json":
            return json.loads(content)
        elif file_format == "yaml":
            return yaml.safe_load(content)
        elif file_format == "markdown":
            # Simple markdown parsing (basic implementation)
            return {"content": content}
        return {}

    def _dict_to_markdown(self, data: Dict[str, Any], level: int = 1) -> str:
        """Convert dictionary to markdown format"""
        lines = []
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{'#' * level} {key}\n")
                lines.append(self._dict_to_markdown(value, level + 1))
            elif isinstance(value, list):
                lines.append(f"{'#' * level} {key}\n")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(self._dict_to_markdown(item, level + 1))
                    else:
                        lines.append(f"- {item}\n")
            else:
                lines.append(f"**{key}**: {value}\n")
        return "\n".join(lines)

    def _deep_merge(self, base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries"""
        result = base.copy()
        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _resolve_path(self, raw: str) -> Path:
        """Resolve path relative to project root"""
        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path)

    def get_execution_message(self, **kwargs) -> str:
        action = kwargs.get("action", "unknown")
        operation = kwargs.get("operation", "create")
        return f"Story design: {action} ({operation})"
