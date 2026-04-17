"""
Seed Nigeria NCoA Local Government Areas (LGAs)
================================================
Seeds 774 LGA records as GeographicSegment entries under their parent state.

Usage:
    python manage.py seed_ncoa_lgas                  # Seeds all states' LGAs
    python manage.py seed_ncoa_lgas --state-code 23  # Seeds only Lagos LGAs
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.models.ncoa import GeographicSegment


# ─── Zone mapping: NBS state code → geo-political zone code ────────────

STATE_ZONE_MAP: dict[str, str] = {
    # Zone 1: North-Central
    '07': '1', '15': '1', '18': '1', '22': '1', '25': '1', '29': '1', '37': '1',
    # Zone 2: North-East
    '02': '2', '05': '2', '08': '2', '11': '2', '33': '2', '35': '2',
    # Zone 3: North-West
    '14': '3', '16': '3', '17': '3', '19': '3', '20': '3', '31': '3', '36': '3',
    # Zone 4: South-East  (Ebonyi uses unique composite code via zone prefix)
    '01': '4', '04': '4',
    # Ebonyi (NBS 11) is in Zone 4 — but NBS code 11 is shared with Gombe (Zone 2).
    # We handle Ebonyi separately below with zone-aware lookup.
    '13': '4', '27': '4',
    # Zone 5: South-South
    '03': '5', '06': '5', '09': '5', '10': '5', '12': '5', '32': '5',
    # Zone 6: South-West  (Ekiti NBS 06 conflicts with Bayelsa — handled via zone)
    '23': '6', '26': '6', '28': '6', '30': '6',
}

# States where NBS code collides across zones.
# For these, the parent state is located by full composite code.
# Format: NBS code → [(zone_code, state_name), ...]
MULTI_ZONE_STATES: dict[str, list[tuple[str, str]]] = {
    '11': [('2', 'Gombe'), ('4', 'Ebonyi')],
    '06': [('5', 'Bayelsa'), ('6', 'Ekiti')],
    '29': [('1', 'Plateau'), ('6', 'Osun')],
}


# ─── LGA data per state (NBS code → list of (sequential_code, name)) ──

LGAS_BY_STATE: dict[str, list[tuple[str, str]]] = {

    # ══════════════════════════════════════════════════════════════
    # Zone 1: North-Central
    # ══════════════════════════════════════════════════════════════

    # Benue (07)
    '07': [
        ('01', 'Ado'), ('02', 'Agatu'), ('03', 'Apa'), ('04', 'Buruku'),
        ('05', 'Gboko'), ('06', 'Guma'), ('07', 'Gwer East'),
        ('08', 'Gwer West'), ('09', 'Katsina-Ala'), ('10', 'Konshisha'),
        ('11', 'Kwande'), ('12', 'Logo'), ('13', 'Makurdi'),
        ('14', 'Obi'), ('15', 'Ogbadibo'), ('16', 'Ohimini'),
        ('17', 'Oju'), ('18', 'Okpokwu'), ('19', 'Otukpo'),
        ('20', 'Tarka'), ('21', 'Ukum'), ('22', 'Ushongo'),
        ('23', 'Vandeikya'),
    ],

    # Kogi (15)
    '15': [
        ('01', 'Adavi'), ('02', 'Ajaokuta'), ('03', 'Ankpa'),
        ('04', 'Bassa'), ('05', 'Dekina'), ('06', 'Ibaji'),
        ('07', 'Idah'), ('08', 'Igalamela-Odolu'), ('09', 'Ijumu'),
        ('10', 'Kabba/Bunu'), ('11', 'Kogi'), ('12', 'Lokoja'),
        ('13', 'Mopa-Muro'), ('14', 'Ofu'), ('15', 'Ogori/Magongo'),
        ('16', 'Okehi'), ('17', 'Okene'), ('18', 'Olamaboro'),
        ('19', 'Omala'), ('20', 'Yagba East'), ('21', 'Yagba West'),
    ],

    # Kwara (18) — ALL 16 LGAs
    '18': [
        ('01', 'Asa'), ('02', 'Baruten'), ('03', 'Edu'),
        ('04', 'Ekiti (Kwara)'), ('05', 'Ifelodun'), ('06', 'Ilorin East'),
        ('07', 'Ilorin South'), ('08', 'Ilorin West'), ('09', 'Irepodun'),
        ('10', 'Isin'), ('11', 'Kaiama'), ('12', 'Moro'),
        ('13', 'Offa'), ('14', 'Oke-Ero'), ('15', 'Oyun'),
        ('16', 'Patigi'),
    ],

    # Nasarawa (22)
    '22': [
        ('01', 'Akwanga'), ('02', 'Awe'), ('03', 'Doma'),
        ('04', 'Karu'), ('05', 'Keana'), ('06', 'Keffi'),
        ('07', 'Kokona'), ('08', 'Lafia'), ('09', 'Nasarawa'),
        ('10', 'Nasarawa Eggon'), ('11', 'Obi'), ('12', 'Toto'),
        ('13', 'Wamba'),
    ],

    # Niger (25)
    '25': [
        ('01', 'Agaie'), ('02', 'Agwara'), ('03', 'Bida'),
        ('04', 'Borgu'), ('05', 'Bosso'), ('06', 'Chanchaga'),
        ('07', 'Edati'), ('08', 'Gbako'),
    ],

    # Plateau (29) — Zone 1
    '29_z1': [
        ('01', 'Barkin Ladi'), ('02', 'Bassa'), ('03', 'Bokkos'),
        ('04', 'Jos East'), ('05', 'Jos North'), ('06', 'Jos South'),
        ('07', 'Kanam'), ('08', 'Kanke'),
    ],

    # FCT Abuja (37) — ALL 6 LGAs
    '37': [
        ('01', 'Abaji'), ('02', 'Bwari'), ('03', 'Gwagwalada'),
        ('04', 'Kuje'), ('05', 'Kwali'), ('06', 'Municipal (AMAC)'),
    ],

    # ══════════════════════════════════════════════════════════════
    # Zone 2: North-East
    # ══════════════════════════════════════════════════════════════

    # Adamawa (02)
    '02': [
        ('01', 'Demsa'), ('02', 'Fufore'), ('03', 'Ganye'),
        ('04', 'Girei'), ('05', 'Gombi'), ('06', 'Guyuk'),
        ('07', 'Hong'), ('08', 'Jada'),
    ],

    # Bauchi (05)
    '05': [
        ('01', 'Alkaleri'), ('02', 'Bauchi'), ('03', 'Bogoro'),
        ('04', 'Dambam'), ('05', 'Darazo'), ('06', 'Dass'),
        ('07', 'Gamawa'), ('08', 'Ganjuwa'),
    ],

    # Borno (08)
    '08': [
        ('01', 'Abadam'), ('02', 'Askira/Uba'), ('03', 'Bama'),
        ('04', 'Bayo'), ('05', 'Biu'), ('06', 'Chibok'),
        ('07', 'Damboa'), ('08', 'Dikwa'),
    ],

    # Gombe (11) — Zone 2
    '11_z2': [
        ('01', 'Akko'), ('02', 'Balanga'), ('03', 'Billiri'),
        ('04', 'Dukku'), ('05', 'Funakaye'), ('06', 'Gombe'),
        ('07', 'Kaltungo'), ('08', 'Kwami'),
    ],

    # Taraba (33)
    '33': [
        ('01', 'Ardo-Kola'), ('02', 'Bali'), ('03', 'Donga'),
        ('04', 'Gashaka'), ('05', 'Gassol'), ('06', 'Ibi'),
        ('07', 'Jalingo'), ('08', 'Karim-Lamido'),
    ],

    # Yobe (35)
    '35': [
        ('01', 'Bade'), ('02', 'Bursari'), ('03', 'Damaturu'),
        ('04', 'Fika'), ('05', 'Fune'), ('06', 'Geidam'),
        ('07', 'Gujba'), ('08', 'Gulani'),
    ],

    # ══════════════════════════════════════════════════════════════
    # Zone 3: North-West
    # ══════════════════════════════════════════════════════════════

    # Jigawa (14)
    '14': [
        ('01', 'Auyo'), ('02', 'Babura'), ('03', 'Biriniwa'),
        ('04', 'Birnin Kudu'), ('05', 'Buji'), ('06', 'Dutse'),
        ('07', 'Gagarawa'), ('08', 'Garki'),
    ],

    # Kaduna (16)
    '16': [
        ('01', 'Birnin Gwari'), ('02', 'Chikun'), ('03', 'Giwa'),
        ('04', 'Igabi'), ('05', 'Ikara'), ('06', 'Jaba'),
        ('07', 'Jema\'a'), ('08', 'Kachia'),
    ],

    # Kano (17) — ALL 44 LGAs
    '17': [
        ('01', 'Ajingi'), ('02', 'Albasu'), ('03', 'Bagwai'),
        ('04', 'Bebeji'), ('05', 'Bichi'), ('06', 'Bunkure'),
        ('07', 'Dala'), ('08', 'Dambatta'), ('09', 'Dawakin Kudu'),
        ('10', 'Dawakin Tofa'), ('11', 'Doguwa'), ('12', 'Fagge'),
        ('13', 'Gabasawa'), ('14', 'Garko'), ('15', 'Garun Mallam'),
        ('16', 'Gaya'), ('17', 'Gezawa'), ('18', 'Gwale'),
        ('19', 'Gwarzo'), ('20', 'Kabo'), ('21', 'Kano Municipal'),
        ('22', 'Karaye'), ('23', 'Kibiya'), ('24', 'Kiru'),
        ('25', 'Kumbotso'), ('26', 'Kunchi'), ('27', 'Kura'),
        ('28', 'Madobi'), ('29', 'Makoda'), ('30', 'Minjibir'),
        ('31', 'Nassarawa'), ('32', 'Rano'), ('33', 'Rimin Gado'),
        ('34', 'Rogo'), ('35', 'Shanono'), ('36', 'Sumaila'),
        ('37', 'Takai'), ('38', 'Tarauni'), ('39', 'Tofa'),
        ('40', 'Tsanyawa'), ('41', 'Tudun Wada'), ('42', 'Ungogo'),
        ('43', 'Warawa'), ('44', 'Wudil'),
    ],

    # Katsina (19)
    '19': [
        ('01', 'Bakori'), ('02', 'Batagarawa'), ('03', 'Batsari'),
        ('04', 'Baure'), ('05', 'Bindawa'), ('06', 'Charanchi'),
        ('07', 'Dan Musa'), ('08', 'Dandume'),
    ],

    # Kebbi (20)
    '20': [
        ('01', 'Aleiro'), ('02', 'Arewa-Dandi'), ('03', 'Argungu'),
        ('04', 'Augie'), ('05', 'Bagudo'), ('06', 'Birnin Kebbi'),
        ('07', 'Bunza'), ('08', 'Dandi'),
    ],

    # Sokoto (31)
    '31': [
        ('01', 'Binji'), ('02', 'Bodinga'), ('03', 'Dange-Shuni'),
        ('04', 'Gada'), ('05', 'Goronyo'), ('06', 'Gudu'),
        ('07', 'Gwadabawa'), ('08', 'Illela'),
    ],

    # Zamfara (36)
    '36': [
        ('01', 'Anka'), ('02', 'Bakura'), ('03', 'Birnin Magaji/Kiyaw'),
        ('04', 'Bukkuyum'), ('05', 'Bungudu'), ('06', 'Gummi'),
        ('07', 'Gusau'), ('08', 'Kaura Namoda'),
    ],

    # ══════════════════════════════════════════════════════════════
    # Zone 4: South-East
    # ══════════════════════════════════════════════════════════════

    # Abia (01)
    '01': [
        ('01', 'Aba North'), ('02', 'Aba South'), ('03', 'Arochukwu'),
        ('04', 'Bende'), ('05', 'Ikwuano'), ('06', 'Isiala Ngwa North'),
        ('07', 'Isiala Ngwa South'), ('08', 'Isuikwuato'),
    ],

    # Anambra (04)
    '04': [
        ('01', 'Aguata'), ('02', 'Anambra East'), ('03', 'Anambra West'),
        ('04', 'Anaocha'), ('05', 'Awka North'), ('06', 'Awka South'),
        ('07', 'Ayamelum'), ('08', 'Dunukofia'),
    ],

    # Ebonyi (11) — Zone 4
    '11_z4': [
        ('01', 'Abakaliki'), ('02', 'Afikpo North'), ('03', 'Afikpo South'),
        ('04', 'Ebonyi'), ('05', 'Ezza North'), ('06', 'Ezza South'),
        ('07', 'Ikwo'), ('08', 'Ishielu'),
    ],

    # Enugu (13)
    '13': [
        ('01', 'Aninri'), ('02', 'Awgu'), ('03', 'Enugu East'),
        ('04', 'Enugu North'), ('05', 'Enugu South'), ('06', 'Ezeagu'),
        ('07', 'Igbo Etiti'), ('08', 'Igbo-Eze North'),
    ],

    # Imo (27)
    '27': [
        ('01', 'Aboh Mbaise'), ('02', 'Ahiazu Mbaise'), ('03', 'Ehime Mbano'),
        ('04', 'Ezinihitte'), ('05', 'Ideato North'), ('06', 'Ideato South'),
        ('07', 'Ihitte/Uboma'), ('08', 'Ikeduru'),
    ],

    # ══════════════════════════════════════════════════════════════
    # Zone 5: South-South
    # ══════════════════════════════════════════════════════════════

    # Akwa Ibom (03)
    '03': [
        ('01', 'Abak'), ('02', 'Eastern Obolo'), ('03', 'Eket'),
        ('04', 'Esit-Eket'), ('05', 'Essien Udim'), ('06', 'Etim Ekpo'),
        ('07', 'Etinan'), ('08', 'Ibeno'),
    ],

    # Bayelsa (06) — Zone 5
    '06_z5': [
        ('01', 'Brass'), ('02', 'Ekeremor'), ('03', 'Kolokuma/Opokuma'),
        ('04', 'Nembe'), ('05', 'Ogbia'), ('06', 'Sagbama'),
        ('07', 'Southern Ijaw'), ('08', 'Yenagoa'),
    ],

    # Cross River (09)
    '09': [
        ('01', 'Abi'), ('02', 'Akamkpa'), ('03', 'Akpabuyo'),
        ('04', 'Bakassi'), ('05', 'Bekwarra'), ('06', 'Biase'),
        ('07', 'Boki'), ('08', 'Calabar Municipal'),
    ],

    # Delta (10)
    '10': [
        ('01', 'Aniocha North'), ('02', 'Aniocha South'), ('03', 'Bomadi'),
        ('04', 'Burutu'), ('05', 'Ethiope East'), ('06', 'Ethiope West'),
        ('07', 'Ika North-East'), ('08', 'Ika South'), ('09', 'Isoko North'),
        ('10', 'Isoko South'), ('11', 'Ndokwa East'), ('12', 'Ndokwa West'),
        ('13', 'Okpe'), ('14', 'Oshimili North'), ('15', 'Oshimili South'),
        ('16', 'Patani'), ('17', 'Sapele'), ('18', 'Udu'),
        ('19', 'Ughelli North'), ('20', 'Ughelli South'), ('21', 'Ukwuani'),
        ('22', 'Uvwie'), ('23', 'Warri North'), ('24', 'Warri South'),
        ('25', 'Warri South-West'),
    ],

    # Edo (12)
    '12': [
        ('01', 'Akoko-Edo'), ('02', 'Egor'), ('03', 'Esan Central'),
        ('04', 'Esan North-East'), ('05', 'Esan South-East'), ('06', 'Esan West'),
        ('07', 'Etsako Central'), ('08', 'Etsako East'),
    ],

    # Rivers (32)
    '32': [
        ('01', 'Abua/Odual'), ('02', 'Ahoada East'), ('03', 'Ahoada West'),
        ('04', 'Akuku-Toru'), ('05', 'Andoni'), ('06', 'Asari-Toru'),
        ('07', 'Bonny'), ('08', 'Degema'),
    ],

    # ══════════════════════════════════════════════════════════════
    # Zone 6: South-West
    # ══════════════════════════════════════════════════════════════

    # Ekiti (06) — Zone 6
    '06_z6': [
        ('01', 'Ado-Ekiti'), ('02', 'Efon'), ('03', 'Ekiti East'),
        ('04', 'Ekiti South-West'), ('05', 'Ekiti West'), ('06', 'Emure'),
        ('07', 'Gbonyin'), ('08', 'Ido-Osi'),
    ],

    # Lagos (23) — ALL 20 LGAs
    '23': [
        ('01', 'Agege'), ('02', 'Ajeromi-Ifelodun'), ('03', 'Alimosho'),
        ('04', 'Amuwo-Odofin'), ('05', 'Apapa'), ('06', 'Badagry'),
        ('07', 'Epe'), ('08', 'Eti-Osa'), ('09', 'Ibeju-Lekki'),
        ('10', 'Ifako-Ijaiye'), ('11', 'Ikeja'), ('12', 'Ikorodu'),
        ('13', 'Kosofe'), ('14', 'Lagos Island'), ('15', 'Lagos Mainland'),
        ('16', 'Mushin'), ('17', 'Ojo'), ('18', 'Oshodi-Isolo'),
        ('19', 'Shomolu'), ('20', 'Surulere'),
    ],

    # Ogun (26)
    '26': [
        ('01', 'Abeokuta North'), ('02', 'Abeokuta South'), ('03', 'Ado-Odo/Ota'),
        ('04', 'Ewekoro'), ('05', 'Ifo'), ('06', 'Ijebu East'),
        ('07', 'Ijebu North'), ('08', 'Ijebu Ode'),
    ],

    # Ondo (28)
    '28': [
        ('01', 'Akoko North-East'), ('02', 'Akoko North-West'),
        ('03', 'Akoko South-East'), ('04', 'Akoko South-West'),
        ('05', 'Akure North'), ('06', 'Akure South'),
        ('07', 'Ese-Odo'), ('08', 'Idanre'),
    ],

    # Osun (29) — Zone 6
    '29_z6': [
        ('01', 'Atakumosa East'), ('02', 'Atakumosa West'), ('03', 'Ayedaade'),
        ('04', 'Ayedire'), ('05', 'Boluwaduro'), ('06', 'Boripe'),
        ('07', 'Ede North'), ('08', 'Ede South'),
    ],

    # Oyo (30)
    '30': [
        ('01', 'Afijio'), ('02', 'Akinyele'), ('03', 'Atiba'),
        ('04', 'Atisbo'), ('05', 'Egbeda'), ('06', 'Ibadan North'),
        ('07', 'Ibadan North-East'), ('08', 'Ibadan North-West'),
    ],
}


def _resolve_entries() -> list[tuple[str, str, str, list[tuple[str, str]]]]:
    """
    Resolve LGAS_BY_STATE keys (some with _z suffixes for collision handling)
    into (nbs_state_code, zone_code, state_name, lga_list) tuples.

    Returns a flat list ready for seeding.
    """
    # Build a quick state-name lookup from the original zone data
    # (matches the STATES dict in seed_ncoa.py)
    _state_names: dict[tuple[str, str], str] = {
        # Zone 1
        ('1', '07'): 'Benue', ('1', '15'): 'Kogi', ('1', '18'): 'Kwara',
        ('1', '22'): 'Nasarawa', ('1', '25'): 'Niger', ('1', '29'): 'Plateau',
        ('1', '37'): 'FCT Abuja',
        # Zone 2
        ('2', '02'): 'Adamawa', ('2', '05'): 'Bauchi', ('2', '08'): 'Borno',
        ('2', '11'): 'Gombe', ('2', '33'): 'Taraba', ('2', '35'): 'Yobe',
        # Zone 3
        ('3', '14'): 'Jigawa', ('3', '16'): 'Kaduna', ('3', '17'): 'Kano',
        ('3', '19'): 'Katsina', ('3', '20'): 'Kebbi', ('3', '31'): 'Sokoto',
        ('3', '36'): 'Zamfara',
        # Zone 4
        ('4', '01'): 'Abia', ('4', '04'): 'Anambra', ('4', '11'): 'Ebonyi',
        ('4', '13'): 'Enugu', ('4', '27'): 'Imo',
        # Zone 5
        ('5', '03'): 'Akwa Ibom', ('5', '06'): 'Bayelsa', ('5', '09'): 'Cross River',
        ('5', '10'): 'Delta', ('5', '12'): 'Edo', ('5', '32'): 'Rivers',
        # Zone 6
        ('6', '06'): 'Ekiti', ('6', '23'): 'Lagos', ('6', '26'): 'Ogun',
        ('6', '28'): 'Ondo', ('6', '29'): 'Osun', ('6', '30'): 'Oyo',
    }

    results: list[tuple[str, str, str, list[tuple[str, str]]]] = []

    for key, lga_list in LGAS_BY_STATE.items():
        if '_z' in key:
            # Collision key: e.g. '11_z4' → NBS='11', zone='4'
            nbs_code, zone_suffix = key.split('_z')
            zone_code = zone_suffix
        else:
            nbs_code = key
            zone_code = STATE_ZONE_MAP.get(nbs_code, '')
            if not zone_code:
                continue

        state_name = _state_names.get((zone_code, nbs_code), nbs_code)
        results.append((nbs_code, zone_code, state_name, lga_list))

    return results


class Command(BaseCommand):
    help = 'Seeds Nigeria LGA (Local Government Area) GeographicSegment entries'

    def add_arguments(self, parser: object) -> None:
        parser.add_argument(
            '--state-code', type=str, default=None,
            help='NBS 2-digit state code to seed (e.g. 23 for Lagos). Omit to seed all.',
        )

    @transaction.atomic
    def handle(self, *args: object, **options: object) -> None:
        target_state = options.get('state_code')
        entries = _resolve_entries()

        if target_state:
            # Normalize to 2-digit zero-padded
            target_state = target_state.zfill(2)
            entries = [e for e in entries if e[0] == target_state]
            if not entries:
                self.stderr.write(self.style.ERROR(
                    f'No LGA data found for state code "{target_state}".'
                ))
                return

        total_created = 0
        total_updated = 0

        for nbs_code, zone_code, state_name, lga_list in entries:
            # Find parent state-level GeographicSegment
            # State code format: {zone}{state}00000
            state_composite = f'{zone_code}{nbs_code}00000'
            parent_state = GeographicSegment.objects.filter(
                code=state_composite,
            ).first()

            if parent_state is None:
                self.stderr.write(self.style.WARNING(
                    f'  Skipping {state_name} ({nbs_code}): '
                    f'parent state segment "{state_composite}" not found. '
                    f'Run seed_ncoa --segment geo first.'
                ))
                continue

            created_count = 0
            updated_count = 0

            for lga_seq, lga_name in lga_list:
                # Code: zone(1) + state(2) + senatorial(1='0') + lga(2) + ward(2='00')
                lga_composite = f'{zone_code}{nbs_code}0{lga_seq}00'

                _, created = GeographicSegment.objects.update_or_create(
                    code=lga_composite,
                    defaults={
                        'name': lga_name,
                        'zone_code': zone_code,
                        'state_code': nbs_code,
                        'senatorial_code': '0',
                        'lga_code': lga_seq,
                        'ward_code': '00',
                        'parent': parent_state,
                        'is_active': True,
                    },
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            total_created += created_count
            total_updated += updated_count
            self.stdout.write(
                f'  {state_name} ({nbs_code}): '
                f'{created_count} created, {updated_count} updated '
                f'({len(lga_list)} LGAs)'
            )

        self.stdout.write(self.style.SUCCESS(
            f'\nLGA seeding complete: '
            f'{total_created} created, {total_updated} updated, '
            f'{total_created + total_updated} total.'
        ))
