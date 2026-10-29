import asyncio
import json
import os
import glob
import time
import base64
import cv2
import websockets
from pathlib import Path
from datetime import datetime

# 配置
HOST = "0.0.0.0"
PORT = 8089
SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SERVICE_DIR, "person_save_output")
INPUT_DIR = os.path.join(SERVICE_DIR, "person_save_input")

async def get_latest_results(limit=20):
    """
    获取最新的超分结果
    返回格式: [{"id":..., "origin_face":..., "enhanced_face":..., "timestamp":...}, ...]
    """
    results = []
    
    # 1. 扫描所有 track 输出目录
    # 目录名格式: {camera_id}_track_{track_id}
    track_dirs = glob.glob(os.path.join(OUTPUT_DIR, "*_track_*"))
    
    # 优化：按目录修改时间倒序排列，只处理最近活跃的 20 个 track
    # 这样避免了随着历史数据积累导致的性能下降
    track_dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    recent_track_dirs = track_dirs[:20]
    
    # 收集所有可能的 cmp 图片
    # 结构: track_dir/cmp/xxx.png
    all_cmp_images = []
    
    for track_dir in recent_track_dirs:
        cmp_dir = os.path.join(track_dir, "cmp")
        if not os.path.exists(cmp_dir):
            continue
            
        # 获取该 track 的 cmp 图片
        images = glob.glob(os.path.join(cmp_dir, "*.png"))
        if not images:
            continue
            
        # 尝试获取时间戳
        # 优先读取 info.txt 中的 processed_at，或者尝试关联 input 目录获取 created_at
        # 为了性能和简化，这里先尝试读取 track_dir 的修改时间，或者 info.txt
        timestamp_str = ""
        info_path = os.path.join(track_dir, "info.txt")
        
        # 尝试从 info.txt 读取 source 路径，进而去 input 目录找 created_at
        # 也可以直接用 info.txt 里的 processed_at
        try:
            created_at = None
            if os.path.exists(info_path):
                with open(info_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("source:"):
                            source_path = line.split(":", 1)[1].strip()
                            input_info = os.path.join(source_path, "info.txt")
                            if os.path.exists(input_info):
                                with open(input_info, "r", encoding="utf-8") as f2:
                                    for line2 in f2:
                                        if line2.startswith("created_at:"):
                                            created_at = line2.split(":", 1)[1].strip()
                                            break
                            break
            
            if created_at:
                timestamp_str = created_at
            else:
                # 回退：使用当前时间或文件修改时间
                mtime = os.path.getmtime(track_dir)
                timestamp_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        track_dirname = os.path.basename(track_dir)
        
        for img_path in images:
            all_cmp_images.append({
                "path": img_path,
                "timestamp": timestamp_str,
                "track_dirname": track_dirname,
                "mtime": os.path.getmtime(img_path)
            })
            
    # 按修改时间倒序排列，取最新的 limit 条
    all_cmp_images.sort(key=lambda x: x["mtime"], reverse=True)
    recent_images = all_cmp_images[:limit]
    
    for item in recent_images:
        try:
            img_path = item["path"]
            track_dirname = item["track_dirname"]
            timestamp = item["timestamp"]
            
            # 读取图片
            img = cv2.imread(img_path)
            if img is None:
                continue
                
            # 切分图片: 左半部分 origin, 右半部分 enhanced
            h, w = img.shape[:2]
            mid = w // 2
            origin_img = img[:, :mid]
            enhanced_img = img[:, mid:]
            
            # 编码为 base64
            _, origin_buf = cv2.imencode(".jpg", origin_img)
            origin_b64 = base64.b64encode(origin_buf).decode("utf-8")
            
            _, enhanced_buf = cv2.imencode(".jpg", enhanced_img)
            enhanced_b64 = base64.b64encode(enhanced_buf).decode("utf-8")
            
            # ID 生成: {track_dirname}_result_{filename}
            # 例如: live_camera_3_face_sr_track_2_result_000006_00
            basename = os.path.splitext(os.path.basename(img_path))[0]
            result_id = f"{track_dirname}_result_{basename}"
            
            results.append({
                "id": result_id,
                "origin_face": origin_b64,
                "enhanced_face": enhanced_b64,
                "timestamp": timestamp
            })
            
        except Exception as e:
            print(f"Error processing image {item['path']}: {e}")
            continue
            
    return results

async def handler(websocket):
    print(f"Client connected: {websocket.remote_address}")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "ping":
                    # 虽然 websockets 库会自动处理 ping/pong 帧，
                    # 但根据协议描述，客户端发送的是 JSON 消息 {"type": "ping"}
                    # 我们可以回复一个简单的 pong 或者不做业务层响应（只维持连接）
                    # 这里选择回复一个简单的 pong 确认
                    # await websocket.send(json.dumps({"type": "pong"}))
                    pass
                    
                elif msg_type == "get_results":
                    print("Received get_results request")
                    results = await get_latest_results(limit=10) # 限制返回最新的10条
                    response = {"Results": results}
                    await websocket.send(json.dumps(response))
                    
                else:
                    print(f"Unknown message type: {msg_type}")
                    
            except json.JSONDecodeError:
                print("Invalid JSON received")
            except Exception as e:
                print(f"Error handling message: {e}")
                
    except websockets.ConnectionClosed:
        print("Client disconnected")

async def main():
    print(f"Starting WebSocket server on ws://{HOST}:{PORT}/ws/results")
    # 设置 max_size=None 取消消息大小限制（Base64 图片可能很大）
    async with websockets.serve(handler, HOST, PORT, max_size=None):
        print("WebSocket server started successfully!")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped")
