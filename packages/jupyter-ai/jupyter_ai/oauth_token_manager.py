import asyncio
import base64
import json
import time
import logging
from typing import Optional
import aiohttp
from pathlib import Path

from .models import UpdateConfigRequest, GlobalConfig

# HR Configuration for different environments
HR_CONFIG = {
    "prod": {
        "portkeyConfig": "pc-defaul-01e117",
        "krakendHost": "appgateway.hackerrank.com"
    },
    "private": {
        "portkeyConfig": "pc-defaul-f995c3", 
        "krakendHost": "pgr4g8vmr5.execute-api.us-east-2.amazonaws.com/dev/ai-auth"
    }
}

async def isProd() -> bool:
    """Check if running in production environment"""
    # For now, always return False (development/private environment)
    # TODO: Implement proper environment detection logic
    return True

async def getKrakendHost() -> str:
    """Get Krakend host based on environment"""
    return HR_CONFIG["prod"]["krakendHost"] if await isProd() else HR_CONFIG["private"]["krakendHost"]

async def getPortkeyConfig() -> str:
    """Get Portkey config based on environment"""
    return HR_CONFIG["prod"]["portkeyConfig"] if await isProd() else HR_CONFIG["private"]["portkeyConfig"]

class OAuthTokenManager:
    """
    OAuth token manager for Jupyter AI.
    Automatically handles HMAP token exchange, session refresh, and config updates.
    """
    
    # ===============================================
    # INITIALIZATION
    # ===============================================
    def __init__(self, config_manager, log: logging.Logger):
        self.config_manager = config_manager
        self.log = log
        
        # Token state
        self.auth_token: Optional[str] = None  # HMAP token from file
        self.access_token: Optional[str] = None  # JWT access token
        self.refresh_token: Optional[str] = None  # JWT refresh token
        
        # Refresh scheduling
        self.refresh_timer: Optional[asyncio.Task] = None
        self.create_session_promise: Optional[asyncio.Task] = None
        
        # Configuration - will be set dynamically in init()
        self.defaultHeader = {}
        self.auth_token_path = "/opt/hackerrank/tokens/hmap.token"
        self.host = ""
        self.hardcoded_auth_token = "HARDCODED_TOKEN_FOR_DEV"
        self.provide_base_url = "https://api.portkey.ai/v1"

    async def init(self):
        """Initialize OAuth manager when extension loads"""
        # Set dynamic configuration based on environment
        self.host = await getKrakendHost()
        portkey_config = await getPortkeyConfig()
        self.defaultHeader = {
            "x-portkey-config": portkey_config
        }


        # Pre-configure all supported models with Portkey settings
        try:
            self.configure_all_supported_models()

            config = self.config_manager._read_config()
            api_keys = config.api_keys or {}
            
            # Access token is stored as OPENAI_API_KEY
            self.access_token = api_keys.get("OPENAI_API_KEY")
            self.refresh_token = api_keys.get("REFRESH_TOKEN")

            if not self.access_token:
                self.log.info("[jupyter-ai] No access token found, creating new session...")
                await self.create_session()
            else:
                self.log.info("[jupyter-ai] Access token found, scheduling proactive refresh...")
                self.schedule_proactive_refresh()
        except Exception as e:
            self.log.error(f"[jupyter-ai]: Failed to initialize OAuth manager: {e}")
            self.log.exception(e)
            raise

    def configure_all_supported_models(self):
        """Pre-configure all supported models with Portkey settings"""
        try:
            # Path to supported models config
            config_dir = Path(__file__).parent / "config"
            supported_models_config_path = config_dir / "supported-models.json"
            
            if not supported_models_config_path.exists():
                self.log.error(f"[jupyter-ai] Supported models file not found: {supported_models_config_path}")
                return None
                
            with open(supported_models_config_path, 'r') as f:
                supported_models_config = json.load(f)
                
            if not supported_models_config:
                self.log.error("[jupyter-ai] Cannot configure models - failed to load supported models config")
                return
            
            provider = supported_models_config.get("provider", "openai-chat-custom")
            supported_models = supported_models_config.get("models", [])

            # Load current config
            config = self.config_manager._read_config()
            config_dict = config.model_dump()
            
            # Ensure fields exists
            if "fields" not in config_dict:
                config_dict["fields"] = {}
                
            models_configured = 0
            
            # Configure each supported model
            for model_info in supported_models:
                model_id = model_info.get("id")
                if not model_id:
                    continue
                    
                # Create full model identifier with provider prefix
                full_model_id = f"{provider}:{model_id}"
                
                # Pre-configure the model with all necessary settings
                config_dict["fields"][full_model_id] = {
                    "openai_api_base": self.provide_base_url,
                    "default_headers": self.defaultHeader,
                }
                
                models_configured += 1
                self.log.info(f"[jupyter-ai] Pre-configured model: {full_model_id}")
            
            existing_updated = 0
            # For completions_fields and embeddings_fields: read existing keys and update them
            update_field_types = ["completions_fields", "embeddings_fields"]
            for field_type in update_field_types:
                if field_type not in config_dict:
                    config_dict[field_type] = {}
                
                # Update existing keys in this field type
                for existing_key, existing_config in config_dict[field_type].items():
                    if isinstance(existing_config, dict):
                        # Update existing model with Portkey settings
                        existing_config.update({
                            "openai_api_base": self.provide_base_url,
                            "default_headers": self.defaultHeader,
                        })
                        existing_updated += 1
                        self.log.info(f"[jupyter-ai] Updated existing key: {existing_key} in {field_type}")
            
            # Save the updated config
            self.config_manager._write_config(GlobalConfig(**config_dict))
            self.log.info(f"[jupyter-ai] Configuration complete: {models_configured} models configured in fields, {existing_updated} existing keys updated in completions/embeddings")
            
        except Exception as e:
            self.log.error(f"❌ Failed to configure supported models: {e}")
            self.log.exception(e)
  
    # ===============================================
    # SESSION CREATION
    # ===============================================
    async def create_session(self):
        """Create new authentication session using HMAP token."""
        self.log.info("[jupyter-ai] Starting session creation process...")

        if self.create_session_promise:
            self.log.info("[jupyter-ai] Session creation already in progress, waiting...")
            await self.create_session_promise
            return

        self.create_session_promise = asyncio.create_task(self.create_session_impl())
        
        try:
            await self.create_session_promise
        except Exception as e:
            self.log.error(f"[jupyter-ai]: Session creation failed: {e}")
            raise
        finally:
            self.create_session_promise = None

    async def create_session_impl(self):        
        if not self.auth_token:
            await self.load_auth_token_from_file()

        if not self.auth_token:
            self.log.error("[jupyter-ai] Auth token not loaded")
            raise Exception("Auth token not loaded")
        
        if not self.host:
            self.log.error("[jupyter-ai] Host not configured")
            raise Exception("Host not configured - please set host URL")
        
        url = f"https://{self.host}/candidate/authn/v1/candidate/session"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    headers={
                        'Cookie': f'cyno_session={self.auth_token}',
                    }
                ) as resp:                    
                    if not (200 <= resp.status < 300):
                        self.log.error(f"[jupyter-ai] HTTP error - Status: {resp.status}, Reason: {resp.reason}")
                        raise Exception(f"Failed to create session: {resp.status} {resp.reason}")
                    
                    access_token = resp.cookies.get('jwt_access_token')
                    refresh_token = resp.cookies.get('jwt_refresh_token')
                    
                    # Extract values from cookie morsels
                    access_token_value = access_token.value if access_token else None
                    refresh_token_value = refresh_token.value if refresh_token else None
                    
                    if access_token_value or refresh_token_value:
                        await self.handle_and_persist_session_tokens(
                            access_token_value,
                            refresh_token_value
                        )
                        self.log.info("[jupyter-ai] Session created successfully")
                    else:
                        self.log.error("[jupyter-ai] No tokens found in cookies")
                        raise Exception("No tokens received in response")
                        
            except aiohttp.ClientError as e:
                self.log.error(f"[jupyter-ai] Network error creating session: {e}")
                raise Exception(f"Failed to create session: {e}")
            except Exception as e:
                self.log.error(f"[jupyter-ai] Unexpected error: {e}")
                raise
    
    async def load_auth_token_from_file(self):
        """Load HMAP token from file"""
        
        try:
            self.log.info(f"[jupyter-ai] Loading auth token from file: {self.auth_token_path}")
            
            # TODO: Uncomment when file access is available
            # if not os.path.exists(self.auth_token_path):
            #     self.log.error(f"[jupyter-ai] Auth token file not found: {self.auth_token_path}")
            #     raise FileNotFoundError(f"Auth token file not found: {self.auth_token_path}")
                
            # with open(self.auth_token_path, 'r') as f:
            #     self.auth_token = f.read().strip()

            # Using hardcoded token for now (TODO: remove in production)
            self.log.warning("[jupyter-ai] Using hardcoded auth token (development mode)")
            self.auth_token = self.hardcoded_auth_token 
            
            if not self.auth_token:
                self.log.error("[jupyter-ai] Auth token is empty")
                raise ValueError("Auth token file is empty")
            
        except Exception as e:
            self.log.error(f"[jupyter-ai] Failed to read auth_token file: {e}")
            self.auth_token = None
            raise

    # ===============================================
    # SESSION REFRESH
    # ===============================================
    def schedule_proactive_refresh(self):
        """Schedule proactive token refresh based on JWT expiry."""
        self.log.info("[jupyter-ai] Scheduling proactive token refresh...")
        
        if self.refresh_timer:
            self.refresh_timer.cancel()

        expiry = self.parse_jwt_field(self.access_token, 'exp')
        
        if not expiry:
            self.log.warning("[jupyter-ai] Cannot parse token expiry, attempting refresh immediately")
            expiry = int(time.time() * 1000)
            return

        current_time = int(time.time() * 1000)

        # Refresh 1 minute before expiry (same as VSCode)
        refresh_time = expiry - 60_000
        time_until_refresh = max(0, refresh_time - current_time) # 0 for already expired token
        
        if time_until_refresh == 0:
            self.log.warning("[jupyter-ai] Token is already expired or expires very soon!")
        
        self.log.info(f"[jupyter-ai] Will refresh in {time_until_refresh / 1000} seconds")
        
        async def refresh_worker():
            try:
                self.log.info(f"[jupyter-ai]: Waiting {time_until_refresh / 1000} seconds until refresh...")
                # Wait until refresh time
                await asyncio.sleep(time_until_refresh / 1000)
                await self.refresh_session()
            except Exception as e:
                self.log.error(f"[jupyter-ai]: Proactive token refresh failed: {e}")
                self.log.exception(e)
        
        self.refresh_timer = asyncio.create_task(refresh_worker())

    def parse_jwt_field(self, token: str, field: str) -> Optional[int]:
        """Parse JWT field (same as VSCode)"""
        self.log.info(f"🔍 OAUTH_JWT: Parsing JWT field '{field}'...")
        
        try:
            if not token:
                self.log.warning("⚠️ OAUTH_JWT: Token is empty or None")
                return None
                
            # Split JWT token and decode payload
            token_parts = token.split('.')
            if len(token_parts) != 3:
                self.log.warning(f"⚠️ OAUTH_JWT: Invalid JWT format - expected 3 parts, got {len(token_parts)}")
                return None
                
            payload_b64 = token_parts[1]
            self.log.info(f"🔍 OAUTH_JWT: Extracted payload part: {payload_b64[:20]}...")
            
            # Add padding if needed
            payload_b64 += '=' * (4 - len(payload_b64) % 4)
            
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            self.log.info(f"🔍 OAUTH_JWT: Decoded payload JSON: {payload_json[:100]}...")
            
            payload = json.loads(payload_json)
            
            value = payload.get(field)
            self.log.info(f"🔍 OAUTH_JWT: Field '{field}' value: {value}")
            
            if field in ['exp', 'iat']:
                result = value * 1000 if value else None  # Convert to milliseconds
                self.log.info(f"🔍 OAUTH_JWT: Converted timestamp to milliseconds: {result}")
                return result
            return value
        except Exception as e:
            self.log.warning(f"⚠️ OAUTH_JWT: Failed to parse JWT field '{field}': {e}")
            return None
    
    async def refresh_session(self):
        """Refresh authentication session using refresh token."""

        if not self.refresh_token:
            raise Exception("No refresh token available")
            
        if not self.host:
            raise Exception("Host not configured - please set host URL")

        url = f"https://{self.host}/candidate/authn/v1/candidate/session/refresh"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    headers={
                        'Cookie': f'jwt_refresh_token={self.refresh_token}',
                    }
                ) as resp:
                    
                    if not (200 <= resp.status < 300):
                        self.log.error(f"[jupyter-ai] HTTP error - Status: {resp.status}, Reason: {resp.reason}")
                        raise Exception(f"Failed to refresh session: {resp.status} {resp.reason}")
                    
                    access_token = resp.cookies.get('jwt_access_token')
                    refresh_token = resp.cookies.get('jwt_refresh_token')
                    
                    # Extract values from cookie morsels
                    access_token_value = access_token.value if access_token else None
                    refresh_token_value = refresh_token.value if refresh_token else None
                    
                    self.log.info(f"[jupyter-ai] New access token found: {bool(access_token_value)}")
                    self.log.info(f"[jupyter-ai] New refresh token found: {bool(refresh_token_value)}")
                    
                    if access_token_value or refresh_token_value:
                        await self.handle_and_persist_session_tokens(
                            access_token_value,
                            refresh_token_value
                        )
                    else:
                        self.log.error("[jupyter-ai] No tokens found in cookies")
                        raise Exception("No tokens received in refresh response")
                        
            except aiohttp.ClientError as e:
                self.log.error(f"[jupyter-ai] Network error refreshing session: {e}")
                raise Exception(f"Failed to refresh session: {e}")
            except Exception as e:
                self.log.error(f"[jupyter-ai] Unexpected error: {e}")
                raise

    # ===============================================
    # COMMON 
    # ===============================================
    async def handle_and_persist_session_tokens(self, access_token: Optional[str], refresh_token: Optional[str]):
        """Handle new session tokens and save to token to config.json"""
        try:
            # Prepare API keys dictionary
            api_keys = {}
            if access_token:
                self.access_token = access_token
                api_keys["OPENAI_API_KEY"] = access_token
            else:
                self.log.warning("[jupyter-ai] No access token provided")

            if refresh_token:
                self.refresh_token = refresh_token
                api_keys["REFRESH_TOKEN"] = refresh_token
            else:
                self.log.warning("[jupyter-ai] No refresh token provided")
            
            # Create UpdateConfigRequest object as expected by config_manager
            update_request = UpdateConfigRequest(api_keys=api_keys)
            self.config_manager.update_config(update_request)

            self.schedule_proactive_refresh()
        except Exception as e:
            self.log.error(f"[jupyter-ai]: Failed to persist tokens to config: {e}")
            self.log.exception(e)
            raise

    def dispose(self):
        """Clean up resources (same as VSCode)"""
        self.log.info("[jupyter-ai] Disposing OAuth token manager...")
        if self.refresh_timer:
            self.refresh_timer.cancel()
            self.refresh_timer = None
            
        if self.create_session_promise:
            self.create_session_promise.cancel()
            self.create_session_promise = None
            
        # Clear sensitive data
        self.auth_token = None
        self.access_token = None
        self.refresh_token = None
            