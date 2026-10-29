#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import glob
from flask import Flask, render_template, send_file, jsonify, request
import json
from pathlib import Path
import zipfile
import tempfile
from datetime import datetime

# 设置模板目录为当前目录（因为 tt.py 和 index.html 在同一个目录）
app = Flask(__name__, template_folder=os.path.dirname(__file__))

# 数据源路径（包含日期文件夹）
DATA_SOURCE = "/home/guest/Documents/lkh/mtx/python/reid/save/"

# 人员列表文件路径
NAMES_FILE = os.path.join(os.path.dirname(__file__), 'names.json')
# 标注结果文件夹路径
RESULT_DIR = os.path.join(os.path.dirname(__file__), 'result')

# 当前选择的日期
current_date = None


def load_names():
    """从文件加载人员列表"""
    if os.path.exists(NAMES_FILE):
        try:
            with open(NAMES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载人员列表失败: {e}")
            return {}
    return {}


def save_names(name2rawpid):
    """保存人员列表到文件"""
    try:
        with open(NAMES_FILE, 'w', encoding='utf-8') as f:
            json.dump(name2rawpid, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"保存人员列表失败: {e}")
        return False


# 加载人员列表
name2rawpid = load_names()

# 存储标注映射 {文件夹名: 姓名}
annotations = {}


def get_res_file_path(date):
    """获取指定日期的结果文件路径"""
    os.makedirs(RESULT_DIR, exist_ok=True)
    return os.path.join(RESULT_DIR, f"{date}.txt")


def load_annotations(date):
    """从文件加载指定日期的标注结果"""
    if not date:
        return {}
    
    res_file = get_res_file_path(date)
    if os.path.exists(res_file):
        try:
            annotations_dict = {}
            with open(res_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and '\t' in line:
                        parts = line.split('\t', 1)
                        if len(parts) == 2:
                            folder_name, name = parts
                            annotations_dict[folder_name] = name
            return annotations_dict
        except Exception as e:
            print(f"加载标注结果失败: {e}")
            return {}
    return {}


def save_annotations(date):
    """保存标注结果到指定日期的文件"""
    if not date:
        return False
    
    try:
        res_file = get_res_file_path(date)
        with open(res_file, 'w', encoding='utf-8') as f:
            for folder_name, name in sorted(annotations.items()):
                f.write(f"{folder_name}\t{name}\n")
        return True
    except Exception as e:
        print(f"保存标注结果失败: {e}")
        return False


def get_available_dates():
    """获取所有可用的日期文件夹"""
    dates = []
    if os.path.exists(DATA_SOURCE):
        for item in os.listdir(DATA_SOURCE):
            item_path = os.path.join(DATA_SOURCE, item)
            if os.path.isdir(item_path):
                # 检查是否是日期格式 (YYYY-MM-DD)
                try:
                    from datetime import datetime
                    datetime.strptime(item, '%Y-%m-%d')
                    dates.append(item)
                except ValueError:
                    continue
    return sorted(dates, reverse=True)  # 最新的在前

# 支持的图片格式
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}


def get_image_files(folder_path):
    """获取文件夹中的所有图片文件"""
    image_files = []
    for ext in IMAGE_EXTENSIONS:
        image_files.extend(glob.glob(os.path.join(folder_path, f"*{ext}")))
        image_files.extend(glob.glob(os.path.join(folder_path, f"*{ext.upper()}")))
    return sorted(image_files)


def get_valid_folders(date):
    """获取指定日期下所有图片数量 >= 3 的文件夹"""
    valid_folders = []
    if not date:
        return valid_folders
    
    date_path = os.path.join(DATA_SOURCE, date)
    if not os.path.exists(date_path):
        return valid_folders
    
    for folder_name in os.listdir(date_path):
        folder_path = os.path.join(date_path, folder_name)
        if os.path.isdir(folder_path):
            image_files = get_image_files(folder_path)
            if len(image_files) >= 3:
                valid_folders.append(folder_name)
    
    return sorted(valid_folders)


@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')


@app.route('/api/dates')
def get_dates():
    """获取所有可用的日期列表"""
    dates = get_available_dates()
    return jsonify(dates)


@app.route('/api/set_date', methods=['POST'])
def set_date():
    """设置当前日期并加载对应的标注结果"""
    global current_date, annotations
    data = request.json
    date = data.get('date', '').strip()
    
    if not date:
        return jsonify({"success": False, "error": "日期不能为空"}), 400
    
    # 验证日期格式
    try:
        from datetime import datetime
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return jsonify({"success": False, "error": "日期格式错误，应为 YYYY-MM-DD"}), 400
    
    current_date = date
    # 加载该日期的标注结果
    annotations = load_annotations(date)
    
    return jsonify({
        "success": True,
        "date": date,
        "annotations_count": len(annotations)
    })


@app.route('/api/names')
def get_names():
    """获取人员列表"""
    global name2rawpid
    name2rawpid = load_names()
    return jsonify(name2rawpid)


@app.route('/api/add_name', methods=['POST'])
def add_name():
    """添加新人员"""
    global name2rawpid
    data = request.json
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({"success": False, "error": "姓名不能为空"}), 400
    
    # 重新加载确保最新
    name2rawpid = load_names()
    
    # 检查是否已存在
    if name in name2rawpid:
        return jsonify({"success": False, "error": "该姓名已存在"}), 400
    
    # 获取新的ID（当前最大ID + 1）
    new_id = max(name2rawpid.values()) + 1 if name2rawpid else 1
    name2rawpid[name] = new_id
    
    # 保存到文件
    if save_names(name2rawpid):
        return jsonify({"success": True, "message": f"已添加: {name} (ID: {new_id})", "name": name, "id": new_id})
    else:
        return jsonify({"success": False, "error": "保存失败"}), 500


@app.route('/api/folders')
def get_folders():
    """获取当前日期下所有有效文件夹列表"""
    if not current_date:
        return jsonify({"error": "请先选择日期"}), 400
    folders = get_valid_folders(current_date)
    return jsonify(folders)


@app.route('/api/images/<folder_name>')
def get_images(folder_name):
    """获取指定文件夹的前三张图片"""
    if not current_date:
        return jsonify({"error": "请先选择日期"}), 400
    
    folder_path = os.path.join(DATA_SOURCE, current_date, folder_name)
    if not os.path.exists(folder_path):
        return jsonify({"error": "文件夹不存在"}), 404
    
    image_files = get_image_files(folder_path)
    if len(image_files) < 3:
        return jsonify({"error": "图片数量不足"}), 404
    
    # 获取前三张图片
    first_three = image_files[:3]
    # 转换为相对于数据源的路径，用于 URL
    image_urls = []
    for img_path in first_three:
        # 路径格式：日期/文件夹名/图片名
        rel_path = os.path.join(current_date, folder_name, os.path.basename(img_path))
        image_urls.append(rel_path)
    
    return jsonify({
        "images": image_urls,
        "folder_name": folder_name,
        "current_annotation": annotations.get(folder_name, None)
    })


@app.route('/api/annotate', methods=['POST'])
def annotate():
    """添加标注"""
    global name2rawpid, annotations, current_date
    data = request.json
    folder_name = data.get('folder_name')
    name = data.get('name')
    
    if not current_date:
        return jsonify({"success": False, "error": "请先选择日期"}), 400
    
    if folder_name and name:
        # 重新加载确保最新
        name2rawpid = load_names()
        if name in name2rawpid:
            annotations[folder_name] = name
            # 立即保存到对应日期的文件
            save_annotations(current_date)
            return jsonify({"success": True, "message": f"已标注: {folder_name} -> {name}"})
        else:
            return jsonify({"success": False, "error": "无效的姓名"}), 400
    else:
        return jsonify({"success": False, "error": "缺少参数"}), 400


@app.route('/api/annotations')
def get_annotations():
    """获取所有标注"""
    return jsonify(annotations)


@app.route('/api/last_annotated_index')
def get_last_annotated_index():
    """获取最后一个标注的文件夹索引"""
    if not current_date:
        return jsonify({"index": -1})
    
    folders = get_valid_folders(current_date)
    if not folders:
        return jsonify({"index": -1})
    
    # 找到最后一个已标注的文件夹索引
    last_index = -1
    for i, folder in enumerate(folders):
        if folder in annotations:
            last_index = i
    
    # 如果找到了，返回下一个未标注的索引；否则返回0
    if last_index >= 0:
        # 找下一个未标注的
        for i in range(last_index + 1, len(folders)):
            if folders[i] not in annotations:
                return jsonify({"index": i})
        # 如果后面都标注了，返回最后一个的下一个（即长度，表示已完成）
        return jsonify({"index": len(folders)})
    else:
        # 没有标注过，返回第一个未标注的
        for i, folder in enumerate(folders):
            if folder not in annotations:
                return jsonify({"index": i})
        return jsonify({"index": 0})


@app.route('/api/download')
def download():
    """下载当前日期的标注为 txt 文件"""
    global current_date
    if not current_date:
        return jsonify({"error": "请先选择日期"}), 400
    
    import tempfile
    from flask import after_this_request
    
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    temp_path = temp_file.name
    
    # 写入标注映射
    for folder_name, name in sorted(annotations.items()):
        temp_file.write(f"{folder_name}\t{name}\n")
    
    temp_file.close()
    
    # 下载后删除临时文件
    @after_this_request
    def remove_file(response):
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        return response
    
    return send_file(
        temp_path,
        as_attachment=True,
        download_name=f'{current_date}.txt',
        mimetype='text/plain'
    )


@app.route('/api/download_all')
def download_all():
    """下载所有日期的标注结果为 zip 文件"""
    from flask import after_this_request
    
    if not os.path.exists(RESULT_DIR):
        return jsonify({"error": "result 文件夹不存在"}), 404
    
    # 创建临时 zip 文件
    temp_zip = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
    temp_zip_path = temp_zip.name
    temp_zip.close()
    
    try:
        # 创建 zip 文件
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 遍历 result 文件夹中的所有文件
            for root, dirs, files in os.walk(RESULT_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    # 计算相对路径（相对于 result 文件夹）
                    arcname = os.path.relpath(file_path, RESULT_DIR)
                    zipf.write(file_path, arcname)
        
        # 生成下载文件名（包含当前时间戳）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        download_name = f'result_{timestamp}.zip'
        
        # 下载后删除临时文件
        @after_this_request
        def remove_file(response):
            try:
                os.unlink(temp_zip_path)
            except Exception:
                pass
            return response
        
        return send_file(
            temp_zip_path,
            as_attachment=True,
            download_name=download_name,
            mimetype='application/zip'
        )
    except Exception as e:
        # 如果出错，尝试删除临时文件
        try:
            os.unlink(temp_zip_path)
        except Exception:
            pass
        return jsonify({"error": f"打包失败: {str(e)}"}), 500


@app.route('/images/<path:image_path>')
def serve_image(image_path):
    """提供图片文件服务"""
    # image_path 格式：日期/文件夹名/图片名
    full_path = os.path.join(DATA_SOURCE, image_path)
    if os.path.exists(full_path) and os.path.isfile(full_path):
        return send_file(full_path)
    else:
        return "图片不存在", 404


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)

