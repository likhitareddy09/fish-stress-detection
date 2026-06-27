from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from app.core.security import authenticate_user, create_access_token, get_current_user

router = APIRouter()


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    username:     str
    role:         str
    expires_in:   str = "24 hours"


@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login with username + password, get a JWT token back.
    
    Team credentials:
    - taahira / backend2024   (admin)
    - likhita / cv2024        (writer)
    - yashwanth / hardware2024 (writer)
    - viewer / view2024       (reader)
    
    Use the returned access_token in all subsequent requests:
    Authorization: Bearer <token>
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
    )


@router.get("/me")
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    """Returns the profile of whoever is currently logged in."""
    return {
        "username": current_user["username"],
        "role":     current_user["role"],
        "permissions": {
            "read":  True,
            "write": current_user["role"] in ("admin", "writer"),
            "admin": current_user["role"] == "admin",
        }
    }


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """
    JWT tokens are stateless — logout just confirms the token was valid.
    Client-side should discard the token.
    """
    return {"message": f"Goodbye {current_user['username']}. Discard your token."}