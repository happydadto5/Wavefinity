$projectPath = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$destinationPath = Join-Path $projectPath 'wave.zip'
$allowedExtensions = @(
    '.py', '.js', '.html', '.css', '.md', '.txt', '.json', '.bat', '.ps1',
    '.vbs', '.yml', '.yaml'
)
$allowedNames = @('Dockerfile', 'requirements.txt', 'LICENSE')
$excludedDirectories = @('.git', '.venv', '__pycache__', 'generated', 'archive', 'test results')

$files = Get-ChildItem -LiteralPath $projectPath -Recurse -File | Where-Object {
    $relative = $_.FullName.Substring($projectPath.Length).TrimStart('\')
    $segments = $relative -split '\\'
    -not ($segments | Where-Object { $_ -in $excludedDirectories }) -and
    $_.FullName -ne $destinationPath -and
    ($_.Extension -in $allowedExtensions -or $_.Name -in $allowedNames)
}
if (-not $files) {
    throw 'No code or readme files found.'
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
Remove-Item -LiteralPath $destinationPath -Force -ErrorAction SilentlyContinue
$archive = [System.IO.Compression.ZipFile]::Open(
    $destinationPath,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    foreach ($file in $files) {
        $entryName = $file.FullName.Substring($projectPath.Length).TrimStart('\').Replace('\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $file.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $archive.Dispose()
}

Write-Host "Created `"$destinationPath`" with $($files.Count) files."
