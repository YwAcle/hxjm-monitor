import time
import cv2
import numpy as np
import os
from FastSAMTrt.trt_loader import TrtModelNMS
import torch
from PIL import Image
from FastSAMTrt.utils import overlay, segment_everything
from ultralytics.yolo.engine.results import Results
from ultralytics.yolo.utils import ops
from random import randint
# from models.models import Darknet

print(f"[Info] PyTorch version: {torch.__version__}")
print(f"[Info] CUDA available: {torch.cuda.is_available()}")


retina_masks = True
conf = 0.25
iou = 0.7
agnostic_nms = False

def postprocess(preds, img, orig_imgs, retina_masks, conf, iou, agnostic_nms=False):
    """Post-process predictions for FastSAM segmentation.
    
    Args:
        preds: [detection_output, proto_masks]
            - detection_output: (batch, 37, num_anchors) = (batch, 4+1+32, anchors)
            - proto_masks: (batch, 32, mask_h, mask_w)
        img: preprocessed input image (batch, 3, h, w)
        orig_imgs: original image(s)
        retina_masks: whether to use retina masks
        conf: confidence threshold
        iou: IoU threshold for NMS
        agnostic_nms: whether to use class-agnostic NMS
    """
    # preds[0] is detection output: (batch, 37, 8400)
    # preds[1] is proto masks: (batch, 32, 160, 160)
    detection_output = preds[0]  # (batch, 37, 8400)
    proto = preds[1]  # (batch, 32, 160, 160)
    
    # print(f"[Debug] Detection output shape: {detection_output.shape}")
    # print(f"[Debug] Proto shape: {proto.shape}")
    
    # NMS expects (batch, num_classes + 4 + num_masks, num_boxes)
    # which is (batch, 37, 8400) - no transpose needed!
    # nm = 32 (mask coefficients), nc = 1 (class)
    p = ops.non_max_suppression(detection_output,
                                conf,
                                iou,
                                agnostic_nms,
                                max_det=100,
                                nc=1)
    
    # print(f"[Debug] NMS results: {len(p)} batches, first batch has {len(p[0])} detections")
    # if len(p[0]) > 0:
        # print(f"[Debug] First detection shape: {p[0].shape}")

    results = []
    for i, pred in enumerate(p):
        orig_img = orig_imgs[i] if isinstance(orig_imgs, list) else orig_imgs
        img_path = "ok"
        if not len(pred):  # no detections
            results.append(Results(orig_img=orig_img, path=img_path, names="segment", boxes=pred[:, :6]))
            continue
        
        # pred shape after NMS: (num_detections, 6 + 32) = (num_det, 38)
        # where 6 = x1, y1, x2, y2, confidence, class
        # and 32 = mask coefficients
        # print(f"[Debug] pred shape: {pred.shape}")
        # print(f"[Debug] pred[:, 6:] shape: {pred[:, 6:].shape}")
        
        # proto[i] shape: (32, 160, 160)
        proto_i = proto[i]
        # print(f"[Debug] proto_i shape: {proto_i.shape}")
        
        if retina_masks:
            if not isinstance(orig_imgs, torch.Tensor):
                pred[:, :4] = ops.scale_boxes(img.shape[2:], pred[:, :4], orig_img.shape)
            masks = ops.process_mask_native(proto_i, pred[:, 6:], pred[:, :4], orig_img.shape[:2])  # HWC
        else:
            masks = ops.process_mask(proto_i, pred[:, 6:], pred[:, :4], img.shape[2:], upsample=True)  # HWC
            if not isinstance(orig_imgs, torch.Tensor):
                pred[:, :4] = ops.scale_boxes(img.shape[2:], pred[:, :4], orig_img.shape)
        results.append(
            Results(orig_img=orig_img, path=img_path, names="1213", boxes=pred[:, :6], masks=masks))
    return results

def pre_processing(img_origin, imgsz=1024):
    h, w = img_origin.shape[:2]
    if h>w:
        scale   = min(imgsz / h, imgsz / w)
        inp     = np.zeros((imgsz, imgsz, 3), dtype = np.uint8)
        nw      = int(w * scale)
        nh      = int(h * scale)
        a = int((nh-nw)/2) 
        inp[: nh, a:a+nw, :] = cv2.resize(cv2.cvtColor(img_origin, cv2.COLOR_BGR2RGB), (nw, nh))
    else:
        scale   = min(imgsz / h, imgsz / w)
        inp     = np.zeros((imgsz, imgsz, 3), dtype = np.uint8)
        nw      = int(w * scale)
        nh      = int(h * scale)
        a = int((nw-nh)/2) 

        inp[a: a+nh, :nw, :] = cv2.resize(cv2.cvtColor(img_origin, cv2.COLOR_BGR2RGB), (nw, nh))
    rgb = np.array([inp], dtype = np.float32) / 255.0
    return np.transpose(rgb, (0, 3, 1, 2))

