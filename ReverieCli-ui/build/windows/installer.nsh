!macro customInstall
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\reverie-path.ps1" -InstallDir "$INSTDIR"'
!macroend

!macro customUnInstall
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\reverie-path.ps1" -InstallDir "$INSTDIR" -Remove'
!macroend
