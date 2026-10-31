import logging
import logging.config


def setup_logging(level: str = "INFO") -> None:
    """Единая настройка логов. В логи нельзя писать реквизиты и секреты (ТЗ §6, §13)."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                },
            },
            "root": {"level": level, "handlers": ["console"]},
        }
    )
