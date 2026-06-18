"""
Replace ``Warrant.quarter`` as the primary period with explicit date
range fields ``effective_from`` / ``effective_to``. Keep ``quarter``
as a nullable convenience column so legacy quarter-grouped reports
keep working while new writes use the date range.

Backfill strategy for existing rows:
  • Pull the FiscalYear via ``appropriation.fiscal_year`` to determine
    that warrant's calendar bounds.
  • Map the integer quarter to a [start, end] inside that fiscal year.
  • Write effective_from = quarter start, effective_to = quarter end.

The ``unique_together = (appropriation, quarter)`` index is dropped:
multiple non-overlapping date ranges on the same appropriation are
the new norm. Range-overlap enforcement is in Warrant.clean().

Adds ``EXPIRED`` to STATUS_CHOICES.
"""
from datetime import date
from django.db import migrations, models


def _quarter_bounds(fy_start: date, fy_end: date, q: int) -> tuple[date, date]:
    """Carve a fiscal year into 4 equal-ish quarters and return the
    (start, end) of quarter ``q`` (1..4). Falls back to (fy_start,
    fy_end) when q is missing or malformed so the row always has a
    valid range after migration."""
    if not q or q < 1 or q > 4:
        return fy_start, fy_end
    # Total span in days then split into four buckets. Using days
    # rather than calendar months means we don't have to special-case
    # short years / leap years — the bucket boundaries are just dates.
    span_days = (fy_end - fy_start).days
    if span_days <= 0:
        return fy_start, fy_end
    bucket = span_days // 4
    start = fy_start.replace() if q == 1 else fy_start.toordinal() + bucket * (q - 1)
    end = fy_end if q == 4 else fy_start.toordinal() + bucket * q - 1
    if isinstance(start, int):
        start = date.fromordinal(start)
    if isinstance(end, int):
        end = date.fromordinal(end)
    return start, end


def backfill_date_ranges(apps, schema_editor):
    Warrant = apps.get_model('budget', 'Warrant')
    for w in Warrant.objects.select_related('appropriation__fiscal_year').iterator():
        appr = w.appropriation
        fy = getattr(appr, 'fiscal_year', None)
        fy_start = getattr(fy, 'start_date', None) if fy else None
        fy_end = getattr(fy, 'end_date', None) if fy else None
        # Sensible fallback when the fiscal year row hasn't got
        # explicit dates: use a calendar year derived from the
        # integer ``year`` attribute, defaulting to current year.
        if not fy_start or not fy_end:
            yr = getattr(fy, 'year', None) or date.today().year
            fy_start = date(yr, 1, 1)
            fy_end = date(yr, 12, 31)
        eff_from, eff_to = _quarter_bounds(fy_start, fy_end, w.quarter or 0)
        w.effective_from = eff_from
        w.effective_to = eff_to
        w.save(update_fields=['effective_from', 'effective_to'])


def noop_reverse(apps, schema_editor):
    """Reverse is a no-op — the new fields stay populated; the
    quarter column was kept on the table so reverting just removes
    the new fields, no data loss the other way."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('budget', '0015_add_warrant_printout_settings'),
    ]

    operations = [
        # 1. Add new fields nullable so the migration succeeds even on
        #    populated tables.
        migrations.AddField(
            model_name='warrant',
            name='effective_from',
            field=models.DateField(
                null=True, blank=True,
                help_text='Date the warrant becomes effective (inclusive).',
            ),
        ),
        migrations.AddField(
            model_name='warrant',
            name='effective_to',
            field=models.DateField(
                null=True, blank=True,
                help_text=(
                    'Date the warrant expires (inclusive). After this '
                    'date the warrant cannot be drawn against.'
                ),
            ),
        ),
        # 2. Make quarter nullable so new annual warrants don't have
        #    to set it (save() derives it from effective_from when
        #    absent).
        migrations.AlterField(
            model_name='warrant',
            name='quarter',
            field=models.IntegerField(
                choices=[(1, 'Q1'), (2, 'Q2'), (3, 'Q3'), (4, 'Q4')],
                null=True, blank=True,
            ),
        ),
        # 3. Add EXPIRED to status choices.
        migrations.AlterField(
            model_name='warrant',
            name='status',
            field=models.CharField(
                max_length=15,
                choices=[
                    ('PENDING', 'Pending Release'),
                    ('RELEASED', 'Released'),
                    ('SUSPENDED', 'Suspended'),
                    ('EXHAUSTED', 'Exhausted'),
                    ('EXPIRED', 'Expired'),
                ],
                default='PENDING',
            ),
        ),
        # 4. Backfill date ranges from quarter+fiscal_year on existing
        #    rows so the new fields are populated before the schema
        #    rejects nulls (we keep them nullable for now to avoid
        #    breaking partial deploys; tightening can come later).
        migrations.RunPython(backfill_date_ranges, noop_reverse),
        # 5. Drop the (appropriation, quarter) uniqueness — multiple
        #    non-overlapping ranges per appropriation are the new
        #    norm; overlap enforcement moves into Warrant.clean().
        migrations.AlterUniqueTogether(
            name='warrant',
            unique_together=set(),
        ),
        # 6. Reorder default ordering and add range-friendly indexes.
        migrations.AlterModelOptions(
            name='warrant',
            options={
                'ordering': ['appropriation', '-effective_from'],
                'verbose_name': 'Warrant (Cash Release)',
                'verbose_name_plural': 'Warrants (Cash Releases)',
            },
        ),
        migrations.AddIndex(
            model_name='warrant',
            index=models.Index(
                fields=['appropriation', 'effective_from'],
                name='budget_warr_appr_eff_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='warrant',
            index=models.Index(
                fields=['effective_to', 'status'],
                name='budget_warr_to_status_idx',
            ),
        ),
    ]
