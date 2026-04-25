from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
import os

router = APIRouter()


@router.get("/")
def home():
    template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "dashboard.html")
    return FileResponse(template_path, media_type="text/html")
