import os
from typing import Any, Dict, List, Optional, Tuple

from Primitive import *
from StreamUtils import StreamUtil
from Utils import MemoryMappedFile

from ..DataClasses import Annotation, DataClass, Stopwatch
from ..LogInterfaceBase import (
    IndexMap,
    LogInterfaceAccessorClass,
    LogInterfaceInstanceClass,
)
from .MessageBase import MessageBase
from .MessageInstance import MessageInstance

Messages = Union[List[MessageInstance], "MessageAccessor"]


class MessageAccessor(MessageBase, LogInterfaceAccessorClass):
    messageIdxFileName: str = "messageIndexFile.cache"
    maxCachedReprObj: int = 200

    @staticmethod
    def decodeIndexBytes(bytes: bytes) -> Tuple[int, int, int, int]:
        if len(bytes) != MessageAccessor.messageIdxByteLength:
            raise ValueError(f"Invalid index bytes length: {len(bytes)}")
        parsedBytes = np.frombuffer(
            bytes,
            dtype=np.uint64,
        )
        return (
            int(parsedBytes[0]),
            int(parsedBytes[1]),
            int(parsedBytes[2]),
            int(parsedBytes[3]),
        )

    def __init__(self, log: Any, indexMap: Optional[IndexMap] = None):
        LogInterfaceAccessorClass.__init__(self, log, indexMap)
        # cache
        self._reprObj_cached: Dict[int, DataClass] = {}
        self._reprDict_cached: Dict[int, Dict[str, Any]] = {}

    def __getitem__(self, indexOrKey: Union[int, str]) -> Any:
        """Two mode, int index can change the Accessor's index; while str index can fetch an attribute from current message repr object"""
        if isinstance(indexOrKey, str):
            result = MessageBase.__getitem__(self, indexOrKey)
        elif isinstance(indexOrKey, int):
            result = LogInterfaceAccessorClass.__getitem__(self, indexOrKey)
        else:
            raise KeyError("Invalid key type")

        return result

    # Core Properties
    @property
    def logId(self) -> UChar:
        return UChar(int.from_bytes(self.headerBytes[0:1], "little"))

    @property
    def reprObj(self) -> DataClass:
        if not self.isParsed():
            self.parseBytes()
        return self._reprObj_cached[self.absIndex]

    @reprObj.setter
    def reprObj(self, value: DataClass):
        """Set the representation object"""
        if not isinstance(value, self.classType):
            raise ValueError("Invalid representation object")
        if isinstance(value, Annotation):
            value.frame = self.frame.threadName
        self._reprObj_cached[self.absIndex] = value
        if len(self._reprObj_cached) > self.maxCachedReprObj:
            self._reprObj_cached.pop(next(iter(self._reprObj_cached)))

    # Index file related
    @staticmethod
    def idxFileName() -> str:
        return MessageAccessor.messageIdxFileName

    @property
    def indexFileBytes(self) -> bytes:
        """The bytes of current index in messageIndexFile, which store the location of the message in the log file"""
        byteIndex = self.absIndex * self.messageIdxByteLength
        return self.getBytesFromMmap(
            self._idxFile.getData(), byteIndex, byteIndex + self.messageIdxByteLength
        )

    @property
    def messageByteIndex(self) -> Tuple[int, int, int, int]:
        """
        [messageIndex, parentFrameIndex, startByte, endByte]
        """
        return self.decodeIndexBytes(self.indexFileBytes)

    @property
    def frameIndex(self) -> int:
        return self.messageByteIndex[1]

    @property
    def startByte(self) -> int:
        return self.messageByteIndex[2]

    @property
    def endByte(self) -> int:
        return self.messageByteIndex[3]

    @classmethod
    def validate(cls, idxFile: MemoryMappedFile, absIndex: int, frameIndex: int):
        size = idxFile.getSize()
        if size == 0:
            return False
        lastIndex = size // cls.messageIdxByteLength - 1
        if absIndex > lastIndex:
            return False
        startByte = absIndex * cls.messageIdxByteLength
        endByte = startByte + cls.messageIdxByteLength
        messageIndex = cls.decodeIndexBytes(idxFile.getData()[startByte:endByte])
        if messageIndex[0] != absIndex:
            return False
        if frameIndex != messageIndex[1]:
            return False
        return True

    # # Validation
    # @classmethod
    # def ensureValid(
    #     cls,
    #     log,
    #     indexMap: Optional[IndexMap] = None,
    #     CorrectFrameIndexMap: Optional[IndexMap] = None,
    # ) -> bool:
    #     indexFilePath = log.cacheDir / cls.idxFileName()
    #     if not indexFilePath.exists():
    #         # print(f"Index file not found: {indexFilePath}")
    #         return False, 0
    #     tempIdxFile = MemoryMappedFile(indexFilePath)
    #     size = tempIdxFile.getSize()
    #     if size // cls.messageIdxByteLength == 0:
    #         # Not a single message
    #         return False, 0
    #     if size % cls.messageIdxByteLength != 0:  # The index file need to be clipped
    #         size = size - size % cls.messageIdxByteLength
    #         with open(indexFilePath, "r+b") as f:
    #             f.truncate(size)
    #         tempIdxFile.getData().resize(size)

    #     lastIndex = size // cls.messageIdxByteLength - 1
    #     # messageAccessor = cls(log)

    #     if indexMap is None:
    #         indexMap = [lastIndex]

    #     def runValidation():
    #         for i in indexMap:
    #             if i > lastIndex:
    #                 return False, lastIndex

    #             startByte = i * cls.messageIdxByteLength
    #             endByte = startByte + cls.messageIdxByteLength
    #             messageIndex = cls.decodeIndexBytes(tempIdxFile[startByte:endByte])

    #             if messageIndex[0] != i:
    #                 return False, i
    #             if CorrectFrameIndexMap is not None and i < len(CorrectFrameIndexMap):
    #                 if messageIndex[1] != CorrectFrameIndexMap[i]:
    #                     return False, i

    #         return True, -1

    #     validTill = lastIndex
    #     while True:
    #         result, breakPos = runValidation()
    #         if result:
    #             break
    #         else:
    #             if breakPos == 0:
    #                 validTill = 0
    #                 break
    #             validTill = breakPos - 1
    #             indexMap = [breakPos - 1]  # Check if the prev 1 messages are valid
    #             CorrectFrameIndexMap = None  # Don't check the frame index

    #     return True, validTill

    # Parent
    @property
    def parent(self) -> Union[LogInterfaceAccessorClass, LogInterfaceInstanceClass]:
        if not self.parentIsAssigend:  # Fake a parent
            self._parent = (
                self.log.getFrameAccessor()
            )  # instantiate a FrameAccessor without any constraints
            self._parent.absIndex = self.frameIndex

        if isinstance(self._parent, LogInterfaceAccessorClass):
            if not self.parentIsAssigend:
                self._parent.absIndex = self.frameIndex
            return self._parent
        elif isinstance(self._parent, LogInterfaceInstanceClass):  # Must be assigned
            return self._parent
        else:
            raise Exception("Invalid parent type")

    def eval(self, sutil: StreamUtil, offset: int = 0):
        raise NotImplementedError(
            "Accessor is only used to access messages already evaluated, it cannot eval"
        )

    def isParsed(self) -> bool:
        return self.absIndex in self._reprObj_cached

    def hasPickledRepr(self) -> bool:
        if os.path.isfile(self.reprPicklePath):  # type: ignore
            return True
        return False

    @property
    def reprDict(self) -> Dict[str, Any]:
        if self.absIndex not in self._reprDict_cached:
            if isinstance(self.reprObj, Stopwatch):
                # We don't want to replace our orignal Stopwatch object
                self._reprDict_cached[self.absIndex] = self.frame.timer.getStopwatch(
                    self.frameIndex
                ).asDict()
            else:
                self._reprDict_cached[self.absIndex] = self.reprObj.asDict()
        return self._reprDict_cached[self.absIndex]

    @staticmethod
    def getInstanceClass() -> Type["MessageInstance"]:
        return MessageInstance

    def getInstance(self) -> MessageInstance:
        result: MessageInstance = LogInterfaceAccessorClass.getInstance(self)  # type: ignore
        result._parent = self.parent
        result._startByte = self.startByte
        result._endByte = self.endByte
        result._logId = UChar(self.logId)
        if self.isParsed():
            result.reprObj = self.reprObj
        result._absIndex_cached = self.absIndex
        return result
