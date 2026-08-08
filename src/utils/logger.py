import logging
import os
import re
from datetime import datetime


_SENSITIVE_KEY_NAMES = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|token|password|secret)\s*[=:]\s*([^\s,;]+)"
)
_TOKEN_PATTERN = re.compile(r"(?i)\b(?:sk|key|token)-[A-Za-z0-9._-]{6,}\b")


class SensitiveDataFilter(logging.Filter):
    """Remove credential-like values before records reach console or files."""

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        rendered = _SENSITIVE_KEY_NAMES.sub(lambda match: f"{match.group(1)}=[REDACTED]", rendered)
        rendered = _TOKEN_PATTERN.sub("[REDACTED]", rendered)
        record.msg = rendered
        record.args = ()
        return True


def log_event(logger: logging.Logger, level: int, event: str, **fields: object) -> None:
    values = " ".join(f"{key}={value}" for key, value in sorted(fields.items()) if value is not None)
    logger.log(level, "event=%s%s", event, f" {values}" if values else "")

class Logger:
    """日志模块"""
    
    def __init__(self, log_dir="logs"):
        """初始化日志模块
        
        Args:
            log_dir: 日志文件存储目录
        """
        # 创建日志目录
        self.log_dir = log_dir
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        
        # 生成日志文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"scenario_agent_{timestamp}.log")
        
        # 配置日志
        self.logger = logging.getLogger("ScenarioAgent")
        self.logger.setLevel(logging.INFO)
        
        # 避免重复添加处理器
        if not self.logger.handlers:
            # 文件处理器
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setLevel(logging.INFO)
            
            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)

            file_handler.addFilter(SensitiveDataFilter())
            console_handler.addFilter(SensitiveDataFilter())
            
            # 格式化器
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            # 添加处理器
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)
    
    def get_logger(self):
        """获取日志记录器
        
        Returns:
            logging.Logger: 日志记录器
        """
        return self.logger
    
    def get_log_file(self):
        """获取日志文件路径
        
        Returns:
            str: 日志文件路径
        """
        return self.log_file

# 单例模式
logger_instance = None

def get_logger():
    """获取日志记录器单例
    
    Returns:
        logging.Logger: 日志记录器
    """
    global logger_instance
    if logger_instance is None:
        logger_instance = Logger()
    return logger_instance.get_logger()

def get_log_file():
    """获取日志文件路径
    
    Returns:
        str: 日志文件路径
    """
    global logger_instance
    if logger_instance is None:
        logger_instance = Logger()
    return logger_instance.get_log_file()
