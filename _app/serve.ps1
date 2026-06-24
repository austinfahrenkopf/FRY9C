param([string]$Root = $PSScriptRoot, [int]$Port = 8003)
Add-Type -AssemblyName System.Web

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()

# custom formulas persist to a file IN this folder -> OneDrive/SharePoint syncs it
$FormulasFile = Join-Path $Root "custom_formulas.json"

Write-Host "Serving $Root at http://localhost:$Port/"
Write-Host "Keep this window open while using the dashboard."
Start-Process "http://localhost:$Port/"   # auto-open the browser when ready

while ($listener.IsListening) {
    $context  = $listener.GetContext()
    $request  = $context.Request
    $response = $context.Response
    try {
        $path = [System.Web.HttpUtility]::UrlDecode($request.Url.AbsolutePath).TrimStart('/')

        # --- API: SAVE custom formulas (POST /api/save-formulas) ---
        if ($request.HttpMethod -eq 'POST' -and $path -eq 'api/save-formulas') {
            $reader = New-Object System.IO.StreamReader($request.InputStream, $request.ContentEncoding)
            $body = $reader.ReadToEnd(); $reader.Close()
            [System.IO.File]::WriteAllText($FormulasFile, $body)
            $response.StatusCode = 200; $response.ContentType = 'application/json'
            $b = [System.Text.Encoding]::UTF8.GetBytes('{"ok":true}')
            $response.OutputStream.Write($b, 0, $b.Length); $response.Close(); continue
        }

        # --- API: LOAD custom formulas (GET /api/formulas) ---
        if ($request.HttpMethod -eq 'GET' -and $path -eq 'api/formulas') {
            $response.ContentType = 'application/json'
            if (Test-Path $FormulasFile) { $b = [System.IO.File]::ReadAllBytes($FormulasFile) }
            else { $b = [System.Text.Encoding]::UTF8.GetBytes('[]') }
            $response.OutputStream.Write($b, 0, $b.Length); $response.Close(); continue
        }

        # --- Static file serving (with Range support for fast parquet loading) ---
        if ([string]::IsNullOrWhiteSpace($path)) { $path = "index.html" }
        $filePath = Join-Path $Root $path

        if (Test-Path $filePath -PathType Leaf) {
            $ext = [System.IO.Path]::GetExtension($filePath).ToLowerInvariant()
            $contentType = switch ($ext) {
                ".html" { "text/html; charset=utf-8" }
                ".css"  { "text/css" }
                ".js"   { "application/javascript" }
                ".json" { "application/json" }
                ".svg"  { "image/svg+xml" }
                ".png"  { "image/png" }
                ".jpg"  { "image/jpeg" }
                ".jpeg" { "image/jpeg" }
                ".gif"  { "image/gif" }
                ".ico"  { "image/x-icon" }
                ".parquet" { "application/octet-stream" }
                default { "application/octet-stream" }
            }
            $response.ContentType = $contentType
            $response.AddHeader("Accept-Ranges", "bytes")

            $bytes = [System.IO.File]::ReadAllBytes($filePath)
            $rangeHeader = $request.Headers["Range"]
            if ($rangeHeader -and $rangeHeader -match "bytes=(\d*)-(\d*)") {
                $start = if ($matches[1] -ne "") { [int64]$matches[1] } else { 0 }
                $end   = if ($matches[2] -ne "") { [int64]$matches[2] } else { $bytes.Length - 1 }
                if ($end -gt $bytes.Length - 1) { $end = $bytes.Length - 1 }
                $len = $end - $start + 1
                $response.StatusCode = 206
                $response.AddHeader("Content-Range", "bytes $start-$end/$($bytes.Length)")
                $response.ContentLength64 = $len
                $response.OutputStream.Write($bytes, [int]$start, [int]$len)
            } else {
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
        } else {
            $response.StatusCode = 404
        }
    } catch {
        $response.StatusCode = 500
    } finally {
        $response.Close()
    }
}
