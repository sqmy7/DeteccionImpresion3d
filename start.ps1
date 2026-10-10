# Levanta todo el stack de PrintWatch: mantiene WSL2 vivo (si no, Docker se apaga solo - ver
# docs/KNOWN_LIMITATIONS.md punto 2), sube Postgres/Redis/backend/inference-worker, y arranca
# el frontend en una ventana nueva. No levanta capture.main a proposito: necesita la camara
# conectada, asi que se arranca a mano cuando corresponda (ver mensaje final).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# Traduce la ruta de Windows a la que WSL usa para el mismo disco (/mnt/c/...), en vez de
# hardcodear un usuario/ruta especifica - este script se va a clonar en otras máquinas.
$wslPath = "/mnt/" + $root.Substring(0,1).ToLower() + $root.Substring(2).Replace('\', '/')

if (-not (Get-Process wsl -ErrorAction SilentlyContinue)) {
    Write-Host "Iniciando sesion de WSL (mantiene Docker vivo)..."
    Start-Process -FilePath "wsl.exe" -ArgumentList "--", "sleep", "infinity" -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

Write-Host "Levantando Postgres, Redis, backend e inference-worker..."
wsl bash -lc "cd '$wslPath' && docker compose --env-file .env -f infra/docker-compose.yml --profile full up -d"

Write-Host "Esperando a que el backend conteste..." -NoNewline
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $health = Invoke-RestMethod http://localhost:8000/health -TimeoutSec 3
        if ($health.status -eq "ok") { $ready = $true; break }
    } catch {}
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 2
}
Write-Host ""
if ($ready) {
    Write-Host "Backend OK (postgres/redis/inference-worker tambien deberian estar sanos)." -ForegroundColor Green
} else {
    Write-Host "El backend no respondio a tiempo - revisa con: wsl docker ps" -ForegroundColor Yellow
}

Write-Host "Iniciando el frontend en una ventana nueva..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"

Write-Host ""
Write-Host "Listo. Web en http://localhost:5173" -ForegroundColor Cyan
Write-Host "(o http://<tu-ip-de-red-local>:5173 desde el celular, si ya configuraste el portproxy - ver docs/KNOWN_LIMITATIONS.md)"
Write-Host ""
Write-Host "Falta un paso manual: la camara. Cuando la tengas conectada, en otra terminal:"
Write-Host "  capture\.venv\Scripts\python.exe -m capture.main" -ForegroundColor DarkGray
