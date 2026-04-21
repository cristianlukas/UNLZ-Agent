!macro NSIS_HOOK_POSTINSTALL
  ; Do not create desktop shortcut here.
  ; Desktop shortcut must be controlled only by the Finish-page checkbox.
  ; We only clean stale desktop links and normalize Start Menu icon.
  Delete "$DESKTOP\$(^Name).lnk"
  Delete "$DESKTOP\UNLZ Agent.lnk"
  Delete "$DESKTOP\AGENT.lnk"
  Delete "$SMSTARTUP\UNLZ Agent.lnk"

  IfFileExists "$INSTDIR\unlz-agent.exe" 0 check_spaced_name
  IfFileExists "$SMPROGRAMS\UNLZ Agent.lnk" 0 done
  IfFileExists "$INSTDIR\resources\icon.ico" 0 +2
    CreateShortCut "$SMPROGRAMS\UNLZ Agent.lnk" "$INSTDIR\unlz-agent.exe" "" "$INSTDIR\resources\icon.ico" 0
  IfFileExists "$SMPROGRAMS\UNLZ Agent.lnk" 0 +2
    Goto done
  CreateShortCut "$SMPROGRAMS\UNLZ Agent.lnk" "$INSTDIR\unlz-agent.exe" "" "$INSTDIR\unlz-agent.exe" 0
  Goto done

check_spaced_name:
  IfFileExists "$INSTDIR\UNLZ Agent.exe" 0 done
  IfFileExists "$SMPROGRAMS\UNLZ Agent.lnk" 0 done
  IfFileExists "$INSTDIR\resources\icon.ico" 0 +2
    CreateShortCut "$SMPROGRAMS\UNLZ Agent.lnk" "$INSTDIR\UNLZ Agent.exe" "" "$INSTDIR\resources\icon.ico" 0
  IfFileExists "$SMPROGRAMS\UNLZ Agent.lnk" 0 +2
    Goto done
  CreateShortCut "$SMPROGRAMS\UNLZ Agent.lnk" "$INSTDIR\UNLZ Agent.exe" "" "$INSTDIR\UNLZ Agent.exe" 0

done:
!macroend
