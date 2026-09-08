#!/bin/bash
# Script para limpiar todos los workspaces General duplicados
# Ejecutar desde el contenedor Docker backend

echo ""
echo "======================================================================"
echo "🧹 LIMPIEZA MASIVA DE WORKSPACES GENERAL DUPLICADOS"
echo "======================================================================"
echo ""

# Lista de usuarios con duplicados (actualizar según list_duplicate_generals.py)
USUARIOS=(
    "manuel.aliaga"
    "perf_e2e_01"
    "socio"
    "testuser01"
    "testuser"
    "usuario"
)

echo "📋 Se limpiarán duplicados para ${#USUARIOS[@]} usuarios:"
for usuario in "${USUARIOS[@]}"; do
    echo "   • $usuario"
done
echo ""

read -p "¿Continuar? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Operación cancelada"
    exit 1
fi

echo ""
echo "🚀 Iniciando limpieza..."
echo ""

total=0
exitosos=0
fallidos=0

for usuario in "${USUARIOS[@]}"; do
    echo "----------------------------------------------------------------------"
    echo "Procesando: $usuario"
    echo ""
    
    total=$((total + 1))
    
    if python scripts/cleanup_duplicate_generals.py "$usuario" --yes; then
        exitosos=$((exitosos + 1))
        echo "✅ $usuario: Completado"
    else
        fallidos=$((fallidos + 1))
        echo "❌ $usuario: Error"
    fi
    
    echo ""
done

echo "======================================================================"
echo "📊 RESUMEN FINAL"
echo "======================================================================"
echo ""
echo "   • Total usuarios procesados: $total"
echo "   • Exitosos: $exitosos"
echo "   • Fallidos: $fallidos"
echo ""
