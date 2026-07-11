"""日志配置"""
import logging

def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%H:%M:%S")

def get_logger(name: str):
    return logging.getLogger(name)
