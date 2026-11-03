from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import client
from routes.meeting import router as meeting_router
from routes.chat import router as chat_router
from routes.auth import router as auth_router
from routes.admin import router as admin_router
from fastapi.staticfiles import StaticFiles
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.admin.command("ping")
    print("MongoDB connected")

    # JWT secret length validation (HS256 requires >= 32 bytes)
    jwt_secret = os.getenv("JWT_SECRET", "")
    secret_bytes = len(jwt_secret.encode())
    if not jwt_secret:
        print("WARNING: JWT_SECRET is not set. Authentication will not work.")
    elif secret_bytes < 32:
        print(
            f"WARNING: JWT_SECRET is only {secret_bytes} bytes. "
            f"HS256 requires at least 32 bytes. "
            f"Generate a secure replacement with: "
            f"python3 -c \"import secrets; print(secrets.token_hex(32))\""
        )
    else:
        print(f"JWT_SECRET: {secret_bytes} bytes (OK)")

    yield

    await client.close()

app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://syncora-by-prabh.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(meeting_router)
app.include_router(chat_router)
app.include_router(admin_router)

os.makedirs("uploads/profiles", exist_ok=True)

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {
        "message": "Syncora Backend"
    }