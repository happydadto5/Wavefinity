Option Explicit

' Start the existing best-effort Poller shim without inheriting the launcher's console.
Dim shell, files, shim
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
shim = files.BuildPath(files.GetParentFolderName(WScript.ScriptFullName), "Start_Wavefinity_Dispatch_Runner.bat")
If files.FileExists(shim) Then shell.Run Chr(34) & shim & Chr(34), 0, False
