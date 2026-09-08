import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../../lib/utils"

const buttonVariants = cva(
    "inline-flex items-center justify-center gap-2 px-6 py-3 text-[15px] font-semibold rounded-md transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed",
    {
        variants: {
            variant: {
                default:
                    "bg-linear-to-br from-tivit-red to-tivit-red-dark text-white shadow-[0_4px_14px_var(--color-tivit-red-glow)] hover:from-tivit-red-light hover:to-tivit-red hover:-translate-y-0.5 hover:shadow-[0_8px_24px_var(--color-tivit-red-glow)]",
                secondary:
                    "bg-gray-100 text-black border border-gray-300 hover:bg-gray-200 hover:border-gray-400",
                ghost: "bg-transparent text-gray-600 hover:bg-gray-100 hover:text-black",
                success: "bg-success text-white hover:bg-opacity-90",
                danger: "bg-error text-white hover:bg-opacity-90",
                outline: "border border-gray-200 bg-white hover:bg-gray-100 text-gray-900",
            },
            size: {
                default: "h-11 px-6 py-3",
                sm: "h-9 rounded-md px-4 text-xs",
                lg: "h-14 rounded-md px-8 text-base",
                icon: "h-10 w-10 px-0",
            },
            fullWidth: {
                true: "w-full",
            },
        },
        defaultVariants: {
            variant: "default",
            size: "default",
            fullWidth: false,
        },
    }
)

export interface ButtonProps
    extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> { }

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
    ({ className, variant, size, fullWidth, ...props }, ref) => {
        return (
            <button
                className={cn(buttonVariants({ variant, size, fullWidth, className }))}
                ref={ref}
                {...props}
            />
        )
    }
)
Button.displayName = "Button"

export { Button, buttonVariants }
