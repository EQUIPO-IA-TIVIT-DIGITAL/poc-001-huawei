import { useState } from 'react';
import { MessageCircle, CheckCircle } from 'lucide-react';
import { WorkspaceChatModal } from './WorkspaceChatModal';

interface WorkspaceChatButtonProps {
    workspaceId: string;
    workspaceName?: string; // Optional now to match usage
    variant?: 'primary' | 'secondary' | 'outline';
    onContextImproved?: () => void;
    className?: string;
    isContextualized?: boolean;
}

export function WorkspaceChatButton({ workspaceId, workspaceName = '', variant = 'secondary', onContextImproved, className = '', isContextualized = false }: WorkspaceChatButtonProps) {
    const [chatOpen, setChatOpen] = useState(false);

    let baseClasses = "px-3 py-2 rounded-lg font-medium transition-all flex items-center justify-center gap-2";
    let variantClasses = "";

    switch (variant) {
        case 'primary':
            variantClasses = "bg-gray-900 hover:bg-gray-700 text-white shadow-lg";
            break;
        case 'secondary':
            variantClasses = "border border-gray-300 text-gray-700 hover:bg-gray-50 hover:border-gray-400";
            break;
        case 'outline':
            variantClasses = "border border-gray-200 text-gray-700 hover:bg-gray-50";
            break;
        default:
            variantClasses = "bg-gray-900 text-white hover:bg-gray-700";
    }

    return (
        <>
            <button
                onClick={(e) => {
                    e.stopPropagation();
                    setChatOpen(true);
                }}
                className={`${baseClasses} ${variantClasses} ${className} ${isContextualized ? 'bg-green-50 text-green-700 hover:bg-green-100 border-green-200' : ''}`}
                title={isContextualized ? "Contexto IA Optimizado" : "Validar contexto con IA"}
            >
                {isContextualized ? <CheckCircle size={14} className="text-green-600" /> : <MessageCircle size={14} />}
                <span className="hidden sm:inline">{isContextualized ? "IA Optimizada" : "Validar IA"}</span>
            </button>

            <WorkspaceChatModal
                open={chatOpen}
                onClose={() => setChatOpen(false)}
                workspaceId={workspaceId}
                workspaceName={workspaceName}
                onContextImproved={() => {
                    onContextImproved?.();
                    setChatOpen(false);
                }}
            />
        </>
    );
}
