Option Explicit

' Starts the batch bootstrapper with no command window.  Use this file for
' normal launches; keep the .bat file for diagnostics and --check.
Dim shell, files, batchFile, exitCode
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
batchFile = files.BuildPath(files.GetParentFolderName(WScript.ScriptFullName), "Launch_Organizer_UI.bat")

If Not files.FileExists(batchFile) Then
    MsgBox "Wavefinity's launcher could not be found.", vbCritical, "Wavefinity"
    WScript.Quit 1
End If

shell.CurrentDirectory = files.GetParentFolderName(batchFile)
exitCode = shell.Run(Chr(34) & batchFile & Chr(34), 0, True)
If exitCode <> 0 Then
    MsgBox "Wavefinity could not start. Run Launch_Organizer_UI.bat to see the error details.", vbCritical, "Wavefinity"
End If
