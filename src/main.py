from gui.provisioning_frame import ProvisioningFrame
from gui.setting_frame import SettingFrame
from gui.window import Window

if __name__ == '__main__':
    window = Window([(ProvisioningFrame, 'Provisioning'), 
                     (SettingFrame, 'Setting')])
    window.mainloop()
