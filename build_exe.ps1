param(
  [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if ($InstallDeps) {
  python -m pip install -e ".[screen,ocr]"
  python -m pip install pyinstaller
}

$args = @(
  "--noconfirm",
  "--clean",
  "--onefile",
  "--windowed",
  "--name", "ScreenAutoSolver",
  "--collect-all", "rapidocr_onnxruntime",
  "--collect-all", "onnxruntime",
  "--collect-all", "mss",
  "--collect-all", "pyautogui",
  "--hidden-import=mss",
  "--hidden-import=pyautogui",
  "--hidden-import=cv2",
  "--hidden-import=yaml",
  "--hidden-import=httpx",
  "--hidden-import=PIL.Image",
  "--hidden-import=PIL.ImageChops",
  "--hidden-import=PIL.ImageStat",
  "--hidden-import=PIL.ImageGrab",
  "--add-data", "config.example.yaml;.",
  "auto_solver\gui_entry.py"
)

python -m PyInstaller @args

Write-Host ""
Write-Host "Built executable:"
Write-Host (Join-Path $PSScriptRoot "dist\ScreenAutoSolver.exe")
