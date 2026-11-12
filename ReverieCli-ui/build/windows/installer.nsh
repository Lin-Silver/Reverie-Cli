!macro customInstall
  !ifndef BUILD_UNINSTALLER
    Call wstyleFinishUpgrade
    ${if} $wstyleRestoreFailed == "1"
      SetErrorLevel 2
      Abort "User data could not be restored; the backup path is shown in the installer log."
    ${endif}
  !endif
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\reverie-path.ps1" -InstallDir "$INSTDIR"'
!macroend

# Older uninstallers move each resource file through a long temporary path.
# Stage packaged directories and user data on the same volume before they run.
!macro wstyleStashData SOURCE BACKUP DIRECTORY
  ${if} ${SOURCE} != ""
  ${andIf} ${FileExists} "${SOURCE}\${DIRECTORY}\*.*"
    ClearErrors
    ${if} ${BACKUP} == ""
      ${GetParent} "${SOURCE}" $wstyleParent
      GetTempFileName $wstyleCandidate "$wstyleParent"
      IfErrors wstyle_backup_failed
      Delete "$wstyleCandidate"
      CreateDirectory "$wstyleCandidate"
      IfErrors wstyle_backup_failed
      StrCpy ${BACKUP} $wstyleCandidate
      StrCpy $wstyleCandidate ""
    ${endif}
    Rename "${SOURCE}\${DIRECTORY}" "${BACKUP}\${DIRECTORY}"
    IfErrors wstyle_backup_failed
  ${endif}
!macroend

# The stock failure handler uses Quit, which skips callbacks in silent mode.
!macro customUnInstallCheck
  ${if} ${Errors}
  ${orIf} $R0 != 0
    Call wstyleRestoreUserData
    SetErrorLevel 2
    Abort "The previous version could not be removed. User data was preserved; check the installer log before retrying."
  ${endif}
!macroend

!macro customUnInstallCheckCurrentUser
  !insertmacro customUnInstallCheck
!macroend

!macro customCheckAppRunning
  !insertmacro IS_POWERSHELL_AVAILABLE
  !insertmacro _CHECK_APP_RUNNING
  !ifndef BUILD_UNINSTALLER
    Call wstylePreserveUserData
  !endif
!macroend

!macro wstyleRestoreData SOURCE BACKUP DIRECTORY
  ${if} ${BACKUP} != ""
  ${andIf} ${FileExists} "${BACKUP}\${DIRECTORY}\*.*"
    ClearErrors
    CreateDirectory "${SOURCE}"
    Rename "${BACKUP}\${DIRECTORY}" "${SOURCE}\${DIRECTORY}"
    ${if} ${Errors}
      StrCpy $wstyleRestoreFailed "1"
      DetailPrint "Backup remains in ${BACKUP}\${DIRECTORY}; destination ${SOURCE} was not overwritten."
      MessageBox MB_OK|MB_ICONSTOP "Could not restore ${DIRECTORY}. A backup remains in ${BACKUP}\${DIRECTORY}. Close Reverie and restore it before starting the application." /SD IDOK
    ${endif}
  ${endif}
!macroend

