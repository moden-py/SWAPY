set home=%cd%
C:\Python27\Scripts\pyinstaller.exe --clean --uac-admin swapy.spec
copy dist\swapy.exe %home%\swapy32bit.exe

C:\Python27x64\Scripts\pyinstaller.exe --clean --uac-admin swapy.spec
copy dist\swapy.exe %home%\swapy64bit.exe
