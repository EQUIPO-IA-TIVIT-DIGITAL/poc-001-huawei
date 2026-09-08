import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from './ui/dialog';
import { Button } from './ui/button';
import { AlertTriangle, Trash2, XCircle } from 'lucide-react';

interface ConfirmDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onConfirm: () => void;
    title: string;
    description: string;
    confirmText?: string;
    cancelText?: string;
    variant?: 'danger' | 'warning';
    loading?: boolean;
}

export function ConfirmDialog({
    open,
    onOpenChange,
    onConfirm,
    title,
    description,
    confirmText = 'Confirmar',
    cancelText = 'Cancelar',
    variant = 'danger',
    loading = false
}: ConfirmDialogProps) {
    const Icon = variant === 'danger' ? Trash2 : AlertTriangle;
    const iconColor = variant === 'danger' ? 'text-red-600' : 'text-orange-600';
    const buttonColor = variant === 'danger' ? 'bg-red-600 hover:bg-red-700' : 'bg-orange-600 hover:bg-orange-700';

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-md bg-white border-2 border-gray-900 shadow-2xl">
                <DialogHeader>
                    <div className="flex items-center gap-3 mb-2">
                        <div className={`p-3 rounded-full bg-gray-900`}>
                            <Icon className={`${iconColor}`} size={24} />
                        </div>
                        <DialogTitle className="text-xl font-bold text-gray-900">
                            {title}
                        </DialogTitle>
                    </div>
                    <DialogDescription className="text-gray-700 text-base leading-relaxed pt-2">
                        {description}
                    </DialogDescription>
                </DialogHeader>

                <div className="bg-red-50 border-l-4 border-red-600 p-4 my-4">
                    <div className="flex items-start gap-2">
                        <XCircle className="text-red-600 mt-0.5" size={20} />
                        <div className="text-sm text-red-800">
                            <p className="font-semibold mb-1">⚠️ Acción irreversible</p>
                            <p>Esta acción no se puede deshacer. Los datos serán eliminados permanentemente.</p>
                        </div>
                    </div>
                </div>

                <DialogFooter className="gap-2 sm:gap-2">
                    <Button
                        variant="outline"
                        onClick={() => onOpenChange(false)}
                        disabled={loading}
                        className="flex-1 border-2 border-gray-300 hover:bg-gray-100"
                    >
                        {cancelText}
                    </Button>
                    <Button
                        onClick={onConfirm}
                        disabled={loading}
                        className={`flex-1 ${buttonColor} text-white font-semibold shadow-lg hover:shadow-xl transition-all`}
                    >
                        {loading ? (
                            <>
                                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent mr-2"></div>
                                Eliminando...
                            </>
                        ) : (
                            <>
                                <Trash2 size={16} className="mr-2" />
                                {confirmText}
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
