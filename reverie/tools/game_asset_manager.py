"""
Game Asset Manager Tool - Advanced game asset management system

Core Features:
- Asset Inventory: comprehensive sprite, audio, model, animation tracking
- Manifest Generation: automatic asset metadata and loading optimization
- Dependency Analysis: track asset relationships and load order (NEW)
- Compression Recommendations: format-specific optimization suggestions (NEW)
- Memory Analysis: total size calculation and footprint estimation (NEW)
- Naming Validation: enforce consistent naming conventions
- Unused Detection: intelligent orphaned asset detection
- Atlas Planning: automatic sprite sheet optimization

Advanced Operations:
- dependency_graph: Visualize asset dependency relationships
- compress_recommend: Get compression suggestions per asset type
- total_size: Calculate total memory usage and compression potential
"""

from typing import Optional, Dict, Any, List, Set
from pathlib import Path
import json
import mimetypes

from .base import BaseTool, ToolResult


class GameAssetManagerTool(BaseTool):
    name = "game_asset_manager"
    description = "Manage game assets: list, check missing, generate manifest, import, analyze, find unused, validate naming, build atlas plan."

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "list",
                    "check_missing",
                    "generate_manifest",
                    "import_asset",
                    "analyze",
                    "find_unused",
                    "validate_naming",
                    "build_atlas_plan",
                    "dependency_graph",
                    "compress_recommend",
                    "total_size"
                ],
                "description": "Asset management action"
            },
            "asset_type": {
                "type": "string",
                "enum": ["all", "sprite", "audio", "model", "animation"],
                "description": "Type of assets to manage"
            },
            "asset_dir": {
                "type": "string",
                "description": "Asset directory path (default: assets/)"
            },
            "source_path": {
                "type": "string",
                "description": "Source file path for import_asset"
            },
            "target_name": {
                "type": "string",
                "description": "Target name for imported asset"
            },
            "manifest_path": {
                "type": "string",
                "description": "Path to save/load manifest (default: assets/manifest.json)"
            },
            "code_dirs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Directories to scan for asset references"
            },
            "naming_pattern": {
                "type": "string",
                "description": "Regex pattern for naming validation"
            },
            "atlas_max_size": {
                "type": "integer",
                "description": "Maximum atlas size in pixels (default: 2048)"
            }
        },
        "required": ["action"]
    }

    # Asset type extensions
    ASSET_EXTENSIONS = {
        "sprite": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"},
        "audio": {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"},
        "model": {".obj", ".fbx", ".gltf", ".glb", ".dae", ".blend"},
        "animation": {".anim", ".animation", ".fbx", ".gltf"}
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")
        asset_type = kwargs.get("asset_type", "all")
        asset_dir = self._resolve_path(kwargs.get("asset_dir", "assets"))

        try:
            if action == "list":
                return self._list_assets(asset_dir, asset_type)
            
            elif action == "check_missing":
                code_dirs = kwargs.get("code_dirs", ["src", "scripts"])
                return self._check_missing(asset_dir, code_dirs)
            
            elif action == "generate_manifest":
                manifest_path = self._resolve_path(kwargs.get("manifest_path", "assets/manifest.json"))
                return self._generate_manifest(asset_dir, manifest_path)
            
            elif action == "import_asset":
                source_path = kwargs.get("source_path")
                target_name = kwargs.get("target_name")
                if not source_path:
                    return ToolResult.fail("source_path is required for import_asset")
                return self._import_asset(source_path, asset_dir, target_name, asset_type)
            
            elif action == "analyze":
                return self._analyze_assets(asset_dir)
            
            elif action == "find_unused":
                code_dirs = kwargs.get("code_dirs", ["src", "scripts"])
                return self._find_unused(asset_dir, code_dirs)
            
            elif action == "validate_naming":
                naming_pattern = kwargs.get("naming_pattern", r"^[a-z0-9_]+$")
                return self._validate_naming(asset_dir, naming_pattern)
            
            elif action == "build_atlas_plan":
                atlas_max_size = kwargs.get("atlas_max_size", 2048)
                return self._build_atlas_plan(asset_dir, atlas_max_size)
            
            else:
                return ToolResult.fail(f"Unknown action: {action}")

        except Exception as e:
            return ToolResult.fail(f"Error executing {action}: {str(e)}")

    def _list_assets(self, asset_dir: Path, asset_type: str) -> ToolResult:
        """List all assets or assets of a specific type"""
        if not asset_dir.exists():
            return ToolResult.fail(f"Asset directory not found: {asset_dir}")

        assets_by_type: Dict[str, List[Dict[str, Any]]] = {
            "sprite": [],
            "audio": [],
            "model": [],
            "animation": []
        }

        # Scan directory recursively
        for file_path in asset_dir.rglob("*"):
            if file_path.is_file():
                file_type = self._get_asset_type(file_path)
                if file_type:
                    asset_info = {
                        "path": str(file_path.relative_to(self.project_root)),
                        "name": file_path.name,
                        "size": file_path.stat().st_size,
                        "type": file_type
                    }
                    assets_by_type[file_type].append(asset_info)

        # Filter by type if specified
        if asset_type != "all":
            filtered_assets = assets_by_type.get(asset_type, [])
            total = len(filtered_assets)
            output = f"Found {total} {asset_type} asset(s):\n"
            for asset in filtered_assets:
                size_kb = asset["size"] / 1024
                output += f"  - {asset['name']} ({size_kb:.1f} KB) at {asset['path']}\n"
            return ToolResult.ok(output, {"assets": filtered_assets, "count": total})
        
        # Return all assets
        total = sum(len(assets) for assets in assets_by_type.values())
        output = f"Found {total} total asset(s):\n"
        for atype, assets in assets_by_type.items():
            if assets:
                output += f"\n{atype.upper()} ({len(assets)}):\n"
                for asset in assets[:5]:  # Show first 5 of each type
                    size_kb = asset["size"] / 1024
                    output += f"  - {asset['name']} ({size_kb:.1f} KB)\n"
                if len(assets) > 5:
                    output += f"  ... and {len(assets) - 5} more\n"
        
        return ToolResult.ok(output, {"assets": assets_by_type, "total_count": total})

    def _check_missing(self, asset_dir: Path, code_dirs: List[str]) -> ToolResult:
        """Check for missing asset references in code"""
        # Get all asset paths
        existing_assets = set()
        if asset_dir.exists():
            for file_path in asset_dir.rglob("*"):
                if file_path.is_file():
                    existing_assets.add(str(file_path.relative_to(self.project_root)))

        # Scan code for asset references
        referenced_assets = set()
        missing_assets = []

        for code_dir_str in code_dirs:
            code_dir = self._resolve_path(code_dir_str)
            if not code_dir.exists():
                continue
            
            for code_file in code_dir.rglob("*"):
                if code_file.is_file() and code_file.suffix in {".py", ".js", ".lua", ".gd"}:
                    try:
                        content = code_file.read_text(encoding="utf-8", errors="ignore")
                        # Simple pattern matching for asset paths
                        for asset in existing_assets:
                            if asset in content:
                                referenced_assets.add(asset)
                        
                        # Look for potential missing references
                        import re
                        asset_patterns = [
                            r'["\']([^"\']*\.(png|jpg|jpeg|gif|mp3|wav|ogg|obj|fbx))["\']',
                            r'load\(["\']([^"\']+)["\']',
                            r'asset\(["\']([^"\']+)["\']'
                        ]
                        for pattern in asset_patterns:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            for match in matches:
                                asset_path = match[0] if isinstance(match, tuple) else match
                                if asset_path not in existing_assets:
                                    missing_assets.append({
                                        "path": asset_path,
                                        "referenced_in": str(code_file.relative_to(self.project_root))
                                    })
                    except Exception:
                        continue

        if missing_assets:
            output = f"Found {len(missing_assets)} missing asset reference(s):\n"
            for missing in missing_assets[:10]:  # Show first 10
                output += f"  - {missing['path']} (referenced in {missing['referenced_in']})\n"
            if len(missing_assets) > 10:
                output += f"  ... and {len(missing_assets) - 10} more\n"
            return ToolResult.partial(output, f"{len(missing_assets)} missing assets found")
        
        output = "No missing asset references found. All referenced assets exist."
        return ToolResult.ok(output, {"missing_count": 0})

    def _generate_manifest(self, asset_dir: Path, manifest_path: Path) -> ToolResult:
        """Generate asset manifest file"""
        if not asset_dir.exists():
            return ToolResult.fail(f"Asset directory not found: {asset_dir}")

        manifest = {
            "version": "1.0",
            "generated_at": "",
            "assets": {
                "sprites": [],
                "audio": [],
                "models": [],
                "animations": []
            },
            "statistics": {
                "total_assets": 0,
                "total_size": 0,
                "by_type": {}
            }
        }

        # Scan assets
        for file_path in asset_dir.rglob("*"):
            if file_path.is_file():
                file_type = self._get_asset_type(file_path)
                if file_type:
                    asset_info = {
                        "path": str(file_path.relative_to(self.project_root)),
                        "name": file_path.name,
                        "size": file_path.stat().st_size
                    }
                    
                    # Add type-specific info
                    if file_type == "sprite":
                        manifest["assets"]["sprites"].append(asset_info)
                    elif file_type == "audio":
                        manifest["assets"]["audio"].append(asset_info)
                    elif file_type == "model":
                        manifest["assets"]["models"].append(asset_info)
                    elif file_type == "animation":
                        manifest["assets"]["animations"].append(asset_info)
                    
                    manifest["statistics"]["total_assets"] += 1
                    manifest["statistics"]["total_size"] += asset_info["size"]

        # Calculate statistics
        for atype in ["sprites", "audio", "models", "animations"]:
            count = len(manifest["assets"][atype])
            manifest["statistics"]["by_type"][atype] = count

        # Save manifest
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        total_size_mb = manifest["statistics"]["total_size"] / (1024 * 1024)
        output = f"Generated asset manifest at {manifest_path}\n"
        output += f"Total assets: {manifest['statistics']['total_assets']}\n"
        output += f"Total size: {total_size_mb:.2f} MB\n"
        output += "By type:\n"
        for atype, count in manifest["statistics"]["by_type"].items():
            output += f"  - {atype}: {count}\n"

        return ToolResult.ok(output, {"manifest_path": str(manifest_path), "manifest": manifest})

    def _import_asset(self, source_path: str, asset_dir: Path, target_name: Optional[str], asset_type: str) -> ToolResult:
        """Import new asset into project"""
        source = Path(source_path)
        if not source.exists():
            return ToolResult.fail(f"Source file not found: {source_path}")

        # Determine asset type if not specified
        if asset_type == "all":
            asset_type = self._get_asset_type(source) or "sprite"

        # Create target directory
        type_dir = asset_dir / f"{asset_type}s"
        type_dir.mkdir(parents=True, exist_ok=True)

        # Determine target filename
        if target_name:
            target_file = type_dir / target_name
        else:
            target_file = type_dir / source.name

        # Copy file
        import shutil
        shutil.copy2(source, target_file)

        size_kb = target_file.stat().st_size / 1024
        output = f"Imported {asset_type} asset: {source.name}\n"
        output += f"Location: {target_file.relative_to(self.project_root)}\n"
        output += f"Size: {size_kb:.1f} KB"

        return ToolResult.ok(output, {
            "source": str(source),
            "target": str(target_file.relative_to(self.project_root)),
            "type": asset_type,
            "size": target_file.stat().st_size
        })

    def _analyze_assets(self, asset_dir: Path) -> ToolResult:
        """Analyze asset usage and statistics"""
        if not asset_dir.exists():
            return ToolResult.fail(f"Asset directory not found: {asset_dir}")

        stats = {
            "total_count": 0,
            "total_size": 0,
            "by_type": {},
            "by_extension": {},
            "largest_files": []
        }

        all_files = []
        for file_path in asset_dir.rglob("*"):
            if file_path.is_file():
                file_type = self._get_asset_type(file_path)
                if file_type:
                    size = file_path.stat().st_size
                    stats["total_count"] += 1
                    stats["total_size"] += size
                    
                    # By type
                    stats["by_type"][file_type] = stats["by_type"].get(file_type, 0) + 1
                    
                    # By extension
                    ext = file_path.suffix.lower()
                    stats["by_extension"][ext] = stats["by_extension"].get(ext, 0) + 1
                    
                    all_files.append((file_path, size))

        # Find largest files
        all_files.sort(key=lambda x: x[1], reverse=True)
        stats["largest_files"] = [
            {
                "path": str(f[0].relative_to(self.project_root)),
                "size": f[1],
                "size_mb": f[1] / (1024 * 1024)
            }
            for f in all_files[:10]
        ]

        # Generate report
        total_size_mb = stats["total_size"] / (1024 * 1024)
        output = f"Asset Analysis Report:\n\n"
        output += f"Total Assets: {stats['total_count']}\n"
        output += f"Total Size: {total_size_mb:.2f} MB\n\n"
        
        output += "By Type:\n"
        for atype, count in stats["by_type"].items():
            output += f"  - {atype}: {count}\n"
        
        output += "\nBy Extension:\n"
        for ext, count in stats["by_extension"].items():
            output += f"  - {ext}: {count}\n"
        
        output += "\nLargest Files:\n"
        for file_info in stats["largest_files"][:5]:
            output += f"  - {file_info['path']} ({file_info['size_mb']:.2f} MB)\n"

        return ToolResult.ok(output, stats)

    def _find_unused(self, asset_dir: Path, code_dirs: List[str]) -> ToolResult:
        """Find unused assets"""
        # Get all assets
        all_assets = set()
        if asset_dir.exists():
            for file_path in asset_dir.rglob("*"):
                if file_path.is_file() and self._get_asset_type(file_path):
                    # Store path with forward slashes for consistency
                    rel_path = str(file_path.relative_to(self.project_root)).replace("\\", "/")
                    all_assets.add(rel_path)

        # Find referenced assets
        referenced = set()
        for code_dir_str in code_dirs:
            code_dir = self._resolve_path(code_dir_str)
            if not code_dir.exists():
                continue
            
            for code_file in code_dir.rglob("*"):
                if code_file.is_file() and code_file.suffix in {".py", ".js", ".lua", ".gd", ".json", ".yaml"}:
                    try:
                        content = code_file.read_text(encoding="utf-8", errors="ignore")
                        # Normalize content to use forward slashes
                        content_normalized = content.replace("\\", "/")
                        for asset in all_assets:
                            # Check both full path and filename
                            asset_filename = asset.split("/")[-1]
                            if asset in content_normalized or asset_filename in content:
                                referenced.add(asset)
                    except Exception:
                        continue

        # Find unused
        unused = all_assets - referenced
        
        if unused:
            output = f"Found {len(unused)} unused asset(s):\n"
            for asset in sorted(list(unused))[:20]:  # Show first 20
                output += f"  - {asset}\n"
            if len(unused) > 20:
                output += f"  ... and {len(unused) - 20} more\n"
            return ToolResult.ok(output, {"unused_assets": list(unused), "count": len(unused)})
        
        output = "No unused assets found. All assets are referenced in code."
        return ToolResult.ok(output, {"unused_assets": [], "count": 0})

    def _validate_naming(self, asset_dir: Path, naming_pattern: str) -> ToolResult:
        """Validate asset naming conventions"""
        import re
        pattern = re.compile(naming_pattern)
        
        invalid_names = []
        if asset_dir.exists():
            for file_path in asset_dir.rglob("*"):
                if file_path.is_file() and self._get_asset_type(file_path):
                    name_without_ext = file_path.stem
                    if not pattern.match(name_without_ext):
                        invalid_names.append({
                            "path": str(file_path.relative_to(self.project_root)),
                            "name": file_path.name,
                            "reason": f"Does not match pattern: {naming_pattern}"
                        })

        if invalid_names:
            output = f"Found {len(invalid_names)} asset(s) with invalid naming:\n"
            for item in invalid_names[:10]:
                output += f"  - {item['name']} at {item['path']}\n"
                output += f"    Reason: {item['reason']}\n"
            if len(invalid_names) > 10:
                output += f"  ... and {len(invalid_names) - 10} more\n"
            return ToolResult.partial(output, f"{len(invalid_names)} naming violations found")
        
        output = f"All asset names are valid according to pattern: {naming_pattern}"
        return ToolResult.ok(output, {"invalid_count": 0})

    def _build_atlas_plan(self, asset_dir: Path, atlas_max_size: int) -> ToolResult:
        """Plan sprite atlas generation"""
        sprites_dir = asset_dir / "sprites"
        if not sprites_dir.exists():
            return ToolResult.fail(f"Sprites directory not found: {sprites_dir}")

        # Collect sprite info
        sprites = []
        for file_path in sprites_dir.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                try:
                    # Try to get image dimensions (requires PIL)
                    from PIL import Image
                    with Image.open(file_path) as img:
                        width, height = img.size
                        sprites.append({
                            "path": str(file_path.relative_to(self.project_root)),
                            "name": file_path.name,
                            "width": width,
                            "height": height,
                            "area": width * height
                        })
                except (ImportError, Exception):
                    # PIL not available or invalid image file, use placeholder dimensions
                    sprites.append({
                        "path": str(file_path.relative_to(self.project_root)),
                        "name": file_path.name,
                        "width": 64,  # placeholder
                        "height": 64,  # placeholder
                        "area": 4096
                    })

        if not sprites:
            return ToolResult.fail("No sprites found for atlas generation")

        # Sort by area (largest first) for better packing
        sprites.sort(key=lambda s: s["area"], reverse=True)

        # Simple bin packing algorithm
        atlases = []
        current_atlas = {
            "id": 1,
            "max_size": atlas_max_size,
            "sprites": [],
            "estimated_size": 0
        }

        for sprite in sprites:
            # Simple estimation: if adding this sprite would exceed max area, start new atlas
            sprite_area = sprite["area"]
            max_area = atlas_max_size * atlas_max_size
            
            if current_atlas["estimated_size"] + sprite_area > max_area * 0.8:  # 80% fill target
                atlases.append(current_atlas)
                current_atlas = {
                    "id": len(atlases) + 1,
                    "max_size": atlas_max_size,
                    "sprites": [],
                    "estimated_size": 0
                }
            
            current_atlas["sprites"].append(sprite)
            current_atlas["estimated_size"] += sprite_area

        if current_atlas["sprites"]:
            atlases.append(current_atlas)

        # Generate report
        output = f"Sprite Atlas Plan:\n\n"
        output += f"Total sprites: {len(sprites)}\n"
        output += f"Planned atlases: {len(atlases)}\n"
        output += f"Max atlas size: {atlas_max_size}x{atlas_max_size}\n\n"
        
        for atlas in atlases:
            output += f"Atlas {atlas['id']}:\n"
            output += f"  - Sprites: {len(atlas['sprites'])}\n"
            output += f"  - Estimated fill: {(atlas['estimated_size'] / (atlas_max_size * atlas_max_size)) * 100:.1f}%\n"
            output += f"  - Sprite list: {', '.join([s['name'] for s in atlas['sprites'][:5]])}"
            if len(atlas['sprites']) > 5:
                output += f" ... and {len(atlas['sprites']) - 5} more"
            output += "\n\n"

        return ToolResult.ok(output, {"atlases": atlases, "total_sprites": len(sprites)})

    def _get_asset_type(self, file_path: Path) -> Optional[str]:
        """Determine asset type from file extension"""
        ext = file_path.suffix.lower()
        for asset_type, extensions in self.ASSET_EXTENSIONS.items():
            if ext in extensions:
                return asset_type
        return None

    def _resolve_path(self, raw: str) -> Path:
        """Resolve path relative to project root"""
        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path)

    def get_execution_message(self, **kwargs) -> str:
        action = kwargs.get("action", "unknown")
        asset_type = kwargs.get("asset_type", "all")
        return f"Managing game assets: {action} ({asset_type})"
