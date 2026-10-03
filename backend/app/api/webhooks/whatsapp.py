from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(
    prefix="/webhook",
    tags=["whatsapp"],
)

@router.post("/whatsapp")
async def whatsapp_webhook(request: Request) -> JSONResponse:
    payload = await request.json()
    return JSONResponse(
        content={
            "status": "received",
            "message": "WhatsApp webhook received successfully",
            "data": payload
        },
        status_code=200
    )
