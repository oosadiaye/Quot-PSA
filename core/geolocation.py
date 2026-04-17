"""
IP Geolocation and Language Detection Utilities

Provides country detection from IP addresses and maps countries to languages.
"""
import logging
from typing import Optional, Dict
from functools import lru_cache

logger = logging.getLogger('dtsg')

# Country to Language mapping
COUNTRY_LANGUAGE_MAP: Dict[str, str] = {
    # Africa
    'NG': 'en',  # Nigeria - English
    'GH': 'en',  # Ghana - English
    'KE': 'en',  # Kenya - English
    'ZA': 'en',  # South Africa - English
    'EG': 'ar',  # Egypt - Arabic
    'MA': 'ar',  # Morocco - Arabic
    'TZ': 'en',  # Tanzania - English
    'UG': 'en',  # Uganda - English
    'SN': 'fr',  # Senegal - French
    'CI': 'fr',  # Ivory Coast - French
    'CM': 'fr',  # Cameroon - French
    'FR': 'fr',  # France - French
    'BE': 'fr',  # Belgium - French
    'TG': 'fr',  # Togo - French
    'BJ': 'fr',  # Benin - French
    'NE': 'fr',  # Niger - French

    # Europe
    'GB': 'en',  # United Kingdom - English
    'IE': 'en',  # Ireland - English
    'DE': 'de',  # Germany - German
    'AT': 'de',  # Austria - German
    'CH': 'de',  # Switzerland - German
    'ES': 'es',  # Spain - Spanish
    'MX': 'es',  # Mexico - Spanish
    'AR': 'es',  # Argentina - Spanish
    'CO': 'es',  # Colombia - Spanish
    'PE': 'es',  # Peru - Spanish
    'CL': 'es',  # Chile - Spanish
    'VE': 'es',  # Venezuela - Spanish
    'PT': 'pt',  # Portugal - Portuguese
    'BR': 'pt',  # Brazil - Portuguese
    'IT': 'it',  # Italy - Italian
    'NL': 'nl',  # Netherlands - Dutch
    'PL': 'pl',  # Poland - Polish
    'RO': 'ro',  # Romania - Romanian
    'GR': 'el',  # Greece - Greek
    'RU': 'ru',  # Russia - Russian
    'UA': 'uk',  # Ukraine - Ukrainian
    'SE': 'sv',  # Sweden - Swedish
    'NO': 'no',  # Norway - Norwegian
    'DK': 'da',  # Denmark - Danish
    'FI': 'fi',  # Finland - Finnish
    'CZ': 'cs',  # Czech - Czech
    'HU': 'hu',  # Hungary - Hungarian

    # Asia
    'CN': 'zh',  # China - Chinese
    'HK': 'zh',  # Hong Kong - Chinese
    'TW': 'zh',  # Taiwan - Chinese
    'JP': 'ja',  # Japan - Japanese
    'KR': 'ko',  # Korea - Korean
    'IN': 'hi',  # India - Hindi
    'ID': 'id',  # Indonesia - Indonesian
    'MY': 'ms',  # Malaysia - Malay
    'TH': 'th',  # Thailand - Thai
    'VN': 'vi',  # Vietnam - Vietnamese
    'PH': 'tl',  # Philippines - Filipino
    'SG': 'en',  # Singapore - English
    'AE': 'ar',  # UAE - Arabic
    'SA': 'ar',  # Saudi Arabia - Arabic
    'QA': 'ar',  # Qatar - Arabic
    'KW': 'ar',  # Kuwait - Arabic
    'IL': 'he',  # Israel - Hebrew
    'TR': 'tr',  # Turkey - Turkish
    'PK': 'ur',  # Pakistan - Urdu

    # Americas
    'US': 'en',  # United States - English
    'CA': 'en',  # Canada - English
    'AU': 'en',  # Australia - English
    'NZ': 'en',  # New Zealand - English
    'JM': 'en',  # Jamaica - English
    'BB': 'en',  # Barbados - English
    'TT': 'en',  # Trinidad - English
    'HT': 'fr',  # Haiti - French
}

# Supported languages
SUPPORTED_LANGUAGES = {
    'en': {'name': 'English', 'native_name': 'English', 'is_rtl': False},
    'fr': {'name': 'French', 'native_name': 'Français', 'is_rtl': False},
    'es': {'name': 'Spanish', 'native_name': 'Español', 'is_rtl': False},
    'de': {'name': 'German', 'native_name': 'Deutsch', 'is_rtl': False},
    'pt': {'name': 'Portuguese', 'native_name': 'Português', 'is_rtl': False},
    'it': {'name': 'Italian', 'native_name': 'Italiano', 'is_rtl': False},
    'nl': {'name': 'Dutch', 'native_name': 'Nederlands', 'is_rtl': False},
    'ar': {'name': 'Arabic', 'native_name': 'العربية', 'is_rtl': True},
    'zh': {'name': 'Chinese', 'native_name': '中文', 'is_rtl': False},
    'ja': {'name': 'Japanese', 'native_name': '日本語', 'is_rtl': False},
    'ko': {'name': 'Korean', 'native_name': '한국어', 'is_rtl': False},
    'hi': {'name': 'Hindi', 'native_name': 'हिन्दी', 'is_rtl': False},
    'ru': {'name': 'Russian', 'native_name': 'Русский', 'is_rtl': False},
    'tr': {'name': 'Turkish', 'native_name': 'Türkçe', 'is_rtl': False},
}

