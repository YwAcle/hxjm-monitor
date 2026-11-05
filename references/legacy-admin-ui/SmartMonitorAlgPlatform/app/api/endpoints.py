import sys
import os
import importlib
import threading
from typing import Dict, Any
import time

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import List, Optional
import json
import aiofiles
from app.core.config import settings
import base64
from app.core.alg import model_processor
from app.core.algmodellibrary import ModelLoader

# 示例：face_detection.py
from my_project.test import ts_main
from my_project.main import StreamConfig

# 全局字典来存储每个任务的状态，指定键为str类型，值为dict类型
task_status: Dict[str, Dict[str, Any]] = {}

def run_ts_main_background(task_id: str, images_list: list, model_params_dict: dict, machines_list: list):
    """在后台运行 ts_main"""
    try:
        task_status[task_id] = {"status": "running", "start_time": time.time()}
        ts_main(images_list, model_params_dict, machines_list)
        task_status[task_id]["status"] = "completed"
    except Exception as e:
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["error"] = str(e)

router = APIRouter()
@router.post("/test")
async def process_test(
    images: Optional[str] = Form(None),
    model_params: str = Form(...),
    machines: str = Form(...)
):
    # 处理 images 为 None 的情况
    images_list = json.loads(images) if images is not None else []
    model_params_dict = json.loads(model_params)
    machines_list = json.loads(machines)
    
    # 生成唯一的任务ID
    task_id = f"task_{int(time.time()*1000)}"
    
    # 创建新线程运行 ts_main
    thread = threading.Thread(
        target=run_ts_main_background,
        args=(task_id, images_list, model_params_dict, machines_list)
    )
    thread.daemon = True  # 设置为守护线程，这样主程序退出时线程会自动结束
    thread.start()
    
    return {
        "code": 200,
        "task_id": task_id,
        "status": "success"
    }

@router.post("/alg_start")
async def alg_start(
    images: Optional[str] = Form(None),
    model_params: str = Form(...),
    machines: str = Form(...)
):
    try:
        # 处理输入参数
        images_list = json.loads(images) if images is not None else []
        model_params_dict = json.loads(model_params)
        machines_list = json.loads(machines)

        # 获取模型配置
        with open('resource/models_config.json', 'r', encoding='utf-8') as f:
            models_config = json.load(f)

        model_code = model_params_dict.get('modelCode')
        if not model_code or model_code not in models_config:
            raise HTTPException(status_code=400, detail="无效的模型代码")

        model_info = models_config[model_code]
        wheel_path = model_info['path']  # wheel文件路径
        
        # 从wheel文件名解析包名
        package_name = "rtsp_face_test"  # wheel包的实际包名
        
        # 生成任务ID
        task_id = f"task_{int(time.time()*1000)}"
        
        # 创建后台线程执行模型
        def run_model_background():
            try:
                task_status[task_id] = {"status": "running", "start_time": time.time()}
                result = ModelLoader.execute_model(
                    wheel_path=wheel_path,
                    package_name=package_name,
                    images_list=images_list,
                    model_params=model_params_dict,
                    machines_list=machines_list
                )
                task_status[task_id]["status"] = "completed"
                task_status[task_id]["result"] = result
            except Exception as e:
                task_status[task_id]["status"] = "failed"
                task_status[task_id]["error"] = str(e)

        thread = threading.Thread(target=run_model_background)
        thread.daemon = True
        thread.start()

        return {
            "code": 200,
            "task_id": task_id,
            "status": "success"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加一个新接口来查询任务状态
@router.get("/test/status/{task_id}")
async def get_task_status(task_id: str):
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    status_info = task_status[task_id]
    return {
        "task_id": task_id,
        "status": status_info["status"],
        "runtime": time.time() - status_info["start_time"],
        "error": status_info.get("error")  # 如果任务失败，返回错误信息
    }

#标准接口
@router.post("/process")
async def process_media(
    images: Optional[str] = Form(None),
    model_params: str = Form(...),
    machines: str = Form(...)
):
    """处理媒体文件"""
    try:
        # 处理 images 为 None 的情况
        images_list = json.loads(images) if images is not None else []
        model_params_dict = json.loads(model_params)
        machines_list = json.loads(machines)
        
        # 处理文件
        processed_files = []
        for image in images_list:
            processed_files.append({
                "file_name": image['name'],
                "processed": True,
                "imgBase64": image['data']  # 直接使用传入的base64数据
            })
            
        return {
            "status": "success",
            "message": "处理完成",
            "model": model_params_dict,
            "machines": machines_list,
            "results": processed_files
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"处理失败: {str(e)}"
        )
#上传模型文件到resource目录
@router.post("/upload_model")
async def upload_model(
    model_file: UploadFile = File(...),
    model_name: str = Form(...),
    model_code: str = Form(...)
):
    """上传模型文件到resource目录，并将模型信息写入配置文件"""
    try:
        # 确保resource目录存在
        resource_dir = "resource/models"
        os.makedirs(resource_dir, exist_ok=True)

        # 构建保存路径
        file_path = os.path.join(resource_dir, model_file.filename)
        # 检查并创���models_config文件
        config_file = os.path.join("resource", "models_config.json")

        # 读取现有配置或创建新配置
        if os.path.exists(config_file):
            async with aiofiles.open(config_file, 'r') as f:
                content = await f.read()
                models_config = json.loads(content) if content else {}
        else:
            models_config = {}

        # 更新配置信息
        models_config[model_code] = {
            "name": model_name,
            "file": model_file.filename,
            "code": model_code,
            "path": file_path
        }

        # 写入更新后的配置
        async with aiofiles.open(config_file, 'w') as f:
            await f.write(json.dumps(models_config, indent=4))
        # 分块写入文件
        async with aiofiles.open(file_path, 'wb') as out_file:
            while content := await model_file.read(settings.CHUNK_SIZE):
                await out_file.write(content)

        # 返回结果
        model_info = {
            "name": model_name,
            "code": model_code,
            "filename": model_file.filename,
            "path": file_path
        }

        return {
            "message": "模型上传成功",
            "model_info": model_info
        }

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)  # 清理失败的文件
        raise HTTPException(status_code=500, detail=f"模型上传失败: {str(e)}")
