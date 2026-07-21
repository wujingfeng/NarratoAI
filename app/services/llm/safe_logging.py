"""LLM 异常的最小安全日志元数据。"""

import hashlib
from loguru import logger


def log_llm_error(stage: str, error: BaseException, code: str = "LLM_STAGE_FAILED") -> None:
    """记录类型、阶段、错误码和不可逆消息摘要，不记录异常正文。"""
    message = str(error)
    logger.bind(
        stage=stage,
        error_type=type(error).__name__,
        code=code,
        error_length=len(message),
        error_sha256=hashlib.sha256(message.encode("utf-8")).hexdigest(),
    ).error("llm_stage_failed")
