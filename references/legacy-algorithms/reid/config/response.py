from enum import Enum

class ResponseCode(Enum):
    """
    API响应状态码枚举类
    每个状态码包含数字码和对应的消息
    """
    SUCCESS = (200, "操作成功")              # 请求成功
    PARAM_ERROR = (400, "参数错误")          # 请求参数错误
    UNAUTHORIZED = (401, "未授权")           # 未经授权
    FORBIDDEN = (403, "禁止访问")            # 禁止访问
    NOT_FOUND = (404, "资源未找到")          # 请求的资源不存在
    SERVER_ERROR = (500, "服务器内部错误")    # 服务器错误
    SERVICE_UNAVAILABLE = (503, "服务不可用") # 服务不可用
    
    def __init__(self, code: int, message: str):
        """
        初始化响应码
        Args:
            code: 状态码数字
            message: 状态码对应的消息
        """
        self.code = code
        self.message = message 