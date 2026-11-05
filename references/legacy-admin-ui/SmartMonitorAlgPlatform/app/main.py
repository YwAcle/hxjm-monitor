# 导入FastAPI框架
from fastapi import FastAPI
# 导入CORS中间件用于处理跨域请求
from fastapi.middleware.cors import CORSMiddleware
# 导入API路由
from app.api import endpoints
from app.core.config import settings

# 创建FastAPI应用实例
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0"
)

# 配置 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:5000",
        "http://127.0.0.1:8888",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# 注册路由
app.include_router(endpoints.router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": settings.PROJECT_NAME} 