$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:4567/")
$listener.Start()
Write-Host "Serving on http://localhost:4567/"
$file = Join-Path $PSScriptRoot "index.html"
while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $html = [System.IO.File]::ReadAllText($file)
    $buf = [System.Text.Encoding]::UTF8.GetBytes($html)
    $ctx.Response.ContentType = "text/html; charset=utf-8"
    $ctx.Response.ContentLength64 = $buf.Length
    $ctx.Response.OutputStream.Write($buf, 0, $buf.Length)
    $ctx.Response.OutputStream.Close()
}
