from .registry import mapper_registry, register_mapper

# 导入 predefined_config_mappers 以触发装饰器注册
from . import predefined_config_mappers  # 关键！

def get_mapper(name: str):
    """Get config mapper by model type."""
    return mapper_registry.get_mapper(name)

def list_mappers():
    """List all registered mappers."""
    return mapper_registry.list_registered_mappers()

__all__ = [
    'mapper_registry',
    'register_mapper', 
    'get_mapper',
    'list_mappers',
]