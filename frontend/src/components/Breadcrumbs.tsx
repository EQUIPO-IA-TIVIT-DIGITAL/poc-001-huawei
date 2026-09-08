import { Link } from '@tanstack/react-router';
import { ChevronRight, Home } from 'lucide-react';

interface BreadcrumbItem {
    label: string;
    to?: string;
}

interface BreadcrumbsProps {
    items: BreadcrumbItem[];
}

export function Breadcrumbs({ items }: BreadcrumbsProps) {
    return (
        <nav className="flex items-center gap-2 text-sm text-gray-600 mb-6">
            <Link
                to="/dashboard"
                className="flex items-center gap-1 hover:text-red-600 transition-colors"
            >
                <Home size={16} />
                <span>Inicio</span>
            </Link>

            {items.map((item, index) => (
                <div key={index} className="flex items-center gap-2">
                    <ChevronRight size={16} className="text-gray-400" />
                    {item.to ? (
                        <Link
                            to={item.to}
                            className="hover:text-red-600 transition-colors"
                        >
                            {item.label}
                        </Link>
                    ) : (
                        <span className="text-gray-900 font-medium">{item.label}</span>
                    )}
                </div>
            ))}
        </nav>
    );
}
