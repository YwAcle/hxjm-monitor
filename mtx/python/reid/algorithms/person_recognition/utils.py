# 优化边界框，使其更适合人体比例	
def optimize_bbox(bbox):
    """优化边界框，使其更适合人体比例"""
    x1, y1, x2, y2 = bbox
    width = x2 - x1
    height = y2 - y1
    
    # 调整宽高比为1:3（典型人体比例）
    target_ratio = 1/3
    current_ratio = width / height
    
    if current_ratio > target_ratio:
        # 太宽了，增加高度
        new_height = width / target_ratio
        center_y = (y1 + y2) / 2
        y1 = max(0, int(center_y - new_height / 2))
        y2 = int(center_y + new_height / 2)
    else:
        # 太高了，增加宽度
        new_width = height * target_ratio
        center_x = (x1 + x2) / 2
        x1 = max(0, int(center_x - new_width / 2))
        x2 = int(center_x + new_width / 2)
    
    return [x1, y1, x2, y2]