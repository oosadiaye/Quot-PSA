from datetime import date, timedelta
from calendar import monthrange
import calendar


def get_month_end_date(ref_date: date = None) -> date:
    """
    Returns the last day of the month for the given date.
    If no date is provided, returns the last day of the current month.
    """
    if ref_date is None:
        ref_date = date.today()
    
    last_day = monthrange(ref_date.year, ref_date.month)[1]
    return date(ref_date.year, ref_date.month, last_day)


def get_month_start_date(ref_date: date = None) -> date:
    """
    Returns the first day of the month for the given date.
    If no date is provided, returns the first day of the current month.
    """
    if ref_date is None:
        ref_date = date.today()
    
    return date(ref_date.year, ref_date.month, 1)


def get_next_month_first_day(ref_date: date = None) -> date:
    """
    Returns the first day of the next month.
    If no date is provided, calculates from the current date.
    """
    if ref_date is None:
        ref_date = date.today()
    
    if ref_date.month == 12:
        next_month = date(ref_date.year + 1, 1, 1)
    else:
        next_month = date(ref_date.year, ref_date.month + 1, 1)
    
    return next_month


def get_current_month_end_date() -> date:
    """
    Returns the last day of the current month based on today's date.
    """
    return get_month_end_date(date.today())


def get_current_month_first_day() -> date:
    """
    Returns the first day of the current month.
    """
    return get_month_start_date(date.today())


def get_next_month_end_date(ref_date: date = None) -> date:
    """
    Returns the last day of the next month.
    """
    if ref_date is None:
        ref_date = date.today()
    
    next_month_first = get_next_month_first_day(ref_date)
    return get_month_end_date(next_month_first)


def is_first_of_month(ref_date: date = None) -> bool:
    """
    Checks if the given date is the first day of the month.
    """
    if ref_date is None:
        ref_date = date.today()
    
    return ref_date.day == 1


def is_last_day_of_month(ref_date: date = None) -> bool:
    """
    Checks if the given date is the last day of the month.
    """
    if ref_date is None:
        ref_date = date.today()
    
    last_day = monthrange(ref_date.year, ref_date.month)[1]
    return ref_date.day == last_day


def get_default_posting_and_reversal_dates() -> dict:
    """
    Returns a dictionary with default posting and reversal dates.
    Posting date = last day of current month
    Reversal date = first day of next month
    """
    return {
        'posting_date': get_current_month_end_date(),
        'reversal_date': get_next_month_first_day()
    }


def calculate_period_dates(frequency: str, start_date: date = None) -> dict:
    """
    Calculate next run dates based on frequency.
    Returns a dictionary with next_run_date and (optionally) posting_date.
    """
    if start_date is None:
        start_date = date.today()
    
    if frequency == 'daily':
        next_run = start_date + timedelta(days=1)
    elif frequency == 'weekly':
        next_run = start_date + timedelta(weeks=1)
    elif frequency == 'biweekly':
        next_run = start_date + timedelta(weeks=2)
    elif frequency == 'monthly':
        # Get same day next month
        if start_date.month == 12:
            next_run = date(start_date.year + 1, 1, start_date.day)
        else:
            # Handle months with fewer days
            max_day = monthrange(start_date.year, start_date.month + 1)[1]
            next_day = min(start_date.day, max_day)
            next_run = date(start_date.year, start_date.month + 1, next_day)
    elif frequency == 'quarterly':
        # Get same day 3 months later
        new_month = start_date.month + 3
        year_add = (new_month - 1) // 12
        month = ((new_month - 1) % 12) + 1
        max_day = monthrange(start_date.year + year_add, month)[1]
        next_day = min(start_date.day, max_day)
        next_run = date(start_date.year + year_add, month, next_day)
    elif frequency == 'annually':
        # Get same day next year
        max_day = monthrange(start_date.year + 1, start_date.month)[1]
        next_day = min(start_date.day, max_day)
        next_run = date(start_date.year + 1, start_date.month, next_day)
    else:
        next_run = start_date + timedelta(days=1)
    
    return {
        'next_run_date': next_run,
        'posting_date': get_month_end_date(next_run) if frequency == 'monthly' else next_run
    }
