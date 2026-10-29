from typing import TypeVar, Generic, Optional, Any
from pydantic import BaseModel
from config.response import ResponseCode

# 定义泛型类型变量，用于响应数据的类型
T = TypeVar('T')

class ResponseModel(BaseModel, Generic[T]):
    """
    统一的API响应模型
    支持泛型，可以包含任意类型的数据
    """
    code: int           # 响应状态码
    message: str        # 响应消息
    data: Optional[T] = None  # 响应数据，可选
    
    @classmethod
    def success(cls, data: Any = None, message: str = "操作成功"):
        """
        创建成功响应
        Args:
            data: 响应数据
            message: 成功消息
        Returns:
            ResponseModel实例
        """
        return cls(
            code=ResponseCode.SUCCESS.code,
            message=message,
            data=data
        )
    
    @classmethod
    def error(cls, code: ResponseCode, message: str = None):
        """
        创建错误响应
        Args:
            code: 错误码
            message: 错误消息
        Returns:
            ResponseModel实例
        """
        return cls(
            code=code.code,
            message=message or code.message
        ) 