# HRM Module Specification

## Overview
Human Resource Management module for QUOT ERP system. Manages employees, leave, attendance, payroll, recruitment, performance, training, and compliance.

## Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/hrm/dashboard` | HRMDashboard | HRM overview and stats |
| `/hrm` | HRMDashboard | Redirect to dashboard |
| `/hrm/employees` | EmployeeList | Employee directory |
| `/hrm/departments` | DepartmentList | Department management |
| `/hrm/positions` | PositionList | Job positions |
| `/hrm/leave` | LeaveManagement | Leave requests |
| `/hrm/attendance` | AttendanceList | Attendance tracking |
| `/hrm/holidays` | HolidayList | Holiday calendar |
| `/hrm/job-posts` | JobPostList | Job openings |
| `/hrm/candidates` | CandidateList | Applicant tracking |
| `/hrm/payroll` | PayrollList | Payroll runs |
| `/hrm/payslips` | PayslipList | Employee payslips |
| `/hrm/performance` | PerformanceList | Reviews & goals |
| `/hrm/training` | TrainingList | Training programs |
| `/hrm/skills` | SkillList | Skills matrix |
| `/hrm/policies` | PolicyList | HR policies |
| `/hrm/compliance` | ComplianceList | Compliance tracking |
| `/hrm/exit` | ExitManagement | Offboarding |

## Hooks (useHrm.ts)

### Employee Hooks
- `useEmployees(params?)` - List employees
- `useEmployee(id)` - Get employee details
- `useCreateEmployee()` - Create employee
- `useUpdateEmployee(id)` - Update employee
- `useDeleteEmployee(id)` - Delete employee

### Department Hooks
- `useDepartments(params?)` - List departments
- `useDepartment(id)` - Get department details
- `useCreateDepartment()` - Create department
- `useUpdateDepartment(id)` - Update department
- `useDeleteDepartment(id)` - Delete department

### Position Hooks
- `usePositions(params?)` - List positions
- `usePosition(id)` - Get position details
- `useCreatePosition()` - Create position
- `useUpdatePosition(id)` - Update position
- `useDeletePosition(id)` - Delete position

### Leave Hooks
- `useLeaveTypes(params?)` - List leave types
- `useLeaveRequests(params?)` - List leave requests
- `useLeaveRequest(id)` - Get leave request details
- `useCreateLeaveRequest()` - Create leave request
- `useApproveLeave(id)` - Approve leave request
- `useRejectLeave(id)` - Reject leave request

### Attendance Hooks
- `useAttendances(params?)` - List attendance records
- `useCreateAttendance()` - Create attendance
- `useMarkAttendance()` - Bulk mark attendance

### Holiday Hooks
- `useHolidays(params?)` - List holidays
- `useCreateHoliday()` - Create holiday

### Recruitment Hooks
- `useJobPosts(params?)` - List job posts
- `useJobPost(id)` - Get job post details
- `useCreateJobPost()` - Create job post
- `useCandidates(params?)` - List candidates
- `useCandidate(id)` - Get candidate details
- `useCreateCandidate()` - Create candidate

### Payroll Hooks
- `usePayrollRuns(params?)` - List payroll runs
- `useCreatePayrollRun()` - Create payroll run
- `usePayslips(params?)` - List payslips
- `usePayslip(id)` - Get payslip details

### Performance Hooks
- `usePerformanceReviews(params?)` - List reviews
- `useCreatePerformanceReview()` - Create review
- `useGoals(params?)` - List goals
- `useCreateGoal()` - Create goal

### Training Hooks
- `useTrainingPrograms(params?)` - List programs
- `useTrainingEnrollments(params?)` - List enrollments

### Skills Hooks
- `useSkills(params?)` - List skills
- `useCreateSkill()` - Create skill

### Policy Hooks
- `usePolicies(params?)` - List policies

### Compliance Hooks
- `useComplianceRecords(params?)` - List records

### Exit Hooks
- `useExitRequests(params?)` - List exit requests

## API Endpoints

All endpoints prefixed with `/api/hrm/`

- `GET/POST /departments/`
- `GET/PUT/DELETE /departments/{id}/`
- `GET/POST /positions/`
- `GET/PUT/DELETE /positions/{id}/`
- `GET/POST /employees/`
- `GET/PUT/DELETE /employees/{id}/`
- `GET/POST /leave-types/`
- `GET/POST /leave-requests/`
- `GET/PUT/DELETE /leave-requests/{id}/`
- `POST /leave-requests/{id}/approve/`
- `POST /leave-requests/{id}/reject/`
- `GET/POST /attendances/`
- `GET/POST /holidays/`
- `GET/POST /job-posts/`
- `GET/PUT/DELETE /job-posts/{id}/`
- `GET/POST /candidates/`
- `GET/PUT/DELETE /candidates/{id}/`
- `GET/POST /payroll-runs/`
- `GET/PUT/DELETE /payroll-runs/{id}/`
- `GET/POST /payslips/`
- `GET/PUT/DELETE /payslips/{id}/`
- `GET/POST /performance-reviews/`
- `GET/PUT/DELETE /performance-reviews/{id}/`
- `GET/POST /goals/`
- `GET/PUT/DELETE /goals/{id}/`
- `GET/POST /training-programs/`
- `GET/PUT/DELETE /training-programs/{id}/`
- `GET/POST /training-enrollments/`
- `GET/POST /skills/`
- `GET/PUT/DELETE /skills/{id}/`
- `GET/POST /policies/`
- `GET/PUT/DELETE /policies/{id}/`
- `GET/POST /compliance-records/`
- `GET/PUT/DELETE /compliance-records/{id}/`
- `GET/POST /exit-requests/`
- `GET/PUT/DELETE /exit-requests/{id}/`

## Pagination

API responses use `{ results: [], count: number, next: string, previous: string }` format. Frontend hooks handle this automatically.
