from fastapi import HTTPException
from config.response import ResponseCode

class APIException(HTTPException):
    """
    自定义API异常基类
    继承自FastAPI的HTTPException
    """
    def __init__(
        self,
        code: ResponseCode,
        message: str = None,
        headers: dict = None
    ):
        """
        初始化API异常
        Args:
            code: 响应码
            message: 错误消息
            headers: 响应头
        """
        super().__init__(
            status_code=code.code,
            detail={
                "code": code.code,
                "message": message or code.message
            },
            headers=headers
        )

class ParameterError(APIException):
    """
    参数错误异常
    用于请求参数验证失败时抛出
    """
    def __init__(self, message: str = None):
        super().__init__(ResponseCode.PARAM_ERROR, message)

class ServiceError(APIException):
    """
    服务错误异常
    用于服务器内部错误时抛出
    """
    def __init__(self, message: str = None):
        super().__init__(ResponseCode.SERVER_ERROR, message) 