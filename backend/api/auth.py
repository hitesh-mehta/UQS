from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import httpx
from backend.config import settings
from backend.core.auth import create_access_token
import logging

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("uqs.auth")

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
async def login(credentials: LoginRequest):
    """
    Authenticate against Supabase Auth (GoTrue).
    If successful, issue a local backend JWT to avoid passing the
    Supabase access token back & forth continuously.
    """
    url = f"{settings.supabase_url}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": settings.supabase_anon_key,
        "Content-Type": "application/json"
    }
    data = {
        "email": credentials.email,
        "password": credentials.password
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, headers=headers, json=data, timeout=10.0)
        except Exception as e:
            log.error(f"Supabase Auth connection error: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not reach authentication provider."
            )
        
    if resp.status_code != 200:
        error_msg = "Invalid credentials"
        try:
            payload = resp.json()
            if "error_description" in payload:
                error_msg = payload["error_description"]
            elif "msg" in payload:
                error_msg = payload["msg"]
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_msg,
        )
        
    # Success
    auth_data = resp.json()
    user_data = auth_data.get("user", {})
    user_id = user_data.get("id", "u_unknown")
    email = user_data.get("email", credentials.email)
    
    # Check if role comes from Supabase user_metadata
    user_meta = user_data.get("user_metadata", {})
    role = user_meta.get("role")
    
    if not role:
        # Fallback heuristic if not explicitly set in Supabase user metadata
        role = "viewer"
        email_lower = email.lower()
        if "admin" in email_lower:
            role = "admin"
        elif "analyst" in email_lower or "sharma" in email_lower:
            role = "analyst"
        elif "manager" in email_lower:
            role = "regional_manager"
        elif "audit" in email_lower:
            role = "auditor"
            
    # Issue UQS backend JWT
    token = create_access_token(user_id=user_id, role=role, email=email)
    return {"access_token": token, "token_type": "bearer", "role": role}

