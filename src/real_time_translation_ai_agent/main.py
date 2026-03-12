import uvicorn

from .app import app, settings


def main() -> None:
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        access_log=settings.debug,
    )


if __name__ == '__main__':
    main()
