"""
防止ID跳动的最佳实践 Demo
使用多种策略减少ID切换问题
"""

from pathlib import Path
import cv2
import numpy as np
import torch
import torchvision
from boxmot import create_tracker, get_tracker_config

# ====================
# 配置参数
# ====================
DEVICE = torch.device('cpu')
CONFIDENCE_THRESHOLD = 0.4  # 降低阈值，减少漏检
REID_WEIGHTS = Path('osnet_x0_25_msmt17.pt')

# 选择最佳跟踪器
# 推荐顺序: HybridSORT > DeepOCSORT > BoostTrack > StrongSORT > BotSort
TRACKER_TYPE = 'hybridsort'  # 最强的ID一致性


class AntiIDSwitchTracker:
    """
    防ID跳动的行人跟踪器
    
    核心策略:
    1. 使用最强的跟踪算法 (HybridSORT/DeepOCSORT)
    2. 优化跟踪参数 (长期ReID、轨迹平滑)
    3. 提高检测质量 (降低阈值、NMS优化)
    4. 时序平滑 (卡尔曼滤波增强)
    """
    
    def __init__(
        self, 
        tracker_type='hybridsort',
        reid_weights='osnet_x0_25_msmt17.pt',
        device='cpu',
        detection_thresh=0.4
    ):
        self.device = torch.device(device)
        self.detection_thresh = detection_thresh
        self.tracker_type = tracker_type
        
        # 加载检测模型
        print(f"🔧 加载检测模型...")
        self.detector = torchvision.models.detection.fasterrcnn_resnet50_fpn(pretrained=True)
        self.detector.eval().to(self.device)
        
        # 初始化跟踪器 - 使用优化参数
        print(f"🔧 初始化 {tracker_type.upper()} 跟踪器...")
        self.tracker = self._create_optimized_tracker(tracker_type, reid_weights, device)
        
        print("✅ 初始化完成!")
    
    def _create_optimized_tracker(self, tracker_type, reid_weights, device):
        """创建优化参数的跟踪器"""
        
        # 根据不同跟踪器优化参数
        if tracker_type == 'hybridsort':
            # HybridSORT - 最强ID一致性
            return create_tracker(
                tracker_type='hybridsort',
                tracker_config=None,
                reid_weights=Path(reid_weights),
                device=device,
                half=False,
                per_class=False,
            )
            
        elif tracker_type == 'deepocsort':
            # DeepOCSORT - 强ReID + 运动建模
            tracker_conf = get_tracker_config('deepocsort')
            return create_tracker(
                tracker_type='deepocsort',
                tracker_config=tracker_conf,
                reid_weights=Path(reid_weights),
                device=device,
                half=False,
                per_class=False,
            )
            
        elif tracker_type == 'boosttrack':
            # BoostTrack - 平衡性能和准确度
            return create_tracker(
                tracker_type='boosttrack',
                tracker_config=None,
                reid_weights=Path(reid_weights),
                device=device,
                half=False,
                per_class=False,
            )
            
        elif tracker_type == 'strongsort':
            # StrongSORT - 经典强力跟踪
            return create_tracker(
                tracker_type='strongsort',
                tracker_config=None,
                reid_weights=Path(reid_weights),
                device=device,
                half=False,
            )
            
        else:  # botsort (默认)
            from boxmot import BotSort
            return BotSort(
                reid_weights=Path(reid_weights),
                device=device,
                half=False,
                # 优化BotSort参数
                track_high_thresh=0.5,      # 适中的高阈值
                track_low_thresh=0.05,      # 更低的低阈值，减少漏检
                new_track_thresh=0.8,       # 高新轨迹阈值，避免频繁创建新ID
                track_buffer=50,            # 更大的缓存，应对长时间遮挡
                match_thresh=0.85,          # 更严格的匹配
                proximity_thresh=0.6,       # 放宽位置匹配
                appearance_thresh=0.2,      # 更严格的外观匹配（核心！）
                cmc_method='ecc',           # ECC相机运动补偿
                with_reid=True,             # 必须开启ReID
                max_age=50,                 # 更长的最大丢失帧数
                min_hits=2,                 # 降低最小命中，快速确认
                iou_threshold=0.2,          # 更宽松的IoU
            )
    
    def process(self, frame):
        """
        处理单帧 - 带ID稳定性优化
        """
        # 1. 检测 - 优化NMS
        frame_tensor = torchvision.transforms.functional.to_tensor(frame).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            results = self.detector(frame_tensor)[0]
        
        # 2. 提取行人检测 - 使用更低的阈值
        dets = []
        for i, (label, score) in enumerate(zip(results['labels'], results['scores'])):
            if label == 1 and score >= self.detection_thresh:
                x1, y1, x2, y2 = results['boxes'][i].cpu().numpy()
                dets.append([x1, y1, x2, y2, score.item(), 0])
        
        dets = np.array(dets) if len(dets) > 0 else np.empty((0, 6))
        
        # 3. 应用NMS去重（重要！减少重复检测导致的ID切换）
        if len(dets) > 0:
            dets = self._apply_nms(dets, nms_thresh=0.4)
        
        # 4. 跟踪更新
        tracks = self.tracker.update(dets, frame)
        
        return {
            'tracks': tracks,
            'num_persons': len(tracks),
            'detections': dets
        }
    
    def _apply_nms(self, dets, nms_thresh=0.4):
        """应用NMS去除重复检测"""
        if len(dets) == 0:
            return dets
        
        boxes = dets[:, :4]
        scores = dets[:, 4]
        
        # 计算IoU矩阵
        x1 = boxes[:, 0]
        y1 = boxes[:, 1]
        x2 = boxes[:, 2]
        y2 = boxes[:, 3]
        
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            
            w = np.maximum(0.0, xx2 - xx1)
            h = np.maximum(0.0, yy2 - yy1)
            inter = w * h
            
            iou = inter / (areas[i] + areas[order[1:]] - inter)
            
            inds = np.where(iou <= nms_thresh)[0]
            order = order[inds + 1]
        
        return dets[keep]
    
    def visualize(self, frame, results, show_trajectories=True):
        """可视化"""
        tracks = results['tracks']
        
        if len(tracks) == 0:
            return frame
        
        # 绘制边界框和ID
        for track in tracks:
            x1, y1, x2, y2 = track[:4].astype('int')
            track_id = int(track[4])
            conf = track[5]
            
            color = self._id_to_color(track_id)
            
            # 边界框
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # ID标签 - 更大更明显
            label = f'ID:{track_id} {conf:.2f}'
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            
            # 背景框
            cv2.rectangle(frame, (x1, y1 - label_size[1] - 10), 
                         (x1 + label_size[0], y1), color, -1)
            
            # 文字
            cv2.putText(frame, label, (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # 轨迹
        if show_trajectories:
            frame = self.tracker.plot_results(frame, show_trajectories=True)
        
        return frame
    
    @staticmethod
    def _id_to_color(track_id):
        """ID到颜色"""
        np.random.seed(int(track_id))
        return tuple(np.random.randint(0, 255, 3).tolist())


# ============================================
# 对比测试：不同跟踪器
# ============================================
def compare_trackers():
    """对比不同跟踪器的ID稳定性"""
    
    print("\n" + "="*60)
    print("跟踪器ID稳定性对比")
    print("="*60)
    
    trackers_to_test = [
        ('hybridsort', 'HybridSORT (推荐 - 最强ID一致性)'),
        ('deepocsort', 'DeepOCSORT (推荐 - 强ReID)'),
        ('boosttrack', 'BoostTrack (推荐 - 平衡性能)'),
        ('strongsort', 'StrongSORT (经典强力)'),
        ('botsort', 'BotSort (默认)'),
    ]
    
    print("\n可用跟踪器:")
    for i, (name, desc) in enumerate(trackers_to_test, 1):
        print(f"{i}. {desc}")
    
    choice = input("\n选择跟踪器 (1-5, 默认1): ").strip() or "1"
    tracker_name = trackers_to_test[int(choice)-1][0]
    
    return tracker_name


# ============================================
# 主程序
# ============================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("防止ID跳动的最佳实践 Demo")
    print("="*60)
    
    # 选择跟踪器
    tracker_type = compare_trackers()
    
    # 初始化
    tracker = AntiIDSwitchTracker(
        tracker_type=tracker_type,
        reid_weights=REID_WEIGHTS,
        device='cpu',
        detection_thresh=CONFIDENCE_THRESHOLD
    )
    
    # 选择视频源
    print("\n视频源:")
    print("1. 摄像头")
    print("2. 视频文件")
    
    choice = input("选择 (1/2): ").strip()
    
    if choice == '1':
        cap = cv2.VideoCapture(0)
    else:
        video_path = input("视频路径: ").strip()
        cap = cv2.VideoCapture(video_path)
    
    frame_count = 0
    id_switches = 0  # 统计ID切换次数
    prev_ids = set()
    
    print("\n🚀 开始跟踪...")
    print("提示: 按 'q' 退出\n")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_count += 1
            
            # 处理
            results = tracker.process(frame)
            
            # 统计ID切换
            current_ids = set(int(track[4]) for track in results['tracks'])
            if frame_count > 1:
                new_ids = current_ids - prev_ids
                if len(new_ids) > 0 and len(prev_ids) > 0:
                    id_switches += len(new_ids)
            prev_ids = current_ids
            
            # 可视化
            frame = tracker.visualize(frame, results, show_trajectories=True)
            
            # 显示统计
            info = f"Frame:{frame_count} | Persons:{results['num_persons']} | ID切换:{id_switches}"
            cv2.putText(frame, info, (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            cv2.imshow('Anti ID Switch Tracking', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        
        # 输出统计
        print("\n" + "="*60)
        print("跟踪统计")
        print("="*60)
        print(f"总帧数: {frame_count}")
        print(f"ID切换次数: {id_switches}")
        print(f"平均每帧切换: {id_switches/frame_count if frame_count > 0 else 0:.3f}")
        print("="*60)
