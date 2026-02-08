"""
Game Asset Packer Tool - Pack game assets into distributable archives

Supports operations:
- pack: Pack assets into zip file
- unpack: Extract assets from zip file
- generate_manifest: Generate packing manifest
- validate: Validate packed archive
"""

from typing import Optional, Dict, Any, List
from pathlib import Path
import json
import zipfile
import hashlib

from .base import BaseTool, ToolResult


class GameAssetPackerTool(BaseTool):
    name = "game_asset_packer"
    description = "Pack game assets into distributable archives (zip) with manifest generation."

    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["pack", "unpack", "generate_manifest", "validate"],
                "description": "Packing action"
            },
            "source_dir": {
                "type": "string",
                "description": "Source directory to pack (default: assets/)"
            },
            "output_path": {
                "type": "string",
                "description": "Output zip file path (default: assets.zip)"
            },
            "archive_path": {
                "type": "string",
                "description": "Archive path for unpack/validate"
            },
            "target_dir": {
                "type": "string",
                "description": "Target directory for unpack"
            },
            "include_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File patterns to include (e.g., ['*.png', '*.json'])"
            },
            "exclude_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File patterns to exclude"
            },
            "compression_level": {
                "type": "integer",
                "description": "Compression level 0-9 (default: 6)"
            },
            "generate_checksums": {
                "type": "boolean",
                "description": "Generate file checksums (default: true)"
            }
        },
        "required": ["action"]
    }

    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = Path(context.get("project_root")) if context and context.get("project_root") else Path.cwd()

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action")

        try:
            if action == "pack":
                source_dir = self._resolve_path(kwargs.get("source_dir", "assets"))
                output_path = self._resolve_path(kwargs.get("output_path", "assets.zip"))
                include_patterns = kwargs.get("include_patterns", ["*"])
                exclude_patterns = kwargs.get("exclude_patterns", [])
                compression_level = kwargs.get("compression_level", 6)
                generate_checksums = kwargs.get("generate_checksums", True)
                
                return self._pack_assets(
                    source_dir, output_path, include_patterns, exclude_patterns,
                    compression_level, generate_checksums
                )
            
            elif action == "unpack":
                archive_path = kwargs.get("archive_path")
                target_dir = kwargs.get("target_dir", "assets_unpacked")
                if not archive_path:
                    return ToolResult.fail("archive_path is required for unpack")
                
                return self._unpack_assets(
                    self._resolve_path(archive_path),
                    self._resolve_path(target_dir)
                )
            
            elif action == "generate_manifest":
                source_dir = self._resolve_path(kwargs.get("source_dir", "assets"))
                return self._generate_packing_manifest(source_dir)
            
            elif action == "validate":
                archive_path = kwargs.get("archive_path")
                if not archive_path:
                    return ToolResult.fail("archive_path is required for validate")
                
                return self._validate_archive(self._resolve_path(archive_path))
            
            else:
                return ToolResult.fail(f"Unknown action: {action}")

        except Exception as e:
            return ToolResult.fail(f"Error executing {action}: {str(e)}")

    def _pack_assets(
        self,
        source_dir: Path,
        output_path: Path,
        include_patterns: List[str],
        exclude_patterns: List[str],
        compression_level: int,
        generate_checksums: bool
    ) -> ToolResult:
        """Pack assets into zip file"""
        if not source_dir.exists():
            return ToolResult.fail(f"Source directory not found: {source_dir}")

        # Collect files to pack
        files_to_pack = []
        for pattern in include_patterns:
            for file_path in source_dir.rglob(pattern):
                if file_path.is_file():
                    # Check exclude patterns
                    excluded = False
                    for exclude_pattern in exclude_patterns:
                        if file_path.match(exclude_pattern):
                            excluded = True
                            break
                    
                    if not excluded and file_path not in files_to_pack:
                        files_to_pack.append(file_path)

        if not files_to_pack:
            return ToolResult.fail("No files found to pack")

        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Pack files
        manifest = {
            "version": "1.0",
            "source_dir": str(source_dir.relative_to(self.project_root)),
            "file_count": len(files_to_pack),
            "files": []
        }

        compression = zipfile.ZIP_DEFLATED if compression_level > 0 else zipfile.ZIP_STORED
        
        with zipfile.ZipFile(output_path, 'w', compression=compression, compresslevel=compression_level) as zf:
            for file_path in files_to_pack:
                arcname = str(file_path.relative_to(source_dir))
                zf.write(file_path, arcname)
                
                file_info = {
                    "path": arcname,
                    "size": file_path.stat().st_size
                }
                
                if generate_checksums:
                    file_info["md5"] = self._calculate_md5(file_path)
                
                manifest["files"].append(file_info)

        # Save manifest
        manifest_path = output_path.with_suffix('.json')
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Calculate statistics
        archive_size = output_path.stat().st_size
        total_size = sum(f["size"] for f in manifest["files"])
        compression_ratio = (1 - archive_size / total_size) * 100 if total_size > 0 else 0

        output = f"Successfully packed {len(files_to_pack)} file(s) into {output_path.name}\n"
        output += f"Archive size: {archive_size / 1024:.1f} KB\n"
        output += f"Original size: {total_size / 1024:.1f} KB\n"
        output += f"Compression ratio: {compression_ratio:.1f}%\n"
        output += f"Manifest saved to: {manifest_path.name}"

        return ToolResult.ok(output, {
            "archive_path": str(output_path.relative_to(self.project_root)),
            "manifest_path": str(manifest_path.relative_to(self.project_root)),
            "file_count": len(files_to_pack),
            "archive_size": archive_size,
            "original_size": total_size,
            "compression_ratio": compression_ratio
        })

    def _unpack_assets(self, archive_path: Path, target_dir: Path) -> ToolResult:
        """Extract assets from zip file"""
        if not archive_path.exists():
            return ToolResult.fail(f"Archive not found: {archive_path}")

        if not zipfile.is_zipfile(archive_path):
            return ToolResult.fail(f"Invalid zip file: {archive_path}")

        # Create target directory
        target_dir.mkdir(parents=True, exist_ok=True)

        # Extract files
        extracted_files = []
        with zipfile.ZipFile(archive_path, 'r') as zf:
            file_list = zf.namelist()
            for file_name in file_list:
                zf.extract(file_name, target_dir)
                extracted_files.append(file_name)

        output = f"Successfully extracted {len(extracted_files)} file(s) to {target_dir}\n"
        output += "Extracted files:\n"
        for file_name in extracted_files[:10]:  # Show first 10
            output += f"  - {file_name}\n"
        if len(extracted_files) > 10:
            output += f"  ... and {len(extracted_files) - 10} more\n"

        return ToolResult.ok(output, {
            "target_dir": str(target_dir.relative_to(self.project_root)),
            "file_count": len(extracted_files),
            "files": extracted_files
        })

    def _generate_packing_manifest(self, source_dir: Path) -> ToolResult:
        """Generate packing manifest"""
        if not source_dir.exists():
            return ToolResult.fail(f"Source directory not found: {source_dir}")

        manifest = {
            "version": "1.0",
            "source_dir": str(source_dir.relative_to(self.project_root)),
            "files": [],
            "statistics": {
                "total_files": 0,
                "total_size": 0,
                "by_extension": {}
            }
        }

        # Scan directory
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                size = file_path.stat().st_size
                ext = file_path.suffix.lower()
                
                file_info = {
                    "path": str(file_path.relative_to(source_dir)),
                    "size": size,
                    "extension": ext
                }
                
                manifest["files"].append(file_info)
                manifest["statistics"]["total_files"] += 1
                manifest["statistics"]["total_size"] += size
                manifest["statistics"]["by_extension"][ext] = \
                    manifest["statistics"]["by_extension"].get(ext, 0) + 1

        # Save manifest
        manifest_path = source_dir / "packing_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        total_size_mb = manifest["statistics"]["total_size"] / (1024 * 1024)
        output = f"Generated packing manifest at {manifest_path}\n"
        output += f"Total files: {manifest['statistics']['total_files']}\n"
        output += f"Total size: {total_size_mb:.2f} MB\n"
        output += "By extension:\n"
        for ext, count in sorted(manifest["statistics"]["by_extension"].items()):
            output += f"  - {ext}: {count}\n"

        return ToolResult.ok(output, {
            "manifest_path": str(manifest_path.relative_to(self.project_root)),
            "manifest": manifest
        })

    def _validate_archive(self, archive_path: Path) -> ToolResult:
        """Validate packed archive"""
        if not archive_path.exists():
            return ToolResult.fail(f"Archive not found: {archive_path}")

        if not zipfile.is_zipfile(archive_path):
            return ToolResult.fail(f"Invalid zip file: {archive_path}")

        issues = []
        
        # Test archive integrity
        with zipfile.ZipFile(archive_path, 'r') as zf:
            # Test all files
            bad_files = zf.testzip()
            if bad_files:
                issues.append(f"Corrupted file in archive: {bad_files}")
            
            # Get file list
            file_list = zf.namelist()
            file_count = len(file_list)
            
            # Check for empty archive
            if file_count == 0:
                issues.append("Archive is empty")

        # Check manifest if exists
        manifest_path = archive_path.with_suffix('.json')
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest_file_count = manifest.get("file_count", 0)
                
                if manifest_file_count != file_count:
                    issues.append(
                        f"File count mismatch: manifest says {manifest_file_count}, "
                        f"archive has {file_count}"
                    )
            except Exception as e:
                issues.append(f"Failed to read manifest: {str(e)}")

        if issues:
            output = f"Archive validation found {len(issues)} issue(s):\n"
            for issue in issues:
                output += f"  - {issue}\n"
            return ToolResult.partial(output, f"{len(issues)} validation issues found")
        
        archive_size = archive_path.stat().st_size
        output = f"Archive validation passed!\n"
        output += f"Archive: {archive_path.name}\n"
        output += f"Files: {file_count}\n"
        output += f"Size: {archive_size / 1024:.1f} KB"

        return ToolResult.ok(output, {
            "valid": True,
            "file_count": file_count,
            "archive_size": archive_size
        })

    def _calculate_md5(self, file_path: Path) -> str:
        """Calculate MD5 checksum of file"""
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()

    def _resolve_path(self, raw: str) -> Path:
        """Resolve path relative to project root"""
        path = Path(raw)
        return path if path.is_absolute() else (self.project_root / path)

    def get_execution_message(self, **kwargs) -> str:
        action = kwargs.get("action", "unknown")
        return f"Packing game assets: {action}"
