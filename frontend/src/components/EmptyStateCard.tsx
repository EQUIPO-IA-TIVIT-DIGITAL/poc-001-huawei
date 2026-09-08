import { ReactNode } from 'react';
import { motion } from 'framer-motion';

interface EmptyStateFeature {
  icon?: ReactNode;
  label: string;
}

interface EmptyStateCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  primaryActionLabel: string;
  onPrimaryAction: () => void;
  primaryActionIcon?: ReactNode;
  features?: EmptyStateFeature[];
}

export function EmptyStateCard({
  icon,
  title,
  description,
  primaryActionLabel,
  onPrimaryAction,
  primaryActionIcon,
  features = [],
}: EmptyStateCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-sm border border-gray-100 p-12 lg:p-16 text-center"
    >
      <div className="flex justify-center mb-5">
        <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center border border-gray-200/50">
          {icon}
        </div>
      </div>
      <h3 className="text-xl font-bold text-gray-800 mb-2">{title}</h3>
      <p className="text-gray-500 mb-6 max-w-xl mx-auto leading-relaxed">{description}</p>

      {features.length > 0 && (
        <div className="flex flex-wrap gap-2.5 justify-center mb-8">
          {features.map((feature) => (
            <span
              key={feature.label}
              className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-red-50 to-rose-50 text-red-700 border border-red-100 rounded-full text-sm font-medium"
            >
              {feature.icon}
              {feature.label}
            </span>
          ))}
        </div>
      )}

      <motion.button
        whileHover={{ scale: 1.03 }}
        whileTap={{ scale: 0.97 }}
        onClick={onPrimaryAction}
        className="inline-flex items-center gap-2 bg-gradient-to-r from-tivit-red to-rose-600 text-white px-7 py-3.5 rounded-xl font-semibold shadow-lg shadow-red-200/40 hover:shadow-red-300/50 transition-all duration-200"
      >
        {primaryActionIcon}
        {primaryActionLabel}
      </motion.button>
    </motion.div>
  );
}
