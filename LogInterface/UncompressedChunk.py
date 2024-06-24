import asyncio
import csv
import io
from mailbox import Message
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from tqdm import tqdm

from .LogInterfaceBase import IndexMap
from Primitive.PrimitiveDefinitions import UChar
from StreamUtils import StreamUtil
from Utils import MemoryMappedFile

from .Chunk import Chunk, ChunkEnum
from .DataClasses import DataClass, Stopwatch, Timer
from .Frame import FrameAccessor, FrameBase, FrameInstance, Frames
from .Message import MessageAccessor, MessageBase, MessageInstance, Messages

SutilCursor = int
AbsoluteByteIndex = int


class UncompressedChunk(Chunk):
    def __init__(self, parent):
        super().__init__(parent)
        self._threads: Dict[str, Frames] = {}
        self._timers: Dict[str, Timer] = {}

        # cached index of messages and data objects
        self._messages_cached: Messages
        self._reprs_cached: List[DataClass]

    @property
    def frames(self) -> Frames:
        return self._children  # type: ignore

    @frames.setter
    def frames(self, value: Frames):
        self._children = value

    def clearIndexFiles(self):
        messageIdxFilePath: Path = (
            self.log.cacheDir / MessageAccessor.messageIdxFileName
        )
        frameIdxFilePath: Path = self.log.cacheDir / FrameAccessor.frameIdxFileName
        if messageIdxFilePath.exists():
            messageIdxFilePath.unlink()
        if frameIdxFilePath.exists():
            frameIdxFilePath.unlink()

    def evalLarge(self, sutil: StreamUtil, offset: int = 0):

        startPos: SutilCursor = sutil.tell()
        chunkMagicBit: UChar = sutil.readUChar()
        if chunkMagicBit != ChunkEnum.UncompressedChunk.value:
            raise Exception(
                f"Expect magic number {ChunkEnum.UncompressedChunk.value}, but get:{chunkMagicBit}"
            )

        header = sutil.readQueueHeader()

        headerSize = sutil.tell() - 1 - startPos
        usedSize = int(header[0]) << 32 | int(header[2])
        logSize = os.path.getsize(self.parent.logFilePath)
        remainingSize = logSize - offset
        hasIndex = header[1] != 0x0FFFFFFF and usedSize != (logSize - offset)

        messageStartByte = offset + (sutil.tell() - startPos)
        byteIndex = 0
        frameCnt = 0
        messageCnt = 0
        self.log.cacheDir.mkdir(parents=True, exist_ok=True)

        messageIdxFilePath: Path = (
            self.log.cacheDir / MessageAccessor.messageIdxFileName
        )
        frameIdxFilePath: Path = self.log.cacheDir / FrameAccessor.frameIdxFileName

        if not UncompressedChunk.ensureIndexFilesValid(self.log):
            self.clearIndexFiles()

        messageAccessor = MessageAccessor(self.log)
        lastMessage = messageAccessor[-1]
        frameAccessor = FrameAccessor(self.log)
        lastFrame = frameAccessor[-1]
        # Since this frame accessor's parent is not fully initialized, parent related field should not be used
        frameCnt = lastFrame.absIndex + 1
        messageCnt = lastMessage.absIndex + 1
        byteIndex = lastMessage.endByte - messageStartByte
        sutil.seek(lastMessage.endByte - offset + startPos)

        messageIdxFile = open(messageIdxFilePath, "ab")
        frameIdxFile = open(frameIdxFilePath, "ab")

        while byteIndex < min(usedSize, remainingSize):
            frame = FrameInstance(self)
            try:
                frame.eval(sutil, byteIndex + messageStartByte)
            except EOFError:
                break  # TODO: check this, should not be EOFError in UncompressedChunk

            frameMessageIndexStart = messageCnt
            for message in frame.messages:
                messageIdxFile.write(
                    MessageAccessor.encodeIndexBytes(
                        (messageCnt, frameCnt, message.startByte, message.endByte)
                    )
                )

                messageCnt += 1

            frameMessageIndexEnd = messageCnt

            frameIdxFile.write(
                FrameAccessor.encodeIndexBytes(
                    (
                        frameCnt,
                        frame.threadName,
                        frameMessageIndexStart,
                        frameMessageIndexEnd,
                    )
                )
            )

            byteIndex += frame.size
            frameCnt += 1
        self.frames = self.log.getFrameAccessor()
        threadIndexMaps = {}

        for index, frame in enumerate(self.frames):
            if frame.threadName not in threadIndexMaps:
                threadIndexMaps[frame.threadName] = [index]
            else:
                threadIndexMaps[frame.threadName].append(index)
        for threadName, indexes in threadIndexMaps.items():
            self._threads[threadName] = FrameAccessor(self.log, indexes)
        # Sicne the file is large, storing data in memory isn't a good idea.
        self._startByte = offset
        self._endByte = sutil.tell() - startPos + offset

    def eval(self, sutil: StreamUtil, offset: int = 0):
        startPos = sutil.tell()
        chunkMagicBit = sutil.readUChar()
        if chunkMagicBit != ChunkEnum.UncompressedChunk.value:
            raise Exception(
                f"Expect magic number {ChunkEnum.UncompressedChunk.value}, but get:{chunkMagicBit}"
            )

        self.frames = []

        header = sutil.readQueueHeader()

        headerSize = sutil.tell() - 1 - startPos
        usedSize = int(header[0]) << 32 | int(header[2])
        logSize = os.path.getsize(self.parent.logFilePath)
        remainingSize = logSize - offset
        hasIndex = header[1] != 0x0FFFFFFF and usedSize != (logSize - offset)

        messageStartByte = offset + (sutil.tell() - startPos)
        byteIndex = 0
        frameIndex = []
        while byteIndex < min(usedSize, remainingSize):
            frame = FrameInstance(self)
            try:
                frame.eval(sutil, byteIndex + messageStartByte)
            except EOFError:
                break  # TODO: check this, should not be EOFError in UncompressedChunk
            self.frames.append(frame)

            if frame.threadName not in self._threads:
                self._threads[frame.threadName] = []
                self._timers[frame.threadName] = Timer()

            self._threads[frame.threadName].append(frame)  # type: ignore

            frameIndex.append(frame.startByte - messageStartByte)
            byteIndex += frame.size

        for threadName, threadFrames in self._threads.items():
            self._timers[threadName].initStorage(
                [frame.index for frame in threadFrames]
            )

        self._startByte = offset
        self._endByte = sutil.tell() - startPos + offset

    def parseBytes(self, showProgress: bool = True, cacheRepr: bool = True):
        Wrapper = partial(MessageBase.parseBytesWrapper, logFilePath=self.logFilePath)
        cached = []
        parsed = []
        unparsed = []

        # currently parsing everything is faster TODO: check what cause this strange phenomena

        for message in tqdm(
            self.messages, desc="Checking Message Parsed", disable=not showProgress
        ):
            if message.isParsed():
                parsed.append(message)
                continue
            elif message.hasPickledRepr():
                cached.append(message)
            else:
                unparsed.append(message)

        # failed = asyncio.get_event_loop().run_until_complete(self.loadReprs(cached))
        # unparsed.extend(failed)
        # for message in failed:
        #     print(f"Failed to parse message {message.index}")

        # unparsed = self.messages
        if len(unparsed) == 0:
            print("All messages are parsed")
            return
        with Pool(cpu_count()) as p:
            results = list(
                tqdm(
                    p.imap(
                        Wrapper,
                        [
                            (
                                message.startByte + 4,
                                message.endByte,
                                message.classType.read,
                            )
                            for message in unparsed
                        ],
                    ),
                    total=len(unparsed),
                    desc="Parsing All Messages",
                )
            )
        for idx, result in tqdm(
            enumerate(results),
            total=len(results),
            desc="Distributing All Messages",
        ):
            unparsed[idx].reprObj = result
            if isinstance(result, Stopwatch):
                # if not hasattr(self.messages[idx].frame, "timer"):
                frameTmp: FrameBase = unparsed[idx].frame
                frameTmp.timer.parseStopwatch(result, frameTmp.index)
        if cacheRepr:
            asyncio.get_event_loop().run_until_complete(
                self.dumpReprs(results, unparsed)
            )

    # Index file Validation
    @classmethod
    def ensureIndexFilesValid(
        cls,
        log,
        checkFrameRange: Optional[IndexMap] = None,
    ):
        """
        Check if the index file is valid, if not, try to fix it
        If cannot fix, return False, else return True
        """

        indexFrameFilePath = log.cacheDir / FrameAccessor.idxFileName()
        indexMessageFilePath = log.cacheDir / MessageAccessor.idxFileName()
        if not indexFrameFilePath.exists() or not indexMessageFilePath.exists():
            return False

        tempFrameIdxFile = MemoryMappedFile(indexFrameFilePath)
        tempMessageIdxFile = MemoryMappedFile(indexMessageFilePath)

        frameIndexFileSize = tempFrameIdxFile.getSize()
        messageIndexFileSize = tempMessageIdxFile.getSize()

        lastFrameIndex = frameIndexFileSize // FrameAccessor.frameIdxByteLength - 1

        frameTruncatePos = frameIndexFileSize // FrameAccessor.frameIdxByteLength
        messageTruncatePos = (
            messageIndexFileSize // MessageAccessor.messageIdxByteLength
        )

        if isinstance(checkFrameRange, range):
            checkFrameRange = list(checkFrameRange)

        if checkFrameRange is None:
            checkFrameRange = [lastFrameIndex]
        else:
            checkFrameRange += [lastFrameIndex]  # always check the last frame
        # for i in indexMap:

        i = 0
        while True:
            if i >= len(checkFrameRange):
                break
            frameIdx = checkFrameRange[i]
            if frameIdx < 0:
                return False  # Didn't find any valid frame

            if frameIdx > lastFrameIndex:
                continue  # Skip this invalid frame

            startByte = frameIdx * FrameAccessor.frameIdxByteLength
            endByte = startByte + FrameAccessor.frameIdxByteLength
            frameIndex = FrameAccessor.decodeIndexBytes(
                tempFrameIdxFile.getData()[startByte:endByte]
            )

            if (
                frameIndex[0] != frameIdx
            ):  # This is a big problem, the whole file might be wrong
                i = 0
                checkFrameRange = [frameIdx - 1]
                lastFrameIndex = frameIdx - 1
                continue
            for msgAbsIdx in range(frameIndex[2], frameIndex[3]):
                if not MessageAccessor.validate(
                    tempMessageIdxFile, msgAbsIdx, frameIndex[0]
                ):  # This is a small problem, usually caused by writing interrupted by keyboard
                    frameTruncatePos = frameIdx
                    messageTruncatePos = frameIndex[2]
                    checkFrameRange.append(frameIdx - 1)  # Check the position before it
                    lastFrameIndex = frameIdx - 1
                    break
            # Till here we make sure the last frame is valid
            if frameIndex[0] == lastFrameIndex:
                lastMessageIndex = int(frameIndex[3])

                frameTruncatePos = (
                    int(frameIndex[0] + 1)
                    if int(frameIndex[0] + 1) < frameTruncatePos
                    else frameTruncatePos
                )
                messageTruncatePos = (
                    lastMessageIndex
                    if lastMessageIndex < messageTruncatePos
                    else messageTruncatePos
                )
                # updateTruncatePos(frameIndex[0], lastMessageIndex)
            i += 1
        with open(indexFrameFilePath, "r+b") as f:
            f.truncate(frameTruncatePos * FrameAccessor.frameIdxByteLength)
        with open(indexMessageFilePath, "r+b") as f:
            f.truncate(messageTruncatePos * MessageAccessor.messageIdxByteLength)
        return True

    # Repr batch IO
    async def loadReprs(self, unparsed: Messages) -> List[DataClass]:
        loop = asyncio.get_running_loop()
        failed = []

        # Create a ThreadPoolExecutor
        with ThreadPoolExecutor() as executor:
            # Schedule the synchronous tasks in the executor
            futures = [
                loop.run_in_executor(
                    executor,
                    MessageBase.loadReprWrapper,
                    unparsed[idx].reprPicklePath,
                    idx,
                )
                for idx in tqdm(
                    range(len(unparsed)),
                    total=len(unparsed),
                    desc="Queuing All Repr to Load",
                )
            ]

            # Show progress bar for loading
            for future in tqdm(
                asyncio.as_completed(futures),
                total=len(futures),
                desc="Loading All Representations",
            ):
                result, index = await future
                if result is not None:
                    unparsed[index].reprObj = result
                failed.append(unparsed[index])

        return failed

    async def dumpReprs(self, results: List[DataClass], unparsed: Messages):
        loop = asyncio.get_running_loop()

        # Create a ThreadPoolExecutor
        with ThreadPoolExecutor() as executor:
            # Schedule the synchronous tasks in the executor
            futures = [
                loop.run_in_executor(
                    executor,
                    MessageBase.dumpReprWrapper,
                    unparsed[idx].reprPicklePath,
                    results[idx],
                )
                for idx in tqdm(
                    range(len(results)),
                    total=len(results),
                    desc="Queuing All Repr to Dump",
                )
            ]

            # Show progress bar for queuing
            for future in tqdm(
                asyncio.as_completed(futures),
                total=len(futures),
                desc="Dumping All Representations",
            ):
                await future

    def numFrames(self):
        return len(self.frames)

    def asDict(self):
        return {
            "numFrames": self.numFrames(),
            "frames": [frame.asDict() for frame in self.frames],
        }

    def writeMessageIndexCsv(self, filePath):
        with open(filePath, "w") as f:
            writer = csv.writer(f)
            for message in self.messages:
                writer.writerow(
                    [
                        message.index,
                        message.frame.index,
                        message.logId,
                        message.startByte,
                        message.endByte,
                    ]
                )

    # def readMessageIndexCsv(self, indexFilePath, logFilePath):
    #     # MessageID = self.log.MessageID
    #     self._children = []
    #     self._threads = {}
    #     self._timers = {}
    #     with open(indexFilePath, "r") as f:
    #         reader = csv.reader(f)
    #         # next(reader)
    #         frame: FrameInstance = None  # type: ignore
    #         for row in reader:
    #             if int(row[2]) == 1:  # idFrameBegin
    #                 frame = FrameInstance(self)
    #                 frame._children = []
    #                 frame.dummyMessages = []

    #             message = MessageInstance(frame)
    #             message._index_cached = int(row[0])
    #             message._logId = UChar(row[2])
    #             message._startByte = int(row[3])
    #             message._endByte = int(row[4])

    #             if len(frame.children) != message.index:
    #                 raise ValueError
    #             frame._children.append(message)  # type: ignore
    #             if int(row[2]) == 2:  # idFrameEnd
    #                 frame._index_cached = int(row[1])
    #                 if len(self.frames) != frame.index:
    #                     raise ValueError
    #                 frame._startByte = frame.messages[0].startByte
    #                 frame._endByte = frame.messages[-1].endByte

    #                 self._children.append(frame)
    #                 with open(logFilePath, "rb") as logFile:
    #                     nameStartByte = frame.messages[-1].startByte + 4 + 4
    #                     nameEndByte = frame.messages[-1].endByte
    #                     logFile.seek(nameStartByte)
    #                     threadName = logFile.read(nameEndByte - nameStartByte).decode()
    #                 if threadName not in self._threads:
    #                     self._threads[threadName] = []
    #                     self._timers[threadName] = Timer()
    #                 self._threads[threadName].append(frame)  # type: ignore

    #     for threadName, threadFrames in self._threads.items():
    #         self._timers[threadName].initStorage(
    #             [frame.index for frame in threadFrames]
    #         )
    #     if len(self.frames) == 0:
    #         raise ValueError

    #     self._startByte = self.frames[0].startByte
    #     self._endByte = self.frames[-1].endByte

    # def __getstate__(self):
    #     states=super().__getstate__()

    #     return states

    def __setstate__(self, state):
        super().__setstate__(state)
        if hasattr(self, "_threads"):
            for threadName, threadFrameAccessor in self._threads.items():
                threadFrameAccessor._parent = self
                threadFrameAccessor._log = self

    @property
    def providedAttributes(self) -> List[str]:
        return ["frames"]

    @property
    def children(self) -> Frames:
        return self.frames

    @property
    def messages(self) -> Messages:
        if hasattr(self, "_messages_cached"):
            return self._messages_cached
        self._messages_cached = []
        if self.frames.isAccessorClass:
            self._messages_cached = self.log.getMessageAccessor()
        else:
            # Danger Zone, poor performace
            raise Exception("Danger Zone, poor performace")
            for frame in self.frames:
                if frame.children.isAccessorClass:
                    for message in frame.children:
                        self._messages_cached.append(message.copy())
                else:  # Instance class
                    self._messages_cached.extend(frame.messages)  # type: ignore
        return self._messages_cached

    def thread(self, name: str) -> Frames:
        return self._threads[name]

    @property
    def threads(self) -> Dict[str, Frames]:
        return self._threads

    @property
    def threadNames(self) -> List[str]:
        return list(self._threads.keys())
