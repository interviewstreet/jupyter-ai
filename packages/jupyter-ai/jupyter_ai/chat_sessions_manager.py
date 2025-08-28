"""
Simple ChatSessionManager service for managing chat sessions
Public Functions
- clear_all() - Delete all chat files and clear chats directory
- load_chat_session(session_id: str) -> Optional[Dict[str, Any]] - Load chat with given ID
- list_chat_sessions() -> List[Dict[str, Any]] - Return list of all chat sessions from chat-sessions.json
- generate_title(chat_history: List, llm=None) -> str - Generate a simple local title for the chat without LLM.
- save(chat_history: List, chat_id: str = None, llm=None) -> str - Save chat history to file
- reconstruct_chat_session(session_id: str) -> Optional[Dict[str, Any]] - Reconstruct chat session with properly formatted messages and LLM memory pairs.
"""
import json
import re
import os, shutil
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

CHAT_SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "chat_sessions")
CHAT_SESSIONS_INDEX_PATH = os.path.join(CHAT_SESSIONS_DIR, "chat-sessions.json")

class ChatSessionManager:
    """Simple service to manage chat history"""
    
    def __init__(self, root_dir: str = None, log=None):
        self.log = log
        self._current_chat_id = None
        # Ensure chat_sessions directory exists
        os.makedirs(CHAT_SESSIONS_DIR, exist_ok=True)

        # Clear all chats on startup
        self.clear_all()

    @property
    def current_chat_id(self) -> str:
        """Get the current chat ID"""
        return self._current_chat_id

    @current_chat_id.setter
    def current_chat_id(self, chat_id: str) -> None:
        """Set the current chat ID"""
        self._current_chat_id = chat_id
    
    def clear_all(self):
        """Delete all chat files and clear chats directory"""
        try:
            shutil.rmtree(CHAT_SESSIONS_DIR, ignore_errors=True)
            os.makedirs(CHAT_SESSIONS_DIR, exist_ok=True)                
            self.current_chat_id = None
            self.log.info("[jupyter-ai] All chats cleared successfully")
        except Exception as e:
            self.log.error(f"[jupyter-ai]: Failed to clear all chats: {e}")
            self.log.exception(e)
    
    def load_chat_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load chat with given ID"""
        try:
            session_file = os.path.join(CHAT_SESSIONS_DIR, f"chat_{session_id}.json")
            if not os.path.exists(session_file):
                return None
            
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            return session_data
        except Exception as e:
            self.log.error(f"[jupyter-ai] Error loading chat {session_id}: {e}")
            self.log.exception(e)
            return None

    def list_chat_sessions(self) -> List[Dict[str, Any]]:
        """Return list of all chat sessions from chat-sessions.json"""
        try:
            index_data = self._load_chat_sessions_index()
            sessions = index_data.get("sessions", [])
            # Sort by created_at, newest first
            sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return sessions
        except Exception as e:
            self.log.error(f"[jupyter-ai] Error listing chat sessions: {e}")
            self.log.exception(e)
            return []

    def _load_chat_sessions_index(self) -> Dict[str, Any]:
        """Load the chat-sessions.json index file"""
        if os.path.exists(CHAT_SESSIONS_INDEX_PATH):
            try:
                with open(CHAT_SESSIONS_INDEX_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.log.warning(f"[jupyter-ai] Could not load chats index: {e}")
                self.log.exception(e)
                return {"sessions": []}
        
        return {"sessions": []}
    
    def _save_chat_sessions_index(self, index_data: Dict[str, Any]):
        """Save the chat-sessions.json index file"""
        try:
            with open(CHAT_SESSIONS_INDEX_PATH, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log.error(f"[jupyter-ai] Could not save chat sessions index: {e}")
            self.log.exception(e)
    
    def generate_title(self, chat_history: List) -> str:
        """Generate a simple local title for the chat without LLM."""
        if not chat_history or len(chat_history) == 0:
            return "Untitled Chat"

        try:
            # Extract the first user message
            first_message = ""
            for msg in chat_history:
                # Handle pydantic model objects
                if hasattr(msg, 'type') and msg.type == "human":
                    first_message = getattr(msg, 'body', getattr(msg, 'prompt', "")).strip()
                    break
                # Handle dictionary format
                elif isinstance(msg, dict):
                    if msg.get("type") == "human":
                        first_message = msg.get("body", msg.get("prompt", "")).strip()
                        break
                    elif msg.get("role") == "user":
                        first_message = msg.get("content", "").strip()
                        break
                # Handle string format
                elif isinstance(msg, str):
                    first_message = msg.strip()
                    break

            # Clean up the message for title use
            if first_message:
                # Remove extra spaces and special characters
                title = re.sub(r'[^a-zA-Z0-9\s]', '', first_message)
                title = title.strip()
                title = " ".join(title.split()[:5])  # limit to first 5 words
                return title if title else "Chat Session"

            return "Chat Session"

        except Exception as e:
            self.log.warning(f"[jupyter-ai] Could not generate local title: {e}")
            self.log.exception(e)
            return "Chat Session"
    
    def reconstruct_chat_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load and reconstruct a chat session with properly formatted messages and LLM memory pairs.
        Returns dict with 'messages' and 'llm_memory_pairs' keys, or None if session not found.
        """
        try:
            session_data = self.load_chat_session(session_id)
            if not session_data:
                return None
            
            loaded_history = session_data.get("chat_history", [])
            reconstructed_messages = []
            llm_memory_pairs = []
            human_messages = {}
            
            # Import here to avoid circular imports
            from .models import HumanChatMessage, AgentChatMessage, AgentStreamMessage
            
            # First pass: reconstruct messages and collect human messages
            for msg_data in loaded_history:
                if not isinstance(msg_data, dict):
                    continue
                    
                try:
                    msg_type = msg_data.get("type")
                    if msg_type == "human":
                        message = HumanChatMessage(**msg_data)
                        reconstructed_messages.append(message)
                        human_messages[message.id] = message.prompt
                    elif msg_type == "agent":
                        message = AgentChatMessage(**msg_data)
                        reconstructed_messages.append(message)
                    elif msg_type == "agent-stream":
                        message = AgentStreamMessage(**msg_data)
                        reconstructed_messages.append(message)
                    else:
                        self.log.warning(f"[jupyter-ai] Unknown message type: {msg_type}")
                except Exception as e:
                    self.log.warning(f"[jupyter-ai] Could not reconstruct message: {e}")
                    continue
            
            # Second pass: extract LLM memory pairs from reconstructed messages
            for message in reconstructed_messages:
                if hasattr(message, 'type') and message.type in ["agent", "agent-stream"]:
                    if hasattr(message, 'reply_to') and message.reply_to in human_messages:
                        llm_memory_pairs.append({
                            "human": human_messages[message.reply_to],
                            "ai": message.body,
                            "human_id": message.reply_to
                        })
            
            return {
                "messages": reconstructed_messages,
                "llm_memory_pairs": llm_memory_pairs,
                "metadata": session_data.get("metadata", {})
            }
            
        except Exception as e:
            self.log.error(f"[jupyter-ai] Error reconstructing chat session {session_id}: {e}")
            self.log.exception(e)
            return None
        
    def save(self, chat_history: List, chat_id: str = None) -> str:
        """Save chat history to file"""
        try:
            # Determine if this is a new chat
            is_new_chat = False
            if not chat_id:
                chat_id = str(uuid.uuid4())[:8]
                is_new_chat = True
            
            # Paths & timestamps
            now = datetime.now(timezone.utc).isoformat()
            chat_file = os.path.join(CHAT_SESSIONS_DIR, f"chat_{chat_id}.json")


            # If chat_id was provided but file doesn't exist, treat as new
            if not is_new_chat and not os.path.exists(chat_file):
                is_new_chat = True

            if is_new_chat:
                # Generate title for new chat
                title = self.generate_title(chat_history)
                metadata = {
                    "title": title,
                    "created_at": now,
                    "id": chat_id,
                    "modified_at": now,
                    "message_count": len(chat_history)
                }
            else:
                # Load existing metadata and update                
                with open(chat_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                existing_meta = existing_data.get("metadata", {})
                metadata = {
                    "title": existing_meta.get("title", self.generate_title(chat_history)),
                    "created_at": existing_meta.get("created_at", now),
                    "id": chat_id,
                    "modified_at": now,
                    "message_count": len(chat_history)
                }
            
            # Save chat data
            chat_data = {
                "metadata": metadata,
                "chat_history": [msg.model_dump() if hasattr(msg, 'model_dump') else msg for msg in chat_history],
            }
            
            # Write chat file
            chat_file = os.path.join(CHAT_SESSIONS_DIR, f"chat_{chat_id}.json")
            with open(chat_file, 'w', encoding='utf-8') as f:
                json.dump(chat_data, f, indent=2, ensure_ascii=False)
            
            # Update index
            index_data = self._load_chat_sessions_index() or {}
            sessions = index_data.get("sessions", [])

            # Remove any existing entry with same id, then append updated one
            sessions = [s for s in sessions if s.get("id") != chat_id]
            sessions.append(
                {
                    "id": chat_id,
                    "title": metadata["title"],
                    "created_at": metadata["created_at"],
                    "modified_at": metadata["modified_at"],
                }
            )
            index_data["sessions"] = sessions
            self._save_chat_sessions_index(index_data)
            self.log.info(f"[jupyter-ai] Chat saved successfully: {chat_id}")
            return chat_id
            
        except Exception as e:
            self.log.error(f"[jupyter-ai] Error saving chat: {e}")
            self.log.exception(e)
            raise
