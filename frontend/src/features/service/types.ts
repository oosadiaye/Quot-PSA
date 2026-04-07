export interface SLATracking {
    id: number;
    ticket: number;
    response_time_limit: number;
    resolution_time_limit: number;
    first_response_at: string | null;
    is_response_met: boolean;
    is_resolution_met: boolean;
}

export interface ServiceTicket {
    id: number;
    ticket_number: string;
    subject: string;
    description: string;
    status: 'Open' | 'In Progress' | 'Resolved' | 'Closed';
    priority: 'Low' | 'Medium' | 'High' | 'Critical';
    asset: number | null;
    asset_name: string | null;
    asset_serial: string | null;
    technician: number | null;
    technician_name: string | null;
    due_date: string | null;
    resolved_at: string | null;
    started_at: string | null;
    sla: SLATracking | null;
    created_at: string;
    updated_at: string;
    created_by: number | null;
    updated_by: number | null;
}

export interface Technician {
    id: number;
    name: string;
    employee_code: string;
    email: string;
    phone: string;
    specialization: string;
    is_active: boolean;
    is_available: boolean;
    active_tickets: number;
    created_at: string;
    updated_at: string;
    created_by: number | null;
    updated_by: number | null;
}

export interface ServiceAsset {
    id: number;
    name: string;
    serial_number: string;
    purchase_date: string | null;
    warranty_expiry: string | null;
    created_at: string;
    updated_at: string;
    created_by: number | null;
    updated_by: number | null;
}

export interface WorkOrderMaterial {
    id: number;
    work_order: number;
    item_description: string;
    quantity: number;
    unit_price: number;
    total_price: number;
}

export interface WorkOrder {
    id: number;
    work_order_number: string;
    title: string;
    description: string;
    status: 'Pending' | 'Assigned' | 'In Progress' | 'Completed' | 'Cancelled';
    priority: 'Low' | 'Medium' | 'High' | 'Urgent';
    asset: number | null;
    asset_name: string | null;
    technician: number | null;
    technician_name: string | null;
    scheduled_date: string | null;
    completed_date: string | null;
    labor_hours: number;
    labor_cost: number;
    parts_cost: number;
    total_cost: number;
    notes: string;
    materials: WorkOrderMaterial[];
    created_at: string;
    updated_at: string;
    created_by: number | null;
    updated_by: number | null;
}

export interface CitizenRequest {
    id: number;
    request_number: string;
    citizen_name: string;
    citizen_email: string;
    citizen_phone: string;
    citizen_address: string;
    category: string;
    subject: string;
    description: string;
    status: 'Submitted' | 'Acknowledged' | 'In Progress' | 'Resolved' | 'Closed';
    latitude: number | null;
    longitude: number | null;
    related_ticket: number | null;
    related_ticket_number: string | null;
    created_at: string;
    updated_at: string;
    created_by: number | null;
    updated_by: number | null;
}

export interface MaintenanceSchedule {
    id: number;
    asset: number;
    asset_name: string;
    title: string;
    description: string;
    frequency: 'Daily' | 'Weekly' | 'Monthly' | 'Quarterly' | 'Yearly';
    next_run_date: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
    created_by: number | null;
    updated_by: number | null;
}

export interface ServiceMetric {
    id: number;
    name: string;
    period: 'Daily' | 'Weekly' | 'Monthly' | 'Quarterly' | 'Yearly';
    period_start: string;
    period_end: string;
    total_tickets: number;
    open_tickets: number;
    resolved_tickets: number;
    closed_tickets: number;
    avg_response_time: number;
    avg_resolution_time: number;
    sla_response_met: number;
    sla_response_total: number;
    sla_resolution_met: number;
    sla_resolution_total: number;
    total_work_orders: number;
    completed_work_orders: number;
    total_labor_hours: number;
    total_cost: number;
    response_sla_percentage: number;
    resolution_sla_percentage: number;
}

export interface ServiceDashboardStats {
    total_tickets: number;
    open_tickets: number;
    resolved_tickets: number;
    total_work_orders: number;
    pending_work_orders: number;
    completed_work_orders: number;
    total_citizen_requests: number;
    technicians_available: number;
}

export interface PaginatedResponse<T> {
    count: number;
    next: string | null;
    previous: string | null;
    results: T[];
}
