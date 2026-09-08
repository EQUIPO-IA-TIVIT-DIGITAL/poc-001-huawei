# Script PowerShell para limpiar todos los workspaces General duplicados
# Ejecutar desde la carpeta raíz del proyecto

Write-Host ""
Write-Host "======================================================================"
Write-Host "🧹 LIMPIEZA MASIVA DE WORKSPACES GENERAL DUPLICADOS"
Write-Host "======================================================================"
Write-Host ""

# Lista de usuarios con duplicados
$usuarios = @(
    "manuel.aliaga",
    "perf_e2e_01",
    "socio",
    "testuser01",
    "testuser",
    "usuario"
)

Write-Host "📋 Se limpiarán duplicados para $($usuarios.Count) usuarios:"
foreach ($usuario in $usuarios) {
    Write-Host "   • $usuario"
}
Write-Host ""

$respuesta = Read-Host "¿Continuar? (s/n)"
if ($respuesta -ne "s" -and $respuesta -ne "S") {
    Write-Host "❌ Operación cancelada"
    exit 1
}

Write-Host ""
Write-Host "🚀 Iniciando limpieza..."
Write-Host ""

$total = 0
$exitosos = 0
$fallidos = 0

foreach ($usuario in $usuarios) {
    Write-Host "----------------------------------------------------------------------"
    Write-Host "Procesando: $usuario"
    Write-Host ""
    
    $total++
    
    try {
        docker exec tivit-vision-backend python scripts/cleanup_duplicate_generals.py $usuario --yes
        
        if ($LASTEXITCODE -eq 0) {
            $exitosos++
            Write-Host "✅ $usuario`: Completado" -ForegroundColor Green
        } else {
            $fallidos++
            Write-Host "❌ $usuario`: Error" -ForegroundColor Red
        }
    } catch {
        $fallidos++
        Write-Host "❌ $usuario`: Error - $_" -ForegroundColor Red
    }
    
    Write-Host ""
}

Write-Host "======================================================================"
Write-Host "📊 RESUMEN FINAL"
Write-Host "======================================================================"
Write-Host ""
Write-Host "   • Total usuarios procesados: $total"
Write-Host "   • Exitosos: $exitosos"
Write-Host "   • Fallidos: $fallidos"
Write-Host ""
