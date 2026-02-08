from typing import List, Dict, Any, Optional
import json
from pathlib import Path
from datetime import datetime
import requests
import logging

logger = logging.getLogger(__name__)

def validate_payload_for_compression(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and sanitize payload for context compression API calls.
    
    Args:
        payload: The payload dictionary to validate
        
    Returns:
        A sanitized payload dictionary
        
    Raises:
        ValueError: If the payload cannot be sanitized
    """
    try:
        # Test JSON serialization
        json_str = json.dumps(payload, ensure_ascii=False)
        # Verify it can be parsed back
        json.loads(json_str)
        return payload
    except (TypeError, ValueError) as e:
        logger.error(f"Payload validation failed in compressor: {e}")
        # Try to fix by truncating overly long messages
        if "messages" in payload:
            messages = payload["messages"]
            sanitized_messages = []
            for msg in messages:
                if isinstance(msg, dict) and "content" in msg:
                    content = msg["content"]
                    if isinstance(content, str) and len(content) > 100000:
                        # Truncate very long messages
                        logger.warning(f"Truncating message from {len(content)} to 100000 chars")
                        content = content[:100000] + "... [truncated]"
                    sanitized_messages.append({
                        "role": msg.get("role", "user"),
                        "content": content
                    })
                else:
                    sanitized_messages.append(msg)
            payload["messages"] = sanitized_messages
        
        # Try again
        try:
            json_str = json.dumps(payload, ensure_ascii=False)
            json.loads(json_str)
            return payload
        except (TypeError, ValueError) as e2:
            logger.error(f"Failed to sanitize payload: {e2}")
            raise ValueError(f"Cannot sanitize payload: {e2}")


def make_compression_request_with_retry(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    max_retries: int = 2
) -> requests.Response:
    """
    Make a compression API request with retry logic.
    
    Args:
        url: The API endpoint URL
        headers: Request headers
        payload: Request payload
        max_retries: Maximum number of retry attempts
        
    Returns:
        The response object
        
    Raises:
        requests.RequestException: If all retries fail
    """
    # Validate payload
    payload = validate_payload_for_compression(payload)
    
    last_error = None
    for attempt in range(max_retries):
        try:
            logger.debug(f"Compression request attempt {attempt + 1}/{max_retries}")
            
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=120  # Longer timeout for compression
            )
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"Compression request failed on attempt {attempt + 1}: {e}")
            
            if attempt < max_retries - 1:
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
    
    raise last_error or requests.RequestException("All compression retry attempts failed")

class ContextCompressor:
    """
    Handles prompt compression and memory checkpointing.
    Used when the active token context exceeds limits.
    
    Inspired by GPT-5.1 codex max, this implementation focuses on technical
    retainment and recursive summary retrieval.
    """
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir / 'checkpoints'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.last_checkpoint = None

    def save_checkpoint(self, messages: List[Dict], note: str = "", session_id: str = "default") -> str:
        """Save current messages to a checkpoint file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'session_id': session_id,
            'note': note,
            'message_count': len(messages),
            'messages': messages
        }
        filename = f"checkpoint_{session_id}_{timestamp}.json"
        path = self.cache_dir / filename
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
            self.last_checkpoint = str(path)
            return str(path)
        except Exception as e:
            return ""

    def compress(self, messages: List[Dict], client: Any, model: str, session_id: str = "default", 
              provider: str = "openai-sdk", base_url: str = "", api_key: str = "") -> List[Dict]:
        """
        Compresses the conversation history using the LLM.
        Retains system prompt and last few messages.
        Summarizes the rest using recursive technical retainment.
        
        Args:
            messages: List of messages to compress
            client: Client object (for openai-sdk and anthropic providers)
            model: Model name
            session_id: Session ID for checkpointing
            provider: Provider type (openai-sdk, request, anthropic)
            base_url: Base URL for request provider
            api_key: API key for request provider
        """
        if not messages:
            return []
            
        # Identify system prompt
        system_msgs = [m for m in messages if m.get('role') == 'system']
        other_msgs = [m for m in messages if m.get('role') != 'system']
        
        # If conversation is short, don't separate too aggressively
        if len(other_msgs) < 8:
            return messages
            
        # Keep last 4 messages to maintain immediate context
        recent_msgs = other_msgs[-4:]
        history_to_compress = other_msgs[:-4]
        
        if not history_to_compress:
            return messages

        # Save checkpoint before compression (Safety)
        self.save_checkpoint(messages, "Pre-compression auto-save", session_id)
        
        # Prepare summarization prompt
        conversation_text = ""
        for msg in history_to_compress:
            role = msg.get('role', 'unknown')
            content = msg.get('content')
            if content:
                conversation_text += f"{role.upper()}: {content}\n\n"
            
        prompt = [
            {
                "role": "system", 
                "content": (
                    "You are a specialized Context Engine Optimizer. Your task is to compress scientific and technical memory. "
                    "Analyze the provided conversation history and create a dense, structured technical summary. "
                    "Focus on: 1. Core architectural decisions, 2. Key code snippets or logic implemented, 3. Dependencies identified, "
                    "4. Current state of the project, 5. Pending tasks or identified bugs. "
                    "Discard all conversational filler. This summary will be used as the primary 'long-term memory' for the agent."
                )
            },
            {"role": "user", "content": f"Compress the following conversation into a high-fidelity technical summary for context retrieval:\n\n{conversation_text}"}
        ]
        
        try:
            # Use the provided client to summarize based on provider
            if provider == "openai-sdk":
                response = client.chat.completions.create(
                    model=model,
                    messages=prompt,
                    stream=False
                )
                summary = response.choices[0].message.content
            elif provider == "request":
                # Use requests library for request provider
                payload = {
                    "model": model,
                    "messages": prompt,
                    "stream": False
                }
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                response = make_compression_request_with_retry(base_url, headers, payload)
                response_data = response.json()
                summary = response_data["choices"][0]["message"]["content"]
            elif provider == "anthropic":
                # Use Anthropic SDK
                # Convert messages to Anthropic format
                anthropic_messages = []
                system_message = None
                
                for msg in prompt:
                    if msg["role"] == "system":
                        system_message = msg["content"]
                    else:
                        anthropic_messages.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                
                kwargs = {
                    "model": model,
                    "messages": anthropic_messages,
                    "max_tokens": 4096,
                }
                
                if system_message:
                    kwargs["system"] = system_message
                
                response = client.messages.create(**kwargs)
                summary = response.content[0].text
            else:
                raise ValueError(f"Unknown provider: {provider}")
            
            # Construct new history
            summary_message = {
                "role": "system", 
                "content": f"[MEMORY CONSOLIDATION - Context Engine Cache]\n{summary}\n[END MEMORY]"
            }
            
            new_history = system_msgs + [summary_message] + recent_msgs
            
            # Save post-compression checkpoint
            self.save_checkpoint(new_history, "Post-compression optimized summary", session_id)
            
            return new_history
            
        except Exception as e:
            # If summarization fails, safely return original messages
            return messages

    def list_checkpoints(self, session_id: Optional[str] = None) -> List[Dict]:
        """List all available checkpoints for a session."""
        checkpoints = []
        for p in self.cache_dir.glob("checkpoint_*.json"):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    # Just read metadata, not the whole message history
                    data = json.load(f)
                    if session_id and data.get('session_id') != session_id:
                        continue
                    checkpoints.append({
                        'path': str(p),
                        'filename': p.name,
                        'timestamp': data.get('timestamp'),
                        'note': data.get('note'),
                        'message_count': data.get('message_count')
                    })
            except:
                continue
        
        return sorted(checkpoints, key=lambda x: x['timestamp'], reverse=True)


