# author : 'wangzhong';
# date: 2021/2/2 16:04
import cv2
import numpy as np
from PIL import Image
from torch.utils.data import Dataset


class YoloDataset(Dataset):
    def __init__(self, train_lines, image_size, is_train):
        super(YoloDataset, self).__init__()

        self.train_lines = train_lines
        self.train_batches = len(train_lines)
        self.image_size = image_size
        self.is_train = is_train

    def __len__(self):
        return self.train_batches

    def rand(self, a=0, b=1):
        return np.random.rand() * (b - a) + a

    def get_random_data(self, annotation_line, input_shape, jitter=.3, hue=.1, sat=1.5, val=1.5, random=True):
        """实时数据增强的随机预处理"""
        # VOCdevkit/VOC2007/JPEGImages/000002.jpg 139,200,207,301,18
        line = annotation_line.split()
        image = Image.open(line[0])
        iw, ih = image.size
        h, w = input_shape
        # [139,200,207,301,18]
        box = np.array([np.array(list(map(int, box.split(',')))) for box in line[1:]])

        if not random:
            scale = min(w / iw, h / ih)
            nw = int(iw * scale)
            nh = int(ih * scale)
            dx = (w - nw) // 2
            dy = (h - nh) // 2
            # 插入灰色边界
            image = image.resize((nw, nh), Image.BICUBIC)
            new_image = Image.new('RGB', (w, h), (128, 128, 128))
            new_image.paste(image, (dx, dy))
            image_data = np.array(new_image, np.float32)

            # 调整目标框坐标
            box_data = np.zeros((len(box), 5))
            if len(box) > 0:
                np.random.shuffle(box)
                # 0和2是两个x值， 乘以缩放的倍数，再加上填充的数量
                box[:, [0, 2]] = box[:, [0, 2]] * nw / iw + dx
                # 1和3是两个y值
                box[:, [1, 3]] = box[:, [1, 3]] * nh / ih + dy
                box[:, 0:2][box[:, 0:2] < 0] = 0
                box[:, 2][box[:, 2] > w] = w
                box[:, 3][box[:, 3] > h] = h
                # 新的宽和高
                box_w = box[:, 2] - box[:, 0]
                box_h = box[:, 3] - box[:, 1]
                # 逻辑与，框的大小至少要大于1
                box = box[np.logical_and(box_w > 1, box_h > 1)]  # 保留有效框
                box_data[:len(box)] = box

            return image_data, box_data

        # 这里是train的步骤
        # 调整图片大小
        new_ar = w / h * self.rand(1 - jitter, 1 + jitter) / self.rand(1 - jitter, 1 + jitter)
        scale = self.rand(.25, 2)
        if new_ar < 1:
            nh = int(scale * h)
            nw = int(nh * new_ar)
        else:
            nw = int(scale * w)
            nh = int(nw / new_ar)
        image = image.resize((nw, nh), Image.BICUBIC)

        # 放置图片
        dx = int(self.rand(0, w - nw))
        dy = int(self.rand(0, h - nh))
        new_image = Image.new('RGB', (w, h), (128, 128, 128))
        new_image.paste(image, (dx, dy))
        image = new_image

        # 是否翻转图片
        flip = self.rand() < .5
        if flip:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)

        # 色域变换
        hue = self.rand(-hue, hue)
        sat = self.rand(1, sat) if self.rand() < .5 else 1 / self.rand(1, sat)
        val = self.rand(1, val) if self.rand() < .5 else 1 / self.rand(1, val)
        x = cv2.cvtColor(np.array(image, np.float32) / 255, cv2.COLOR_RGB2HSV)
        x[..., 0] += hue * 360
        x[..., 0][x[..., 0] > 1] -= 1
        x[..., 0][x[..., 0] < 0] += 1
        x[..., 1] *= sat
        x[..., 2] *= val
        x[x[:, :, 0] > 360, 0] = 360
        x[:, :, 1:][x[:, :, 1:] > 1] = 1
        x[x < 0] = 0
        image_data = cv2.cvtColor(x, cv2.COLOR_HSV2RGB) * 255

        # 调整目标框坐标
        box_data = np.zeros((len(box), 5))
        if len(box) > 0:
            np.random.shuffle(box)
            box[:, [0, 2]] = box[:, [0, 2]] * nw / iw + dx
            box[:, [1, 3]] = box[:, [1, 3]] * nh / ih + dy
            if flip:
                box[:, [0, 2]] = w - box[:, [2, 0]]
            box[:, 0:2][box[:, 0:2] < 0] = 0
            box[:, 2][box[:, 2] > w] = w
            box[:, 3][box[:, 3] > h] = h
            box_w = box[:, 2] - box[:, 0]
            box_h = box[:, 3] - box[:, 1]
            box = box[np.logical_and(box_w > 1, box_h > 1)]  # 保留有效框
            box_data = np.zeros((len(box), 5))
            box_data[:len(box)] = box
        # 这里存的还是左上角和右下角的坐标，只是根据图像进行了缩放
        return image_data, box_data

    def __getitem__(self, index):
        lines = self.train_lines
        n = self.train_batches
        index = index % n
        if self.is_train:
            # 传入一行数据，数据为图片的路径和gt和类别
            img, y = self.get_random_data(lines[index], self.image_size[0:2])
        else:
            img, y = self.get_random_data(lines[index], self.image_size[0:2], False)

        if len(y) != 0:
            # 从坐标转换成0~1的百分比
            boxes = np.array(y[:, :4], dtype=np.float32)
            boxes[:, 0] = boxes[:, 0] / self.image_size[1]
            boxes[:, 1] = boxes[:, 1] / self.image_size[0]
            boxes[:, 2] = boxes[:, 2] / self.image_size[1]
            boxes[:, 3] = boxes[:, 3] / self.image_size[0]

            boxes = np.maximum(np.minimum(boxes, 1), 0)
            boxes[:, 2] = boxes[:, 2] - boxes[:, 0]
            boxes[:, 3] = boxes[:, 3] - boxes[:, 1]
            # 这里将坐标值转换为了中心值和高宽的归一，2是宽，3是高
            # 这里的中心值的归一化，是相对于全图来说的，比如0.8，就是全图的0.8*416，而不是相对于左上角而言
            boxes[:, 0] = boxes[:, 0] + boxes[:, 2] / 2
            boxes[:, 1] = boxes[:, 1] + boxes[:, 3] / 2
            y = np.concatenate([boxes, y[:, -1:]], axis=-1)

        img = np.array(img, dtype=np.float32)

        tmp_inp = np.transpose(img / 255.0, (2, 0, 1))
        tmp_targets = np.array(y, dtype=np.float32)
        return tmp_inp, tmp_targets


# DataLoader中collate_fn使用
def yolo_dataset_collate(batch):
    images = []
    bboxes = []
    for img, box in batch:
        images.append(img)
        bboxes.append(box)
    images = np.array(images)
    return images, bboxes
