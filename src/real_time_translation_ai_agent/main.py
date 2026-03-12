from .agent import LiveTranslationAgent
from .config import get_settings


def main() -> None:
    settings = get_settings()
    agent = LiveTranslationAgent()
    agent.run(host=settings.host, port=settings.port)


if __name__ == '__main__':
    main()
