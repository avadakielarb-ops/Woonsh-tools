param([Parameter(Mandatory=$true)][string]$ImagePath, [switch]$Regions)
$ErrorActionPreference = 'Stop'
if ($Regions) {
    Add-Type -AssemblyName System.Drawing
    & $PSCommandPath -ImagePath $ImagePath
    $sourceImage = [System.Drawing.Bitmap]::FromFile($ImagePath)
    try {
        foreach ($region in @(@(0.0,0.0,0.65,0.65), @(0.35,0.0,0.65,0.65), @(0.0,0.35,0.65,0.65), @(0.35,0.35,0.65,0.65))) {
            $rect = New-Object System.Drawing.Rectangle([int]($region[0]*$sourceImage.Width), [int]($region[1]*$sourceImage.Height), [int][Math]::Floor($region[2]*$sourceImage.Width), [int][Math]::Floor($region[3]*$sourceImage.Height))
            $crop = $sourceImage.Clone($rect, [System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
            $cropPath = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), 'vzhuh_ocr_' + [Guid]::NewGuid().ToString('N') + '.png')
            try {
                $crop.Save($cropPath, [System.Drawing.Imaging.ImageFormat]::Png)
                & $PSCommandPath -ImagePath $cropPath
            } finally {
                $crop.Dispose()
                if ([System.IO.File]::Exists($cropPath)) { [System.IO.File]::Delete($cropPath) }
            }
        }
    } finally { $sourceImage.Dispose() }
    return
}
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType=WindowsRuntime]
$taskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetGenericArguments().Length -eq 1 -and
    $_.GetParameters().Length -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await-Result($operation, $resultType) {
    $task = $taskMethod.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.Wait()
    return $task.Result
}
$file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await-Result ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try {
    $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $null = [Windows.Graphics.Imaging.BitmapTransform, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
    $transform = New-Object Windows.Graphics.Imaging.BitmapTransform
    $edge = [Math]::Max($decoder.PixelWidth, $decoder.PixelHeight)
    $scale = [Math]::Min(3.0, ([Windows.Media.Ocr.OcrEngine]::MaxImageDimension - 16.0) / $edge)
    $transform.ScaledWidth = [uint32][Math]::Max(1, [Math]::Floor($decoder.PixelWidth * $scale))
    $transform.ScaledHeight = [uint32][Math]::Max(1, [Math]::Floor($decoder.PixelHeight * $scale))
    $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
        [Windows.Graphics.Imaging.BitmapAlphaMode]::Ignore, $transform,
        [Windows.Graphics.Imaging.ExifOrientationMode]::RespectExifOrientation,
        [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
    try {
        $engines = @()
        $english = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | Where-Object { $_.LanguageTag -like 'en*' } | Select-Object -First 1
        if ($english) { $engines += [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($english) }
        $profileEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        if ($profileEngine -and -not ($engines | Where-Object { $_.RecognizerLanguage.LanguageTag -eq $profileEngine.RecognizerLanguage.LanguageTag })) {
            $engines += $profileEngine
        }
        if ($engines.Count -eq 0) { throw 'Windows OCR language is unavailable' }
        foreach ($engine in $engines) {
            $result = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            foreach ($line in $result.Lines) { [Console]::WriteLine($line.Text) }
            [Console]::WriteLine('')
        }
    } finally { $bitmap.Dispose() }
} finally { $stream.Dispose() }
