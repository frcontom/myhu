param(
    [string]$HostName = "pypi.org",
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"

if (-not $OutFile) {
    $OutFile = Join-Path $PSScriptRoot "..\backend\ca\corporate-ca-chain.crt"
}

$dir = Split-Path $OutFile -Parent
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$tcp = [System.Net.Sockets.TcpClient]::new($HostName, 443)
$ssl = [System.Net.Security.SslStream]::new($tcp.GetStream(), $false, { $true })
try {
    $ssl.AuthenticateAsClient($HostName)
    $chain = [System.Security.Cryptography.X509Certificates.X509Chain]::new()
    [void]$chain.Build($ssl.RemoteCertificate)

    $sb = [System.Text.StringBuilder]::new()
    foreach ($el in $chain.ChainElements) {
        $c = $el.Certificate
        [void]$sb.AppendLine("-----BEGIN CERTIFICATE-----")
        [void]$sb.AppendLine([Convert]::ToBase64String($c.RawData, [Base64FormattingOptions]::InsertLineBreaks))
        [void]$sb.AppendLine("-----END CERTIFICATE-----")
    }

    [System.IO.File]::WriteAllText($OutFile, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))

    $last = $chain.ChainElements[$chain.ChainElements.Count - 1].Certificate
    $isSelfSigned = $last.Subject -eq $last.Issuer
    if (-not $isSelfSigned) {
        Write-Host "Buscando la CA raiz en el store de Windows..."
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "LocalMachine")
        $store.Open("ReadOnly")
        try {
            $rootFound = $false
            foreach ($c in $store.Certificates) {
                if ($c.Subject -eq $last.Issuer -and $c.Subject -eq $c.Issuer) {
                    [void]$sb.AppendLine("-----BEGIN CERTIFICATE-----")
                    [void]$sb.AppendLine([Convert]::ToBase64String($c.RawData, [Base64FormattingOptions]::InsertLineBreaks))
                    [void]$sb.AppendLine("-----END CERTIFICATE-----")
                    $rootFound = $true
                    break
                }
            }
            if ($rootFound) {
                [System.IO.File]::WriteAllText($OutFile, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
            } else {
                Write-Host "ADVERTENCIA: no se encontro la raiz en el store 'Root'. Si la validacion sigue fallando, importala primero (certmgr.msc -> Trusted Root)."
            }
        } finally {
            $store.Dispose()
        }
    }

    $count = ([regex]::Matches($sb.ToString(), "BEGIN CERTIFICATE")).Count
    Write-Host ""
    Write-Host "Cadena generada: $count certificado(s)"
    Write-Host "Guardada en: $OutFile"
    Write-Host ""
} finally {
    $ssl.Dispose()
    $tcp.Dispose()
}