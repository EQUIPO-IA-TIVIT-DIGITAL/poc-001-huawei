import { useState } from 'react';
import { MessageCircle, CheckCircle2 } from 'lucide-react';
import { Button, type ButtonProps } from './ui/button';
import { WorkspaceChatModal } from './WorkspaceChatModal';
import { useTranslation } from '../i18n';

interface WorkspaceChatButtonProps {
    workspaceId: string;
    workspaceName?: string;
    variant?: 'primary' | 'secondary' | 'outline';
    onContextImproved?: () => void;
    className?: string;
    isContextualized?: boolean;
}

const VARIANT_MAP: Record<NonNullable<WorkspaceChatButtonProps['variant']>, ButtonProps['variant']> = {
    primary: 'default',
    secondary: 'outline',
    outline: 'secondary',
};

export function WorkspaceChatButton({
    workspaceId,
    workspaceName = '',
    variant = 'secondary',
    onContextImproved,
    className = '',
    isContextualized = false,
}: WorkspaceChatButtonProps) {
    const { t } = useTranslation();
    const [chatOpen, setChatOpen] = useState(false);

    return (
        <>
            <Button
                variant={isContextualized ? 'success' : VARIANT_MAP[variant]}
                size="sm"
                className={className}
                aria-label={isContextualized ? t('workspaceChat.contextualized') : t('workspaceChat.validate')}
                title={isContextualized ? t('workspaceChat.contextualized') : t('workspaceChat.validate')}
                onClick={(e) => {
                    e.stopPropagation();
                    setChatOpen(true);
                }}
            >
                {isContextualized ? (
                    <CheckCircle2 aria-hidden="true" />
                ) : (
                    <MessageCircle aria-hidden="true" />
                )}
                <span className="hidden sm:inline">
                    {isContextualized ? t('workspaceChat.optimized') : t('workspaceChat.validateShort')}
                </span>
            </Button>

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
