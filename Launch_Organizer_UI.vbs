Option Explicit

' Story 2647: stable Wavefinity entry point (windowless).
' activate_wavefinity_launcher.ps1 installs this file as
' %LOCALAPPDATA%\Wavefinity\Launcher\Launch_Organizer_UI.vbs and points the
' Wavefinity shortcut at it. It runs the installed current launcher version
' hidden, then shows the outcome the launcher reported: READY (brief),
' RUNNING UNVERIFIED (stays until dismissed) or STOPPED with the action to take.
' A copy run from a Wavefinity checkout is only a shim for the installed
' launcher; it never starts anything from the checkout.
Dim shell, files, own, launcherRoot, batchFile, versionId, pattern
Dim statusFile, exitCode, reply, lines, state, message, index

Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
own = files.GetParentFolderName(WScript.ScriptFullName)
launcherRoot = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Wavefinity\Launcher"
batchFile = ""

If files.FileExists(files.BuildPath(own, "launcher.json")) Then
    batchFile = files.BuildPath(own, "Launch_Organizer_UI.bat")
ElseIf files.FileExists(launcherRoot & "\current.txt") Then
    With files.OpenTextFile(launcherRoot & "\current.txt", 1, False)
        If Not .AtEndOfStream Then versionId = Trim(.ReadLine())
        .Close
    End With
    Set pattern = New RegExp
    pattern.Pattern = "^[0-9A-Za-z][0-9A-Za-z._-]*$"
    If pattern.Test(versionId) Then
        If files.FileExists(launcherRoot & "\versions\" & versionId & "\launcher.json") Then
            batchFile = launcherRoot & "\versions\" & versionId & "\Launch_Organizer_UI.bat"
        End If
    End If
End If

If batchFile = "" Or Not files.FileExists(batchFile) Then
    MsgBox "STOPPED - Wavefinity's stable launcher is not installed, so nothing was started." & vbCrLf & vbCrLf & _
        "Action: run activate_wavefinity_launcher.ps1 from the approved Wavefinity checkout to install it.", _
        vbCritical, "Wavefinity"
    WScript.Quit 2
End If

If Not files.FolderExists(launcherRoot & "\status") Then files.CreateFolder launcherRoot & "\status"
Randomize
statusFile = launcherRoot & "\status\launch-" & Int(Timer * 1000) & "-" & Int(Rnd * 1000000) & ".txt"
shell.Environment("Process")("WAVEFINITY_STATUS_FILE") = statusFile

shell.CurrentDirectory = files.GetParentFolderName(batchFile)
exitCode = shell.Run(Chr(34) & batchFile & Chr(34), 0, True)

state = ""
message = ""
If files.FileExists(statusFile) Then
    With files.OpenTextFile(statusFile, 1, False)
        If Not .AtEndOfStream Then
            lines = Split(Replace(.ReadAll, vbCr, ""), vbLf)
            state = Trim(lines(0))
            For index = 1 To UBound(lines)
                If Len(Trim(lines(index))) > 0 Then message = message & lines(index) & vbCrLf
            Next
        End If
        .Close
    End With
    On Error Resume Next
    files.DeleteFile statusFile
    On Error GoTo 0
End If

If state = "READY" Then
    shell.Popup Trim(message), 6, "Wavefinity", 64
ElseIf state = "OFFLINE_UNVERIFIED" Then
    shell.Popup Trim(message), 0, "Wavefinity - running unverified", 48
ElseIf state = "STOPPED" Or exitCode <> 0 Then
    If Len(message) = 0 Then message = "STOPPED - Wavefinity stopped before it could report why." & vbCrLf & "Action: run Launch_Organizer_UI.bat from the installed launcher folder to see the details."
    MsgBox Trim(message), vbCritical, "Wavefinity"
    If exitCode = 0 Then exitCode = 2
    WScript.Quit exitCode
End If
