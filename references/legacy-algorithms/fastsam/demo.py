import torch
from fastsam import FastSAM, FastSAMPrompt
import logging
logging.getLogger("ultralytics").setLevel(logging.ERROR)

import time

torch.cuda.reset_peak_memory_stats()


model = FastSAM('./weights/FastSAM-x.pt')
IMAGE_PATH = './tt.png'
DEVICE = 'cuda'
# ===== warm-up（非常重要）=====
for _ in range(5):
    _ = model(IMAGE_PATH, device=DEVICE, imgsz=1024)
  
# ===== 计时 =====
torch.cuda.synchronize()
t0 = time.time()

N = 1
for _ in range(N):
    everything_results = model(
        IMAGE_PATH,
        device=DEVICE,
        retina_masks=True,
        imgsz=640,
        conf=0.3,
        iou=0.9,
    )
    prompt_process = FastSAMPrompt(IMAGE_PATH, everything_results, device=DEVICE)
    ann = prompt_process.everything_prompt()

torch.cuda.synchronize()
t1 = time.time()

# ===== 单帧耗时（ms）=====
avg_ms = (t1 - t0) * 1000 / N
print(f"FastSAM avg inference time: {avg_ms:.2f} ms/frame")
allocated = torch.cuda.memory_allocated() / 1024**2
peak = torch.cuda.max_memory_allocated() / 1024**2

print(f"Allocated: {allocated:.2f} MB")
print(f"Peak:      {peak:.2f} MB")
# everything prompt

prompt_process.plot(annotations=ann,output_path='./t2.jpg',)
