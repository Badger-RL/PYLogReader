import os
import pickle
import types
from typing import Any, List, Union

from .LogInterfaceBase import LogInterfaceBaseClass


class LogInterfaceInstanceClass(LogInterfaceBaseClass):
    def __init__(self, parent):
        super().__init__()
        self._parent = parent

        # available after eval
        self._startByte: int
        self._endByte: int
        self._children: Union[List, "LogInterfaceBaseClass"]

        # cached references
        self._log_cached: Any  # type: ignore TODO: add a forward reference to Log
        self._index_cached: int
        self._absIndex_cached: int

    @property
    def parent(self) -> Any:
        return self._parent

    @parent.setter
    def parent(self, value: Any):
        self._parent = value

    @property
    def startByte(self) -> int:
        return self._startByte

    @property
    def endByte(self) -> int:
        return self._endByte

    @property
    def children(self) -> Union[List, LogInterfaceBaseClass]:
        return self._children

    @property
    def index(self) -> int:
        """Relative index of current object in its parent's children list"""
        if self.parent is None:
            return 0
        if not hasattr(self, "_index_cached"):
            return self.parent.indexOf(self)
        else:
            return self._index_cached

    @property
    def log(self) -> "Any":
        """Shortcut reference to root interface, result is cached to avoid repeated resolves"""
        if not hasattr(self, "_log_cached") or self._log_cached.file is None:
            ref = self.parent
            if ref is None:
                return self
            while hasattr(ref, "parent") and ref.parent is not None:
                ref = ref.parent
            self._log_cached = ref
        return self._log_cached

    # IO using pickle
    def pickleDump(self):
        print(f"Pickling {self.picklePath}")
        os.makedirs(self.picklePath.parent, exist_ok=True)
        # FrameAccessor.getInstanceClass()
        pickle.dump(self, open(self.picklePath, "wb"))
        print("finished pickling")

    def pickleLoad(self):
        self.__setstate__(pickle.load(open(self.picklePath, "rb")).__dict__)

    def __getstate__(self):
        state = {}
        for key, value in self.__dict__.items():
            if key.endswith("_cached"):
                continue
            state[key] = value
        return state

    # def __setstate__(self, state) -> None:
    #     self.__dict__.update(state)
    #     if hasattr(self, "_children"):
    #         for idx in range(len(self._children)):
    #             if isinstance(self._children[idx], LogInterfaceBaseClass):
    #                 self._children[idx]._parent = self
    def __setstate__(self, state) -> None:
        self.__dict__.update(state)

        if hasattr(self, "_children"):
            for idx in range(len(self._children)):
                child = self._children[idx]
                if isinstance(child, LogInterfaceInstanceClass):
                    child.parent = self
                elif child.isAccessorClass:
                    child._log = self
                    if child.parentIsAssigend:
                        child.parent = self
                    else:
                        child._parent = self
                    break  # For an accessor, only need to set once
                else:
                    pass

    @property
    def isInstanceClass(self) -> bool:
        return True

    @property
    def isAccessorClass(self) -> bool:
        return False
