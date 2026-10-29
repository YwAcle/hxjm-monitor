import torch
import torchvision.transforms as transforms
import numpy as np
import cv2
import logging

from .model import Net


class Extractor(object):
    def __init__(self, model_path, use_cuda=True):
        self.net = Net(reid=True)
        self.device = "cuda" if torch.cuda.is_available() and use_cuda else "cpu"
        state_dict = torch.load(model_path, map_location=lambda storage, loc: storage)['net_dict']
        self.net.load_state_dict(state_dict)
        logger = logging.getLogger("root.tracker")
        logger.info("Loading weights from {}... Done!".format(model_path))
        self.net.to(self.device)
        self.size = (64, 128)
        self.norm = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

    def _preprocess(self, im_crops):
        """
        TODO:
            1. to float with scale from 0 to 1
            2. resize to (64, 128) as Market1501 dataset did
            3. concatenate to a numpy array
            3. to torch Tensor
            4. normalize
        """

        # def _resize(im, size):
        #     return cv2.resize(im.astype(np.float32) / 255., size)

        def _resize(im, size):
            """
            调整图像尺寸。

            Args:
                im (torch.Tensor or numpy.ndarray): 输入图像，可以是Tensor或NumPy数组。
                                                   - 如果是Tensor，需为NCHW格式 (batch, channels, height, width)。
                                                   - 如果是NumPy数组，需为HWC格式 (height, width, channels)。
                size (tuple): 目标尺寸，格式为 (width, height)。

            Returns:
                numpy.ndarray: 调整尺寸后的图像，HWC格式，值已归一化到 [0.0, 1.0]。
            """
            # 1. 如果输入是Tensor，先转换为NumPy数组并调整维度
            if isinstance(im, torch.Tensor):
                # 确保Tensor在CPU上
                im_np = im.cpu().numpy()

                # 如果是NCHW格式 (如 (1, 3, 256, 128))，需要转换为HWC格式
                if im_np.ndim == 4 and im_np.shape[0] == 1:
                    im_np = im_np.squeeze(0)  # 移除batch维度，变为 (3, 256, 128)
                if im_np.ndim == 3 and im_np.shape[0] in [1, 3]:  # 检查是否为CHW格式
                    im_np = np.transpose(im_np, (1, 2, 0))  # 转换为HWC格式 (256, 128, 3)

                im = im_np

            # 2. 检查输入图像格式是否正确
            if not isinstance(im, np.ndarray) or im.ndim != 3:
                raise ValueError(
                    f"输入图像格式不正确，期望是3维NumPy数组(HWC)或4维Tensor(NCHW)，但得到了 {type(im)} 且维度为 {im.ndim}")

            # 3. 归一化到 [0.0, 1.0]
            # 假设输入图像的像素值范围是 [0, 255]
            if im.dtype == np.uint8:
                im_normalized = im.astype(np.float32) / 255.0
            else:
                # 如果已经是float类型，假设已经归一化或在合理范围内
                im_normalized = im.astype(np.float32)

            # 4. 调用cv2.resize进行缩放
            # 注意：cv2.resize的dsize参数是 (width, height)
            resized_im = cv2.resize(im_normalized, size)

            return resized_im

        im_batch = torch.cat([self.norm(_resize(im, self.size)).unsqueeze(0) for im in im_crops], dim=0).float()
        return im_batch

    def __call__(self, im_crops):
        im_batch = self._preprocess(im_crops)
        with torch.no_grad():
            im_batch = im_batch.to(self.device)
            features = self.net(im_batch)
        return features.cpu().numpy()


if __name__ == '__main__':
    img = cv2.imread("demo.jpg")[:, :, (2, 1, 0)]
    extr = Extractor("checkpoint/ckpt.t7")
    feature = extr(img)
    print(feature.shape)

