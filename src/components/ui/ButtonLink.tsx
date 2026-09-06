import type { ReactNode } from 'react';
import { Link, type LinkProps } from 'react-router';
import { buttonClasses } from './buttonClasses';
import type { ButtonSize, ButtonVariant } from './Button';

export interface ButtonLinkProps extends LinkProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  leadingIcon?: ReactNode;
  trailingIcon?: ReactNode;
}

/** A router link that looks like a Button (navigation should be a link, not a button). */
export function ButtonLink({
  variant = 'primary',
  size = 'md',
  block,
  className,
  leadingIcon,
  trailingIcon,
  children,
  ...rest
}: ButtonLinkProps) {
  return (
    <Link className={buttonClasses({ variant, size, block: block ?? false, className })} {...rest}>
      {leadingIcon && <span className="inline-flex shrink-0 [&>svg]:size-4">{leadingIcon}</span>}
      {children}
      {trailingIcon && <span className="inline-flex shrink-0 [&>svg]:size-4">{trailingIcon}</span>}
    </Link>
  );
}
