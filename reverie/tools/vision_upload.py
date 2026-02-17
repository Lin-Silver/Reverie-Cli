"""
Vision Upload Tool - Upload and process visual files for AI models

Supports image files for models with vision capabilities.
"""

from pathlib import Path
from typing import Dict, Any, Optional
import base64
import mimetypes

from .base import BaseTool, ToolResult


class VisionUploadTool(BaseTool):
    """Tool for uploading and encoding visual files for AI models"""
    
    name = "vision_upload"
    description = "Upload and encode visual files (images) for AI model processing"
    
    def __init__(self, context: Optional[Dict] = None):
        super().__init__(context)
        self.project_root = context.get('project_root') if context else Path.cwd()
        self.supported_formats = {
            '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.tif'
        }
    
    def get_spec(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "vision_upload",
                "description": "Upload and encode visual files (images) for AI model processing. Use this when the user wants the AI to analyze, describe, or process image files. Supports PNG, JPG, GIF, BMP, WEBP, TIFF formats.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the image file (relative to project root or absolute path)"
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description or context about what to analyze in the image"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        }
    
    def execute(self, file_path: str, description: Optional[str] = None) -> ToolResult:
        """
        Upload and encode an image file for AI processing.
        
        Args:
            file_path: Path to the image file
            description: Optional description of what to analyze
            
        Returns:
            ToolResult with base64-encoded image data and metadata
        """
        try:
            # Resolve path
            path = Path(file_path)
            if not path.is_absolute():
                path = self.project_root / path
            
            # Check if file exists
            if not path.exists():
                return ToolResult(
                    success=False,
                    error=f"File not found: {file_path}"
                )
            
            # Check if it's a file
            if not path.is_file():
                return ToolResult(
                    success=False,
                    error=f"Path is not a file: {file_path}"
                )
            
            # Check file extension
            if path.suffix.lower() not in self.supported_formats:
                return ToolResult(
                    success=False,
                    error=f"Unsupported image format: {path.suffix}. Supported formats: {', '.join(self.supported_formats)}"
                )
            
            # Read and encode file
            with open(path, 'rb') as f:
                image_data = f.read()
            
            # Encode to base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            # Detect MIME type
            mime_type, _ = mimetypes.guess_type(str(path))
            if not mime_type:
                # Fallback based on extension
                ext_to_mime = {
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.bmp': 'image/bmp',
                    '.webp': 'image/webp',
                    '.tiff': 'image/tiff',
                    '.tif': 'image/tiff'
                }
                mime_type = ext_to_mime.get(path.suffix.lower(), 'image/jpeg')
            
            # Get file size
            file_size = len(image_data)
            file_size_kb = file_size / 1024
            file_size_mb = file_size_kb / 1024
            
            # Format size string
            if file_size_mb >= 1:
                size_str = f"{file_size_mb:.2f} MB"
            else:
                size_str = f"{file_size_kb:.2f} KB"
            
            # Build output message
            output_lines = [
                f"Image uploaded successfully: {path.name}",
                f"Format: {mime_type}",
                f"Size: {size_str}",
                f"Path: {path}"
            ]
            
            if description:
                output_lines.append(f"Context: {description}")
            
            output_lines.append("")
            output_lines.append("The image has been encoded and is ready for AI analysis.")
            output_lines.append("You can now ask questions about the image content.")
            
            # Store image data in metadata for the agent to use
            metadata = {
                "base64_image": base64_image,
                "mime_type": mime_type,
                "file_path": str(path),
                "file_name": path.name,
                "file_size": file_size,
                "description": description
            }
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data=metadata
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to upload image: {str(e)}"
            )
    
    def get_execution_message(self, file_path: str, description: Optional[str] = None) -> str:
        """Get message to display when tool is being executed"""
        if description:
            return f"Uploading image: {file_path} ({description})"
        return f"Uploading image: {file_path}"
