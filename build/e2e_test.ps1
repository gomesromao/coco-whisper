# End to end check: hold the hotkey, play speech into the room, confirm the
# text is pasted into Notepad.
param([string]$Wav, [int]$WaitSeconds = 12)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win {
  [DllImport("user32.dll")] public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, UIntPtr dwExtraInfo);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
"@

$VK_RCONTROL = 0xA3
$VK_MENU = 0x12
$EXT = 0x1
$UP = 0x2

function Focus-Window([IntPtr]$handle) {
  # Windows only grants foreground rights to a thread that just handled input,
  # so tap ALT before asking for it.
  [Win]::keybd_event([byte]$VK_MENU, 0, 0, [UIntPtr]::Zero)
  [Win]::keybd_event([byte]$VK_MENU, 0, $UP, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 150
  [Win]::SetForegroundWindow($handle) | Out-Null
  Start-Sleep -Milliseconds 700
}

Get-Process notepad -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 800
Start-Process notepad
Start-Sleep -Seconds 3
$np = Get-Process notepad -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $np) { "notepad window not found"; exit 1 }
$handle = $np.MainWindowHandle
Focus-Window $handle
"focused notepad: $([Win]::GetForegroundWindow() -eq $handle)"

"pressing Right Ctrl"
[Win]::keybd_event([byte]$VK_RCONTROL, 0, $EXT, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 600
"playing audio"
(New-Object Media.SoundPlayer $Wav).PlaySync()
Start-Sleep -Milliseconds 500
[Win]::keybd_event([byte]$VK_RCONTROL, 0, $EXT -bor $UP, [UIntPtr]::Zero)
"released, waiting $WaitSeconds s for transcription"
Start-Sleep -Seconds $WaitSeconds

# read back what landed in Notepad
Focus-Window $handle
Set-Clipboard -Value "CLIPBOARD-SENTINEL"
$wsh = New-Object -ComObject WScript.Shell
$wsh.SendKeys("^a")
Start-Sleep -Milliseconds 400
$wsh.SendKeys("^c")
Start-Sleep -Milliseconds 800
$text = Get-Clipboard -Raw
"=== NOTEPAD CONTENT ==="
if ([string]::IsNullOrWhiteSpace($text)) { "(empty)" } else { $text }
"======================="
Stop-Process -Id $np.Id -Force -ErrorAction SilentlyContinue
