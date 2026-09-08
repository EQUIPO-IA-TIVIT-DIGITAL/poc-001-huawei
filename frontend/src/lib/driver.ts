import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';

export function startDashboardTour(): void {
    const d = driver({
        showProgress: true,
        animate: true,
        overlayColor: 'rgba(0,0,0,0.7)',
        steps: [
            { element: 'a[href="/dashboard"]', popover: { title: 'Dashboard', description: 'Vista general de métricas y actividad.' } },
            { element: 'a[href="/proyectos"]', popover: { title: 'Proyectos', description: 'Organiza tus videos en workspaces.' } },
            { element: 'a[href="/mis-videos"]', popover: { title: 'Mis Videos', description: 'Biblioteca personal de videos procesados.' } },
            { element: 'a[href="/operational"]', popover: { title: 'Análisis Operativo', description: 'Procesos operativos con heatmaps y comparativas.' } },
            { element: 'a[href="/audio"]', popover: { title: 'Análisis de Audio', description: 'Transcripción, resumen y Q&A semántico.' } },
        ],
    });
    d.drive();
}