def summarize_game_context(
    gdd_path: Optional[str] = None,
    asset_manifest_path: Optional[str] = None,
    task_list_path: Optional[str] = None,
    keep_last_messages: int = 5
) -> Dict[str, Any]:
    """
    Compress game development context for efficient memory usage.
    
    This function creates a compressed summary of game development artifacts:
    - GDD (Game Design Document): Keeps core sections
    - Asset Manifest: Summarizes by type and count
    - Task List: Summarizes by phase and status
    - Recent Messages: Keeps the last N messages
    
    Args:
        gdd_path: Path to the GDD file (Markdown)
        asset_manifest_path: Path to the asset manifest (JSON)
        task_list_path: Path to the task list (JSON)
        keep_last_messages: Number of recent messages to keep
    
    Returns:
        Dictionary containing compressed context
    """
    compressed = {
        'gdd_summary': None,
        'asset_summary': None,
        'task_summary': None,
        'compression_timestamp': datetime.now().isoformat()
    }
    
    # Compress GDD
    if gdd_path and Path(gdd_path).exists():
        try:
            with open(gdd_path, 'r', encoding='utf-8') as f:
                gdd_content = f.read()
            
            # Extract core sections (概述, 核心机制, 角色系统, 剧情系统, 任务系统)
            core_sections = []
            current_section = None
            current_content = []
            
            for line in gdd_content.split('\n'):
                # Check for section headers
                if line.startswith('## '):
                    # Save previous section if it's a core section
                    if current_section and any(keyword in current_section for keyword in 
                                              ['概述', '核心机制', '角色', '剧情', '任务', 'Overview', 'Core', 'Character', 'Story', 'Quest']):
                        core_sections.append({
                            'title': current_section,
                            'content': '\n'.join(current_content[:20])  # Keep first 20 lines
                        })
                    
                    current_section = line[3:].strip()
                    current_content = []
                elif current_section:
                    current_content.append(line)
            
            # Save last section if core
            if current_section and any(keyword in current_section for keyword in 
                                      ['概述', '核心机制', '角色', '剧情', '任务', 'Overview', 'Core', 'Character', 'Story', 'Quest']):
                core_sections.append({
                    'title': current_section,
                    'content': '\n'.join(current_content[:20])
                })
            
            compressed['gdd_summary'] = {
                'core_sections': core_sections,
                'total_sections': gdd_content.count('## ')
            }
        
        except Exception as e:
            logger.error(f"Failed to compress GDD: {e}")
            compressed['gdd_summary'] = {'error': str(e)}
    
    # Compress Asset Manifest
    if asset_manifest_path and Path(asset_manifest_path).exists():
        try:
            with open(asset_manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
            
            # Summarize by type
            asset_summary = {}
            
            if 'assets' in manifest:
                for asset_type, assets in manifest['assets'].items():
                    if isinstance(assets, list):
                        total_size = sum(a.get('size', 0) for a in assets if isinstance(a, dict))
                        asset_summary[asset_type] = {
                            'count': len(assets),
                            'total_size_mb': total_size / (1024 * 1024) if total_size > 0 else 0,
                            'examples': [a.get('path', '') for a in assets[:3] if isinstance(a, dict)]
                        }
            
            # Include statistics if available
            if 'statistics' in manifest:
                asset_summary['statistics'] = manifest['statistics']
            
            compressed['asset_summary'] = asset_summary
        
        except Exception as e:
            logger.error(f"Failed to compress asset manifest: {e}")
            compressed['asset_summary'] = {'error': str(e)}
    
    # Compress Task List
    if task_list_path and Path(task_list_path).exists():
        try:
            with open(task_list_path, 'r', encoding='utf-8') as f:
                tasks = json.load(f)
            
            # Summarize by phase and status
            task_summary = {
                'by_phase': {},
                'by_status': {},
                'total_tasks': 0
            }
            
            if isinstance(tasks, list):
                task_summary['total_tasks'] = len(tasks)
                
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    
                    # Count by phase
                    phase = task.get('phase', 'unknown')
                    if phase not in task_summary['by_phase']:
                        task_summary['by_phase'][phase] = 0
                    task_summary['by_phase'][phase] += 1
                    
                    # Count by status
                    status = task.get('state', task.get('status', 'unknown'))
                    if status not in task_summary['by_status']:
                        task_summary['by_status'][status] = 0
                    task_summary['by_status'][status] += 1
                
                # Include high-priority tasks
                high_priority = [
                    {
                        'name': t.get('name', ''),
                        'phase': t.get('phase', ''),
                        'status': t.get('state', t.get('status', ''))
                    }
                    for t in tasks
                    if isinstance(t, dict) and t.get('priority') in ['high', 'critical']
                ]
                
                if high_priority:
                    task_summary['high_priority_tasks'] = high_priority[:5]  # Keep top 5
            
            elif isinstance(tasks, dict) and 'tasks' in tasks:
                # Handle nested structure
                task_list = tasks['tasks']
                task_summary['total_tasks'] = len(task_list)
                
                for task in task_list:
                    if not isinstance(task, dict):
                        continue
                    
                    phase = task.get('phase', 'unknown')
                    if phase not in task_summary['by_phase']:
                        task_summary['by_phase'][phase] = 0
                    task_summary['by_phase'][phase] += 1
                    
                    status = task.get('state', task.get('status', 'unknown'))
                    if status not in task_summary['by_status']:
                        task_summary['by_status'][status] = 0
                    task_summary['by_status'][status] += 1
            
            compressed['task_summary'] = task_summary
        
        except Exception as e:
            logger.error(f"Failed to compress task list: {e}")
            compressed['task_summary'] = {'error': str(e)}
    
    return compressed


def format_game_context_summary(summary: Dict[str, Any]) -> str:
    """
    Format a game context summary into a readable string.
    
    Args:
        summary: Dictionary from summarize_game_context
    
    Returns:
        Formatted string representation
    """
    lines = ["=== Game Development Context Summary ===\n"]
    
    # GDD Summary
    if summary.get('gdd_summary'):
        lines.append("📄 Game Design Document:")
        gdd = summary['gdd_summary']
        
        if 'error' in gdd:
            lines.append(f"  Error: {gdd['error']}")
        else:
            lines.append(f"  Total Sections: {gdd.get('total_sections', 0)}")
            lines.append("  Core Sections:")
            for section in gdd.get('core_sections', []):
                lines.append(f"    - {section['title']}")
                # Add first few lines of content
                content_preview = section['content'].split('\n')[:3]
                for line in content_preview:
                    if line.strip():
                        lines.append(f"      {line.strip()[:80]}")
        lines.append("")
    
    # Asset Summary
    if summary.get('asset_summary'):
        lines.append("🎨 Game Assets:")
        assets = summary['asset_summary']
        
        if 'error' in assets:
            lines.append(f"  Error: {assets['error']}")
        else:
            total_count = 0
            total_size = 0.0
            
            for asset_type, info in assets.items():
                if asset_type == 'statistics':
                    continue
                if isinstance(info, dict):
                    count = info.get('count', 0)
                    size = info.get('total_size_mb', 0)
                    total_count += count
                    total_size += size
                    lines.append(f"  {asset_type}: {count} files ({size:.2f} MB)")
                    
                    examples = info.get('examples', [])
                    if examples:
                        lines.append(f"    Examples: {', '.join(examples[:2])}")
            
            lines.append(f"  Total: {total_count} assets ({total_size:.2f} MB)")
        lines.append("")
    
    # Task Summary
    if summary.get('task_summary'):
        lines.append("📋 Tasks:")
        tasks = summary['task_summary']
        
        if 'error' in tasks:
            lines.append(f"  Error: {tasks['error']}")
        else:
            lines.append(f"  Total Tasks: {tasks.get('total_tasks', 0)}")
            
            if tasks.get('by_phase'):
                lines.append("  By Phase:")
                for phase, count in tasks['by_phase'].items():
                    lines.append(f"    {phase}: {count}")
            
            if tasks.get('by_status'):
                lines.append("  By Status:")
                for status, count in tasks['by_status'].items():
                    lines.append(f"    {status}: {count}")
            
            if tasks.get('high_priority_tasks'):
                lines.append("  High Priority:")
                for task in tasks['high_priority_tasks']:
                    lines.append(f"    - {task['name']} ({task['phase']}, {task['status']})")
        lines.append("")
    
    lines.append(f"Compressed at: {summary.get('compression_timestamp', 'unknown')}")
    
    return '\n'.join(lines)
