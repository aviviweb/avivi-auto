import uvicorn

from avivi_master.config import settings


def main() -> None:
    uvicorn.run(
        "avivi_master.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