!macro customHeader
  !include "getProcessInfo.nsh"
  Var pid
  !ifndef BUILD_UNINSTALLER
    Var wstyleSource1
    Var wstyleSource2
    Var wstyleBackup1
    Var wstyleBackup2
    Var wstyleCandidate
    Var wstyleParent
    Var wstyleRestoreFailed

    Function wstyleRestoreUserData
      StrCpy $wstyleRestoreFailed "0"
      !insertmacro wstyleRestoreData $wstyleSource1 $wstyleBackup1 .reverie
      !insertmacro wstyleRestoreData $wstyleSource2 $wstyleBackup2 .reverie
      !insertmacro wstyleRestoreData $wstyleSource1 $wstyleBackup1 reverie-runtime
      !insertmacro wstyleRestoreData $wstyleSource2 $wstyleBackup2 reverie-runtime
      !insertmacro wstyleRestoreData $wstyleSource1 $wstyleBackup1 resources
      !insertmacro wstyleRestoreData $wstyleSource2 $wstyleBackup2 resources
      !insertmacro wstyleRestoreData $wstyleSource1 $wstyleBackup1 locales
      !insertmacro wstyleRestoreData $wstyleSource2 $wstyleBackup2 locales
      ${if} $wstyleRestoreFailed != "1"
        RMDir "$wstyleBackup1"
        RMDir "$wstyleBackup2"
        StrCpy $wstyleBackup1 ""
        StrCpy $wstyleBackup2 ""
      ${endif}
    FunctionEnd

    Function wstyleFinishUpgrade
      StrCpy $wstyleRestoreFailed "0"
      !insertmacro wstyleRestoreData $wstyleSource1 $wstyleBackup1 .reverie
      !insertmacro wstyleRestoreData $wstyleSource2 $wstyleBackup2 .reverie
      ${if} $wstyleRestoreFailed != "1"
        ${if} $wstyleBackup1 != ""
          RMDir /r "\\?\$wstyleBackup1"
        ${endif}
        ${if} $wstyleBackup2 != ""
          RMDir /r "\\?\$wstyleBackup2"
        ${endif}
        StrCpy $wstyleBackup1 ""
        StrCpy $wstyleBackup2 ""
      ${endif}
    FunctionEnd

    Function .onInstFailed
      Call wstyleRestoreUserData
    FunctionEnd

    Function .onGUIEnd
      Call wstyleRestoreUserData
      ${if} $wstyleRestoreFailed == "1"
        SetErrorLevel 2
      ${endif}
    FunctionEnd

    Function wstylePreserveUserData
      SetOutPath $TEMP
      ${if} $installMode == "all"
        StrCpy $wstyleSource1 $perMachineInstallationFolder
        StrCpy $wstyleSource2 $perUserInstallationFolder
      ${else}
        StrCpy $wstyleSource1 $perUserInstallationFolder
      ${endif}
      !insertmacro wstyleStashData $wstyleSource1 $wstyleBackup1 .reverie
      !insertmacro wstyleStashData $wstyleSource1 $wstyleBackup1 reverie-runtime
      !insertmacro wstyleStashData $wstyleSource1 $wstyleBackup1 resources
      !insertmacro wstyleStashData $wstyleSource1 $wstyleBackup1 locales
      ${if} $wstyleSource2 != $wstyleSource1
        !insertmacro wstyleStashData $wstyleSource2 $wstyleBackup2 .reverie
        !insertmacro wstyleStashData $wstyleSource2 $wstyleBackup2 reverie-runtime
        !insertmacro wstyleStashData $wstyleSource2 $wstyleBackup2 resources
        !insertmacro wstyleStashData $wstyleSource2 $wstyleBackup2 locales
      ${endif}
      Goto wstyle_backup_done
      wstyle_backup_failed:
        ${if} $wstyleCandidate != ""
          RMDir "$wstyleCandidate"
        ${endif}
        Call wstyleRestoreUserData
        SetErrorLevel 2
        Abort "Could not preserve user data before upgrading. Close Reverie and retry."
      wstyle_backup_done:
    FunctionEnd
  !endif
!macroend

!macro customUnInstall
  nsExec::ExecToLog 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\reverie-path.ps1" -InstallDir "$INSTDIR" -Remove'
!macroend

# User Cards and config live at the executable root. Keep that data on both
# upgrade and uninstall. Stage whole directories on the same volume so long
# resource paths are never renamed individually and failed removal can roll back.
!macro customRemoveFiles
  SetOutPath $TEMP
  ClearErrors
  GetTempFileName $R3 "$INSTDIR"
  IfErrors wstyle_cleanup_prepare_failed
  Delete "$R3"
  CreateDirectory "$R3"
  IfErrors wstyle_cleanup_prepare_failed
  FindFirst $R1 $R2 "$INSTDIR\*.*"
  wstyle_cleanup_loop:
    StrCmp $R2 "" wstyle_cleanup_done
    StrCmp $R2 "." wstyle_cleanup_next
    StrCmp $R2 ".." wstyle_cleanup_next
    StrCmp $R2 ".reverie" wstyle_cleanup_next
    StrCmp $R2 "${UNINSTALL_FILENAME}" wstyle_cleanup_next
    StrCmp "$INSTDIR\$R2" "$R3" wstyle_cleanup_next
    ClearErrors
    Rename "$INSTDIR\$R2" "$R3\$R2"
    IfErrors wstyle_cleanup_failed
  wstyle_cleanup_next:
    FindNext $R1 $R2
    Goto wstyle_cleanup_loop
  wstyle_cleanup_failed:
    StrCpy $R5 "$INSTDIR\$R2"
    FindClose $R1
    FindFirst $R1 $R2 "$R3\*.*"
  wstyle_rollback_loop:
    StrCmp $R2 "" wstyle_rollback_done
    StrCmp $R2 "." wstyle_rollback_next
    StrCmp $R2 ".." wstyle_rollback_next
    ClearErrors
    Rename "$R3\$R2" "$INSTDIR\$R2"
    IfErrors wstyle_rollback_failed
  wstyle_rollback_next:
    FindNext $R1 $R2
    Goto wstyle_rollback_loop
  wstyle_rollback_done:
    FindClose $R1
    RMDir "$R3"
    !insertmacro customInstall
    Abort "Could not remove $R5. Close applications and retry. User Cards and configuration were preserved."
  wstyle_rollback_failed:
    FindClose $R1
    Abort "Could not restore application files. A backup remains in $R3. User Cards and configuration were preserved."
  wstyle_cleanup_prepare_failed:
    !insertmacro customInstall
    Abort "Could not prepare application cleanup. User Cards and configuration were preserved."
  wstyle_cleanup_done:
    FindClose $R1
    RMDir /r "\\?\$R3"
    Delete "$INSTDIR\${UNINSTALL_FILENAME}"
    RMDir "$INSTDIR"
!macroend
