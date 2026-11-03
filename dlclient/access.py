import wx


class NamedAccessible(wx.Accessible):
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
