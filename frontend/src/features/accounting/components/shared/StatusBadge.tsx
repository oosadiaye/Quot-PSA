import '../../styles/glassmorphism.css';

interface StatusBadgeProps {
    status: string;
    className?: string;
}

export default function StatusBadge({ status, className = '' }: StatusBadgeProps) {
    const getStatusClass = (status: string): string => {
        const statusMap: Record<string, string> = {
            'Draft': 'badge-draft',
            'Pending': 'badge-draft',
            'Approved': 'badge-approved',
            'Sent': 'badge-approved',
            // Posted = GL journal created, AP recognised, awaiting payment.
            // Uses badge-approved (blue) rather than badge-paid (green) so
            // it's visually distinct from a fully-settled invoice.
            'Posted': 'badge-approved',
            'Partially Paid': 'badge-partial',
            'Paid': 'badge-paid',
            'Void': 'badge-void',
            'Rejected': 'badge-void',
            'Overdue': 'badge-void',
            'Active': 'badge-approved',
            'Disposed': 'badge-void',
            'Retired': 'badge-draft',
        };

        return statusMap[status] || 'badge-draft';
    };

    return (
        <span className={`badge-glass ${getStatusClass(status)} ${className}`}>
            {status}
        </span>
    );
}
