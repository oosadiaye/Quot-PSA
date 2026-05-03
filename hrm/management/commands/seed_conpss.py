"""Seed the CONPSS salary grid (Consolidated Public Service Salary Structure).

The numbers below use the 2024 review schedule (GL01–GL17, 15 steps each).
They are representative and MUST be overridden with the gazette figures
for production use — this command is for development/demo only.

Usage:
    python manage.py seed_conpss
    python manage.py seed_conpss --effective 2024-01-01 --overwrite
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from hrm.models import SalaryGrade, SalaryScale, SalaryStep

# --------------------------------------------------------------------------- #
# Representative 2024 CONPSS grid (annual basic in NGN).
# Step 1 → Step 15 for each grade. Values are rounded for readability.
# --------------------------------------------------------------------------- #
CONPSS_2024: dict[str, tuple[int, list[int]]] = {
    # code: (rank_order, [step1, step2, ..., step15])
    'GL01': (1,  [360_000,  376_800,  393_600,  410_400,  427_200,  444_000,  460_800,  477_600,  494_400,  511_200,  528_000,  544_800,  561_600,  578_400,  595_200]),
    'GL02': (2,  [420_000,  439_200,  458_400,  477_600,  496_800,  516_000,  535_200,  554_400,  573_600,  592_800,  612_000,  631_200,  650_400,  669_600,  688_800]),
    'GL03': (3,  [492_000,  514_560,  537_120,  559_680,  582_240,  604_800,  627_360,  649_920,  672_480,  695_040,  717_600,  740_160,  762_720,  785_280,  807_840]),
    'GL04': (4,  [576_000,  602_400,  628_800,  655_200,  681_600,  708_000,  734_400,  760_800,  787_200,  813_600,  840_000,  866_400,  892_800,  919_200,  945_600]),
    'GL05': (5,  [672_000,  702_800,  733_600,  764_400,  795_200,  826_000,  856_800,  887_600,  918_400,  949_200,  980_000,  1_010_800, 1_041_600, 1_072_400, 1_103_200]),
    'GL06': (6,  [780_000,  815_760,  851_520,  887_280,  923_040,  958_800,  994_560,  1_030_320, 1_066_080, 1_101_840, 1_137_600, 1_173_360, 1_209_120, 1_244_880, 1_280_640]),
    'GL07': (7,  [900_000,  941_400,  982_800,  1_024_200, 1_065_600, 1_107_000, 1_148_400, 1_189_800, 1_231_200, 1_272_600, 1_314_000, 1_355_400, 1_396_800, 1_438_200, 1_479_600]),
    'GL08': (8,  [1_080_000,1_129_680,1_179_360,1_229_040,1_278_720,1_328_400,1_378_080,1_427_760,1_477_440,1_527_120,1_576_800,1_626_480,1_676_160,1_725_840,1_775_520]),
    'GL09': (9,  [1_296_000,1_355_568,1_415_136,1_474_704,1_534_272,1_593_840,1_653_408,1_712_976,1_772_544,1_832_112,1_891_680,1_951_248,2_010_816,2_070_384,2_129_952]),
    'GL10': (10, [1_560_000,1_631_784,1_703_568,1_775_352,1_847_136,1_918_920,1_990_704,2_062_488,2_134_272,2_206_056,2_277_840,2_349_624,2_421_408,2_493_192,2_564_976]),
    'GL12': (11, [1_872_000,1_958_112,2_044_224,2_130_336,2_216_448,2_302_560,2_388_672,2_474_784,2_560_896,2_647_008,2_733_120,2_819_232,2_905_344,2_991_456,3_077_568]),
    'GL13': (12, [2_160_000,2_259_360,2_358_720,2_458_080,2_557_440,2_656_800,2_756_160,2_855_520,2_954_880,3_054_240,3_153_600,3_252_960,3_352_320,3_451_680,3_551_040]),
    'GL14': (13, [2_520_000,2_635_920,2_751_840,2_867_760,2_983_680,3_099_600,3_215_520,3_331_440,3_447_360,3_563_280,3_679_200,3_795_120,3_911_040,4_026_960,4_142_880]),
    'GL15': (14, [2_988_000,3_125_448,3_262_896,3_400_344,3_537_792,3_675_240,3_812_688,3_950_136,4_087_584,4_225_032,4_362_480,4_499_928,4_637_376,4_774_824,4_912_272]),
    'GL16': (15, [3_600_000,3_765_600,3_931_200,4_096_800,4_262_400,4_428_000,4_593_600,4_759_200,4_924_800,5_090_400,5_256_000,5_421_600,5_587_200,5_752_800,5_918_400]),
    'GL17': (16, [4_500_000,4_707_000,4_914_000,5_121_000,5_328_000,5_535_000,5_742_000,5_949_000,6_156_000,6_363_000,6_570_000,6_777_000,6_984_000,7_191_000,7_398_000]),
}


class Command(BaseCommand):
    help = "Seed a representative CONPSS salary grid for development."

    def add_arguments(self, parser):
        parser.add_argument(
            '--effective', default='2024-01-01',
            help='effective_from date (YYYY-MM-DD).',
        )
        parser.add_argument(
            '--overwrite', action='store_true',
            help='Delete and recreate an existing scale for the same date.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        effective = date.fromisoformat(options['effective'])
        family = 'CONPSS'

        existing = SalaryScale.objects.filter(
            family=family, effective_from=effective,
        ).first()
        if existing and not options['overwrite']:
            self.stdout.write(self.style.WARNING(
                f'CONPSS scale for {effective} already exists (id={existing.pk}). '
                'Pass --overwrite to recreate.'
            ))
            return
        if existing and options['overwrite']:
            existing.delete()

        scale = SalaryScale.objects.create(
            family=family,
            name=f'CONPSS {effective.year} Review (seed)',
            effective_from=effective,
            is_active=True,
            notes='Representative grid — verify against gazette before production use.',
        )

        total_steps = 0
        for code, (rank, step_values) in CONPSS_2024.items():
            grade = SalaryGrade.objects.create(
                scale=scale, code=code, name=f'Grade Level {code[-2:]}',
                rank_order=rank, max_steps=len(step_values),
                annual_increment_months=12,
            )
            for idx, amount in enumerate(step_values, start=1):
                SalaryStep.objects.create(
                    grade=grade, step_number=idx,
                    annual_basic=Decimal(amount),
                )
                total_steps += 1

        self.stdout.write(self.style.SUCCESS(
            f'Seeded CONPSS {effective}: {len(CONPSS_2024)} grades, '
            f'{total_steps} steps.'
        ))
