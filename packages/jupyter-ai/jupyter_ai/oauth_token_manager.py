import asyncio
import base64
import json
import os
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import aiohttp

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
        
        # Configuration
        self.auth_token_path = "/opt/hackerrank/tokens/hmap.token"
        self.host = ""  # Will be set later by user

    async def init(self):
        """Initialize OAuth manager when extension loads"""
        self.log.info("Initializing OAuth token manager...")
        
        await self.load_tokens_from_config()
        
        if not self.access_token:
            await self.create_session()
        else:
            self.schedule_proactive_refresh()
            
        self.log.info("OAuth token manager initialized successfully")

    async def load_tokens_from_config(self):
        """Load stored tokens from config.json"""
        try:
            config = self.config_manager._read_config()
            api_keys = config.api_keys or {}
            
            # Access token is stored as OPENAI_API_KEY
            self.access_token = api_keys.get("OPENAI_API_KEY")
            self.refresh_token = api_keys.get("REFRESH_TOKEN")
            
            if self.access_token:
                self.log.debug("Loaded access token from config")
            if self.refresh_token:
                self.log.debug("Loaded refresh token from config")
                
        except Exception as e:
            self.log.error(f"Failed to load tokens from config: {e}")
    
    # ===============================================
    # SESSION CREATION
    # ===============================================
    async def create_session(self):
        """Create new authentication session using HMAP token."""
        self.log.debug(f"Creating new session...")

        if self.create_session_promise:
            await self.create_session_promise
            return

        self.create_session_promise = asyncio.create_task(self.create_session_impl())
        
        try:
            await self.create_session_promise
        finally:
            self.create_session_promise = None

    async def create_session_impl(self):
        if not self.auth_token:
            await self.load_auth_token_from_file()

        if not self.auth_token:
            raise Exception("Auth token not loaded")
        
        if not self.host:
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
                    if not resp.ok:
                        raise Exception(f"Failed to create session: {resp.status} {resp.reason}")
                    
                    # Parse Set-Cookie headers for tokens
                    set_cookie = resp.headers.get('set-cookie', '')
                    if set_cookie:
                        tokens = self.parse_cookie_tokens(set_cookie)
                        await self.handle_and_persist_session_tokens(
                            tokens.get('accessToken'),
                            tokens.get('refreshToken')
                        )
                        self.log.info("Session created successfully")
                    else:
                        raise Exception("No tokens received in response")
                        
            except aiohttp.ClientError as e:
                self.log.error(f"Network error creating session: {e}")
                raise Exception(f"Failed to create session: {e}")
    
    async def load_auth_token_from_file(self):
        """Load HMAP token from file (like VSCode's loadAuthTokenFromFile)"""
        try:
            if not os.path.exists(self.auth_token_path):
                raise FileNotFoundError(f"Auth token file not found: {self.auth_token_path}")
                
            with open(self.auth_token_path, 'r') as f:
                self.auth_token = f.read().strip()
                
            if not self.auth_token:
                raise ValueError("Auth token file is empty")
                
            self.log.debug("Successfully loaded auth token from file")
            
        except Exception as e:
            self.log.error(f"Failed to read auth_token file: {e}")
            self.auth_token = None
            raise

    # ===============================================
    # SESSION REFRESH
    # ===============================================
    def schedule_proactive_refresh(self):
        """Schedule proactive token refresh based on JWT expiry."""
        if self.refresh_timer:
            self.refresh_timer.cancel()

        expiry = self.parse_jwt_field(self.access_token, 'exp')
        if not expiry:
            self.log.warning("Cannot parse token expiry, attempting refresh immediately")
            expiry = int(time.time() * 1000)
            return

        # for expiry < current time, 
        # we are assuming that refresh token will work or need to create a new session

        # Refresh 1 minute before expiry (same as VSCode)
        refresh_time = expiry - 60_000
        time_until_refresh = max(0, refresh_time - int(time.time() * 1000)) # 0 for already expired token
        
        async def refresh_worker():
            try:
                # Wait until refresh time
                await asyncio.sleep(time_until_refresh / 1000)
                await self.refresh_session()
            except Exception as e:
                self.log.error(f"Proactive token refresh failed: {e}")
        
        self.refresh_timer = asyncio.create_task(refresh_worker())
        self.log.debug(f"Scheduled proactive refresh for {datetime.fromtimestamp(refresh_time / 1000)}")

    def parse_jwt_field(self, token: str, field: str) -> Optional[int]:
        """Parse JWT field (same as VSCode)"""
        try:
            # Split JWT token and decode payload
            payload_b64 = token.split('.')[1]
            # Add padding if needed
            payload_b64 += '=' * (4 - len(payload_b64) % 4)
            payload_json = base64.b64decode(payload_b64).decode('utf-8')
            payload = json.loads(payload_json)
            
            value = payload.get(field)
            if field in ['exp', 'iat']:
                return value * 1000 if value else None  # Convert to milliseconds
            return value
        except Exception:
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
                    if not resp.ok:
                        raise Exception(f"Failed to refresh session: {resp.status} {resp.reason}")
                    
                    # Parse Set-Cookie headers for new tokens
                    set_cookie = resp.headers.get('set-cookie', '')
                    if set_cookie:
                        tokens = self.parse_cookie_tokens(set_cookie)
                        await self.handle_and_persist_session_tokens(
                            tokens.get('accessToken'),
                            tokens.get('refreshToken')
                        )
                        self.log.info("Session refreshed successfully")
                    else:
                        raise Exception("No tokens received in refresh response")
                        
            except aiohttp.ClientError as e:
                self.log.error(f"Network error refreshing session: {e}")
                raise Exception(f"Failed to refresh session: {e}")

    # ===============================================
    # COMMON 
    # ===============================================
    def parse_cookie_tokens(self, set_cookie: str) -> Dict[str, str]:
        """Parse access and refresh tokens from Set-Cookie header (same as VSCode)"""
        import re
        
        access_match = re.search(r'jwt_access_token=([^;]+)', set_cookie)
        refresh_match = re.search(r'jwt_refresh_token=([^;]+)', set_cookie)
        
        return {
            'accessToken': access_match.group(1) if access_match else None,
            'refreshToken': refresh_match.group(1) if refresh_match else None
        }

    async def handle_and_persist_session_tokens(self, access_token: Optional[str], refresh_token: Optional[str]):
        """Handle new session tokens and save to token to config.json"""
        try:
            update_data = {"api_keys": {}}

            if access_token:
                self.access_token = access_token
                update_data["api_keys"]["OPENAI_API_KEY"] = access_token

            if refresh_token:
                self.refresh_token = refresh_token
                update_data["api_keys"]["REFRESH_TOKEN"] = refresh_token
            
            self.config_manager.update_config(update_data)
            self.schedule_proactive_refresh()
            self.log.debug("Persisted tokens to config")
        except Exception as e:
            self.log.error(f"Failed to persist tokens to config: {e}")

    def dispose(self):
        """Clean up resources (same as VSCode)"""
        if self.refresh_timer:
            self.refresh_timer.cancel()
            self.refresh_timer = None
            
        if self.create_session_promise:
            self.create_session_promise.cancel()
            self.create_session_promise = None
            
        self.log.debug("OAuth token manager disposed")
    