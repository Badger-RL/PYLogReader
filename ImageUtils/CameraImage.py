import cv2
from PIL.Image import Image, fromarray

from LogInterface import DataClass
from Primitive import *
from StreamUtils import StreamUtil

from .Image import Image as ImageBase
from .PixelTypes import YUVPixel, YUYVPixel


class CameraImage(ImageBase, DataClass):
    """
    The YUYV image generated directly by robot's camera, usually used by log from SimRobot

    This class is modified from BadgerRLSystem's C++ class
    At:
    https://github.com/bhuman/BHumanCodeRelease/blob/master/Src/Representations/Infrastructure/JPEGImage.h
    """

    maxResolutionWidth = 1280
    maxResolutionHeight = 960
    readOrder = ["width", "height", "timestamp"]
    attributeCtype = {
        "width": "unsigned int",
        "height": "unsigned int",
        "timestamp": "unsigned int",
    }

    def __init__(self):
        super().__init__()
        self.timestamp: int

    def getPixel(self, x, y) -> YUYVPixel:
        xr = x % 2
        x = x - xr
        result = self.image[y][x : x + 2]
        return YUYVPixel(bytes(result.flatten()))

    def getY(self, x, y):
        return self.getPixel(x, y).y(x)

    def getU(self, x, y):
        return self.getPixel(x, y).u

    def getV(self, x, y):
        return self.getPixel(x, y).v

    def getYUV(self, x, y) -> YUVPixel:
        yuyv = self.getPixel(x, y)
        return YUVPixel((0, yuyv.u, yuyv.y(x), yuyv.v))

    def getGrayscaled(self):
        raise NotImplementedError("getGrayscale not implemented")

    @classmethod
    def read(cls, sutil: StreamUtil, end) -> "CameraImage":
        cameraImage = CameraImage()
        width = sutil.readUInt()
        height = sutil.readUInt()
        timestamp = sutil.readUInt()

        if timestamp & (1 << 31):
            height *= 2
            timestamp = UInt(np.int64(~(1 << 31)) & np.int64(timestamp))
        
        cameraImage.setResolution(width, height)
        cameraImage.timestamp = int(timestamp)

        cameraImage.image = np.frombuffer(
            sutil.read(width * height * YUYVPixel.size), dtype=np.uint8
        ).reshape((height, width * 2, 2))

        if sutil.tell() != end:
            raise ValueError("Buffer Size not used up")

        return cameraImage

    @classmethod
    def distributeReadResult(cls, result) -> "CameraImage":
        instance = cls()
        instance.width = result[0]
        instance.height = result[1]
        instance.timestamp = result[2]
        return instance

    def asDict(self):
        return {
            "width": self.width,
            "height": self.height,
            "timestamp": self.timestamp,
            "image": self.image,
        }

    def draw(self):
        cv2.imshow("Image", self.rgbImage)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    @property
    def rgbImage(self):
        if isinstance(self.image, np.ndarray):
            return cv2.cvtColor(self.image, cv2.COLOR_YUV2RGB_YUYV)
        elif isinstance(self.image, Image):
            return cv2.cvtColor(
                np.array(self.image).reshape((self.height, self.width * 2, 2)),
                cv2.COLOR_YUV2RGB_YUYV,
            )
        else:
            raise ValueError("self.image is not an valid image")

    def saveImage(self, path, metadata=None, slientFail=False):
        try:
            img = fromarray(self.rgbImage)
            img.save(
                path,
                pnginfo=metadata,
            )
        except:
            if slientFail:
                return
            else:
                raise Exception("Failed to save image")
