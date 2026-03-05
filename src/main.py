from gui import Window, ProvisioningPage, SettinPage

if __name__ == '__main__':
    window = Window([(ProvisioningPage, 'Provisioning'), 
                     (SettinPage, 'Setting')])
    window.mainloop()
