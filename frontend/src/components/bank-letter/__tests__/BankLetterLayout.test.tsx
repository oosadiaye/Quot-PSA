import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import BankLetterLayout from '../BankLetterLayout';
import type { BankLetterSettings, PaymentBatch } from
  '../../../features/accounting/hooks/usePaymentBatches';

const settings: BankLetterSettings = {
  id: 1,
  ministry_name: 'MINISTRY OF FINANCE',
  office_name: 'OFFICE OF THE ACCOUNTANT GENERAL',
  office_address: 'ASABA',
  letterhead_logo: null,
  accountant_general_name: 'OKUNBOR V.I',
  accountant_general_title: 'PERMANENT SECRETARY/ACCOUNTANT GENERAL',
  accountant_general_signature: null,
  director_treasury_name: 'OGBAUDU A.B',
  director_treasury_title: 'DIRECTOR TREASURER',
  director_treasury_signature: null,
  director_mgmt_acct_name: 'AGBEDOGUN ISREAL',
  director_mgmt_acct_title: 'DIRECTOR MANAGEMENT ACCT',
  director_mgmt_acct_signature: null,
};

function makeBatch(lineCount: number, amount = '100.00'): PaymentBatch {
  return {
    id: 1,
    batch_number: 'PB/2026/0001',
    batch_date: '2026-08-11',
    source_bank_account: 1,
    source_bank_account_name: 'Treasury Main',
    addressee_bank_name: 'PREMIUM TRUST BANK',
    addressee_account_no: '0100070001',
    status: 'Draft',
    total_amount: (Number(amount) * lineCount).toFixed(2),
    line_count: lineCount,
    notes: '',
    cancelled_reason: '',
    dispatched_at: null,
    confirmed_at: null,
    lines: Array.from({ length: lineCount }, (_, i) => ({
      id: i + 1,
      sequence: i + 1,
      payment: i + 1,
      payment_number: `PAY-${i + 1}`,
      payee_name: `Vendor ${i + 1}`,
      payee_bank: 'Zenith Bank',
      payee_account: '0123456789',
      purpose: 'Supplies',
      amount,
      is_active_membership: true,
    })),
  };
}

describe('BankLetterLayout', () => {
  it('renders the date as DD/MM/YYYY', () => {
    render(<BankLetterLayout batch={makeBatch(1)} settings={settings} />);
    expect(screen.getByText(/DATE:\s*11\/08\/2026/)).toBeInTheDocument();
  });

  it('addresses the bank holding the paying account', () => {
    render(<BankLetterLayout batch={makeBatch(1)} settings={settings} />);
    expect(screen.getByText('THE MANAGER')).toBeInTheDocument();
    expect(screen.getByText(/PREMIUM TRUST BANK/)).toBeInTheDocument();
    expect(screen.getByText(/0100070001/)).toBeInTheDocument();
  });

  it('pads to 14 rows when there are fewer lines', () => {
    const { container } = render(
      <BankLetterLayout batch={makeBatch(3)} settings={settings} />);
    expect(container.querySelectorAll('tbody tr').length).toBe(14);
  });

  it('does not truncate when there are more than 14 lines', () => {
    const { container } = render(
      <BankLetterLayout batch={makeBatch(20)} settings={settings} />);
    expect(container.querySelectorAll('tbody tr').length).toBe(20);
  });

  it('prints the total of all lines', () => {
    render(<BankLetterLayout batch={makeBatch(3, '100.00')} settings={settings} />);
    expect(screen.getByTestId('letter-total')).toHaveTextContent('300.00');
  });

  it('shows all three signatories', () => {
    render(<BankLetterLayout batch={makeBatch(1)} settings={settings} />);
    expect(screen.getByText('OKUNBOR V.I')).toBeInTheDocument();
    expect(screen.getByText('OGBAUDU A.B')).toBeInTheDocument();
    expect(screen.getByText('AGBEDOGUN ISREAL')).toBeInTheDocument();
  });
});
