import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EntityForm } from '../EntityForm';
import type { EntityConfig } from '../types';

const config: EntityConfig = {
  key: 'vehicleAssignment',
  plural: 'vehicle-assignments',
  label: 'Vehicle Assignments',
  searchField: 'assigned_to',
  idField: 'id',
  columns: [],
  fields: [
    { name: 'assigned_to', label: 'Assigned To', type: 'text', required: true },
    { name: 'seats', label: 'Seats', type: 'integer', numeric: true },
    { name: 'budget', label: 'Budget', type: 'decimal', numeric: true },
    { name: 'is_pool', label: 'Pool vehicle', type: 'boolean' },
    { name: 'notes', label: 'Notes', type: 'longtext', secondary: true },
    { name: 'authority', label: 'Authority', type: 'text', secondary: true, required: true },
    { name: 'status', label: 'Status', type: 'text', readOnly: true },
    { name: 'created_at', label: 'Created At', type: 'datetime', hideInForm: true },
  ],
};

function setup(over: Partial<React.ComponentProps<typeof EntityForm>> = {}) {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <EntityForm config={config} onSubmit={onSubmit} onCancel={onCancel} {...over} />
    </QueryClientProvider>,
  );
  return { onSubmit, onCancel };
}

const create = () => screen.getByRole('button', { name: /create vehicle assignment/i });
const type = (label: RegExp | string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

describe('EntityForm validation', () => {
  it('blocks saving and names every required field that is empty', () => {
    const { onSubmit } = setup();
    fireEvent.click(create());
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getAllByText('This field is required.')).toHaveLength(2);          // Assigned To and the required secondary Authority
    expect(screen.getByTestId('ef-error')).toHaveTextContent('2 fields need attention');
  });

  it('marks the empty field invalid for assistive technology', () => {
    setup();
    fireEvent.click(create());
    expect(screen.getByLabelText(/assigned to/i)).toHaveAttribute('aria-invalid', 'true');
  });

  it('clears a field error as soon as it is corrected', () => {
    setup();
    fireEvent.click(create());
    type(/assigned to/i, 'Permanent Secretary');
    expect(screen.getByLabelText(/assigned to/i)).not.toHaveAttribute('aria-invalid');
  });

  it('refuses a fractional number in a whole-number field', () => {
    const { onSubmit } = setup();
    type(/assigned to/i, 'A');
    type(/authority/i, 'Circular 4');
    type(/seats/i, '2.5');
    fireEvent.click(create());
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Enter a whole number.')).toBeInTheDocument();
  });

  it('shows a required field even when it was declared secondary', () => {
    setup();
    expect(screen.getByLabelText(/authority/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^notes/i)).not.toBeInTheDocument();             // optional secondary stays folded away
  });

  it('opens the additional section on demand', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: /additional information/i }));
    expect(screen.getByLabelText(/^notes/i)).toBeInTheDocument();
  });
});

describe('EntityForm payload', () => {
  it('sends filled values, a boolean always, and leaves out untouched optional fields', () => {
    const { onSubmit } = setup();
    type(/assigned to/i, 'Permanent Secretary');
    type(/authority/i, 'Circular 4');
    type(/seats/i, '4');
    fireEvent.click(create());
    expect(onSubmit).toHaveBeenCalledWith({ assigned_to: 'Permanent Secretary', authority: 'Circular 4', seats: 4, is_pool: false });
  });

  it('turns a switch on and reports it', () => {
    const { onSubmit } = setup();
    type(/assigned to/i, 'A');
    type(/authority/i, 'B');
    fireEvent.click(screen.getByRole('switch', { name: /pool vehicle/i }));
    fireEvent.click(create());
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ is_pool: true }));
  });

  it('shows a read-only field but never sends it back', () => {
    const { onSubmit } = setup({ initial: { id: 1, assigned_to: 'A', authority: 'B', status: 'issued' } });
    expect(screen.getByLabelText(/^status/i)).toHaveAttribute('readonly');
    fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('status');
  });

  it('never sends server-managed fields', () => {
    const { onSubmit } = setup();
    type(/assigned to/i, 'A');
    type(/authority/i, 'B');
    fireEvent.click(create());
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('created_at');
  });
});

describe('EntityForm editing and errors', () => {
  it('names the record being edited and offers to save changes', () => {
    setup({ initial: { id: 7, assigned_to: 'Director of Works', authority: 'X', notes: 'n' } });
    expect(screen.getByTestId('ef-record')).toHaveTextContent('Director of Works');
    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/^notes/i)).toBeInTheDocument();                   // a filled secondary field opens the section
  });

  it('shows the server’s reason above the form', () => {
    setup({ error: 'Vehicle: This field may not be null.' });
    expect(screen.getByTestId('ef-error')).toHaveTextContent('Vehicle: This field may not be null.');
  });

  it('cancels without submitting', () => {
    const { onCancel, onSubmit } = setup();
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('shows a saving state and disables the button while submitting', () => {
    setup({ submitting: true });
    expect(screen.getByRole('button', { name: /saving/i })).toBeDisabled();
  });
});
