import onnxruntime as ort
import numpy as np

session = ort.InferenceSession("./yolov8n.onnx")
input_name = session.get_inputs()[0].name

dummy = np.random.rand(1, 3, 640, 640).astype(np.float32)
outputs = session.run(None, {input_name: dummy})

print([o.shape for o in outputs])
