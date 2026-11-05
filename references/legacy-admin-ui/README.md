# Image Processor Model

This is a standalone image processing model that can be integrated into any system.

## Model Format
- ONNX format
- Input: RGB image (224x224)
- Output: Processed image (224x224)

## Requirements
```
onnxruntime>=1.8.0
numpy>=1.19.0
opencv-python>=4.5.0
```

## Usage Example

```python
from inference import ImageProcessorONNX
import cv2

# Initialize model
processor = ImageProcessorONNX("image_processor.onnx")

# Read image
image = cv2.imread("input.jpg")

# Process image
result = processor.process_image(image)

# Save result
cv2.imwrite("output.jpg", result)
```

## Integration Guide

1. Copy the following files to your project:
   - image_processor.onnx
   - inference.py

2. Install dependencies:
   ```bash
   pip install onnxruntime numpy opencv-python
   ```

3. Import and use the model in your code as shown in the example above.