class FastSam(object):
    def __init__(self, 
            model_weights = '/models/fastSAm_wrapper/fast_sam_1024.trt', 
            max_size = 1024):
        self.imgsz = (max_size, max_size)
        # Load model
        self.model = TrtModelNMS(model_weights, max_size)

    def destroy(self):
        """Release TensorRT resources."""
        if self.model is not None:
            self.model.destroy()
            self.model = None


    def segment(self, bgr_img, benchmark=False, loops=100):
        """Run segmentation inference.
        
        Args:
            bgr_img: Input BGR image (numpy array)
            benchmark: If True, run multiple loops and print timing
            loops: Number of benchmark loops
        """
        ## Padded resize
        inp = pre_processing(bgr_img, self.imgsz[0])
        
        if benchmark:
            # Warmup
            for _ in range(10):
                preds = self.model.run(inp)
            
            # Benchmark TensorRT inference only
            t1 = time.time()
            for _ in range(loops):
                preds = self.model.run(inp)
            t2 = time.time()
            print(f"[Benchmark] TensorRT inference: {(t2-t1)*1000/loops:.2f} ms/iter")
        else:
            preds = self.model.run(inp)
        
        # TensorRT outputs:
        # preds[0]: output0 (1, 37, 8400) - detection output (4 bbox + 1 conf + 32 mask coeffs)
        # preds[5]: proto masks (1, 32, 160, 160)
        
        # Convert to torch tensors
        detection_output = torch.from_numpy(preds[0])  # (1, 37, 8400)
        proto_masks = torch.from_numpy(preds[5])       # (1, 32, 160, 160)
        
        # Format for postprocess: [detection_output, proto_masks]
        formatted_preds = [detection_output, proto_masks]
        result = postprocess(formatted_preds, inp, bgr_img, retina_masks, conf, iou, agnostic_nms)
        
        if not result or result[0].masks is None:
            print("[Warning] No masks detected!")
            return None
            
        masks = result[0].masks.data  # (N, H, W)
        
        # Convert BGR numpy to PIL Image for segment_everything
        rgb_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_img)
        
        image_with_masks = segment_everything(pil_img, result, input_size=self.imgsz[0])
        
        # Ensure output directory exists
        
        # Convert PIL Image back to numpy array for saving with cv2
        if isinstance(image_with_masks, Image.Image):
            image_with_masks = cv2.cvtColor(np.array(image_with_masks), cv2.COLOR_RGBA2BGRA)
        
        cv2.imwrite(f"./tt.png", image_with_masks)
        print(f"[Info] Result saved to ./tt.png")
        return masks

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='FastSAM TensorRT Inference')
    parser.add_argument('--weights', type=str, default='./weights/fast_sam_640.trt', help='TensorRT engine path')
    parser.add_argument('--image', type=str, default='/home/guest/Documents/lkh/demo/FastSAMOnnx/FastSam_Awsome_TensorRT/images/tt.png', help='Input image path')
    parser.add_argument('--size', type=int, default=640, help='Input size (640 or 1024)')
    parser.add_argument('--benchmark', action='store_true', help='Run benchmark mode')
    parser.add_argument('--loops', type=int, default=100, help='Number of benchmark loops')
    args = parser.parse_args()
    
    print(f"\n{'='*50}")
    print(f"FastSAM TensorRT 10.0 Inference")
    print(f"{'='*50}")
    print(f"Model: {args.weights}")
    print(f"Image: {args.image}")
    print(f"Size: {args.size}")
    if args.benchmark:
        print(f"Benchmark: {args.loops} loops")
    print(f"{'='*50}\n")
    
    # Check if files exist
    if not os.path.exists(args.weights):
        print(f"[Error] Model file not found: {args.weights}")
        exit(1)
    if not os.path.exists(args.image):
        print(f"[Error] Image file not found: {args.image}")
        exit(1)
    
    model = FastSam(model_weights=args.weights, max_size=args.size)
    img = cv2.imread(args.image)
    
    if img is None:
        print(f"[Error] Failed to read image: {args.image}")
        exit(1)
        
    print(f"[Info] Image shape: {img.shape}")
    
    masks = model.segment(img, benchmark=args.benchmark, loops=args.loops)
    
    if masks is not None:
        print(f"[Output]: masks shape = {masks.shape}")
    
    # Cleanup TensorRT resources before exit
    model.destroy()
    
    print("\n[Done] Inference completed successfully!")


