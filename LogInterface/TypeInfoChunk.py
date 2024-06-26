import importlib
import os
import pickle
import re
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

from ImageUtils import CameraImage, JPEGImage
from LogInterface.LogInterfaceBase import LogInterfaceInstanceClass
from Primitive import *
from StreamUtils import *
from Utils import parseCtype2Pytype, sanitizeCName, type2ReadInstruction

from .Chunk import Chunk, ChunkEnum
from .DataClasses import (Annotation, DataClass, FrameBegin, FrameFinished,
                          Stopwatch)


class TypeInfoChunk(Chunk):
    def __init__(self, parent):
        super().__init__(parent)

        self.primitives: List
        self.enumDescriptions: Dict[str, List[str]]
        self.dataClassDescriptions: Dict[str, List[Tuple[str, str]]]

        self._enumClasses: Dict[str, Type[Enum]]
        self._dataClasses: Dict[str, Type[DataClass]]

    @property
    def enumClasses(self):
        return self._enumClasses

    @property
    def dataClasses(self):
        return self._dataClasses

    def registerEnums(self):
        LogEnum = importlib.import_module(".LogClasses.LogEnum", "LogInterface")
        self._enumClasses = {}
        for enumName, enumClass in self.enumDescriptions.items():
            self._enumClasses[enumName] = getattr(LogEnum, sanitizeCName(enumName))

    def dumpLogEnum(self):
        codeLines = []
        codeLines.append(
            '"""This file is generated by LogInterface/TypeInfoChunk.dumpLogEnum() to utilize multiprocessing, DO NOT EDIT!"""'
        )
        codeLines.append(f'"""Generated from log file: {self.logFilePath}"""')
        codeLines.append("from enum import Enum, auto")
        for enumName, enumClass in self.enumDescriptions.items():
            codeLines.append(f"class {sanitizeCName(enumName)}(Enum):")
            for idx, member in enumerate(enumClass):
                if idx == 0:
                    codeLines.append(f"\t{sanitizeCName(member)} = {0}")
                else:
                    codeLines.append(f"\t{sanitizeCName(member)} = auto()")
            codeLines.append(f"\tnumof{sanitizeCName(enumName)}s = auto()")

        enumString = "\n".join(codeLines)
        with open(Path(__file__).parent / "LogClasses" / "LogEnum.py", "w") as f:
            f.write(enumString)

    def dumpLogClass(self, source=Optional[str]):
        codeLines = []
        codeLines.append(
            '"""This file is generated by LogInterface/TypeInfoChunk.dumpLogClass() to utilize multiprocessing, DO NOT EDIT!"""'
        )
        codeLines.append(
            f'"""Generated from log file: {self.logFilePath if source is None else source}"""'
        )
        codeLines.append("from typing import List, Dict")
        codeLines.append("from ..DataClasses import DataClass")
        codeLines.append("from .LogEnum import *")
        codeLines.append("from Primitive import *")
        codeLines.append("from StreamUtils import *")

        selfDefinedClasses = ["Annotation", "Stopwatch", "FrameBegin", "FrameFinished"]
        for className, dataClass in self.dataClassDescriptions.items():
            if className in selfDefinedClasses:
                continue
            codeLines.append(f"class {sanitizeCName(className)}(DataClass):")
            codeLines.append(f'\t"""CXX Class Name: {className}"""')
            readOrder = [sanitizeCName(attrName) for attrName, attrCtype in dataClass]
            codeLines.append(f"\treadOrder = {readOrder}")
            attributeCtype = {
                sanitizeCName(attrName): attrCtype for attrName, attrCtype in dataClass
            }
            codeLines.append(f"\tattributeCtype = {attributeCtype}")
            init_function = [
                f"\tdef __init__(self):",
                f"\t\tsuper().__init__()",
            ] + [
                f"\t\tself.{attrName}: {parseCtype2Pytype(ctype, True)}"
                for attrName, ctype in attributeCtype.items()
            ]
            codeLines.extend(init_function)

            asDictFunction = [
                f"\tdef asDict(self):",
                f"\t\treturn {{",
            ]
            for attrName in readOrder:
                ctype, length = type2ReadInstruction(attributeCtype[attrName])
                if length == 1:
                    mainComponent = f"self.{attrName}"
                else:
                    mainComponent = f"attrValue"
                if ctype in self.primitives:
                    mainComponent += ""
                elif ctype in self.dataClassDescriptions:
                    mainComponent += ".asDict()"
                elif ctype in self.enumDescriptions:
                    mainComponent += ".name"
                if length != 1:
                    mainComponent = (
                        f"[{mainComponent} for attrValue in self.{attrName}]"
                    )
                asDictFunction.append(f'\t\t\t"{attrName}":{mainComponent},')
            asDictFunction.append(
                "\t\t}",
            )
            codeLines.extend(asDictFunction)

            readFunction = [
                "\t@classmethod",
                f'\tdef read(cls, sutil: StreamUtil, end: int = -1) -> "{sanitizeCName(className)}":',
                "\t\tinstance = cls()",
            ]
            for attrName in readOrder:
                ctype, length = type2ReadInstruction(attributeCtype[attrName])
                pytype = parseCtype2Pytype(ctype)
                if ctype in self.primitives:
                    readFunction.append(
                        f"\t\tinstance.{attrName} = sutil.readPrimitives({pytype},{length})"
                    )
                else:
                    if length != 1:
                        readFunction.append(
                            "\t\tlength = "
                            + (str(length) if length != -1 else "sutil.readUInt()")
                        )
                    if ctype in self.dataClassDescriptions:
                        mainComponent = f"{pytype}.read(sutil)"
                    elif ctype in self.enumDescriptions:
                        mainComponent = f"{pytype}(sutil.readUChar())"
                    if length != 1:
                        mainComponent = f"[{mainComponent} for _ in range(length)]"
                    readFunction.append(f"\t\tinstance.{attrName} = {mainComponent}")
            readFunction.extend(
                [
                    "\t\tif end != -1 and sutil.tell() != end:",
                    f'\t\t\traise EOFError("{className} doesn\'t consume all the bytes in the message")',
                ],
            )
            readFunction.append(
                "\t\treturn instance",
            )
            codeLines.extend(readFunction)

        classString = "\n".join(codeLines)
        with open(Path(__file__).parent / "LogClasses" / "LogClass.py", "w") as f:
            f.write(classString)

    def registerDataClasses(self):
        self._dataClasses = {}
        LogClass = importlib.import_module(".LogClasses.LogClass", "LogInterface")
        for className, dataClass in self.dataClassDescriptions.items():
            self._dataClasses[className] = getattr(LogClass, sanitizeCName(className))
        self._dataClasses["CameraImage"] = CameraImage
        self._dataClasses["JPEGImage"] = JPEGImage
        self._dataClasses["Annotation"] = Annotation
        self._dataClasses["Stopwatch"] = Stopwatch
        self._dataClasses["FrameBegin"] = FrameBegin
        self._dataClasses["FrameFinished"] = FrameFinished

    def eval(self, sutil: StreamUtil, offset: int = 0):
        startPos = sutil.tell()
        chunkMagicBit = sutil.readUChar()
        if chunkMagicBit != ChunkEnum.TypeInfoChunk.value:
            raise Exception(
                f"Expect magic number {ChunkEnum.TypeInfoChunk.value}, but get:{chunkMagicBit}"
            )

        self.primitives = []
        self.dataClassDescriptions = {}
        self.enumDescriptions = {}

        unifiedTypeNames = 0x80000000

        size = sutil.readUInt()
        needsTypenameUnification = unifiedTypeNames & size == 0
        size = UInt(np.int64(size) & ~np.int64(unifiedTypeNames))
        # print(f"Primitives num: {size}")
        for _ in range(size, 0, -1):
            type = sutil.readStr()
            type = self.demangle(type) if needsTypenameUnification else type

            self.primitives.append(type)

        size = sutil.readUInt()
        # print(f"Classes num: {size}")
        for _ in range(size, 0, -1):
            type = sutil.readStr()
            type = self.demangle(type) if needsTypenameUnification else type

            size2 = sutil.readUInt()
            self.dataClassDescriptions[type] = []
            attributes = self.dataClassDescriptions[type]
            for _ in range(size2, 0, -1):
                name = sutil.readStr()
                type2 = sutil.readStr()
                type2 = self.demangle(type2) if needsTypenameUnification else type2
                attributes.append((name, type2))
            if len(self.dataClassDescriptions[type]) != size2:
                raise Exception(
                    f"Expected {size2} attributes for class {type}, but got {len(self.dataClassDescriptions[type])}"
                )
        if len(self.dataClassDescriptions) != size:
            raise Exception(
                f"Expected {size} classes, but got {len(self.dataClassDescriptions)}"
            )

        size = sutil.readUInt()
        # print(f"Enums num: {size}")
        for _ in range(size, 0, -1):
            type = sutil.readStr()
            type = self.demangle(type) if needsTypenameUnification else type

            size2 = sutil.readUInt()
            self.enumDescriptions[type] = []
            constants = self.enumDescriptions[type]
            for _ in range(size2, 0, -1):
                name = sutil.readStr()
                constants.append(name)
            if len(self.enumDescriptions[type]) != size2:
                raise Exception(
                    f"Expected {size2} attributes for enum {type}, but got {len(self.enumDescriptions[type])}"
                )
        if len(self.enumDescriptions) != size:
            raise Exception(
                f"Expected {size} enums, but got {len(self.enumDescriptions)}"
            )
        self.dumpLogEnum()
        self.dumpLogClass()
        self.registerEnums()
        self.registerDataClasses()

        self._children = list(self.dataClasses.items())

        self._startByte = offset
        self._endByte = sutil.tell() - startPos + offset

    def demangle(self, CtypeStr: str) -> str:
        # Regular expressions
        matchAnonymousNamespace = re.compile(r"::__1\b")
        matchUnsignedLong = re.compile(r"([0-9][0-9]*)ul\b")
        matchComma = re.compile(r", ")
        matchAngularBracket = re.compile(r" >")
        matchBracket = re.compile(r" \[")
        matchAsterisk = re.compile(r" \*\(\*\)")

        # Replacements
        CtypeStr = re.sub(matchAnonymousNamespace, "", CtypeStr)
        CtypeStr = re.sub(matchUnsignedLong, r"\1", CtypeStr)
        CtypeStr = re.sub(matchComma, ",", CtypeStr)
        CtypeStr = re.sub(matchAngularBracket, ">", CtypeStr)
        CtypeStr = re.sub(matchBracket, "[", CtypeStr)
        CtypeStr = re.sub(matchAsterisk, "", CtypeStr)

        return CtypeStr

    def parseBytes(self):
        pass

    def asDict(self) -> Dict:
        return {
            "primitives": self.primitives,
            "dataClassDescriptions": self.dataClassDescriptions,
            "dataClasses": self.dataClasses,
            "enumDescriptions": self.enumDescriptions,
            "enumClasses": self.enumClasses,
        }

    @property
    def providedAttributes(self) -> List[str]:
        return [
            "primitives",
            "enumDescriptions",
            "dataClassDescriptions",
            "enumClasses",
            "dataClasses",
        ]

    # def tryDump(self):
    #     states = LogInterfaceInstanceClass.__getstate__(self)
    #     for key, value in states.items():
    #         if key in ["_parent", "_children", "_dataClasses"]:
    #             continue
    #         pickle.dump(value, open(f"{self.log.outputDir}/{key}.pickle", "wb"))
    #         print(f"Pickled {key}")

    def __getstate__(self):
        states = LogInterfaceInstanceClass.__getstate__(self)
        del states["_dataClasses"]
        del states["_parent"]
        del states["_children"]
        states["logFilePath"] = self.logFilePath
        return states

    def __setstate__(self, state: Dict) -> None:
        super().__setstate__(state)
        logFilePath = state.pop("logFilePath")
        self.dumpLogClass(source=logFilePath)
        self.registerDataClasses()
        self._children = list(self.dataClasses.items())
