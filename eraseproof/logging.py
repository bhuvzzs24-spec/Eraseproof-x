import json
import logging


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        result = {"level": record.levelname, "logger": record.name, "message": record.getMessage()}
        for key in (
            "correlation_id",
            "event_id",
            "status",
            "path",
            "target",
            "request_id",
            "failure_code",
        ):
            if hasattr(record, key):
                result[key] = getattr(record, key)
        # Payloads and exception strings are deliberately excluded.
        if record.exc_info:
            result["exception_type"] = record.exc_info[0].__name__
        return json.dumps(result)


def configure() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(logging.INFO)
