"""Spoken names and descriptions for controls, without visible labels."""

import wx


class NamedAccessible(wx.Accessible):
    """Answers a control's name and description for screen readers.

    NVDA reads the name when the control gets focus, then the description
    (with "Report object descriptions" on, which is its default). Role, value
    and everything else still come from the native control.
    """

    def __init__(self, ctrl, name, description=""):
        super().__init__(ctrl)
        self.name = name
        self.description = description
        ctrl.SetAccessible(self)

    def GetName(self, childId):
        if childId == 0:
            return (wx.ACC_OK, self.name)
        return (wx.ACC_NOT_IMPLEMENTED, "")

    def GetDescription(self, childId):
        if childId == 0 and self.description:
            return (wx.ACC_OK, self.description)
        return (wx.ACC_NOT_IMPLEMENTED, "")
