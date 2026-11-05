"""
模型管理模块，提供对深度学习模型的全局管理
"""

# 从model_manager模块导出model_manager单例实例
from models.model_manager import model_manager, get_model_context

# 导出所有公共API
__all__ = ['model_manager', 'get_model_context']