from pydantic import BaseModel
from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    File,
    Depends,
)
from services.dependencies import get_current_user
from database import users_collection
import os
import io
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from services.auth import (
    create_access_token,
    hash_password,
    verify_password,
)
import uuid
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

router = APIRouter(
    prefix="/api/auth",
    tags=["Authentication"]
)


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str


class GoogleLoginRequest(BaseModel):
    credential: str

@router.post("/register")
async def register(request: RegisterRequest):

    # Check whether email already exists
    existing_user = await users_collection.find_one({
        "email": request.email
    })

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Check username
    existing_username = await users_collection.find_one({
        "username": request.username
    })

    if existing_username:
        raise HTTPException(
            status_code=400,
            detail="Username already taken"
        )

    # Hash password
    hashed_password = hash_password(
        request.password
    )

    # Create user
    user = {
        "username": request.username,
        "email": request.email,
        "hashed_password": hashed_password,
        "google_id": None,
        "is_active": True
    }

    result = await users_collection.insert_one(user)

    return {
        "message": "User registered successfully",
        "user_id": str(result.inserted_id)
    }

@router.post("/login")
async def login(request: LoginRequest):

    user = await users_collection.find_one({
        "email": request.email
    })

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    if not user.get("hashed_password"):
        raise HTTPException(
            status_code=401,
            detail="This account does not use password login"
        )

    password_valid = verify_password(
        request.password,
        user["hashed_password"]
    )

    if not password_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    access_token = create_access_token(
        str(user["_id"])
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me")
async def get_me(current_user=Depends(get_current_user)):

    return {
        "id": str(current_user["_id"]),
        "username": current_user["username"],
        "email": current_user["email"],
        "profile_image": current_user.get("profile_image")
    }


@router.post("/google")
async def google_login(
    request: GoogleLoginRequest
):

    try:
        google_user = id_token.verify_oauth2_token(
            request.credential,
            google_requests.Request(),
            os.getenv("GOOGLE_CLIENT_ID")
        )

    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid Google token"
        )

    google_id = google_user.get("sub")
    email = google_user.get("email")
    name = google_user.get("name")
    picture = google_user.get("picture")

    if not google_id or not email:
        raise HTTPException(
            status_code=400,
            detail="Google account information is incomplete"
        )

    # Find existing user
    user = await users_collection.find_one({
        "email": email
    })

    if not user:

        user_data = {
            "username": name or email.split("@")[0],
            "email": email,
            "hashed_password": None,
            "google_id": google_id,
            "profile_image": picture,
            "is_active": True
        }

        result = await users_collection.insert_one(
            user_data
        )

        user = await users_collection.find_one({
            "_id": result.inserted_id
        })

    else:
        update_data = {}

        if not user.get("google_id"):
            update_data["google_id"] = google_id

        if picture and not user.get("profile_image"):
            update_data["profile_image"] = picture

        if update_data:
            await users_collection.update_one(
                {"_id": user["_id"]},
                {"$set": update_data}
            )

            user = await users_collection.find_one({
                "_id": user["_id"]
            })

    access_token = create_access_token(
        str(user["_id"])
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/profile-picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user)
):
    if not file.content_type:
        raise HTTPException(
            status_code=400,
            detail="Invalid file"
        )

    allowed_types = {"image/jpeg", "image/png", "image/webp"}

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, PNG and WebP images are allowed"
        )

    contents = await file.read()

    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Profile picture must be smaller than 5 MB"
        )

    # Delete previous Cloudinary image if one exists
    old_public_id = current_user.get("profile_picture_public_id")
    if old_public_id:
        try:
            cloudinary.uploader.destroy(old_public_id)
        except Exception as err:
            print(f"Cloudinary: could not delete old image {old_public_id}: {err}")

    # Upload to Cloudinary
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(contents),
            folder="syncora/profiles",
            public_id=str(uuid.uuid4()),
            resource_type="image",
            overwrite=True,
        )
    except Exception as err:
        raise HTTPException(
            status_code=500,
            detail="Failed to upload profile picture. Please try again."
        ) from err

    secure_url = result["secure_url"]
    public_id = result["public_id"]

    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {
            "$set": {
                "profile_image": secure_url,
                "profile_picture_public_id": public_id,
            }
        }
    )

    return {
        "message": "Profile picture updated successfully",
        "profile_image": secure_url,
    }


@router.delete("/profile-picture")
async def remove_profile_picture(
    current_user=Depends(get_current_user)
):
    public_id = current_user.get("profile_picture_public_id")
    if public_id:
        try:
            cloudinary.uploader.destroy(public_id)
        except Exception as err:
            print(f"Cloudinary: could not delete image {public_id}: {err}")

    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {
            "$unset": {
                "profile_image": "",
                "profile_picture_public_id": "",
            }
        }
    )

    return {"message": "Profile picture removed successfully"}