# Default language fallback
DEFAULT_LANGUAGE = 'en'


def get_client_ip(request) -> str:
    """Extract client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


def is_local_ip(ip: str) -> bool:
    """Check if IP is local/private."""
    if not ip:
        return True
    return (
        ip.startswith('127.') or
        ip.startswith('10.') or
        ip.startswith('192.168.') or
        ip.startswith('172.16.') or
        ip.startswith('172.31.') or
        ip == '::1' or
        ip == 'localhost'
    )


@lru_cache(maxsize=1000)
def get_country_from_ip(ip: str) -> Optional[str]:
    """
    Get country code from IP address using ip-api.com free service.
    Results are cached for performance.
    """
    if is_local_ip(ip):
        return None  # Cannot determine country from local IP

    try:
        import urllib.request
        import json

        url = f"http://ip-api.com/json/{ip}?fields=countryCode"
        with urllib.request.urlopen(url, timeout=3) as response:
            data = json.loads(response.read().decode())
            if data.get('status') == 'success':
                return data.get('countryCode')
    except Exception as e:
        logger.debug(f"IP geolocation failed for {ip}: {e}")

    return None


def detect_language_from_ip(request) -> str:
    """
    Detect preferred language based on client's IP address.
    Returns the language code.
    """
    ip = get_client_ip(request)
    country = get_country_from_ip(ip)

    if country:
        language = COUNTRY_LANGUAGE_MAP.get(country)
        if language:
            logger.debug(f"Language detected from IP {ip} (country: {country}): {language}")
            return language

    logger.debug(f"Could not detect language from IP {ip}, using default")
    return DEFAULT_LANGUAGE


def detect_language_from_email(email: str) -> Optional[str]:
    """
    Detect language preference from email domain.
    Useful for inferring language from company's country.
    """
    if not email or '@' not in email:
        return None

    domain = email.split('@')[1].lower()

    # Common country-specific email domains
    country_domains = {
        '.ng': 'en',  # Nigeria
        '.gh': 'en',  # Ghana
        '.ke': 'en',  # Kenya
        '.za': 'en',  # South Africa
        '.uk': 'en',  # United Kingdom
        '.co.uk': 'en',
        '.au': 'en',  # Australia
        '.nz': 'en',  # New Zealand
        '.ca': 'en',  # Canada
        '.ie': 'en',  # Ireland
        '.in': 'en',  # India

        '.fr': 'fr',  # France
        '.be': 'fr',  # Belgium
        '.ci': 'fr',  # Ivory Coast
        '.sn': 'fr',  # Senegal
        '.cm': 'fr',  # Cameroon
        '.ht': 'fr',  # Haiti

        '.de': 'de',  # Germany
        '.at': 'de',  # Austria
        '.ch': 'de',  # Switzerland

        '.es': 'es',  # Spain
        '.mx': 'es',  # Mexico
        '.ar': 'es',  # Argentina
        '.co': 'es',  # Colombia
        '.pe': 'es',  # Peru
        '.cl': 'es',  # Chile

        '.br': 'pt',  # Brazil
        '.pt': 'pt',  # Portugal

        '.it': 'it',  # Italy

        '.nl': 'nl',  # Netherlands

        '.cn': 'zh',  # China
        '.com.cn': 'zh',

        '.jp': 'ja',  # Japan

        '.kr': 'ko',  # Korea

        '.ru': 'ru',  # Russia

        '.ae': 'ar',  # UAE
        '.sa': 'ar',  # Saudi Arabia
        '.eg': 'ar',  # Egypt
        '.ma': 'ar',  # Morocco
    }

    for suffix, lang in country_domains.items():
        if domain.endswith(suffix):
            return lang

    return None


def detect_language(request, user=None) -> str:
    """
    Comprehensive language detection from multiple sources.
    Priority: User preference > Email domain > IP geolocation > Default
    """
    # 1. Check if user has saved preference
    if user and hasattr(user, 'preferred_language') and user.preferred_language:
        return user.preferred_language

    # 2. Check request headers (browser language)
    accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
    if accept_language:
        # Parse the first language
        first_lang = accept_language.split(',')[0].split('-')[0].lower()
        if first_lang in SUPPORTED_LANGUAGES:
            return first_lang

    # 3. Try email domain
    if user and user.email:
        email_lang = detect_language_from_email(user.email)
        if email_lang:
            return email_lang

    # 4. Try IP geolocation
    ip_lang = detect_language_from_ip(request)
    if ip_lang:
        return ip_lang

    return DEFAULT_LANGUAGE


def get_language_for_country(country_code: str) -> str:
    """Get the default language for a country code."""
    return COUNTRY_LANGUAGE_MAP.get(country_code, DEFAULT_LANGUAGE)


def is_rtl_language(language_code: str) -> bool:
    """Check if a language is right-to-left."""
    lang_info = SUPPORTED_LANGUAGES.get(language_code, {})
    return lang_info.get('is_rtl', False)
