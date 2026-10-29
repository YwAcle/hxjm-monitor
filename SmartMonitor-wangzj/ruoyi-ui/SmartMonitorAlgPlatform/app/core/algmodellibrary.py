import sys
import os
import subprocess
import importlib
import pip
from typing import Any, Dict

class ModelLoader:
    @staticmethod
    def install_wheel(wheel_path: str) -> bool:
        """安装wheel包"""
        try:
            subprocess.check_call([
                sys.executable, 
                "-m", 
                "pip", 
                "install", 
                wheel_path
            ])
            return True
        except Exception as e:
            print(f"安装wheel包失败: {str(e)}")
            return False

    @staticmethod
    def load_function(package_name: str, function_name: str = 'ts_main'):
        """动态加载包中的函数"""
        try:
            # 重新加载模块（如果已经加载过）
            if package_name in sys.modules:
                module = importlib.reload(sys.modules[package_name])
            else:
                module = importlib.import_module(package_name)
            
            # 获取指定函数
            return getattr(module, function_name)
        except Exception as e:
            print(f"加载函数失败: {str(e)}")
            return None

    @staticmethod
    def execute_model(wheel_path: str, 
                     package_name: str,
                     images_list: list,
                     model_params: Dict[str, Any],
                     machines_list: list):
        """安装wheel包并执行模型"""
        try:
            # 1. 安装wheel包
            if not ModelLoader.install_wheel(wheel_path):
                raise Exception("wheel包安装失败")

            # 2. 加载ts_main函数
            ts_main = ModelLoader.load_function(package_name)
            if not ts_main:
                raise Exception("ts_main函数加载失败")

            # 3. 执行函数
            result = ts_main(images_list, model_params, machines_list)
            return result

        except Exception as e:
            raise Exception(f"模型执行失败: {str(e)}")
