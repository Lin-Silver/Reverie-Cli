from typing import List, Dict, Any, Optional
import json
from pathlib import Path
from datetime import datetime
import requests

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
                response = requests.post(base_url, headers=headers, json=payload)
                response.raise_for_status()
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
