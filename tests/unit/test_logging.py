import logging

from utils.logger import SensitiveDataFilter, log_event


def test_sensitive_values_and_token_patterns_are_redacted(monkeypatch, caplog) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "top-secret-value")
    logger = logging.getLogger("redaction-test")
    logger.addFilter(SensitiveDataFilter())

    with caplog.at_level(logging.INFO, logger="redaction-test"):
        logger.info("api_key=%s bearer sk-example-token", "top-secret-value")

    assert "top-secret-value" not in caplog.text
    assert "sk-example-token" not in caplog.text
    assert "[REDACTED]" in caplog.text


def test_structured_event_contains_generation_context(caplog) -> None:
    logger = logging.getLogger("context-test")
    with caplog.at_level(logging.INFO, logger="context-test"):
        log_event(
            logger,
            logging.INFO,
            "generation_completed",
            scenario_id="scenario-1",
            step="task",
            request_id="request-1",
            duration_ms=125,
        )

    assert "event=generation_completed" in caplog.text
    assert "scenario_id=scenario-1" in caplog.text
    assert "step=task" in caplog.text
    assert "request_id=request-1" in caplog.text
    assert "duration_ms=125" in caplog.text
