import uvicorn
from app.core.config import settings


if __name__ == "__main__":
      uvicorn.run(
         "app.main:app",  # FastAPI应用程序的导入路径
         host="127.0.0.1",  # 监听所有可用的网络接口 
         port=8888,  # 服务运行的端口号
         reload=True,  # 启用热重载,代码更改时自动重启服务器
         timeout_keep_alive=settings.UPLOAD_TIMEOUT,  # 保持连接的超时时间
     )

