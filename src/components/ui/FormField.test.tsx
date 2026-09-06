import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FormField } from './FormField';
import { Input } from './Input';

describe('FormField', () => {
  it('links label, hint and error to the control', () => {
    const { rerender } = render(
      <FormField label="Email" hint="We never share it">
        <Input type="email" />
      </FormField>,
    );
    const input = screen.getByLabelText('Email');
    expect(input).toHaveAccessibleDescription('We never share it');
    expect(input).not.toHaveAttribute('aria-invalid');
    rerender(
      <FormField label="Email" hint="We never share it" error="Enter a valid email address">
        <Input type="email" />
      </FormField>,
    );
    const invalid = screen.getByLabelText('Email');
    expect(invalid).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a valid email address');
    expect(invalid).toHaveAccessibleDescription('Enter a valid email address');
  });
});
