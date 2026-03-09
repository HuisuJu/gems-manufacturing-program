from gui import Window, ProvisioningPage, SettingPage

if __name__ == '__main__':
    window = Window([(ProvisioningPage, 'Provisioning'), 
                     (SettingPage, 'Setting')])
    window.mainloop()
