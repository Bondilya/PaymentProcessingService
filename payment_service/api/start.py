import uvicorn

from payment_service.api.main import app
from payment_service.settings import Settings

if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.api.port,
    )
